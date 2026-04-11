from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sympsense.fact_review_decisions import load_latest_decisions


FACT_PATHS: dict[str, str] = {
    "lab_results": "data/canonical/facts/lab_results_v1.ndjson",
    "clinical_findings": "data/canonical/facts/clinical_findings_v1.ndjson",
    "recommendation_items": "data/canonical/facts/recommendation_items_v1.ndjson",
    "medication_items": "data/canonical/facts/medication_items_v1.ndjson",
    "condition_mentions": "data/canonical/facts/condition_mentions_v1.ndjson",
    "condition_investigation_links": "data/canonical/facts/condition_investigation_links_v1.ndjson",
}


BASE_PRIORITY: dict[str, float] = {
    "condition_mentions": 1.0,
    "clinical_findings": 0.95,
    "condition_investigation_links": 0.9,
    "lab_results": 0.8,
    "recommendation_items": 0.55,
    "medication_items": 0.35,
}


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _to_float(v: Any, default: float = 0.5) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _preview(collection: str, row: dict[str, Any]) -> str:
    if collection == "lab_results":
        analyte = _norm(row.get("analyte_name"))
        value = _norm(row.get("value_text"))
        ref = _norm(row.get("reference_range_text"))
        if analyte or value:
            return f"{analyte}: {value}" + (f" (ref: {ref})" if ref else "")
    if collection in {"clinical_findings", "condition_mentions"}:
        text = _norm(row.get("text") or row.get("condition_text"))
        return text[:320]
    if collection == "recommendation_items":
        return _norm(row.get("text"))[:320]
    if collection == "medication_items":
        med = _norm(row.get("medication_name"))
        instr = _norm(row.get("instruction_text"))
        return (f"{med}: {instr}" if med else instr)[:320]
    if collection == "condition_investigation_links":
        rel = _norm(row.get("relation_type"))
        cond = _norm(row.get("condition_id"))
        inv = _norm(row.get("investigation_id"))
        return f"{rel}: {cond} -> {inv}"
    return _norm(row.get("evidence_excerpt"))[:320]


def _reasons(collection: str, row: dict[str, Any]) -> list[str]:
    reasons = [str(x) for x in (row.get("qa_reasons") or []) if str(x).strip()]
    if collection == "condition_investigation_links":
        reasons.extend([str(x) for x in (row.get("score_reasons") or []) if str(x).strip()])
    return sorted(set(reasons))


def build_fact_review_queue(
    project_root: Path,
    *,
    include_medications: bool = False,
    include_ok: bool = False,
    include_resolved: bool = False,
    collections_filter: set[str] | None = None,
    review_state_filter: str = "all",
    doc_id: str = "",
) -> list[dict[str, Any]]:
    root = project_root.resolve()
    doc_filter = _norm(doc_id)
    review_state_norm = _norm(review_state_filter).lower() or "all"
    if review_state_norm not in {"all", "open", "resolved", "skipped"}:
        review_state_norm = "all"
    decisions = load_latest_decisions(root)

    collections = ["lab_results", "clinical_findings", "condition_mentions", "condition_investigation_links", "recommendation_items"]
    if include_medications:
        collections.append("medication_items")
    if collections_filter:
        normalized = {x.strip().lower() for x in collections_filter if x and x.strip()}
        collections = [x for x in collections if x in normalized]

    queue: list[dict[str, Any]] = []
    for collection in collections:
        path = root / FACT_PATHS[collection]
        rows = _load_ndjson(path)
        for row in rows:
            qa_status = _norm(row.get("qa_status") or "needs_review").lower()
            if not include_ok and qa_status != "needs_review":
                continue

            row_doc_id = _norm(row.get("doc_id") or row.get("condition_doc_id") or row.get("investigation_doc_id"))
            if doc_filter and row_doc_id != doc_filter:
                continue

            confidence = _to_float(row.get("confidence"), default=0.5)
            reasons = _reasons(collection, row)
            base = BASE_PRIORITY.get(collection, 0.4)
            score = base + (1.0 - confidence) * 0.85 + (0.25 if qa_status == "needs_review" else 0.0)
            if "condition_needs_review" in reasons or "investigation_needs_review" in reasons:
                score += 0.1
            if "suspicious_analyte_prefix" in reasons:
                score += 0.1
            if collection in {"condition_mentions", "clinical_findings"} and row_doc_id:
                score += 0.05
            queue_id = f"{collection}:{_norm(row.get('fact_id') or row.get('mention_id') or row.get('link_id'))}"
            decision = decisions.get(queue_id) or {}
            action = _norm(decision.get("action")).lower()
            review_state = "open" if action not in {"resolved", "skipped"} else action
            if not include_resolved and review_state in {"resolved", "skipped"}:
                continue
            if review_state_norm != "all" and review_state != review_state_norm:
                continue

            queue.append(
                {
                    "queue_id": queue_id,
                    "fact_collection": collection,
                    "fact_id": _norm(row.get("fact_id") or row.get("mention_id") or row.get("link_id")),
                    "doc_id": row_doc_id,
                    "doc_type": _norm(row.get("doc_type")),
                    "event_date": _norm(row.get("event_date")),
                    "qa_status": qa_status,
                    "review_state": review_state,
                    "confidence": round(confidence, 3),
                    "priority_score": round(score, 3),
                    "reasons": reasons,
                    "preview": _preview(collection, row),
                    "decision": decision if decision else None,
                }
            )

    queue.sort(key=lambda x: (-float(x.get("priority_score") or 0.0), str(x.get("event_date") or ""), str(x.get("doc_id") or "")))
    return queue
