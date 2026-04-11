from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _latest_report(reports_dir: Path, prefix: str) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = sorted(
        (p for p in reports_dir.glob(f"{prefix}*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None, None
    path = candidates[-1]
    try:
        payload = _load_json(path)
    except Exception:
        payload = None
    return path, payload


def _report_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "missing"
    status = str(payload.get("status") or "").strip().lower()
    if status in {"pass", "fail"}:
        return status
    gate_statuses = [
        str((v or {}).get("status") or "").strip().lower()
        for v in (payload.get("gates") or {}).values()
    ]
    gate_statuses = [x for x in gate_statuses if x]
    if not gate_statuses:
        return "unknown"
    if any(x == "fail" for x in gate_statuses):
        return "fail"
    if all(x == "pass" for x in gate_statuses):
        return "pass"
    return "unknown"


def run_selfcheck(project_root: Path, write_report: bool = True) -> dict[str, Any]:
    root = project_root.resolve()
    data_root = root / "data"
    reports_dir = data_root / "derived/reports"
    audit_log = data_root / "audit/logs/batch_01_agent.ndjson"

    required_files = {
        "registry_active": data_root / "canonical/documents/batch_01_registry_active.json",
        "fact_summary": data_root / "canonical/facts/fact_layer_v1_summary.json",
        "body_summary": data_root / "canonical/facts/body_snapshot_v1_summary.json",
        "condition_mentions": data_root / "canonical/facts/condition_mentions_v1.ndjson",
        "condition_clusters": data_root / "canonical/facts/condition_clusters_v1.ndjson",
        "investigation_events": data_root / "canonical/facts/investigation_events_v1.ndjson",
        "condition_links": data_root / "canonical/facts/condition_investigation_links_v1.ndjson",
    }
    missing_required_files = [
        name for name, path in required_files.items() if not path.exists()
    ]

    registry_rows = _load_json(required_files["registry_active"]) if required_files["registry_active"].exists() else []
    condition_rows = _load_ndjson(required_files["condition_mentions"])
    cluster_rows = _load_ndjson(required_files["condition_clusters"])
    investigation_rows = _load_ndjson(required_files["investigation_events"])
    link_rows = _load_ndjson(required_files["condition_links"])

    condition_ids = {str(x.get("mention_id") or "") for x in condition_rows if str(x.get("mention_id") or "")}
    investigation_ids = {str(x.get("event_id") or "") for x in investigation_rows if str(x.get("event_id") or "")}

    cluster_mentions: list[str] = []
    for cluster in cluster_rows:
        cluster_mentions.extend(
            [str(m) for m in (cluster.get("mention_ids") or []) if str(m)]
        )
    cluster_mention_set = set(cluster_mentions)

    dangling_condition_links = [
        str(x.get("link_id") or "")
        for x in link_rows
        if str(x.get("condition_id") or "") not in condition_ids
    ]
    dangling_investigation_links = [
        str(x.get("link_id") or "")
        for x in link_rows
        if str(x.get("investigation_id") or "") not in investigation_ids
    ]

    unclustered_condition_ids = sorted(condition_ids - cluster_mention_set)
    cluster_unknown_mentions = sorted(cluster_mention_set - condition_ids)
    cluster_duplicate_mentions_count = len(cluster_mentions) - len(cluster_mention_set)

    q_path, q_payload = _latest_report(reports_dir, "quality_gates_v1_")
    bq_path, bq_payload = _latest_report(reports_dir, "body_snapshot_quality_gates_v1_")
    q_status = _report_status(q_payload)
    bq_status = _report_status(bq_payload)

    checks = {
        "required_files_present": len(missing_required_files) == 0,
        "registry_non_empty": len(registry_rows) > 0,
        "links_no_dangling_refs": len(dangling_condition_links) == 0 and len(dangling_investigation_links) == 0,
        "clusters_cover_conditions": len(unclustered_condition_ids) == 0
        and len(cluster_unknown_mentions) == 0
        and cluster_duplicate_mentions_count == 0,
        "quality_gates_pass": q_status == "pass",
        "body_snapshot_quality_gates_pass": bq_status == "pass",
    }

    overall_status = "pass" if all(checks.values()) else "fail"

    report = {
        "generated_at": _now_utc(),
        "version": "system_selfcheck_v1",
        "status": overall_status,
        "project_root": str(root).replace("\\", "/"),
        "checks": checks,
        "sources": {
            "quality_gates_report": str(q_path).replace("\\", "/") if q_path else None,
            "body_snapshot_quality_gates_report": str(bq_path).replace("\\", "/") if bq_path else None,
        },
        "metrics": {
            "registry_docs": len(registry_rows),
            "condition_mentions": len(condition_rows),
            "condition_clusters": len(cluster_rows),
            "investigation_events": len(investigation_rows),
            "condition_links": len(link_rows),
            "missing_required_files_count": len(missing_required_files),
            "dangling_condition_links_count": len(dangling_condition_links),
            "dangling_investigation_links_count": len(dangling_investigation_links),
            "unclustered_conditions_count": len(unclustered_condition_ids),
            "cluster_unknown_mentions_count": len(cluster_unknown_mentions),
            "cluster_duplicate_mentions_count": cluster_duplicate_mentions_count,
            "quality_gates_status": q_status,
            "body_snapshot_quality_gates_status": bq_status,
        },
        "samples": {
            "missing_required_files": missing_required_files[:20],
            "dangling_condition_link_ids": dangling_condition_links[:30],
            "dangling_investigation_link_ids": dangling_investigation_links[:30],
            "unclustered_condition_ids": unclustered_condition_ids[:30],
            "cluster_unknown_mention_ids": cluster_unknown_mentions[:30],
        },
    }

    if write_report:
        out_name = f"system_selfcheck_v1_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        out_path = reports_dir / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(out_path).replace("\\", "/")

        _append_audit(
            audit_log,
            {
                "ts": _now_utc(),
                "event": "agent_system_selfcheck_ran_v1",
                "status": overall_status,
                "report_path": report["report_path"],
                "checks": checks,
            },
        )

    return report

