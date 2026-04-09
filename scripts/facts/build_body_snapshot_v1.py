from __future__ import annotations

import json
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(".")
BATCH_ID = "batch_01"

REGISTRY_PATH = ROOT / "data/canonical/documents/batch_01_registry_active.json"
FACTS_DIR = ROOT / "data/canonical/facts"
REPORTS_DIR = ROOT / "data/derived/reports"
AUDIT_FILE = ROOT / "data/audit/logs/batch_01_agent.ndjson"

CLINICAL_FACTS_PATH = FACTS_DIR / "clinical_findings_v1.ndjson"
LAB_FACTS_PATH = FACTS_DIR / "lab_results_v1.ndjson"

OUT_SUMMARY = FACTS_DIR / "body_snapshot_v1_summary.json"
OUT_SNAPSHOT = FACTS_DIR / "body_snapshot_v1.json"
OUT_CONDITIONS = FACTS_DIR / "condition_mentions_v1.ndjson"
OUT_CONDITION_CLUSTERS = FACTS_DIR / "condition_clusters_v1.ndjson"
OUT_INVESTIGATIONS = FACTS_DIR / "investigation_events_v1.ndjson"
OUT_LINKS = FACTS_DIR / "condition_investigation_links_v1.ndjson"
OUT_PREVIEW = REPORTS_DIR / "body_snapshot_v1_preview.json"

# Strict ICD-like matcher: letter + two digits (+ optional decimal), e.g. M50.1, I10.
ICD_RE = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)\b")
ICD_STRIP_RE = re.compile(r"\b[ABEKMHOPCTXA-TV-ZА-Я]\d{2}(?:\.\d{1,2})?\b", flags=re.IGNORECASE)
COND_TOKEN_RE = re.compile(r"[a-zа-я0-9]+", flags=re.IGNORECASE)
CONDITION_STOPWORDS = {
    "диагноз",
    "заключение",
    "заболевание",
    "основное",
    "сопутствующее",
    "предварительный",
    "предварительное",
    "заключительный",
    "заключительное",
    "острое",
    "хроническое",
    "состояние",
    "синдром",
    "по",
    "для",
    "общее",
    "данных",
    "наличии",
}

RU_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ому",
    "ыми",
    "ими",
    "ыми",
    "ыми",
    "иями",
    "ов",
    "ев",
    "ей",
    "ах",
    "ях",
    "ам",
    "ям",
    "ом",
    "ем",
    "ой",
    "ый",
    "ий",
    "ая",
    "яя",
    "ое",
    "ее",
    "ую",
    "юю",
    "ые",
    "ие",
    "а",
    "я",
    "ы",
    "и",
    "о",
    "е",
    "у",
    "ю",
)

CONDITION_PHRASE_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"поражен\w+\s+межпозвон\w+\s+диск\w+", re.IGNORECASE), "шейная_дископатия"),
    (re.compile(r"шейно-?плечев\w+\s+синдром", re.IGNORECASE), "шейно_плечевой_синдром"),
    (re.compile(r"синдром\s+сухого\s+глаза", re.IGNORECASE), "сухой_глаз"),
    (re.compile(r"латеральн\w+\s+эпикондилит\w*", re.IGNORECASE), "латеральный_эпикондилит"),
    (re.compile(r"теносиновит\w+\s+сухожили\w+", re.IGNORECASE), "теносиновит"),
    (re.compile(r"дорсалг\w+", re.IGNORECASE), "дорсалгия"),
    (re.compile(r"миопи\w+\s+слаб\w+\s+степен\w+", re.IGNORECASE), "миопия_легкая"),
]


@dataclass(frozen=True)
class ConditionMention:
    mention_id: str
    doc_id: str
    event_date: str | None
    finding_type: str
    condition_text: str
    condition_key: str
    condition_group_key: str
    icd_codes: list[str]
    qa_status: str
    confidence: float
    source_fact_id: str
    source: dict[str, Any]
    evidence_excerpt: str


@dataclass(frozen=True)
class InvestigationEvent:
    event_id: str
    doc_id: str
    event_date: str | None
    doc_type: str
    title: str
    qa_status: str
    confidence: float
    highlights: list[str]
    source: dict[str, Any]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_ndjson(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def to_iso(raw: str | None) -> str | None:
    dt = parse_date(raw)
    return dt.isoformat() if dt else None


def clamp(value: float) -> float:
    return max(0.05, min(0.99, round(value, 2)))


def first_sentence(text: str) -> str:
    t = norm(text)
    if not t:
        return ""
    parts = re.split(r"[.;]\s+", t)
    for p in parts:
        p = p.strip()
        if len(p) >= 6:
            return p[:280]
    return t[:280]


def unique_str(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def stable_id(prefix: str, key: str, n: int = 10) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:n]
    return f"{prefix}_{digest}"


def normalize_for_icd(text: str) -> str:
    # Map common Cyrillic lookalikes to Latin for robust ICD extraction.
    table = str.maketrans(
        {
            "А": "A",
            "В": "B",
            "Е": "E",
            "К": "K",
            "М": "M",
            "Н": "H",
            "О": "O",
            "Р": "P",
            "С": "C",
            "Т": "T",
            "Х": "X",
            "а": "a",
            "е": "e",
            "о": "o",
            "р": "p",
            "с": "c",
            "х": "x",
        }
    )
    return text.translate(table)


def extract_icd_codes(text: str) -> list[str]:
    s = normalize_for_icd(text.upper())
    return unique_str(ICD_RE.findall(s))


def recover_cp1251_mojibake(text: str) -> str:
    s = text or ""
    if not s:
        return s
    has_cyr = bool(re.search(r"[А-Яа-яЁё]", s))
    has_latin1 = bool(re.search(r"[À-ÿ]", s))
    if not has_latin1:
        return s
    try:
        candidate = s.encode("latin1", errors="strict").decode("cp1251", errors="strict")
    except Exception:
        return s
    cand_cyr = len(re.findall(r"[А-Яа-яЁё]", candidate))
    cur_cyr = len(re.findall(r"[А-Яа-яЁё]", s))
    if cand_cyr > cur_cyr or (cand_cyr >= 6 and not has_cyr):
        return candidate
    return s


def normalize_condition_phrase(text: str) -> str:
    s = recover_cp1251_mojibake(norm(text)).lower().replace("ё", "е")
    for pattern, repl in CONDITION_PHRASE_MAP:
        s = pattern.sub(repl, s)
    return s


def stem_ru_token(token: str) -> str:
    t = token.lower()
    if len(t) <= 4:
        return t
    for suff in RU_SUFFIXES:
        if t.endswith(suff) and len(t) - len(suff) >= 4:
            return t[: -len(suff)]
    return t


def map_condition_token(token: str) -> str:
    t = token.lower()
    if t.startswith(("цервик", "шейн")):
        return "шея"
    if t.startswith("позвоноч"):
        return "позвоночник"
    if t.startswith("дорсалг"):
        return "дорсалгия"
    if t.startswith("миоп"):
        return "миопия"
    if t.startswith("эпикондил"):
        return "эпикондилит"
    if t.startswith("теносинов"):
        return "теносиновит"
    if t.startswith(("дископат", "диск")):
        return "диск"
    if t.startswith(("коленн", "колен")):
        return "колено"
    if t.startswith("плеч"):
        return "плечо"
    if t.startswith("невролог"):
        return "неврология"
    return t


def normalize_condition_key(text: str) -> str:
    s = normalize_condition_phrase(text)
    s = ICD_STRIP_RE.sub(" ", s)
    s = re.sub(r"[\(\)\[\],.;:!?/\\\-]+", " ", s)
    raw_tokens = [t for t in COND_TOKEN_RE.findall(s) if len(t) >= 2 and not t.isdigit()]
    tokens = [map_condition_token(stem_ru_token(t)) for t in raw_tokens]
    filtered = [t for t in tokens if t not in CONDITION_STOPWORDS and len(t) >= 2]
    if not filtered:
        filtered = tokens
    uniq = sorted(set(filtered))
    return " ".join(uniq[:12]).strip()


def condition_group_key(condition_key: str, icd_codes: list[str], mention_id: str) -> str:
    if icd_codes:
        return f"icd::{icd_codes[0].upper()}"
    if condition_key:
        return f"text::{condition_key[:120]}"
    return f"unknown::{mention_id}"


def to_condition_mentions(
    clinical_rows: list[dict[str, Any]],
) -> list[ConditionMention]:
    out: list[ConditionMention] = []
    for row in clinical_rows:
        text = recover_cp1251_mojibake(norm(str(row.get("text") or "")))
        if not text:
            continue
        mention_text = first_sentence(text)
        icd_codes = extract_icd_codes(text)
        cond_key = normalize_condition_key(mention_text)
        group_key = condition_group_key(cond_key, icd_codes, f"condition_{row.get('fact_id')}")
        qa_status = str(row.get("qa_status") or "needs_review")
        if not cond_key:
            qa_status = "needs_review"
        confidence = clamp(float(row.get("confidence") or 0.5))
        if qa_status == "needs_review":
            confidence = clamp(confidence - 0.08)
        out.append(
            ConditionMention(
                mention_id=f"condition_{row.get('fact_id')}",
                doc_id=str(row.get("doc_id") or ""),
                event_date=to_iso(str(row.get("event_date") or "")),
                finding_type=str(row.get("finding_type") or "unknown"),
                condition_text=mention_text,
                condition_key=cond_key,
                condition_group_key=group_key,
                icd_codes=icd_codes,
                qa_status=qa_status,
                confidence=confidence,
                source_fact_id=str(row.get("fact_id") or ""),
                source=row.get("source") or {},
                evidence_excerpt=str(row.get("evidence_excerpt") or ""),
            )
        )
    return out


def build_condition_clusters(conditions: list[ConditionMention]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ConditionMention]] = defaultdict(list)
    for cond in conditions:
        grouped[cond.condition_group_key].append(cond)

    def key_tokens(k: str) -> set[str]:
        if not k.startswith("text::"):
            return set()
        return set(k.replace("text::", "").split())

    # Merge near-duplicate text clusters by token overlap.
    text_keys = [k for k in grouped if k.startswith("text::")]
    ordered = sorted(text_keys, key=lambda k: len(grouped[k]), reverse=True)
    merged_to: dict[str, str] = {}
    for base in ordered:
        if base in merged_to:
            continue
        base_set = key_tokens(base)
        if not base_set:
            continue
        for other in ordered:
            if other == base or other in merged_to:
                continue
            other_set = key_tokens(other)
            if not other_set:
                continue
            inter = len(base_set & other_set)
            union = len(base_set | other_set)
            if union == 0:
                continue
            jaccard = inter / union
            if jaccard >= 0.72:
                merged_to[other] = base

    if merged_to:
        regrouped: dict[str, list[ConditionMention]] = defaultdict(list)
        for key, members in grouped.items():
            target = merged_to.get(key, key)
            regrouped[target].extend(members)
        grouped = regrouped

    out: list[dict[str, Any]] = []
    for key, members in grouped.items():
        dates = [parse_date(x.event_date) for x in members if x.event_date]
        dates = [x for x in dates if x is not None]
        qa_status = "needs_review" if any(x.qa_status == "needs_review" for x in members) else "ok"
        cluster_conf = clamp(sum(x.confidence for x in members) / len(members))
        if qa_status == "needs_review":
            cluster_conf = clamp(cluster_conf - 0.06)

        text_examples = unique_str([x.condition_text for x in members])[:5]
        icd_codes = unique_str([code for x in members for code in x.icd_codes])
        out.append(
            {
                "cluster_id": stable_id("cluster", key, n=12),
                "group_key": key,
                "mention_count": len(members),
                "doc_count": len({x.doc_id for x in members}),
                "first_date": min(dates).isoformat() if dates else None,
                "last_date": max(dates).isoformat() if dates else None,
                "icd_codes": icd_codes,
                "qa_status": qa_status,
                "confidence": cluster_conf,
                "examples": text_examples,
                "mention_ids": [x.mention_id for x in members],
            }
        )
    out.sort(key=lambda x: (-x["mention_count"], x["group_key"]))
    return out


def to_investigation_events(
    registry_by_doc: dict[str, dict[str, Any]],
    lab_rows_by_doc: dict[str, list[dict[str, Any]]],
    clinical_rows_by_doc: dict[str, list[dict[str, Any]]],
) -> list[InvestigationEvent]:
    out: list[InvestigationEvent] = []
    for doc_id, row in registry_by_doc.items():
        doc_type = str(row.get("doc_type") or "")
        if doc_type != "lab_report" and not doc_type.startswith("imaging_report_"):
            continue

        source = row.get("source") or {}
        event_date = to_iso(str(row.get("event_date_raw") or ""))
        file_name = str(row.get("file_name") or doc_id)

        if doc_type == "lab_report":
            lab_rows = lab_rows_by_doc.get(doc_id, [])
            abnormal = [x for x in lab_rows if bool(x.get("abnormal_flag"))]
            highlights = []
            for x in abnormal[:4]:
                highlights.append(
                    f"{norm(str(x.get('analyte_name') or 'analyte'))}: {norm(str(x.get('value_text') or ''))}"
                )
            if not highlights:
                for x in lab_rows[:3]:
                    highlights.append(
                        f"{norm(str(x.get('analyte_name') or 'analyte'))}: {norm(str(x.get('value_text') or ''))}"
                    )
            qa_status = "needs_review" if any(str(x.get("qa_status")) == "needs_review" for x in lab_rows) else "ok"
            confidence = 0.86 if qa_status == "ok" else 0.62
            title = f"Lab report: {file_name}"
        else:
            clinical_rows = clinical_rows_by_doc.get(doc_id, [])
            snippets: list[str] = []
            for x in clinical_rows:
                t = first_sentence(str(x.get("text") or ""))
                if t:
                    snippets.append(t)
            highlights = unique_str(snippets)[:4]
            qa_status = "needs_review" if any(str(x.get("qa_status")) == "needs_review" for x in clinical_rows) else "ok"
            confidence = 0.84 if qa_status == "ok" else 0.6
            title = f"Imaging report: {file_name}"

        out.append(
            InvestigationEvent(
                event_id=f"investigation_{doc_id}",
                doc_id=doc_id,
                event_date=event_date,
                doc_type=doc_type,
                title=title,
                qa_status=qa_status,
                confidence=clamp(confidence),
                highlights=highlights,
                source={
                    "document_id": doc_id,
                    "file_name": file_name,
                    "relative_path": source.get("relative_path"),
                },
            )
        )
    return out


def build_timeline(
    registry_by_doc: dict[str, dict[str, Any]],
    conditions: list[ConditionMention],
    investigations: list[InvestigationEvent],
    lab_rows_by_doc: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    docs_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in registry_by_doc.values():
        iso = to_iso(str(row.get("event_date_raw") or ""))
        if iso:
            docs_by_date[iso].append(row)

    cond_by_date: dict[str, list[ConditionMention]] = defaultdict(list)
    for c in conditions:
        if c.event_date:
            cond_by_date[c.event_date].append(c)

    inv_by_date: dict[str, list[InvestigationEvent]] = defaultdict(list)
    for i in investigations:
        if i.event_date:
            inv_by_date[i.event_date].append(i)

    all_dates = sorted(set(docs_by_date) | set(cond_by_date) | set(inv_by_date))
    timeline: list[dict[str, Any]] = []
    for idx, d in enumerate(all_dates, start=1):
        docs = docs_by_date.get(d, [])
        conds = cond_by_date.get(d, [])
        invs = inv_by_date.get(d, [])

        abnormal_lab_count = 0
        for doc in docs:
            if str(doc.get("doc_type") or "") == "lab_report":
                doc_id = str(doc.get("id") or "")
                abnormal_lab_count += sum(1 for x in lab_rows_by_doc.get(doc_id, []) if bool(x.get("abnormal_flag")))

        highlights = unique_str(
            [c.condition_text for c in conds[:3]]
            + [h for i in invs[:2] for h in i.highlights[:1]]
        )

        timeline.append(
            {
                "timeline_id": f"timeline_{idx:04d}",
                "date": d,
                "doc_count": len(docs),
                "doc_types": sorted({str(x.get("doc_type") or "") for x in docs}),
                "condition_mentions_count": len(conds),
                "investigation_events_count": len(invs),
                "abnormal_lab_items_count": abnormal_lab_count,
                "doc_ids": [str(x.get("id") or "") for x in docs],
                "highlights": highlights[:5],
            }
        )
    return timeline


def relation_qa_status(cond_status: str, inv_status: str) -> str:
    return "needs_review" if ("needs_review" in (cond_status, inv_status)) else "ok"


def link_score(
    cond: ConditionMention,
    inv: InvestigationEvent,
    relation_type: str,
    days_apart: int | None,
) -> tuple[float, str, str, list[str]]:
    reasons: list[str] = []
    if relation_type == "same_doc":
        base = 0.9
        reasons.append("same_document")
    else:
        if days_apart is None:
            base = 0.52
        elif days_apart <= 7:
            base = 0.72
        elif days_apart <= 21:
            base = 0.67
        else:
            base = 0.58
        reasons.append("time_proximity")

    score = base * 0.45 + cond.confidence * 0.3 + inv.confidence * 0.25
    if cond.icd_codes:
        score += 0.03
        reasons.append("has_icd_code")
    if cond.qa_status == "needs_review":
        score -= 0.08
        reasons.append("condition_needs_review")
    if inv.qa_status == "needs_review":
        score -= 0.07
        reasons.append("investigation_needs_review")

    score = clamp(score)
    priority = "high" if score >= 0.8 else ("medium" if score >= 0.65 else "low")
    qa_status = relation_qa_status(cond.qa_status, inv.qa_status)
    if score < 0.62:
        qa_status = "needs_review"
    return score, priority, qa_status, reasons


def build_condition_investigation_links(
    conditions: list[ConditionMention],
    investigations: list[InvestigationEvent],
) -> list[dict[str, Any]]:
    inv_by_doc: dict[str, list[InvestigationEvent]] = defaultdict(list)
    for inv in investigations:
        inv_by_doc[inv.doc_id].append(inv)

    inv_with_date = [x for x in investigations if x.event_date]
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for cond in conditions:
        # 1) same document links (highest confidence)
        for inv in inv_by_doc.get(cond.doc_id, []):
            key = (cond.mention_id, inv.event_id, "same_doc")
            if key in seen:
                continue
            seen.add(key)
            days_apart = 0 if cond.event_date and inv.event_date else None
            score, priority, qa_status, score_reasons = link_score(cond, inv, "same_doc", days_apart)
            links.append(
                {
                    "link_id": f"link_{len(links)+1:05d}",
                    "condition_id": cond.mention_id,
                    "investigation_id": inv.event_id,
                    "condition_doc_id": cond.doc_id,
                    "investigation_doc_id": inv.doc_id,
                    "relation_type": "same_doc",
                    "days_apart": days_apart,
                    "confidence": score,
                    "link_priority": priority,
                    "qa_status": qa_status,
                    "score_reasons": score_reasons,
                    "rationale": "Condition mention and investigation extracted from the same source document.",
                }
            )

        # 2) temporal proximity links (up to 45 days)
        if not cond.event_date:
            continue
        cond_dt = parse_date(cond.event_date)
        if cond_dt is None:
            continue

        candidates: list[tuple[int, InvestigationEvent]] = []
        for inv in inv_with_date:
            inv_dt = parse_date(inv.event_date)
            if inv_dt is None:
                continue
            days = abs((inv_dt - cond_dt).days)
            if days <= 45 and inv.doc_id != cond.doc_id:
                candidates.append((days, inv))

        candidates.sort(key=lambda x: x[0])
        for days, inv in candidates[:3]:
            key = (cond.mention_id, inv.event_id, "time_proximity_45d")
            if key in seen:
                continue
            seen.add(key)
            score, priority, qa_status, score_reasons = link_score(cond, inv, "time_proximity_45d", days)
            links.append(
                {
                    "link_id": f"link_{len(links)+1:05d}",
                    "condition_id": cond.mention_id,
                    "investigation_id": inv.event_id,
                    "condition_doc_id": cond.doc_id,
                    "investigation_doc_id": inv.doc_id,
                    "relation_type": "time_proximity_45d",
                    "days_apart": days,
                    "confidence": score,
                    "link_priority": priority,
                    "qa_status": qa_status,
                    "score_reasons": score_reasons,
                    "rationale": "Temporal proximity between condition mention and investigation event.",
                }
            )
    return links


def main() -> None:
    ts = now_utc()
    registry_rows = load_json(REGISTRY_PATH)
    registry_by_doc: dict[str, dict[str, Any]] = {
        str(x.get("id") or ""): x for x in registry_rows if str(x.get("id") or "")
    }
    active_doc_ids = set(registry_by_doc.keys())

    clinical_all = load_ndjson(CLINICAL_FACTS_PATH)
    labs_all = load_ndjson(LAB_FACTS_PATH)

    clinical_rows = [x for x in clinical_all if str(x.get("doc_id") or "") in active_doc_ids]
    labs_rows = [x for x in labs_all if str(x.get("doc_id") or "") in active_doc_ids]
    dropped_orphan = {
        "clinical_findings": len(clinical_all) - len(clinical_rows),
        "lab_results": len(labs_all) - len(labs_rows),
    }

    clinical_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in clinical_rows:
        clinical_by_doc[str(row.get("doc_id") or "")].append(row)

    labs_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in labs_rows:
        labs_by_doc[str(row.get("doc_id") or "")].append(row)

    conditions = to_condition_mentions(clinical_rows)
    condition_clusters = build_condition_clusters(conditions)
    investigations = to_investigation_events(registry_by_doc, labs_by_doc, clinical_by_doc)
    timeline = build_timeline(registry_by_doc, conditions, investigations, labs_by_doc)
    links = build_condition_investigation_links(conditions, investigations)

    condition_rows = [
        {
            "mention_id": c.mention_id,
            "doc_id": c.doc_id,
            "event_date": c.event_date,
            "finding_type": c.finding_type,
            "condition_text": c.condition_text,
            "condition_key": c.condition_key,
            "condition_group_key": c.condition_group_key,
            "icd_codes": c.icd_codes,
            "qa_status": c.qa_status,
            "confidence": c.confidence,
            "source_fact_id": c.source_fact_id,
            "source": c.source,
            "evidence_excerpt": c.evidence_excerpt,
        }
        for c in conditions
    ]
    investigation_rows = [
        {
            "event_id": i.event_id,
            "doc_id": i.doc_id,
            "event_date": i.event_date,
            "doc_type": i.doc_type,
            "title": i.title,
            "qa_status": i.qa_status,
            "confidence": i.confidence,
            "highlights": i.highlights,
            "source": i.source,
        }
        for i in investigations
    ]

    write_ndjson(OUT_CONDITIONS, condition_rows)
    write_ndjson(OUT_CONDITION_CLUSTERS, condition_clusters)
    write_ndjson(OUT_INVESTIGATIONS, investigation_rows)
    write_ndjson(OUT_LINKS, links)

    date_values = [parse_date(x["date"]) for x in timeline if x.get("date")]
    date_values = [x for x in date_values if x is not None]
    date_min = min(date_values).isoformat() if date_values else None
    date_max = max(date_values).isoformat() if date_values else None

    summary = {
        "generated_at": ts,
        "batch_id": BATCH_ID,
        "inputs": {
            "active_documents": len(active_doc_ids),
            "clinical_rows_used": len(clinical_rows),
            "lab_rows_used": len(labs_rows),
            "dropped_orphan_facts": dropped_orphan,
        },
        "outputs": {
            "timeline_points": len(timeline),
            "condition_mentions_count": len(condition_rows),
            "condition_clusters_count": len(condition_clusters),
            "investigation_events_count": len(investigation_rows),
            "condition_investigation_links_count": len(links),
            "qa_status_counts": {
                "conditions": {
                    "ok": sum(1 for x in condition_rows if x.get("qa_status") == "ok"),
                    "needs_review": sum(1 for x in condition_rows if x.get("qa_status") == "needs_review"),
                },
                "investigations": {
                    "ok": sum(1 for x in investigation_rows if x.get("qa_status") == "ok"),
                    "needs_review": sum(1 for x in investigation_rows if x.get("qa_status") == "needs_review"),
                },
                "links": {
                    "ok": sum(1 for x in links if x.get("qa_status") == "ok"),
                    "needs_review": sum(1 for x in links if x.get("qa_status") == "needs_review"),
                },
            },
            "link_priority_counts": {
                "high": sum(1 for x in links if x.get("link_priority") == "high"),
                "medium": sum(1 for x in links if x.get("link_priority") == "medium"),
                "low": sum(1 for x in links if x.get("link_priority") == "low"),
            },
            "date_range": {"min": date_min, "max": date_max},
        },
        "paths": {
            "summary": str(OUT_SUMMARY).replace("\\", "/"),
            "snapshot": str(OUT_SNAPSHOT).replace("\\", "/"),
            "condition_mentions": str(OUT_CONDITIONS).replace("\\", "/"),
            "condition_clusters": str(OUT_CONDITION_CLUSTERS).replace("\\", "/"),
            "investigation_events": str(OUT_INVESTIGATIONS).replace("\\", "/"),
            "condition_investigation_links": str(OUT_LINKS).replace("\\", "/"),
            "preview": str(OUT_PREVIEW).replace("\\", "/"),
        },
    }
    save_json(OUT_SUMMARY, summary)

    snapshot = {
        "generated_at": ts,
        "patient_id": "self",
        "batch_id": BATCH_ID,
        "date_range": summary["outputs"]["date_range"],
        "timeline": timeline,
        "condition_mentions": condition_rows,
        "condition_clusters": condition_clusters,
        "investigation_events": investigation_rows,
        "condition_investigation_links": links,
        "notes": [
            "Links are heuristic (same document and temporal proximity), not clinical causality.",
            "Discuss clinical interpretation with a licensed physician.",
        ],
    }
    save_json(OUT_SNAPSHOT, snapshot)

    preview = {
        "generated_at": ts,
        "counts": summary["outputs"],
        "samples": {
            "timeline": timeline[:25],
            "condition_mentions": condition_rows[:25],
            "condition_clusters": condition_clusters[:25],
            "investigation_events": investigation_rows[:25],
            "condition_investigation_links": links[:40],
        },
    }
    save_json(OUT_PREVIEW, preview)

    append_ndjson(
        AUDIT_FILE,
        {
            "ts": ts,
            "event": "agent_body_snapshot_built_v1",
            "batch_id": BATCH_ID,
            "active_documents": len(active_doc_ids),
            "timeline_points": len(timeline),
            "condition_mentions_count": len(condition_rows),
            "investigation_events_count": len(investigation_rows),
            "links_count": len(links),
            "summary_path": str(OUT_SUMMARY).replace("\\", "/"),
        },
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
