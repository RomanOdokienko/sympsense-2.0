from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_MARKERS = [
    "предварительный",
    "окончательный",
    "заключительный",
    "основное заболевание",
    "сопутствующее заболевание",
    "основное",
    "сопутствующее",
    "впервые выявленное",
    "ранее выявленное",
    "острое",
    "хроническое",
]

NOISE_MARKERS = [
    "прием врача",
    "выбора тактики лечения",
    "тактики лечения",
]

EXCLUDED_LABEL_MARKERS = [
    "не выявлено",
    "не обнаружено",
    "без патологии",
    "эхопризнаков патологии",
    "на рентгенограммах",
    "протокол",
    "шейный отдел позвоночного столба",
]

SYMPTOM_MARKERS = [
    "головокруж",
    "головная боль",
    "боль ",
    "астенич",
    "тревож",
    "депрессив",
    "синдром",
]

CONDITION_MARKERS = [
    "артроз",
    "миоп",
    "ринит",
    "варикоз",
    "эпикондил",
    "мениск",
    "поражение",
    "диск",
    "дорсалг",
    "ганглион",
    "гигром",
    "флебопат",
    "микротравм",
    "киста",
]

ICD_SPLIT_RE = re.compile(r"([А-ЯA-ZЁ][^()]{3,}?)\s*\(([A-ZА-Я]\d{2}(?:\.\d+)?)\)")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_audit(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_date(value: str | None) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        return s


def _span_days(first_date: str, last_date: str) -> int:
    if not first_date or not last_date:
        return 0
    try:
        d1 = datetime.fromisoformat(first_date).date()
        d2 = datetime.fromisoformat(last_date).date()
    except Exception:
        return 0
    return max(0, (d2 - d1).days)


def _clean_label(text: str) -> str:
    s = " ".join((text or "").replace("\n", " ").split())
    s = re.sub(r"^\s*по\s+диагнозу\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*[уy]\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(основное|сопутствующее)\s+заболевание\s*:\s*", "", s, flags=re.IGNORECASE)
    return s.strip(" .;:-")


def _normalize_key(text: str, icd_codes: list[str]) -> str:
    if icd_codes:
        return f"icd::{','.join(sorted(icd_codes))}"
    s = _clean_label(text).lower().replace("ё", "е")
    for marker in STATUS_MARKERS:
        s = s.replace(marker, " ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-zа-я0-9]+", " ", s)
    s = " ".join(s.split())
    return f"text::{s}"


def _clean_display_label(text: str) -> str:
    s = _clean_label(text)
    for marker in STATUS_MARKERS:
        s = re.sub(rf"\b{re.escape(marker)}\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" .;:-")
    return s or _clean_label(text)


def _extract_atomic_labels(label: str, fallback_icd: list[str]) -> list[tuple[str, list[str]]]:
    cleaned = _clean_label(label)
    matches = ICD_SPLIT_RE.findall(cleaned)
    if matches:
        out: list[tuple[str, list[str]]] = []
        for name, code in matches:
            piece = _clean_label(name)
            if len(piece) >= 5:
                out.append((piece, [str(code).strip()]))
        if out:
            return out
    return [(cleaned, list(fallback_icd))]


def _contains_any(text: str, markers: list[str]) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in markers)


def _is_excluded_label(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in EXCLUDED_LABEL_MARKERS)


def _classify_problem(
    *,
    label: str,
    icd_codes: list[str],
    mention_count: int,
    doc_count: int,
    span_days: int,
    qa_status: str,
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    is_noise = _contains_any(label, NOISE_MARKERS)
    symptom_like = _contains_any(label, SYMPTOM_MARKERS)
    condition_like = _contains_any(label, CONDITION_MARKERS)
    has_icd = bool(icd_codes)
    chronic_hint = has_icd or doc_count >= 2 or span_days >= 120

    if is_noise:
        reasons.append("noise_marker")

    if reasons:
        return "uncertain", "low", reasons

    if chronic_hint and (has_icd or condition_like):
        reasons.append("repeated_or_coded")
        return "stable_problem", "high" if has_icd else "medium", reasons

    if symptom_like and not has_icd and doc_count <= 1:
        reasons.append("symptom_like_single_episode")
        return "symptom_or_state", "medium", reasons

    reasons.append("single_or_short_history")
    return "episodic_condition", "medium", reasons


def build_problem_list(
    project_root: Path,
    *,
    write_report: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    data_root = root / "data"
    clusters_path = data_root / "canonical/facts/condition_clusters_v1.ndjson"
    clusters = _load_ndjson(clusters_path)
    if not clusters:
        raise FileNotFoundError(f"condition clusters not found: {clusters_path}")
    mentions = _load_ndjson(data_root / "canonical/facts/condition_mentions_v1.ndjson")
    mention_type_by_id = {
        str(row.get("mention_id") or "").strip(): str(row.get("finding_type") or "").strip().lower()
        for row in mentions
        if str(row.get("mention_id") or "").strip()
    }

    by_key: dict[str, dict[str, Any]] = {}
    for cluster in clusters:
        example = str((cluster.get("examples") or [""])[0] or "").strip()
        if not example:
            continue
        mention_ids = [str(x).strip() for x in (cluster.get("mention_ids") or []) if str(x).strip()]
        diagnosis_mentions_count = sum(
            1 for mention_id in mention_ids if mention_type_by_id.get(mention_id) == "diagnosis"
        )
        if diagnosis_mentions_count == 0:
            continue
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        qa_status = str(cluster.get("qa_status") or "").strip().lower() or "unknown"
        mention_count = int(cluster.get("mention_count") or 0)
        doc_count = int(cluster.get("doc_count") or 0)
        first_date = _safe_date(str(cluster.get("first_date") or ""))
        last_date = _safe_date(str(cluster.get("last_date") or ""))
        icd_codes = [str(x).strip() for x in (cluster.get("icd_codes") or []) if str(x).strip()]

        for atomic_label, atomic_codes in _extract_atomic_labels(example, icd_codes):
            key = _normalize_key(atomic_label, atomic_codes)
            if not key or key.endswith("text::"):
                continue
            if _is_excluded_label(atomic_label):
                continue
            row = by_key.get(key)
            if row is None:
                row = {
                    "problem_id": f"problem_{len(by_key) + 1:03d}",
                    "label": atomic_label,
                    "icd_codes": set(atomic_codes),
                    "doc_ids_count": doc_count,
                    "mentions_count": mention_count,
                    "diagnosis_mentions_count": diagnosis_mentions_count,
                    "first_date": first_date,
                    "last_date": last_date,
                    "source_cluster_ids": [cluster_id] if cluster_id else [],
                    "qa_statuses": {qa_status},
                }
                by_key[key] = row
            else:
                if len(atomic_label) < len(str(row["label"])):
                    row["label"] = atomic_label
                row["icd_codes"].update(atomic_codes)
                row["doc_ids_count"] = max(int(row["doc_ids_count"]), doc_count)
                row["mentions_count"] = max(int(row["mentions_count"]), mention_count)
                row["diagnosis_mentions_count"] = max(
                    int(row["diagnosis_mentions_count"]), diagnosis_mentions_count
                )
                row["first_date"] = min(str(row["first_date"] or ""), first_date or str(row["first_date"] or ""))
                row["last_date"] = max(str(row["last_date"] or ""), last_date or str(row["last_date"] or ""))
                if cluster_id and cluster_id not in row["source_cluster_ids"]:
                    row["source_cluster_ids"].append(cluster_id)
                row["qa_statuses"].add(qa_status)

    items: list[dict[str, Any]] = []
    for _, row in by_key.items():
        label = str(row["label"] or "").strip()
        if len(label) < 6:
            continue
        display_label = _clean_display_label(label)
        span_days = _span_days(str(row["first_date"] or ""), str(row["last_date"] or ""))
        qa_status = "ok" if row["qa_statuses"] == {"ok"} else "needs_review"
        category, confidence_tier, category_reasons = _classify_problem(
            label=display_label,
            icd_codes=sorted(row["icd_codes"]),
            mention_count=int(row["mentions_count"]),
            doc_count=int(row["doc_ids_count"]),
            span_days=span_days,
            qa_status=qa_status,
        )
        if label.lower() in {"а и выбора тактики лечения"}:
            category = "uncertain"
            confidence_tier = "low"
            category_reasons = sorted(set(category_reasons + ["noise_marker"]))

        items.append(
            {
                "problem_id": row["problem_id"],
                "label": label,
                "label_clean": display_label,
                "icd_codes": sorted(row["icd_codes"]),
                "category": category,
                "confidence_tier": confidence_tier,
                "category_reasons": category_reasons,
                "timeline": {
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                    "span_days": span_days,
                },
                "support": {
                    "mentions_count": int(row["mentions_count"]),
                    "doc_ids_count": int(row["doc_ids_count"]),
                    "diagnosis_mentions_count": int(row["diagnosis_mentions_count"]),
                    "qa_status": qa_status,
                    "source_cluster_ids": sorted(row["source_cluster_ids"]),
                },
            }
        )

    items.sort(
        key=lambda x: (
            {"stable_problem": 0, "episodic_condition": 1, "symptom_or_state": 2, "uncertain": 3}.get(
                str(x.get("category") or ""), 9
            ),
            -int((x.get("support") or {}).get("doc_ids_count") or 0),
            -int((x.get("support") or {}).get("mentions_count") or 0),
            str(x.get("label") or ""),
        )
    )

    category_counts = dict(Counter(str(x.get("category") or "") for x in items))
    payload: dict[str, Any] = {
        "generated_at": _now_utc(),
        "version": "problem_list_v1",
        "summary": {
            "total_items": len(items),
            "category_counts": category_counts,
        },
        "items": items,
    }

    if write_report:
        canonical_path = data_root / "canonical/facts/problem_list_v1.json"
        reports_dir = data_root / "derived/reports"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = reports_dir / f"problem_list_v1_{ts}.json"
        latest_path = reports_dir / "problem_list_v1_latest.json"
        body = json.dumps(payload, ensure_ascii=False, indent=2)

        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(body, encoding="utf-8")
        snapshot_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")

        payload["report_paths"] = {
            "canonical": str(canonical_path).replace("\\", "/"),
            "snapshot": str(snapshot_path).replace("\\", "/"),
            "latest": str(latest_path).replace("\\", "/"),
        }
        _append_audit(
            data_root / "audit/logs/batch_01_agent.ndjson",
            {
                "ts": _now_utc(),
                "event": "problem_list_built_v1",
                "items_total": len(items),
                "category_counts": category_counts,
                "canonical_path": payload["report_paths"]["canonical"],
                "snapshot_path": payload["report_paths"]["snapshot"],
            },
        )

    return payload
