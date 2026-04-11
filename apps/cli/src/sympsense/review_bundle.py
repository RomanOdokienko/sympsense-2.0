from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReviewPaths:
    registry: Path
    quality_cfg: Path
    reports_dir: Path
    doctor_dir: Path
    recommendations_dir: Path
    labs_dir: Path


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_files(directory: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.json")):
        try:
            out.append(_load_json(p))
        except Exception:
            continue
    return out


def _expected_entities(doc_type: str, cfg: dict[str, Any]) -> list[str]:
    exact = cfg.get("doc_type_requirements", {})
    if doc_type in exact:
        return list(exact[doc_type])
    for prefix, entities in cfg.get("doc_type_prefix_requirements", {}).items():
        if doc_type.startswith(prefix):
            return list(entities)
    return []


def _compute_review_flags(
    doctor_records: list[dict[str, Any]],
    recommendation_records: list[dict[str, Any]],
    labs_records: list[dict[str, Any]],
    full_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    doctor_needs_review = any(str(x.get("status") or "").strip() == "needs_review" for x in doctor_records)
    recommendations_needs_review = any(
        str(x.get("status") or "").strip() == "needs_review" for x in recommendation_records
    )
    labs_review_required = any(bool((x.get("quality") or {}).get("review_required")) for x in labs_records)
    full_extraction_review_required = bool(((full_extraction or {}).get("quality") or {}).get("review_required"))

    reasons: list[str] = []
    if doctor_needs_review:
        reasons.append("doctor_conclusions")
    if recommendations_needs_review:
        reasons.append("recommendations")
    if labs_review_required:
        reasons.append("labs")
    if full_extraction_review_required:
        reasons.append("full_extraction")

    return {
        "doctor_needs_review": doctor_needs_review,
        "recommendations_needs_review": recommendations_needs_review,
        "labs_review_required": labs_review_required,
        "full_extraction_review_required": full_extraction_review_required,
        "any_review_required": bool(reasons),
        "reasons": reasons,
    }


def _quality_state(row: dict[str, Any], has_full: bool, has_expected: bool, review_required: bool) -> str:
    if row.get("status") == "needs_review" or review_required:
        return "review"
    if has_full and has_expected:
        return "complete"
    return "incomplete"


def _build_file_link(project_root: Path, rel_path: str | None) -> dict[str, str] | None:
    if not rel_path:
        return None
    try:
        abs_path = (project_root / rel_path).resolve()
    except Exception:
        return None
    if not abs_path.exists():
        return None
    try:
        href = abs_path.as_uri()
    except Exception:
        href = ""
    return {
        "href": href,
        "abs_path": str(abs_path),
    }


def _flatten_lab_items(lab_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in lab_records:
        for section in rec.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("name") or "section")
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                out.append(
                    {
                        "section": section_name,
                        "parameter": item.get("parameter"),
                        "result": item.get("result"),
                        "reference": item.get("reference"),
                        "unit": item.get("unit"),
                    }
                )
    return out


def _build_search_blob(
    row: dict[str, Any],
    full_record: dict[str, Any] | None,
    doctor_records: list[dict[str, Any]],
    recommendation_records: list[dict[str, Any]],
    lab_items: list[dict[str, Any]],
    max_len: int = 6000,
) -> str:
    chunks: list[str] = [
        str(row.get("id") or ""),
        str(row.get("file_name") or ""),
        str(((row.get("source") or {}).get("relative_path")) or ""),
        str(row.get("doc_type") or ""),
        str(row.get("event_date_raw") or ""),
    ]
    summary = (full_record or {}).get("summary") or {}
    chunks.extend(
        [
            str(summary.get("visit_type") or ""),
            str(summary.get("recommendation") or ""),
            str((full_record or {}).get("raw_text_excerpt") or ""),
        ]
    )
    for item in doctor_records[:4]:
        chunks.append(str(item.get("conclusion_text") or ""))
        chunks.append(str(item.get("findings_text") or ""))
    for item in recommendation_records[:4]:
        chunks.append(str(item.get("recommendation_text") or ""))
    for item in lab_items[:30]:
        chunks.append(
            " ".join(
                [
                    str(item.get("section") or ""),
                    str(item.get("parameter") or ""),
                    str(item.get("result") or ""),
                    str(item.get("reference") or ""),
                ]
            )
        )
    text = " ".join(x for x in chunks if x).replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[:max_len]
    return text


def _paths(project_root: Path) -> ReviewPaths:
    root = project_root.resolve()
    return ReviewPaths(
        registry=root / "data/canonical/documents/batch_01_registry_active.json",
        quality_cfg=root / "configs/quality_gates_v1.json",
        reports_dir=root / "data/derived/reports",
        doctor_dir=root / "data/canonical/doctor_conclusions",
        recommendations_dir=root / "data/canonical/recommendations",
        labs_dir=root / "data/canonical/labs",
    )


def _collect_sources(project_root: Path) -> dict[str, Any]:
    paths = _paths(project_root)
    registry = _load_json(paths.registry)
    qcfg = _load_json(paths.quality_cfg)

    fe_by_doc: dict[str, dict[str, Any]] = {}
    for p in paths.reports_dir.glob("full_extraction_*.json"):
        try:
            payload = _load_json(p)
        except Exception:
            continue
        doc_id = str(payload.get("doc_id") or "").strip()
        if not doc_id:
            continue
        rel_path = str(p.resolve().relative_to(project_root.resolve())).replace("\\", "/")
        payload["_path"] = rel_path
        fe_by_doc[doc_id] = payload

    doctor_by_doc: dict[str, list[dict[str, Any]]] = {}
    for payload in _read_json_files(paths.doctor_dir):
        doc_id = str((payload.get("source") or {}).get("document_id") or payload.get("doc_id") or "").strip()
        if doc_id:
            doctor_by_doc.setdefault(doc_id, []).append(payload)

    recommendations_by_doc: dict[str, list[dict[str, Any]]] = {}
    for payload in _read_json_files(paths.recommendations_dir):
        doc_id = str((payload.get("source") or {}).get("document_id") or payload.get("doc_id") or "").strip()
        if doc_id:
            recommendations_by_doc.setdefault(doc_id, []).append(payload)

    labs_by_doc: dict[str, list[dict[str, Any]]] = {}
    for payload in _read_json_files(paths.labs_dir):
        doc_id = str(payload.get("doc_id") or (payload.get("source") or {}).get("document_id") or "").strip()
        if doc_id:
            labs_by_doc.setdefault(doc_id, []).append(payload)

    return {
        "registry": registry,
        "qcfg": qcfg,
        "fe_by_doc": fe_by_doc,
        "doctor_by_doc": doctor_by_doc,
        "recommendations_by_doc": recommendations_by_doc,
        "labs_by_doc": labs_by_doc,
    }


def build_review_rows(project_root: Path) -> dict[str, Any]:
    sources = _collect_sources(project_root)
    registry = sources["registry"]
    qcfg = sources["qcfg"]
    fe_by_doc = sources["fe_by_doc"]
    doctor_by_doc = sources["doctor_by_doc"]
    recommendations_by_doc = sources["recommendations_by_doc"]
    labs_by_doc = sources["labs_by_doc"]

    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(registry, start=1):
        doc_id = str(row.get("id") or "")
        doc_type = str(row.get("doc_type") or "")
        expected = _expected_entities(doc_type, qcfg)
        labs_records = labs_by_doc.get(doc_id, [])
        lab_items = _flatten_lab_items(labs_records)
        doctor_records = doctor_by_doc.get(doc_id, [])
        recommendation_records = recommendations_by_doc.get(doc_id, [])
        full_record = fe_by_doc.get(doc_id)

        has_full = doc_id in fe_by_doc
        has_expected = True
        for entity in expected:
            if entity == "doctor_conclusions" and not doctor_records:
                has_expected = False
            elif entity == "recommendations" and not recommendation_records:
                has_expected = False
            elif entity == "labs" and (not labs_records or len(lab_items) == 0):
                has_expected = False

        review_flags = _compute_review_flags(
            doctor_records=doctor_records,
            recommendation_records=recommendation_records,
            labs_records=labs_records,
            full_extraction=full_record,
        )

        source_rel = str(((row.get("source") or {}).get("relative_path")) or "")
        full_rel = str((full_record or {}).get("_path") or "")
        rows.append(
            {
                "idx": idx,
                "doc_id": doc_id,
                "file_name": row.get("file_name"),
                "doc_type": doc_type,
                "event_date_raw": row.get("event_date_raw"),
                "status": row.get("status"),
                "parse_mode": row.get("parse_mode"),
                "text_len": row.get("text_len"),
                "source_rel": source_rel,
                "pdf_link": _build_file_link(project_root, source_rel),
                "has_full_extraction": has_full,
                "has_expected_facts": has_expected,
                "expected_entities": expected,
                "quality_status": _quality_state(row, has_full, has_expected, review_flags["any_review_required"]),
                "review_required": review_flags["any_review_required"],
                "review_flags": review_flags,
                "doctor_count": len(doctor_records),
                "recommendation_count": len(recommendation_records),
                "labs_count": len(labs_records),
                "lab_item_count": len(lab_items),
                "search_blob": _build_search_blob(
                    row=row,
                    full_record=full_record,
                    doctor_records=doctor_records,
                    recommendation_records=recommendation_records,
                    lab_items=lab_items,
                ),
                "full_extraction_rel": full_rel,
                "full_extraction_link": _build_file_link(project_root, full_rel),
            }
        )

    return {
        "generated_at": _now_utc(),
        "source_registry": str(_paths(project_root).registry).replace("\\", "/"),
        "total": len(rows),
        "rows": rows,
    }


def build_review_detail(project_root: Path, doc_id: str) -> dict[str, Any] | None:
    sources = _collect_sources(project_root)
    registry = sources["registry"]
    qcfg = sources["qcfg"]
    fe_by_doc = sources["fe_by_doc"]
    doctor_by_doc = sources["doctor_by_doc"]
    recommendations_by_doc = sources["recommendations_by_doc"]
    labs_by_doc = sources["labs_by_doc"]

    row = next((x for x in registry if str(x.get("id") or "") == doc_id), None)
    if row is None:
        return None

    doc_type = str(row.get("doc_type") or "")
    expected = _expected_entities(doc_type, qcfg)
    labs_records = labs_by_doc.get(doc_id, [])
    lab_items = _flatten_lab_items(labs_records)
    doctor_records = doctor_by_doc.get(doc_id, [])
    recommendation_records = recommendations_by_doc.get(doc_id, [])
    full_record = fe_by_doc.get(doc_id)

    has_full = doc_id in fe_by_doc
    has_expected = True
    for entity in expected:
        if entity == "doctor_conclusions" and not doctor_records:
            has_expected = False
        elif entity == "recommendations" and not recommendation_records:
            has_expected = False
        elif entity == "labs" and (not labs_records or len(lab_items) == 0):
            has_expected = False

    review_flags = _compute_review_flags(
        doctor_records=doctor_records,
        recommendation_records=recommendation_records,
        labs_records=labs_records,
        full_extraction=full_record,
    )
    source_rel = str(((row.get("source") or {}).get("relative_path")) or "")
    full_rel = str((full_record or {}).get("_path") or "")

    return {
        "generated_at": _now_utc(),
        "doc_id": doc_id,
        "idx": next((i for i, x in enumerate(registry, start=1) if str(x.get("id") or "") == doc_id), None),
        "file_name": row.get("file_name"),
        "doc_type": doc_type,
        "event_date_raw": row.get("event_date_raw"),
        "status": row.get("status"),
        "parse_mode": row.get("parse_mode"),
        "text_len": row.get("text_len"),
        "source_rel": source_rel,
        "pdf_link": _build_file_link(project_root, source_rel),
        "has_full_extraction": has_full,
        "has_expected_facts": has_expected,
        "expected_entities": expected,
        "quality_status": _quality_state(row, has_full, has_expected, review_flags["any_review_required"]),
        "review_required": review_flags["any_review_required"],
        "review_flags": review_flags,
        "doctor_conclusions": doctor_records,
        "recommendations": recommendation_records,
        "labs": labs_records,
        "lab_item_count": len(lab_items),
        "lab_items_preview": lab_items[:200],
        "full_extraction": full_record,
        "full_extraction_rel": full_rel,
        "full_extraction_link": _build_file_link(project_root, full_rel),
    }
