from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ICD_CODE_RE = re.compile(r"^[A-TV-Z]\d{2}(?:\.\d{1,2})?$")
SPINE_LEVEL_RE = re.compile(r"^[CSL]\d{1,2}(?:[-/]\d{1,2})?$", flags=re.IGNORECASE)


@dataclass
class Paths:
    summary: Path
    snapshot: Path
    conditions: Path
    clusters: Path
    investigations: Path
    links: Path
    config: Path
    output: Path
    reports_dir: Path
    audit_file: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_ndjson(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def gate_max(actual: float, max_allowed: float) -> dict[str, Any]:
    return {
        "actual": actual,
        "max_allowed": max_allowed,
        "status": "pass" if actual <= max_allowed else "fail",
    }


def gate_min(actual: float, min_allowed: float) -> dict[str, Any]:
    return {
        "actual": actual,
        "min_allowed": min_allowed,
        "status": "pass" if actual >= min_allowed else "fail",
    }


def gate_range(actual: float, min_allowed: float, max_allowed: float) -> dict[str, Any]:
    return {
        "actual": actual,
        "min_allowed": min_allowed,
        "max_allowed": max_allowed,
        "status": "pass" if min_allowed <= actual <= max_allowed else "fail",
    }


def find_previous_report(reports_dir: Path, output_file: Path) -> Path | None:
    candidates = sorted(
        (
            p
            for p in reports_dir.glob("body_snapshot_quality_gates_v1_*.json")
            if p.is_file() and p.resolve() != output_file.resolve()
        ),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def run_regression_checks(
    current_metrics: dict[str, float],
    previous_metrics: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    regression_cfg = cfg.get("regression", {})

    for metric, max_inc in regression_cfg.get("count_metrics_max_increase", {}).items():
        prev = safe_float(previous_metrics.get(metric))
        curr = safe_float(current_metrics.get(metric))
        delta = curr - prev
        status = "pass" if delta <= float(max_inc) else "fail"
        row = {
            "type": "count_max_increase",
            "metric": metric,
            "previous": prev,
            "current": curr,
            "delta": delta,
            "max_increase": float(max_inc),
            "status": status,
        }
        checks.append(row)
        if status == "fail":
            failures.append(row)

    for metric, max_drop in regression_cfg.get("ratio_metrics_max_relative_drop", {}).items():
        prev = safe_float(previous_metrics.get(metric))
        curr = safe_float(current_metrics.get(metric))
        if prev <= 0:
            status = "pass"
            drop = None
        else:
            drop = (prev - curr) / prev
            status = "pass" if drop <= float(max_drop) else "fail"
        row = {
            "type": "ratio_max_relative_drop",
            "metric": metric,
            "previous": prev,
            "current": curr,
            "relative_drop": drop,
            "max_relative_drop": float(max_drop),
            "status": status,
        }
        checks.append(row)
        if status == "fail":
            failures.append(row)

    for metric, max_delta in regression_cfg.get("ratio_metrics_max_absolute_delta", {}).items():
        prev = safe_float(previous_metrics.get(metric))
        curr = safe_float(current_metrics.get(metric))
        abs_delta = abs(curr - prev)
        status = "pass" if abs_delta <= float(max_delta) else "fail"
        row = {
            "type": "ratio_max_absolute_delta",
            "metric": metric,
            "previous": prev,
            "current": curr,
            "abs_delta": abs_delta,
            "max_abs_delta": float(max_delta),
            "status": status,
        }
        checks.append(row)
        if status == "fail":
            failures.append(row)

    return checks, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Run body snapshot quality gates v1.")
    parser.add_argument("--summary", default="data/canonical/facts/body_snapshot_v1_summary.json")
    parser.add_argument("--snapshot", default="data/canonical/facts/body_snapshot_v1.json")
    parser.add_argument("--conditions", default="data/canonical/facts/condition_mentions_v1.ndjson")
    parser.add_argument("--clusters", default="data/canonical/facts/condition_clusters_v1.ndjson")
    parser.add_argument("--investigations", default="data/canonical/facts/investigation_events_v1.ndjson")
    parser.add_argument("--links", default="data/canonical/facts/condition_investigation_links_v1.ndjson")
    parser.add_argument("--config", default="configs/body_snapshot_quality_gates_v1.json")
    parser.add_argument("--reports-dir", default="data/derived/reports")
    parser.add_argument("--audit-file", default="data/audit/logs/batch_01_agent.ndjson")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_default = f"body_snapshot_quality_gates_v1_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    paths = Paths(
        summary=Path(args.summary),
        snapshot=Path(args.snapshot),
        conditions=Path(args.conditions),
        clusters=Path(args.clusters),
        investigations=Path(args.investigations),
        links=Path(args.links),
        config=Path(args.config),
        output=Path(args.output) if args.output else Path(args.reports_dir) / output_default,
        reports_dir=Path(args.reports_dir),
        audit_file=Path(args.audit_file),
    )

    cfg = load_json(paths.config)
    thresholds = cfg.get("thresholds", {})
    allowed_values = cfg.get("allowed_values", {})

    required_paths = {
        "summary": paths.summary,
        "snapshot": paths.snapshot,
        "conditions": paths.conditions,
        "clusters": paths.clusters,
        "investigations": paths.investigations,
        "links": paths.links,
    }
    missing_files = [name for name, path in required_paths.items() if not path.exists()]
    missing_required_files_count = len(missing_files)

    summary = load_json(paths.summary) if paths.summary.exists() else {}
    snapshot = load_json(paths.snapshot) if paths.snapshot.exists() else {}
    conditions = load_ndjson(paths.conditions)
    clusters = load_ndjson(paths.clusters)
    investigations = load_ndjson(paths.investigations)
    links = load_ndjson(paths.links)

    condition_ids = {str(x.get("mention_id") or "") for x in conditions if str(x.get("mention_id") or "")}
    investigation_ids = {str(x.get("event_id") or "") for x in investigations if str(x.get("event_id") or "")}

    link_condition_ids = {str(x.get("condition_id") or "") for x in links if str(x.get("condition_id") or "")}
    link_investigation_ids = {str(x.get("investigation_id") or "") for x in links if str(x.get("investigation_id") or "")}

    dangling_cond_links = [
        str(x.get("link_id") or "")
        for x in links
        if str(x.get("condition_id") or "") not in condition_ids
    ]
    dangling_inv_links = [
        str(x.get("link_id") or "")
        for x in links
        if str(x.get("investigation_id") or "") not in investigation_ids
    ]
    dangling_link_refs_count = len(dangling_cond_links) + len(dangling_inv_links)

    cluster_mention_ids: list[str] = []
    for cluster in clusters:
        cluster_mention_ids.extend([str(m) for m in cluster.get("mention_ids", []) if str(m)])
    cluster_mention_set = set(cluster_mention_ids)
    cluster_unknown_mentions = sorted(cluster_mention_set - condition_ids)
    cluster_unknown_mentions_count = len(cluster_unknown_mentions)
    cluster_duplicate_mentions_count = len(cluster_mention_ids) - len(cluster_mention_set)
    unclustered_conditions = sorted(condition_ids - cluster_mention_set)
    unclustered_conditions_count = len(unclustered_conditions)

    allowed_qa = set(allowed_values.get("qa_status", []))
    allowed_priorities = set(allowed_values.get("link_priority", []))
    allowed_rel_types = set(allowed_values.get("relation_type", []))

    invalid_qa_items: list[dict[str, str]] = []
    for row in conditions:
        qa = str(row.get("qa_status") or "")
        if qa not in allowed_qa:
            invalid_qa_items.append({"entity": "condition", "id": str(row.get("mention_id") or ""), "qa_status": qa})
    for row in investigations:
        qa = str(row.get("qa_status") or "")
        if qa not in allowed_qa:
            invalid_qa_items.append(
                {"entity": "investigation", "id": str(row.get("event_id") or ""), "qa_status": qa}
            )
    for row in links:
        qa = str(row.get("qa_status") or "")
        if qa not in allowed_qa:
            invalid_qa_items.append({"entity": "link", "id": str(row.get("link_id") or ""), "qa_status": qa})
    invalid_qa_status_count = len(invalid_qa_items)

    invalid_link_priority_items = [
        {"id": str(x.get("link_id") or ""), "link_priority": str(x.get("link_priority") or "")}
        for x in links
        if str(x.get("link_priority") or "") not in allowed_priorities
    ]
    invalid_link_priority_count = len(invalid_link_priority_items)

    invalid_relation_type_items = [
        {"id": str(x.get("link_id") or ""), "relation_type": str(x.get("relation_type") or "")}
        for x in links
        if str(x.get("relation_type") or "") not in allowed_rel_types
    ]
    invalid_relation_type_count = len(invalid_relation_type_items)

    invalid_icd_codes: list[dict[str, str]] = []
    suspicious_spine_level_icd: list[dict[str, str]] = []
    for row in conditions:
        mention_id = str(row.get("mention_id") or "")
        for code in row.get("icd_codes", []) or []:
            code_s = str(code).strip().upper()
            if not code_s:
                continue
            if not ICD_CODE_RE.match(code_s):
                invalid_icd_codes.append({"mention_id": mention_id, "code": code_s})
            if SPINE_LEVEL_RE.match(code_s):
                suspicious_spine_level_icd.append({"mention_id": mention_id, "code": code_s})
    invalid_icd_code_count = len(invalid_icd_codes)
    suspicious_spine_level_icd_count = len(suspicious_spine_level_icd)

    dropped_orphan = summary.get("inputs", {}).get("dropped_orphan_facts", {})
    dropped_orphan_facts_count = int(dropped_orphan.get("clinical_findings", 0)) + int(
        dropped_orphan.get("lab_results", 0)
    )

    conditions_without_links = sorted(condition_ids - link_condition_ids)
    investigations_without_links = sorted(investigation_ids - link_investigation_ids)
    conditions_without_links_count = len(conditions_without_links)
    investigations_without_links_count = len(investigations_without_links)
    conditions_without_links_share = conditions_without_links_count / max(len(condition_ids), 1)
    investigations_without_links_share = investigations_without_links_count / max(len(investigation_ids), 1)

    high_count = sum(1 for x in links if str(x.get("link_priority") or "") == "high")
    low_count = sum(1 for x in links if str(x.get("link_priority") or "") == "low")
    links_per_condition = len(links) / max(len(condition_ids), 1)
    clusters_per_condition = len(clusters) / max(len(condition_ids), 1)
    high_priority_share = high_count / max(len(links), 1)
    low_priority_share = low_count / max(len(links), 1)

    summary_mismatches: list[dict[str, Any]] = []
    expected_summary = {
        "condition_mentions_count": len(conditions),
        "condition_clusters_count": len(clusters),
        "investigation_events_count": len(investigations),
        "condition_investigation_links_count": len(links),
        "timeline_points": len(snapshot.get("timeline", []) if isinstance(snapshot, dict) else []),
    }
    summary_outputs = summary.get("outputs", {}) if isinstance(summary, dict) else {}
    for key, expected in expected_summary.items():
        actual = summary_outputs.get(key)
        if actual is None:
            summary_mismatches.append({"metric": key, "expected": expected, "actual": None, "reason": "missing"})
            continue
        try:
            actual_int = int(actual)
        except (TypeError, ValueError):
            summary_mismatches.append(
                {"metric": key, "expected": expected, "actual": actual, "reason": "not_int"}
            )
            continue
        if actual_int != expected:
            summary_mismatches.append(
                {"metric": key, "expected": expected, "actual": actual_int, "reason": "value_mismatch"}
            )
    summary_mismatch_count = len(summary_mismatches)

    metrics: dict[str, float] = {
        "missing_required_files_count": float(missing_required_files_count),
        "summary_mismatch_count": float(summary_mismatch_count),
        "dangling_link_refs_count": float(dangling_link_refs_count),
        "cluster_unknown_mentions_count": float(cluster_unknown_mentions_count),
        "cluster_duplicate_mentions_count": float(cluster_duplicate_mentions_count),
        "unclustered_conditions_count": float(unclustered_conditions_count),
        "invalid_qa_status_count": float(invalid_qa_status_count),
        "invalid_link_priority_count": float(invalid_link_priority_count),
        "invalid_relation_type_count": float(invalid_relation_type_count),
        "invalid_icd_code_count": float(invalid_icd_code_count),
        "suspicious_spine_level_icd_count": float(suspicious_spine_level_icd_count),
        "dropped_orphan_facts_count": float(dropped_orphan_facts_count),
        "conditions_without_links_count": float(conditions_without_links_count),
        "conditions_without_links_share": conditions_without_links_share,
        "investigations_without_links_count": float(investigations_without_links_count),
        "investigations_without_links_share": investigations_without_links_share,
        "links_per_condition": links_per_condition,
        "clusters_per_condition": clusters_per_condition,
        "high_priority_share": high_priority_share,
        "low_priority_share": low_priority_share,
    }

    gates = {
        "missing_required_files": gate_max(
            metrics["missing_required_files_count"],
            float(thresholds.get("missing_required_files_count_max", 0)),
        ),
        "summary_mismatch": gate_max(
            metrics["summary_mismatch_count"],
            float(thresholds.get("summary_mismatch_count_max", 0)),
        ),
        "dangling_link_refs": gate_max(
            metrics["dangling_link_refs_count"],
            float(thresholds.get("dangling_link_refs_count_max", 0)),
        ),
        "cluster_unknown_mentions": gate_max(
            metrics["cluster_unknown_mentions_count"],
            float(thresholds.get("cluster_unknown_mentions_count_max", 0)),
        ),
        "cluster_duplicate_mentions": gate_max(
            metrics["cluster_duplicate_mentions_count"],
            float(thresholds.get("cluster_duplicate_mentions_count_max", 0)),
        ),
        "unclustered_conditions": gate_max(
            metrics["unclustered_conditions_count"],
            float(thresholds.get("unclustered_conditions_count_max", 0)),
        ),
        "invalid_qa_status": gate_max(
            metrics["invalid_qa_status_count"],
            float(thresholds.get("invalid_qa_status_count_max", 0)),
        ),
        "invalid_link_priority": gate_max(
            metrics["invalid_link_priority_count"],
            float(thresholds.get("invalid_link_priority_count_max", 0)),
        ),
        "invalid_relation_type": gate_max(
            metrics["invalid_relation_type_count"],
            float(thresholds.get("invalid_relation_type_count_max", 0)),
        ),
        "invalid_icd_code": gate_max(
            metrics["invalid_icd_code_count"],
            float(thresholds.get("invalid_icd_code_count_max", 0)),
        ),
        "suspicious_spine_level_icd": gate_max(
            metrics["suspicious_spine_level_icd_count"],
            float(thresholds.get("suspicious_spine_level_icd_count_max", 0)),
        ),
        "dropped_orphan_facts": gate_max(
            metrics["dropped_orphan_facts_count"],
            float(thresholds.get("dropped_orphan_facts_count_max", 0)),
        ),
        "conditions_without_links_share": gate_max(
            metrics["conditions_without_links_share"],
            float(thresholds.get("conditions_without_links_share_max", 1.0)),
        ),
        "investigations_without_links_share": gate_max(
            metrics["investigations_without_links_share"],
            float(thresholds.get("investigations_without_links_share_max", 1.0)),
        ),
        "links_per_condition": gate_range(
            metrics["links_per_condition"],
            float(thresholds.get("links_per_condition_min", 0.0)),
            float(thresholds.get("links_per_condition_max", 100.0)),
        ),
        "clusters_per_condition": gate_range(
            metrics["clusters_per_condition"],
            float(thresholds.get("clusters_per_condition_min", 0.0)),
            float(thresholds.get("clusters_per_condition_max", 100.0)),
        ),
        "high_priority_share": gate_range(
            metrics["high_priority_share"],
            float(thresholds.get("high_priority_share_min", 0.0)),
            float(thresholds.get("high_priority_share_max", 1.0)),
        ),
        "low_priority_share": gate_max(
            metrics["low_priority_share"],
            float(thresholds.get("low_priority_share_max", 1.0)),
        ),
    }

    previous_report_path = find_previous_report(paths.reports_dir, paths.output)
    regression_checks: list[dict[str, Any]] = []
    regression_failures: list[dict[str, Any]] = []
    if bool(cfg.get("regression", {}).get("enabled", True)) and previous_report_path:
        prev_report = load_json(previous_report_path)
        prev_metrics = prev_report.get("metrics", {})
        regression_checks, regression_failures = run_regression_checks(metrics, prev_metrics, cfg)

    failed_gates = [name for name, payload in gates.items() if payload.get("status") == "fail"]
    overall_status = "pass" if not failed_gates and not regression_failures else "fail"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "body_snapshot_quality_gates_v1",
        "status": overall_status,
        "inputs": {
            "summary": str(paths.summary).replace("\\", "/"),
            "snapshot": str(paths.snapshot).replace("\\", "/"),
            "conditions": str(paths.conditions).replace("\\", "/"),
            "clusters": str(paths.clusters).replace("\\", "/"),
            "investigations": str(paths.investigations).replace("\\", "/"),
            "links": str(paths.links).replace("\\", "/"),
            "config": str(paths.config).replace("\\", "/"),
        },
        "totals": {
            "conditions": len(conditions),
            "clusters": len(clusters),
            "investigations": len(investigations),
            "links": len(links),
        },
        "metrics": metrics,
        "gates": gates,
        "failed_gates": failed_gates,
        "regression": {
            "enabled": bool(cfg.get("regression", {}).get("enabled", True)),
            "previous_report": str(previous_report_path).replace("\\", "/") if previous_report_path else None,
            "checks": regression_checks,
            "failures": regression_failures,
        },
        "samples": {
            "missing_files": missing_files[:20],
            "summary_mismatches": summary_mismatches[:20],
            "dangling_condition_link_ids": dangling_cond_links[:30],
            "dangling_investigation_link_ids": dangling_inv_links[:30],
            "unclustered_condition_ids": unclustered_conditions[:30],
            "cluster_unknown_mention_ids": cluster_unknown_mentions[:30],
            "invalid_qa_items": invalid_qa_items[:30],
            "invalid_link_priority_items": invalid_link_priority_items[:30],
            "invalid_relation_type_items": invalid_relation_type_items[:30],
            "invalid_icd_codes": invalid_icd_codes[:30],
            "suspicious_spine_level_icd_codes": suspicious_spine_level_icd[:30],
            "conditions_without_links": conditions_without_links[:30],
            "investigations_without_links": investigations_without_links[:30],
        },
    }

    paths.output.parent.mkdir(parents=True, exist_ok=True)
    paths.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    append_ndjson(
        paths.audit_file,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "agent_body_snapshot_quality_gates_ran_v1",
            "report_path": str(paths.output).replace("\\", "/"),
            "status": overall_status,
            "failed_gates_count": len(failed_gates),
            "failed_regression_checks_count": len(regression_failures),
            "conditions": len(conditions),
            "clusters": len(clusters),
            "investigations": len(investigations),
            "links": len(links),
        },
    )

    print(str(paths.output).replace("\\", "/"))


if __name__ == "__main__":
    main()
