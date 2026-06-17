from __future__ import annotations

import json
import mimetypes
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from sympsense.analytics_graph import build_body_graph
from sympsense.downstream_export import build_downstream_export
from sympsense.fact_review_decisions import add_decision
from sympsense.fact_review_queue import build_fact_review_queue
from sympsense.longevity_overview import build_longevity_overview
from sympsense.patient_briefing import build_patient_briefing
from sympsense.problem_list import build_problem_list
from sympsense.review_admin import delete_document
from sympsense.review_bundle import build_review_detail, build_review_rows
from sympsense.selfcheck import run_selfcheck


DOC_REGISTRY_REL = "canonical/documents/batch_01_registry_active.json"
FACT_SUMMARY_REL = "canonical/facts/fact_layer_v1_summary.json"
BODY_SUMMARY_REL = "canonical/facts/body_snapshot_v1_summary.json"
BODY_SNAPSHOT_REL = "canonical/facts/body_snapshot_v1.json"
BODY_PREVIEW_REL = "derived/reports/body_snapshot_v1_preview.json"

FACT_COLLECTION_PATHS: dict[str, str] = {
    "lab_results": "canonical/facts/lab_results_v1.ndjson",
    "clinical_findings": "canonical/facts/clinical_findings_v1.ndjson",
    "recommendation_items": "canonical/facts/recommendation_items_v1.ndjson",
    "medication_items": "canonical/facts/medication_items_v1.ndjson",
    "condition_mentions": "canonical/facts/condition_mentions_v1.ndjson",
    "condition_clusters": "canonical/facts/condition_clusters_v1.ndjson",
    "investigation_events": "canonical/facts/investigation_events_v1.ndjson",
    "condition_investigation_links": "canonical/facts/condition_investigation_links_v1.ndjson",
}


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "AGENTS.md").exists() and (candidate / "data").exists():
            return candidate
    return start


def _resolve_data_root() -> Path:
    override = os.getenv("SYMPSENSE_DATA_ROOT", "").strip()
    if override:
        return Path(override)
    root = _find_project_root(Path.cwd().resolve())
    return root / "data"


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


def _read_if_exists_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _load_json(path)


def _latest_report(reports_dir: Path, prefix: str) -> dict[str, Any] | None:
    candidates = sorted(
        (
            p
            for p in reports_dir.glob(f"{prefix}*.json")
            if p.is_file()
        ),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    report_path = candidates[-1]
    payload = _read_if_exists_json(report_path) or {}
    return {
        "path": str(report_path).replace("\\", "/"),
        "generated_at": payload.get("generated_at"),
        "status": payload.get("status"),
        "version": payload.get("version"),
    }


def _latest_quality_report_details(reports_dir: Path, prefix: str) -> dict[str, Any] | None:
    candidates = sorted(
        (p for p in reports_dir.glob(f"{prefix}*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    report_path = candidates[-1]
    payload = _read_if_exists_json(report_path) or {}
    failed_gates = payload.get("failed_gates") or []
    regression_failures = ((payload.get("regression") or {}).get("failures") or [])
    status = payload.get("status")
    if not status:
        gate_statuses = [
            str((gate_payload or {}).get("status") or "").strip().lower()
            for gate_payload in ((payload.get("gates") or {}).values())
        ]
        gate_statuses = [s for s in gate_statuses if s]
        if gate_statuses:
            if any(s == "fail" for s in gate_statuses):
                status = "fail"
            elif all(s == "pass" for s in gate_statuses):
                status = "pass"
            else:
                status = "unknown"
        else:
            status = "unknown"
    return {
        "path": str(report_path).replace("\\", "/"),
        "generated_at": payload.get("generated_at"),
        "status": status,
        "version": payload.get("version"),
        "failed_gates_count": len(failed_gates),
        "failed_regression_checks_count": len(regression_failures),
        "failed_gates": failed_gates[:20],
    }


def _latest_report_path(reports_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(
        (p for p in reports_dir.glob(f"{prefix}*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    return candidates[-1]


def _fact_rows_for_doc(
    data_root: Path,
    doc_id: str,
    limit_per_collection: int,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for collection, rel_path in FACT_COLLECTION_PATHS.items():
        path = data_root / rel_path
        rows = _load_ndjson(path)
        matched = [
            row
            for row in rows
            if str(row.get("doc_id") or row.get("condition_doc_id") or row.get("investigation_doc_id") or "") == doc_id
        ]
        if matched:
            out[collection] = matched[:limit_per_collection]
    return out


def create_app(data_root: Path | None = None) -> FastAPI:
    resolved_data_root = (data_root or _resolve_data_root()).resolve()
    app = FastAPI(
        title="Sympsense Local API",
        version="0.1.0",
        description="Read-only API over local canonical/facts JSON storage.",
    )
    app.state.data_root = resolved_data_root
    app.state.project_root = resolved_data_root.parent.resolve()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def rebuild_ui() -> dict[str, Any]:
        ui_path = app.state.project_root / "data/derived/reports/ui_documents_registry.html"
        bundle_path = app.state.project_root / "data/derived/reports/ui_documents_registry_data.json"
        try:
            from scripts.reports import build_documents_review_ui_v2 as ui_builder
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"UI builder import failed: {exc}") from exc
        ui_builder.build()
        return {
            "ok": True,
            "ui": str(ui_path).replace("\\", "/"),
            "bundle": str(bundle_path).replace("\\", "/"),
            "rebuilt_at": datetime.now(timezone.utc).isoformat(),
        }

    def rebuild_longevity_page() -> dict[str, Any]:
        html_path = app.state.project_root / "data/derived/reports/longevity_v1.html"
        try:
            from scripts.reports import build_longevity_v1 as longevity_builder
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Longevity builder import failed: {exc}") from exc
        out_path = longevity_builder.build(project_root=app.state.project_root)
        return {
            "ok": True,
            "html": str(out_path or html_path).replace("\\", "/"),
            "rebuilt_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        checks = {
            "registry": (data_root_value / DOC_REGISTRY_REL).exists(),
            "fact_summary": (data_root_value / FACT_SUMMARY_REL).exists(),
            "body_summary": (data_root_value / BODY_SUMMARY_REL).exists(),
        }
        status = "ok" if all(checks.values()) else "degraded"
        return {
            "status": status,
            "ts": datetime.now(timezone.utc).isoformat(),
            "data_root": str(data_root_value).replace("\\", "/"),
            "checks": checks,
        }

    @app.get("/")
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui", status_code=307)

    @app.get("/ui")
    def ui_page() -> FileResponse:
        project_root: Path = app.state.project_root
        ui_path = project_root / "data/derived/reports/ui_documents_registry.html"
        if not ui_path.exists():
            rebuild_ui()
        return FileResponse(ui_path, media_type="text/html; charset=utf-8")

    @app.get("/longevity")
    def longevity_page() -> FileResponse:
        project_root: Path = app.state.project_root
        html_path = project_root / "data/derived/reports/longevity_v1.html"
        if not html_path.exists():
            rebuild_longevity_page()
        return FileResponse(html_path, media_type="text/html; charset=utf-8")

    @app.get("/longevity/checklist")
    def longevity_checklist_page() -> FileResponse:
        project_root: Path = app.state.project_root
        html_path = project_root / "data/derived/reports/longevity_checklist_v1.html"
        return FileResponse(html_path, media_type="text/html; charset=utf-8")

    @app.get("/api/health")
    def ui_health() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        ui_path = project_root / "data/derived/reports/ui_documents_registry.html"
        registry_path = project_root / "data/canonical/documents/batch_01_registry_active.json"
        bundle_path = project_root / "data/derived/reports/ui_documents_registry_data.json"
        return {
            "ok": True,
            "ui": str(ui_path).replace("\\", "/"),
            "registry": str(registry_path).replace("\\", "/"),
            "bundle": str(bundle_path).replace("\\", "/"),
        }

    @app.get("/api/file")
    def api_file(rel: str = Query(..., description="Project-relative file path.")) -> FileResponse:
        project_root: Path = app.state.project_root
        rel_clean = rel.strip()
        if not rel_clean:
            raise HTTPException(status_code=400, detail="rel is required")
        try:
            candidate = (project_root / rel_clean).resolve()
            candidate.relative_to(project_root.resolve())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid rel path") from None
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        media_type, _ = mimetypes.guess_type(str(candidate))
        return FileResponse(candidate, media_type=media_type or "application/octet-stream")

    @app.post("/api/delete")
    def api_delete(payload: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(payload.get("doc_id") or "").strip()
        if not doc_id:
            raise HTTPException(status_code=400, detail="doc_id is required")
        project_root: Path = app.state.project_root
        try:
            result = delete_document(project_root=project_root, doc_id=doc_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return result

    @app.post("/api/rebuild")
    def api_rebuild() -> dict[str, Any]:
        try:
            return rebuild_ui()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/overview")
    def overview() -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        registry_path = data_root_value / DOC_REGISTRY_REL
        if not registry_path.exists():
            raise HTTPException(status_code=404, detail="Active registry not found.")

        registry_rows = _load_json(registry_path)
        doc_type_counts = Counter(str(x.get("doc_type") or "unknown") for x in registry_rows)
        parse_mode_counts = Counter(str(x.get("parse_mode") or "unknown") for x in registry_rows)

        fact_summary = _read_if_exists_json(data_root_value / FACT_SUMMARY_REL)
        body_summary = _read_if_exists_json(data_root_value / BODY_SUMMARY_REL)
        reports_dir = data_root_value / "derived" / "reports"
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "documents": len(registry_rows),
                "doc_type_counts": dict(doc_type_counts),
                "parse_mode_counts": dict(parse_mode_counts),
            },
            "summaries": {
                "fact_layer": fact_summary,
                "body_snapshot": body_summary,
            },
            "latest_quality_reports": {
                "quality_gates_v1": _latest_report(reports_dir, "quality_gates_v1_"),
                "body_snapshot_quality_gates_v1": _latest_report(reports_dir, "body_snapshot_quality_gates_v1_"),
            },
        }

    @app.get("/v1/quality/latest")
    def latest_quality() -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        reports_dir = data_root_value / "derived" / "reports"
        base = _latest_quality_report_details(reports_dir, "quality_gates_v1_")
        body = _latest_quality_report_details(reports_dir, "body_snapshot_quality_gates_v1_")

        statuses = [x.get("status") for x in [base, body] if x]
        if not statuses:
            overall = "unknown"
        elif any(s == "fail" for s in statuses):
            overall = "fail"
        elif all(s == "pass" for s in statuses):
            overall = "pass"
        else:
            overall = "unknown"

        total_failed_gates = sum(int((x or {}).get("failed_gates_count") or 0) for x in [base, body])
        total_failed_regression = sum(
            int((x or {}).get("failed_regression_checks_count") or 0) for x in [base, body]
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall,
            "reports": {
                "quality_gates_v1": base,
                "body_snapshot_quality_gates_v1": body,
            },
            "totals": {
                "failed_gates_count": total_failed_gates,
                "failed_regression_checks_count": total_failed_regression,
            },
        }

    @app.get("/v1/selfcheck/latest")
    def selfcheck_latest() -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        reports_dir = data_root_value / "derived" / "reports"
        path = _latest_report_path(reports_dir, "system_selfcheck_v1_")
        if not path:
            raise HTTPException(status_code=404, detail="No selfcheck report found.")
        payload = _read_if_exists_json(path)
        if payload is None:
            raise HTTPException(status_code=500, detail="Failed to read latest selfcheck report.")
        return {
            "path": str(path).replace("\\", "/"),
            "report": payload,
        }

    @app.post("/v1/selfcheck/run")
    def selfcheck_run() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        return run_selfcheck(project_root=project_root, write_report=True)

    @app.get("/v1/documents")
    def list_documents(
        q: str = Query(default="", description="Search over id/file_name/source path."),
        doc_type: str = Query(default="", description="Filter by doc_type."),
        parse_mode: str = Query(default="", description="Filter by parse_mode."),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        registry_path = data_root_value / DOC_REGISTRY_REL
        if not registry_path.exists():
            raise HTTPException(status_code=404, detail="Active registry not found.")

        rows: list[dict[str, Any]] = _load_json(registry_path)
        qn = q.strip().lower()
        dtype = doc_type.strip().lower()
        pmode = parse_mode.strip().lower()

        filtered: list[dict[str, Any]] = []
        for row in rows:
            if dtype and str(row.get("doc_type") or "").strip().lower() != dtype:
                continue
            if pmode and str(row.get("parse_mode") or "").strip().lower() != pmode:
                continue
            if qn:
                hay = " ".join(
                    [
                        str(row.get("id") or ""),
                        str(row.get("file_name") or ""),
                        str((row.get("source") or {}).get("relative_path") or ""),
                    ]
                ).lower()
                if qn not in hay:
                    continue
            filtered.append(row)

        items = filtered[offset : offset + limit]
        return {
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "items": items,
        }

    @app.get("/v1/review/documents")
    def list_review_documents(
        q: str = Query(default="", description="Search over id/file_name/source path."),
        doc_type: str = Query(default="", description="Filter by doc_type."),
        quality_status: str = Query(default="", description="Filter by quality_status: complete|incomplete|review."),
        review_state: str = Query(default="", description="Filter by review_state: needs_review|ok."),
        sort_by: str = Query(default="idx", description="One of: idx,event_date_raw,doc_type,text_len."),
        limit: int = Query(default=500, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        project_root: Path = app.state.project_root
        payload = build_review_rows(project_root)
        rows: list[dict[str, Any]] = payload.get("rows", [])

        qn = q.strip().lower()
        dtype = doc_type.strip().lower()
        qstate = quality_status.strip().lower()
        rstate = review_state.strip().lower()

        filtered: list[dict[str, Any]] = []
        for row in rows:
            if dtype and str(row.get("doc_type") or "").strip().lower() != dtype:
                continue
            if qstate and str(row.get("quality_status") or "").strip().lower() != qstate:
                continue
            if rstate:
                needs_review = bool(row.get("review_required"))
                if rstate == "needs_review" and not needs_review:
                    continue
                if rstate == "ok" and needs_review:
                    continue
            if qn:
                hay = " ".join(
                    [
                        str(row.get("doc_id") or ""),
                        str(row.get("file_name") or ""),
                        str(row.get("source_rel") or ""),
                        str(row.get("doc_type") or ""),
                        str(row.get("search_blob") or ""),
                    ]
                ).lower()
                if qn not in hay:
                    continue
            filtered.append(row)

        if sort_by != "idx":
            def sort_value(rec: dict[str, Any]) -> str:
                value = rec.get(sort_by)
                if value is None:
                    return ""
                return str(value)

            filtered.sort(key=sort_value)

        items = filtered[offset : offset + limit]
        return {
            "generated_at": payload.get("generated_at"),
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "items": items,
            "totals": {
                "all_rows": len(rows),
                "complete": sum(1 for x in rows if str(x.get("quality_status")) == "complete"),
                "incomplete": sum(1 for x in rows if str(x.get("quality_status")) == "incomplete"),
                "review": sum(1 for x in rows if str(x.get("quality_status")) == "review"),
                "needs_review": sum(1 for x in rows if bool(x.get("review_required"))),
            },
        }

    @app.get("/v1/review/documents/{doc_id}")
    def get_review_document(doc_id: str) -> dict[str, Any]:
        project_root: Path = app.state.project_root
        payload = build_review_detail(project_root, doc_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
        return payload

    @app.get("/v1/review/fact-queue")
    def review_fact_queue(
        include_medications: bool = Query(default=False),
        include_ok: bool = Query(default=False),
        include_resolved: bool = Query(default=False),
        collections: str = Query(default="", description="Comma-separated collections."),
        review_state: str = Query(default="all", description="all|open|resolved|skipped"),
        doc_id: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=2000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        project_root: Path = app.state.project_root
        selected_collections = {
            x.strip().lower()
            for x in collections.split(",")
            if x.strip()
        }
        allowed_collections = {
            "lab_results",
            "clinical_findings",
            "condition_mentions",
            "condition_investigation_links",
            "recommendation_items",
            "medication_items",
        }
        unknown_collections = sorted(selected_collections - allowed_collections)
        if unknown_collections:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown collections: {', '.join(unknown_collections)}",
            )
        review_state_norm = review_state.strip().lower() or "all"
        if review_state_norm not in {"all", "open", "resolved", "skipped"}:
            raise HTTPException(status_code=400, detail="review_state must be one of: all, open, resolved, skipped")

        full_queue = build_fact_review_queue(
            project_root=project_root,
            include_medications=include_medications,
            include_ok=include_ok,
            include_resolved=True,
            collections_filter=selected_collections if selected_collections else None,
            review_state_filter="all",
            doc_id=doc_id,
        )
        queue = build_fact_review_queue(
            project_root=project_root,
            include_medications=include_medications,
            include_ok=include_ok,
            include_resolved=include_resolved,
            collections_filter=selected_collections if selected_collections else None,
            review_state_filter=review_state_norm,
            doc_id=doc_id,
        )
        items = queue[offset : offset + limit]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(queue),
            "offset": offset,
            "limit": limit,
            "items": items,
            "counts_by_collection": dict(Counter(str(x.get("fact_collection") or "") for x in queue)),
            "counts_by_review_state": dict(Counter(str(x.get("review_state") or "open") for x in full_queue)),
            "filters": {
                "include_medications": include_medications,
                "include_ok": include_ok,
                "include_resolved": include_resolved,
                "collections": sorted(selected_collections),
                "review_state": review_state_norm,
                "doc_id": doc_id,
            },
        }

    @app.post("/v1/review/fact-queue/decision")
    def review_fact_queue_decision(payload: dict[str, Any]) -> dict[str, Any]:
        queue_id = str(payload.get("queue_id") or "").strip()
        action = str(payload.get("action") or "").strip().lower()
        note = str(payload.get("note") or "").strip()
        actor = str(payload.get("actor") or "user").strip() or "user"
        if not queue_id:
            raise HTTPException(status_code=400, detail="queue_id is required")
        if action not in {"resolved", "skipped", "reopened"}:
            raise HTTPException(status_code=400, detail="action must be one of: resolved, skipped, reopened")
        project_root: Path = app.state.project_root
        try:
            decision = add_decision(
                project_root=project_root,
                queue_id=queue_id,
                action=action,
                note=note,
                actor=actor,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"ok": True, "decision": decision}

    @app.get("/v1/documents/{doc_id}")
    def get_document(
        doc_id: str,
        include_related_facts: bool = Query(default=True),
        limit_per_collection: int = Query(default=30, ge=1, le=200),
    ) -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        registry_path = data_root_value / DOC_REGISTRY_REL
        if not registry_path.exists():
            raise HTTPException(status_code=404, detail="Active registry not found.")

        rows: list[dict[str, Any]] = _load_json(registry_path)
        target = next((x for x in rows if str(x.get("id") or "") == doc_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        related: dict[str, list[dict[str, Any]]] = {}
        if include_related_facts:
            related = _fact_rows_for_doc(data_root_value, doc_id, limit_per_collection)

        related_counts = {key: len(value) for key, value in related.items()}
        return {
            "document": target,
            "related_fact_counts": related_counts,
            "related_facts": related,
        }

    @app.get("/v1/facts/{collection}")
    def list_facts(
        collection: Literal[
            "lab_results",
            "clinical_findings",
            "recommendation_items",
            "medication_items",
            "condition_mentions",
            "condition_clusters",
            "investigation_events",
            "condition_investigation_links",
        ],
        doc_id: str = Query(default="", description="Optional filter by doc_id."),
        qa_status: str = Query(default="", description="Optional filter by qa_status."),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        path = data_root_value / FACT_COLLECTION_PATHS[collection]
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found.")

        rows = _load_ndjson(path)
        doc_filter = doc_id.strip()
        qa_filter = qa_status.strip().lower()

        filtered: list[dict[str, Any]] = []
        for row in rows:
            row_doc = str(row.get("doc_id") or row.get("condition_doc_id") or "")
            row_qa = str(row.get("qa_status") or "").lower()
            if doc_filter and row_doc != doc_filter:
                continue
            if qa_filter and row_qa != qa_filter:
                continue
            filtered.append(row)

        items = filtered[offset : offset + limit]
        return {
            "collection": collection,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "items": items,
        }

    @app.get("/v1/body-snapshot")
    def body_snapshot(include_full: bool = Query(default=False)) -> dict[str, Any]:
        data_root_value: Path = app.state.data_root
        summary = _read_if_exists_json(data_root_value / BODY_SUMMARY_REL)
        if summary is None:
            raise HTTPException(status_code=404, detail="body_snapshot summary not found.")

        response: dict[str, Any] = {"summary": summary}
        if include_full:
            snapshot = _read_if_exists_json(data_root_value / BODY_SNAPSHOT_REL)
            if snapshot is None:
                raise HTTPException(status_code=404, detail="body_snapshot full payload not found.")
            response["snapshot"] = snapshot
        else:
            preview = _read_if_exists_json(data_root_value / BODY_PREVIEW_REL)
            if preview is not None:
                response["preview"] = preview
        return response

    @app.get("/v1/analytics/body-graph")
    def analytics_body_graph(
        include_needs_review: bool = Query(default=False),
        min_link_confidence: float = Query(default=0.62, ge=0.0, le=1.0),
        link_priorities: str = Query(default="high,medium"),
        include_document_nodes: bool = Query(default=True),
        include_orphans: bool = Query(default=False),
    ) -> dict[str, Any]:
        priorities = {
            x.strip().lower()
            for x in link_priorities.split(",")
            if x.strip()
        }
        allowed = {"high", "medium", "low"}
        if not priorities:
            priorities = {"high", "medium"}
        unknown = sorted(priorities - allowed)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown link priorities: {', '.join(unknown)}",
            )
        project_root: Path = app.state.project_root
        try:
            return build_body_graph(
                project_root=project_root,
                include_needs_review=include_needs_review,
                min_link_confidence=min_link_confidence,
                allowed_link_priorities=priorities,
                include_document_nodes=include_document_nodes,
                include_orphans=include_orphans,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/export/downstream-v1")
    def export_downstream_v1(
        include_graph: bool = Query(default=False),
    ) -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_downstream_export(
                project_root=project_root,
                include_graph=include_graph,
                write_report=False,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/export/downstream-v1/build")
    def build_export_downstream_v1(
        include_graph: bool = Query(default=False),
    ) -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_downstream_export(
                project_root=project_root,
                include_graph=include_graph,
                write_report=True,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/reports/patient-briefing/v1")
    def get_patient_briefing_v1() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_patient_briefing(
                project_root=project_root,
                write_report=False,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/reports/patient-briefing/v1/build")
    def build_patient_briefing_v1() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_patient_briefing(
                project_root=project_root,
                write_report=True,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/reports/analyst-findings/latest")
    def get_analyst_findings_latest() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        reports_dir = project_root / "data" / "derived" / "reports"
        files = sorted(reports_dir.glob("analyst_findings_*.json"), reverse=True)
        if not files:
            raise HTTPException(status_code=404, detail="No analyst findings reports found")
        try:
            import json
            return json.loads(files[0].read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/facts/problem-list/v1")
    def get_problem_list_v1() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_problem_list(
                project_root=project_root,
                write_report=False,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/facts/problem-list/v1/build")
    def build_problem_list_v1() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_problem_list(
                project_root=project_root,
                write_report=True,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/longevity/overview")
    def get_longevity_overview() -> dict[str, Any]:
        project_root: Path = app.state.project_root
        try:
            return build_longevity_overview(
                project_root=project_root,
                write_report=False,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/longevity/horsemen")
    def get_longevity_horsemen() -> dict[str, Any]:
        payload = get_longevity_overview()
        return {
            "generated_at": payload.get("generated_at"),
            "version": payload.get("version"),
            "horsemen": payload.get("horsemen") or {},
        }

    @app.get("/v1/longevity/baselines")
    def get_longevity_baselines() -> dict[str, Any]:
        payload = get_longevity_overview()
        return {
            "generated_at": payload.get("generated_at"),
            "items": payload.get("baseline_measurements") or [],
            "physical_baselines": payload.get("physical_baselines") or [],
        }

    @app.get("/v1/longevity/protocols")
    def get_longevity_protocols() -> dict[str, Any]:
        payload = get_longevity_overview()
        return {
            "generated_at": payload.get("generated_at"),
            "items": payload.get("protocols") or [],
        }

    @app.get("/v1/longevity/gaps")
    def get_longevity_gaps() -> dict[str, Any]:
        payload = get_longevity_overview()
        return {
            "generated_at": payload.get("generated_at"),
            "items": payload.get("gaps") or [],
        }

    @app.get("/v1/longevity/screening-calendar")
    def get_longevity_screening_calendar() -> dict[str, Any]:
        payload = get_longevity_overview()
        return {
            "generated_at": payload.get("generated_at"),
            "items": payload.get("screening_calendar") or [],
        }

    return app


app = create_app()
