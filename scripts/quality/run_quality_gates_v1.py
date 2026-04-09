from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RARE_MOJIBAKE_CHARS = set("Ѓѓ‚„…†‡€‰ЉЊЋЏђєѕіїќћџҐЎўЈ¤¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿�")


@dataclass
class Paths:
    registry: Path
    reports_dir: Path
    canonical_dir: Path
    quality_config: Path
    goldset_config: Path
    output: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def get_nested(obj: dict[str, Any], *keys: str) -> Any:
    cursor: Any = obj
    for key in keys:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_text(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"\W+", "", lowered, flags=re.UNICODE)


def count_lab_items_in_record(record: dict[str, Any]) -> int:
    sections = record.get("sections") or []
    total = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        items = section.get("items") or []
        total += len(items) if isinstance(items, list) else 0
    return total


def looks_like_mojibake(text: str, cfg: dict[str, Any]) -> bool:
    if len(text) < int(cfg["min_text_length"]):
        return False

    cyrillic_chars = [ch for ch in text if "\u0400" <= ch <= "\u04ff"]
    if len(cyrillic_chars) < int(cfg["min_cyrillic_chars"]):
        return False

    rare_count = sum(1 for ch in text if ch in RARE_MOJIBAKE_CHARS)
    if rare_count >= int(cfg["rare_chars_trigger_count"]):
        return True

    rs_count = text.count("Р") + text.count("С")
    rs_ratio = rs_count / max(len(cyrillic_chars), 1)
    return rs_ratio >= float(cfg["rs_ratio_threshold"])


def index_full_extractions(reports_dir: Path) -> tuple[dict[str, list[Path]], dict[str, dict[str, Any]], dict[str, bool]]:
    by_doc: dict[str, list[Path]] = {}
    first_record: dict[str, dict[str, Any]] = {}
    mojibake_by_doc: dict[str, bool] = {}

    for path in iter_json_files(reports_dir):
        if not path.name.startswith("full_extraction_"):
            continue
        try:
            record = load_json(path)
        except Exception:
            continue
        doc_id = safe_text(record.get("doc_id")).strip()
        if not doc_id:
            continue
        by_doc.setdefault(doc_id, []).append(path)
        first_record.setdefault(doc_id, record)
    return by_doc, first_record, mojibake_by_doc


def index_canonical_records(
    canonical_dir: Path,
) -> tuple[
    dict[str, list[Path]],
    dict[str, list[Path]],
    dict[str, list[Path]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, int],
]:
    doctor_by_doc: dict[str, list[Path]] = {}
    rec_by_doc: dict[str, list[Path]] = {}
    lab_by_doc: dict[str, list[Path]] = {}
    doctor_first: dict[str, dict[str, Any]] = {}
    rec_first: dict[str, dict[str, Any]] = {}
    lab_items_count_by_doc: dict[str, int] = {}

    doctor_dir = canonical_dir / "doctor_conclusions"
    for path in iter_json_files(doctor_dir):
        try:
            record = load_json(path)
        except Exception:
            continue
        doc_id = safe_text(get_nested(record, "source", "document_id") or record.get("doc_id")).strip()
        if not doc_id:
            continue
        doctor_by_doc.setdefault(doc_id, []).append(path)
        doctor_first.setdefault(doc_id, record)

    rec_dir = canonical_dir / "recommendations"
    for path in iter_json_files(rec_dir):
        try:
            record = load_json(path)
        except Exception:
            continue
        doc_id = safe_text(get_nested(record, "source", "document_id") or record.get("doc_id")).strip()
        if not doc_id:
            continue
        rec_by_doc.setdefault(doc_id, []).append(path)
        rec_first.setdefault(doc_id, record)

    lab_dir = canonical_dir / "labs"
    for path in iter_json_files(lab_dir):
        try:
            record = load_json(path)
        except Exception:
            continue
        doc_id = safe_text(record.get("doc_id") or get_nested(record, "source", "document_id")).strip()
        if not doc_id:
            continue
        lab_by_doc.setdefault(doc_id, []).append(path)
        lab_items_count_by_doc[doc_id] = max(
            lab_items_count_by_doc.get(doc_id, 0),
            count_lab_items_in_record(record),
        )

    return doctor_by_doc, rec_by_doc, lab_by_doc, doctor_first, rec_first, lab_items_count_by_doc


def expected_entities_for_doc(doc_type: str, config: dict[str, Any]) -> list[str]:
    exact = config.get("doc_type_requirements", {})
    if doc_type in exact:
        return list(exact[doc_type])

    for prefix, entities in config.get("doc_type_prefix_requirements", {}).items():
        if doc_type.startswith(prefix):
            return list(entities)
    return []


def gate_result(actual: int, max_allowed: int) -> dict[str, Any]:
    return {
        "actual": actual,
        "max_allowed": max_allowed,
        "status": "pass" if actual <= max_allowed else "fail",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sympsense quality gates v1.")
    parser.add_argument("--registry", default="data/canonical/documents/batch_01_registry_active.json")
    parser.add_argument("--reports-dir", default="data/derived/reports")
    parser.add_argument("--canonical-dir", default="data/canonical")
    parser.add_argument("--quality-config", default="configs/quality_gates_v1.json")
    parser.add_argument("--goldset-config", default="configs/goldset_v1.json")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_default = f"quality_gates_v1_{datetime.now().date().isoformat()}.json"
    paths = Paths(
        registry=Path(args.registry),
        reports_dir=Path(args.reports_dir),
        canonical_dir=Path(args.canonical_dir),
        quality_config=Path(args.quality_config),
        goldset_config=Path(args.goldset_config),
        output=Path(args.output) if args.output else Path(args.reports_dir) / output_default,
    )

    registry = load_json(paths.registry)
    quality_cfg = load_json(paths.quality_config)
    goldset_cfg = load_json(paths.goldset_config)

    full_by_doc, full_first, _ = index_full_extractions(paths.reports_dir)
    doctor_by_doc, rec_by_doc, lab_by_doc, doctor_first, rec_first, lab_items_count_by_doc = index_canonical_records(paths.canonical_dir)

    source_path_missing_docs: list[str] = []
    missing_full_docs: list[str] = []
    multiple_full_docs: list[str] = []
    missing_required_fact_docs: list[dict[str, Any]] = []
    lab_reports_without_items_docs: list[str] = []
    missing_event_date_docs: list[str] = []
    mojibake_docs: list[str] = []
    duplicated_conclusion_recommendation_docs: list[str] = []

    mojibake_cfg = quality_cfg.get("mojibake_detection", {})

    for row in registry:
        doc_id = safe_text(row.get("id")).strip()
        if not doc_id:
            continue

        source_rel = safe_text(get_nested(row, "source", "relative_path")).strip()
        if not source_rel or not Path(source_rel).exists():
            source_path_missing_docs.append(doc_id)

        full_paths = full_by_doc.get(doc_id, [])
        if len(full_paths) == 0:
            missing_full_docs.append(doc_id)
        if len(full_paths) > 1:
            multiple_full_docs.append(doc_id)

        record = full_first.get(doc_id, {})
        event_date = safe_text(record.get("event_date")).strip()
        if not event_date:
            missing_event_date_docs.append(doc_id)

        text_candidates = [
            safe_text(record.get("source_file")),
            safe_text(record.get("raw_text_excerpt")),
            safe_text(get_nested(record, "summary", "visit_type")),
            safe_text(get_nested(record, "summary", "plan")),
            safe_text(get_nested(record, "summary", "recommendation")),
            safe_text(row.get("summary_preview")),
            safe_text(row.get("file_name")),
        ]
        if any(looks_like_mojibake(t, mojibake_cfg) for t in text_candidates if t):
            mojibake_docs.append(doc_id)

        doc_type = safe_text(row.get("doc_type")).strip()
        required_entities = expected_entities_for_doc(doc_type, quality_cfg)
        missing_entities: list[str] = []
        for entity in required_entities:
            if entity == "doctor_conclusions" and not doctor_by_doc.get(doc_id):
                missing_entities.append(entity)
            elif entity == "recommendations" and not rec_by_doc.get(doc_id):
                missing_entities.append(entity)
            elif entity == "labs" and not lab_by_doc.get(doc_id):
                missing_entities.append(entity)
        if missing_entities:
            missing_required_fact_docs.append({"doc_id": doc_id, "missing_entities": missing_entities})

        if doc_type == "lab_report":
            if lab_items_count_by_doc.get(doc_id, 0) <= 0:
                lab_reports_without_items_docs.append(doc_id)

    all_doc_ids = {safe_text(row.get("id")).strip() for row in registry}
    for doc_id in all_doc_ids:
        d = doctor_first.get(doc_id)
        r = rec_first.get(doc_id)
        if not d or not r:
            continue
        conclusion_text = safe_text(d.get("conclusion_text"))
        recommendation_text = safe_text(r.get("recommendation_text"))
        if not conclusion_text or not recommendation_text:
            continue
        norm_conclusion = normalize_text(conclusion_text)
        norm_recommendation = normalize_text(recommendation_text)
        if len(norm_recommendation) < 40:
            continue
        if norm_recommendation in norm_conclusion or norm_conclusion == norm_recommendation:
            duplicated_conclusion_recommendation_docs.append(doc_id)

    gold_results: list[dict[str, Any]] = []
    for item in goldset_cfg.get("documents", []):
        doc_id = safe_text(item.get("doc_id")).strip()
        expected_type = safe_text(item.get("expected_doc_type")).strip()
        required_entities = list(item.get("required_entities", []))
        must_have_clean_text = bool(item.get("must_have_clean_text", True))

        row = next((r for r in registry if safe_text(r.get("id")).strip() == doc_id), None)
        failures: list[str] = []
        if row is None:
            failures.append("missing_in_registry")
            gold_results.append(
                {
                    "doc_id": doc_id,
                    "status": "fail",
                    "failures": failures,
                }
            )
            continue

        if safe_text(row.get("doc_type")).strip() != expected_type:
            failures.append("wrong_doc_type")

        if doc_id in source_path_missing_docs:
            failures.append("source_path_missing")
        if doc_id in missing_full_docs:
            failures.append("missing_full_extraction")
        if doc_id in missing_event_date_docs:
            failures.append("missing_event_date")
        if must_have_clean_text and doc_id in mojibake_docs:
            failures.append("suspected_mojibake")

        for entity in required_entities:
            if entity == "doctor_conclusions" and not doctor_by_doc.get(doc_id):
                failures.append("missing_doctor_conclusions")
            if entity == "recommendations" and not rec_by_doc.get(doc_id):
                failures.append("missing_recommendations")
            if entity == "labs" and not lab_by_doc.get(doc_id):
                failures.append("missing_labs")
            if entity == "labs" and lab_items_count_by_doc.get(doc_id, 0) <= 0:
                failures.append("missing_labs_items")

        if doc_id in duplicated_conclusion_recommendation_docs:
            failures.append("duplicated_conclusion_recommendation")

        gold_results.append(
            {
                "doc_id": doc_id,
                "status": "pass" if not failures else "fail",
                "failures": failures,
            }
        )

    thresholds = quality_cfg.get("thresholds", {})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "quality_gates_v1",
        "inputs": {
            "registry": str(paths.registry).replace("\\", "/"),
            "reports_dir": str(paths.reports_dir).replace("\\", "/"),
            "canonical_dir": str(paths.canonical_dir).replace("\\", "/"),
            "quality_config": str(paths.quality_config).replace("\\", "/"),
            "goldset_config": str(paths.goldset_config).replace("\\", "/"),
        },
        "totals": {
            "registry_docs": len(registry),
            "full_extraction_docs": len(full_by_doc),
            "doctor_conclusion_docs": len(doctor_by_doc),
            "recommendation_docs": len(rec_by_doc),
            "lab_docs": len(lab_by_doc),
            "lab_docs_with_items": sum(1 for _, c in lab_items_count_by_doc.items() if c > 0),
        },
        "counts": {
            "source_path_missing_count": len(source_path_missing_docs),
            "missing_full_extraction_count": len(missing_full_docs),
            "multiple_full_extraction_count": len(multiple_full_docs),
            "missing_required_domain_fact_count": len(missing_required_fact_docs),
            "lab_reports_without_items_count": len(lab_reports_without_items_docs),
            "missing_event_date_count": len(missing_event_date_docs),
            "mojibake_suspected_count": len(mojibake_docs),
            "duplicated_conclusion_recommendation_count": len(duplicated_conclusion_recommendation_docs),
        },
        "gates": {
            "source_path_missing": gate_result(
                len(source_path_missing_docs),
                int(thresholds.get("source_path_missing_count_max", 0)),
            ),
            "missing_full_extraction": gate_result(
                len(missing_full_docs),
                int(thresholds.get("missing_full_extraction_count_max", 0)),
            ),
            "multiple_full_extraction": gate_result(
                len(multiple_full_docs),
                int(thresholds.get("multiple_full_extraction_count_max", 0)),
            ),
            "missing_required_domain_fact": gate_result(
                len(missing_required_fact_docs),
                int(thresholds.get("missing_required_domain_fact_count_max", 0)),
            ),
            "lab_reports_without_items": gate_result(
                len(lab_reports_without_items_docs),
                int(thresholds.get("lab_reports_without_items_count_max", 0)),
            ),
            "missing_event_date": gate_result(
                len(missing_event_date_docs),
                int(thresholds.get("missing_event_date_count_max", 0)),
            ),
            "mojibake_suspected": gate_result(
                len(mojibake_docs),
                int(thresholds.get("mojibake_suspected_count_max", 0)),
            ),
            "duplicated_conclusion_recommendation": gate_result(
                len(duplicated_conclusion_recommendation_docs),
                int(thresholds.get("duplicated_conclusion_recommendation_count_max", 0)),
            ),
        },
        "samples": {
            "source_path_missing_docs": source_path_missing_docs[:30],
            "missing_full_extraction_docs": missing_full_docs[:30],
            "multiple_full_extraction_docs": multiple_full_docs[:30],
            "missing_required_domain_fact_docs": missing_required_fact_docs[:30],
            "lab_reports_without_items_docs": lab_reports_without_items_docs[:30],
            "missing_event_date_docs": missing_event_date_docs[:30],
            "mojibake_suspected_docs": mojibake_docs[:30],
            "duplicated_conclusion_recommendation_docs": duplicated_conclusion_recommendation_docs[:30],
        },
        "goldset": {
            "total": len(gold_results),
            "passed": sum(1 for r in gold_results if r["status"] == "pass"),
            "failed": sum(1 for r in gold_results if r["status"] == "fail"),
            "results": gold_results,
        },
    }

    paths.output.parent.mkdir(parents=True, exist_ok=True)
    paths.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(paths.output).replace("\\", "/"))


if __name__ == "__main__":
    main()
