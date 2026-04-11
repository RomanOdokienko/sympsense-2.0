from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def append_audit(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_rebuild_pipeline(project_root: Path) -> dict[str, Any]:
    steps = [
        "scripts/facts/build_fact_layer_v1.py",
        "scripts/facts/build_body_snapshot_v1.py",
        "scripts/facts/build_problem_list_v1.py",
        "scripts/reports/build_documents_review_ui_v2.py",
    ]
    results: list[dict[str, Any]] = []
    ok = True
    for rel in steps:
        script = (project_root / rel).resolve()
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        results.append(
            {
                "script": rel,
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "").strip()[-800:],
                "stderr_tail": (proc.stderr or "").strip()[-800:],
            }
        )
        if proc.returncode != 0:
            ok = False
            break
    return {"ok": ok, "steps": results}


def is_doc_match(record: dict[str, Any], doc_id: str) -> bool:
    src = record.get("source") or {}
    current = str(record.get("doc_id") or src.get("document_id") or "").strip()
    return current == doc_id


def files_for_doc(
    project_root: Path,
    doc_id: str,
    registry_row: dict[str, Any],
    reports_dir: Path,
    doctor_dir: Path,
    recommendations_dir: Path,
    labs_dir: Path,
) -> list[Path]:
    files: list[Path] = []

    source_rel = str((registry_row.get("source") or {}).get("relative_path") or "").strip()
    if source_rel:
        src_path = (project_root / source_rel).resolve()
        if src_path.exists():
            files.append(src_path)

    for p in reports_dir.glob("full_extraction_*.json"):
        try:
            payload = load_json(p)
        except Exception:
            continue
        if str(payload.get("doc_id") or "").strip() == doc_id:
            files.append(p.resolve())

    for directory in [doctor_dir, recommendations_dir, labs_dir]:
        for p in directory.glob("*.json"):
            try:
                payload = load_json(p)
            except Exception:
                continue
            if is_doc_match(payload, doc_id):
                files.append(p.resolve())

    out: list[Path] = []
    seen: set[str] = set()
    for p in files:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def delete_document(project_root: Path, doc_id: str) -> dict[str, Any]:
    registry_json = project_root / "data/canonical/documents/batch_01_registry_active.json"
    registry_ndjson = project_root / "data/canonical/documents/batch_01_registry_active.ndjson"
    reports_dir = project_root / "data/derived/reports"
    doctor_dir = project_root / "data/canonical/doctor_conclusions"
    recommendations_dir = project_root / "data/canonical/recommendations"
    labs_dir = project_root / "data/canonical/labs"
    audit_log = project_root / "data/audit/logs/batch_01_agent.ndjson"
    bundle_file = project_root / "data/derived/reports/ui_documents_registry_data.json"

    registry = load_json(registry_json)
    if not isinstance(registry, list):
        raise RuntimeError("Registry has unexpected format.")

    target = next((r for r in registry if str(r.get("id") or "").strip() == doc_id), None)
    if not target:
        raise FileNotFoundError(f"doc_id not found: {doc_id}")

    files = files_for_doc(
        project_root=project_root,
        doc_id=doc_id,
        registry_row=target,
        reports_dir=reports_dir,
        doctor_dir=doctor_dir,
        recommendations_dir=recommendations_dir,
        labs_dir=labs_dir,
    )
    deleted_paths: list[str] = []
    for p in files:
        if p.exists() and p.is_file():
            p.unlink()
            deleted_paths.append(str(p))

    new_registry = [r for r in registry if str(r.get("id") or "").strip() != doc_id]
    save_json(registry_json, new_registry)
    save_ndjson(registry_ndjson, new_registry)

    rebuild = run_rebuild_pipeline(project_root=project_root)

    append_audit(
        audit_log,
        {
            "ts": now_utc(),
            "event": "document_deleted_from_ui",
            "doc_id": doc_id,
            "file_name": target.get("file_name"),
            "deleted_paths": [p.replace("\\", "/") for p in deleted_paths],
            "active_registry_records": len(new_registry),
            "bundle": str(bundle_file).replace("\\", "/"),
            "rebuild_ok": bool(rebuild.get("ok")),
        },
    )

    return {
        "ok": True,
        "doc_id": doc_id,
        "deleted_paths": [p.replace("\\", "/") for p in deleted_paths],
        "active_registry_records": len(new_registry),
        "bundle": str(bundle_file).replace("\\", "/"),
        "rebuild": rebuild,
    }
