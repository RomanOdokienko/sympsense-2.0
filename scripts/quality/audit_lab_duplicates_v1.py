from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(".")
FACTS_PATH = ROOT / "data/canonical/facts/lab_results_v1.ndjson"
REPORTS_DIR = ROOT / "data/derived/reports"

VALUE_TOLERANCE_RELATIVE = 0.08


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_name(name: str | None) -> str:
    value = normalize_space(name).lower().replace("ё", "е")
    value = re.sub(r"^\(?[a-z]{2,8}\s*[#%]?\)?\s*", "", value)
    value = value.replace("микроскопия:", "")
    value = re.sub(r"[(),]+", " ", value)
    return normalize_space(value)


def unit_family(unit: str | None) -> str:
    value = normalize_space(unit).lower().replace("x10^", "10*")
    value = value.replace("10^", "10*")
    if "%" in value:
        return "%"
    if "10*9" in value or "тыс/мкл" in value:
        return "10*9/л"
    if "10*12" in value or "млн/мкл" in value:
        return "10*12/л"
    return value


def clean_value_text(value: str | None) -> str:
    return normalize_space(value).replace("↑", "").replace("↓", "").replace(",", ".").lower()


def numeric_value(row: dict[str, Any]) -> float | None:
    value = row.get("value_num")
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(row.get("value_text") or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def values_close(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, str]:
    if unit_family(left.get("unit")) != unit_family(right.get("unit")):
        return False, "different_unit"

    left_text = clean_value_text(left.get("value_text"))
    right_text = clean_value_text(right.get("value_text"))
    if left_text and left_text == right_text:
        return True, "exact_text"

    left_num = numeric_value(left)
    right_num = numeric_value(right)
    if left_num is None or right_num is None:
        return False, "not_numeric"

    denom = max(abs(left_num), abs(right_num), 1e-9)
    relative_delta = abs(left_num - right_num) / denom
    if relative_delta <= VALUE_TOLERANCE_RELATIVE:
        return True, "near_numeric"
    return False, "different_value"


def canonical_key(row: dict[str, Any]) -> str:
    analyte_id = normalize_space(str(row.get("analyte_id") or ""))
    measurement_kind = normalize_space(str(row.get("measurement_kind") or ""))
    specimen = normalize_space(str(row.get("specimen") or ""))
    if analyte_id:
        return "::".join([specimen or "unknown_specimen", analyte_id, measurement_kind or "value"])
    return "::".join(["raw", normalize_name(str(row.get("analyte_name") or ""))])


def row_summary(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source") or {}
    return {
        "fact_id": row.get("fact_id"),
        "doc_id": row.get("doc_id"),
        "file_name": source.get("file_name"),
        "event_date": row.get("event_date"),
        "document_bundle_id": row.get("document_bundle_id"),
        "document_bundle_key": row.get("document_bundle_key"),
        "document_bundle_size": row.get("document_bundle_size"),
        "section_name": row.get("section_name"),
        "analyte_name": row.get("analyte_name"),
        "analyte_id": row.get("analyte_id"),
        "measurement_kind": row.get("measurement_kind"),
        "method": row.get("method"),
        "specimen": row.get("specimen"),
        "value_text": row.get("value_text"),
        "unit": row.get("unit"),
        "reference_range_text": row.get("reference_range_text"),
        "duplicate_group_id": row.get("duplicate_group_id"),
        "duplicate_role": row.get("duplicate_role"),
        "duplicate_of_fact_id": row.get("duplicate_of_fact_id"),
        "duplicate_reason": row.get("duplicate_reason"),
        "cross_document_duplicate_group_id": row.get("cross_document_duplicate_group_id"),
        "cross_document_duplicate_role": row.get("cross_document_duplicate_role"),
        "cross_document_duplicate_of_fact_id": row.get("cross_document_duplicate_of_fact_id"),
        "cross_document_duplicate_reason": row.get("cross_document_duplicate_reason"),
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        out[name] = out.get(name, 0) + 1
    return out


def close_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(rows):
        for right in rows[i + 1 :]:
            is_close, reason = values_close(left, right)
            if is_close:
                pairs.append(
                    {
                        "match_reason": reason,
                        "left": row_summary(left),
                        "right": row_summary(right),
                    }
                )
    return pairs


def audit_intra_document(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = canonical_key(row)
        if key.startswith("raw::"):
            continue
        grouped.setdefault((str(row.get("doc_id") or ""), key), []).append(row)

    duplicate_groups: list[dict[str, Any]] = []
    related_groups: list[dict[str, Any]] = []
    for (doc_id, key), items in sorted(grouped.items()):
        if len(items) < 2:
            continue
        pairs = close_pairs(items)
        if not pairs:
            continue

        methods = {normalize_space(str(item.get("method") or "unknown")) for item in items}
        payload = {
            "doc_id": doc_id,
            "canonical_key": key,
            "methods": sorted(methods),
            "rows_count": len(items),
            "close_pairs_count": len(pairs),
            "rows": [row_summary(item) for item in items],
            "close_pairs": pairs,
        }
        if len(methods) == 1:
            duplicate_groups.append(payload)
        else:
            related_groups.append(payload)

    return duplicate_groups, related_groups


def audit_cross_document(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        document_bundle_id = normalize_space(str(row.get("document_bundle_id") or ""))
        event_date = normalize_space(str(row.get("event_date") or ""))
        scope_id = document_bundle_id or event_date
        if not scope_id:
            continue
        key = (
            scope_id,
            canonical_key(row),
            clean_value_text(row.get("value_text")),
            unit_family(row.get("unit")),
        )
        grouped.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for (scope_id, key, value_text, unit), items in sorted(grouped.items()):
        doc_ids = {str(item.get("doc_id") or "") for item in items}
        if len(doc_ids) < 2:
            continue
        bundle_ids = sorted(
            {str(item.get("document_bundle_id") or "") for item in items if item.get("document_bundle_id")}
        )
        event_dates = sorted({str(item.get("event_date") or "") for item in items if item.get("event_date")})
        out.append(
            {
                "scope_id": scope_id,
                "document_bundle_ids": bundle_ids,
                "event_dates": event_dates,
                "canonical_key": key,
                "value_text": value_text,
                "unit_family": unit,
                "doc_ids_count": len(doc_ids),
                "rows_count": len(items),
                "rows": [row_summary(item) for item in items],
            }
        )
    return out


def main() -> None:
    run_ts = now_iso()
    rows = load_ndjson(FACTS_PATH)
    normalized_rows = [row for row in rows if row.get("analyte_id")]
    flagged_duplicate_rows = [row for row in rows if row.get("duplicate_role")]
    flagged_cross_document_duplicate_rows = [row for row in rows if row.get("cross_document_duplicate_role")]
    marked_cross_document_group_ids = {
        row.get("cross_document_duplicate_group_id")
        for row in flagged_cross_document_duplicate_rows
        if row.get("cross_document_duplicate_group_id")
    }
    document_bundle_ids = {row.get("document_bundle_id") for row in rows if row.get("document_bundle_id")}
    bundled_rows = [row for row in rows if row.get("document_bundle_id")]
    intra_duplicates, related_method_groups = audit_intra_document(rows)
    cross_document_duplicates = audit_cross_document(rows)

    report = {
        "generated_at": run_ts,
        "version": "lab_duplicate_audit_v1",
        "inputs": {
            "lab_results": str(FACTS_PATH).replace("\\", "/"),
        },
        "totals": {
            "lab_results_count": len(rows),
            "normalized_lab_results_count": len(normalized_rows),
            "document_bundle_count": len(document_bundle_ids),
            "bundled_lab_results_count": len(bundled_rows),
            "duplicate_role_counts": count_by(rows, "duplicate_role"),
            "flagged_duplicate_rows_count": len(flagged_duplicate_rows),
            "cross_document_duplicate_role_counts": count_by(rows, "cross_document_duplicate_role"),
            "flagged_cross_document_duplicate_rows_count": len(flagged_cross_document_duplicate_rows),
            "marked_cross_document_duplicate_groups_count": len(marked_cross_document_group_ids),
            "intra_document_duplicate_groups_count": len(intra_duplicates),
            "related_method_groups_count": len(related_method_groups),
            "cross_document_duplicate_groups_count": len(cross_document_duplicates),
        },
        "notes": [
            "This report is audit-only and does not modify facts.",
            "related_method_groups are intentionally not duplicate removals; they usually compare analyzer and manual microscopy rows.",
            "cross_document_duplicate_groups are scoped by document_bundle_id when available, with event_date as fallback.",
        ],
        "intra_document_duplicate_groups": intra_duplicates,
        "related_method_groups": related_method_groups,
        "cross_document_duplicate_groups": cross_document_duplicates,
    }

    report_path = REPORTS_DIR / f"lab_duplicate_audit_v1_{now_stamp()}.json"
    latest_path = REPORTS_DIR / "lab_duplicate_audit_v1_latest.json"
    save_json(report_path, report)
    save_json(latest_path, report)
    print(json.dumps({"report_path": str(report_path), "totals": report["totals"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
