from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sympsense.analytics_graph import build_body_graph
from sympsense.fact_review_queue import build_fact_review_queue


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _load_json(path)


def _latest_report(reports_dir: Path, prefix: str) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = sorted(
        (p for p in reports_dir.glob(f"{prefix}*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None, None
    path = candidates[-1]
    payload = _read_if_exists(path)
    if not isinstance(payload, dict):
        payload = None
    return path, payload


def _report_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "missing"
    status = str(payload.get("status") or "").strip().lower()
    if status in {"pass", "fail"}:
        return status
    gate_statuses = [
        str((gate or {}).get("status") or "").strip().lower()
        for gate in (payload.get("gates") or {}).values()
    ]
    gate_statuses = [x for x in gate_statuses if x]
    if not gate_statuses:
        return "unknown"
    if any(x == "fail" for x in gate_statuses):
        return "fail"
    if all(x == "pass" for x in gate_statuses):
        return "pass"
    return "unknown"


def _append_audit(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _overall_quality_status(*statuses: str) -> str:
    normalized = [str(x or "").strip().lower() for x in statuses if str(x or "").strip()]
    if not normalized:
        return "unknown"
    if any(x == "fail" for x in normalized):
        return "fail"
    if all(x == "pass" for x in normalized):
        return "pass"
    return "unknown"


def build_downstream_export(
    project_root: Path,
    *,
    include_graph: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    data_root = root / "data"
    reports_dir = data_root / "derived/reports"

    registry_path = data_root / "canonical/documents/batch_01_registry_active.json"
    fact_summary_path = data_root / "canonical/facts/fact_layer_v1_summary.json"
    body_summary_path = data_root / "canonical/facts/body_snapshot_v1_summary.json"

    if not registry_path.exists():
        raise FileNotFoundError("batch_01_registry_active.json not found")

    registry_rows: list[dict[str, Any]] = _load_json(registry_path)
    fact_summary = _read_if_exists(fact_summary_path)
    body_summary = _read_if_exists(body_summary_path)

    q_path, q_payload = _latest_report(reports_dir, "quality_gates_v1_")
    bq_path, bq_payload = _latest_report(reports_dir, "body_snapshot_quality_gates_v1_")
    sc_path, sc_payload = _latest_report(reports_dir, "system_selfcheck_v1_")
    q_status = _report_status(q_payload)
    bq_status = _report_status(bq_payload)
    sc_status = _report_status(sc_payload)

    queue = build_fact_review_queue(
        project_root=root,
        include_medications=True,
        include_ok=False,
        include_resolved=False,
        review_state_filter="open",
    )
    queue_counts = dict(Counter(str(x.get("fact_collection") or "") for x in queue))

    graph_payload: dict[str, Any] | None = None
    if include_graph:
        graph_payload = build_body_graph(
            project_root=root,
            include_needs_review=False,
            min_link_confidence=0.62,
            allowed_link_priorities={"high", "medium"},
            include_document_nodes=True,
            include_orphans=False,
        )

    doc_type_counts = dict(Counter(str(x.get("doc_type") or "unknown") for x in registry_rows))
    report: dict[str, Any] = {
        "generated_at": _now_utc(),
        "version": "downstream_export_v1",
        "contract_version": "1.0.0",
        "dataset": {
            "documents_total": len(registry_rows),
            "doc_type_counts": doc_type_counts,
        },
        "quality": {
            "overall_status": _overall_quality_status(q_status, bq_status, sc_status),
            "quality_gates_status": q_status,
            "body_snapshot_quality_gates_status": bq_status,
            "selfcheck_status": sc_status,
        },
        "facts": {
            "fact_layer_summary": fact_summary,
            "body_snapshot_summary": body_summary,
            "open_fact_review_queue_total": len(queue),
            "open_fact_review_by_collection": queue_counts,
        },
        "analytics": {
            "graph_included": include_graph,
            "filters": (graph_payload or {}).get("filters"),
            "counts": (graph_payload or {}).get("counts"),
            "graph": (graph_payload or {}).get("graph"),
        },
        "sources": {
            "registry_path": str(registry_path).replace("\\", "/"),
            "fact_summary_path": str(fact_summary_path).replace("\\", "/"),
            "body_summary_path": str(body_summary_path).replace("\\", "/"),
            "quality_gates_report_path": str(q_path).replace("\\", "/") if q_path else None,
            "body_snapshot_quality_report_path": str(bq_path).replace("\\", "/") if bq_path else None,
            "selfcheck_report_path": str(sc_path).replace("\\", "/") if sc_path else None,
        },
    }

    if write_report:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = reports_dir / f"downstream_export_v1_{ts}.json"
        latest_path = reports_dir / "downstream_export_v1_latest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(report, ensure_ascii=False, indent=2)
        out_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")
        report["report_path"] = str(out_path).replace("\\", "/")
        report["latest_path"] = str(latest_path).replace("\\", "/")

        _append_audit(
            data_root / "audit/logs/batch_01_agent.ndjson",
            {
                "ts": _now_utc(),
                "event": "downstream_export_built_v1",
                "report_path": report["report_path"],
                "include_graph": include_graph,
                "quality_overall_status": report["quality"]["overall_status"],
            },
        )

    return report

