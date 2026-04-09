from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reports import build_documents_review_ui_v2 as ui_builder


REGISTRY_JSON = ROOT / "data/canonical/documents/batch_01_registry_active.json"
REGISTRY_NDJSON = ROOT / "data/canonical/documents/batch_01_registry_active.ndjson"
REPORTS_DIR = ROOT / "data/derived/reports"
DOCTOR_DIR = ROOT / "data/canonical/doctor_conclusions"
RECS_DIR = ROOT / "data/canonical/recommendations"
LABS_DIR = ROOT / "data/canonical/labs"
UI_FILE = ROOT / "data/derived/reports/ui_documents_registry.html"
BUNDLE_FILE = ROOT / "data/derived/reports/ui_documents_registry_data.json"
AUDIT_LOG = ROOT / "data/audit/logs/batch_01_agent.ndjson"


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


def append_audit(row: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_doc_match(record: dict[str, Any], doc_id: str) -> bool:
    src = record.get("source") or {}
    current = str(record.get("doc_id") or src.get("document_id") or "").strip()
    return current == doc_id


def files_for_doc(doc_id: str, registry_row: dict[str, Any]) -> list[Path]:
    files: list[Path] = []

    source_rel = str((registry_row.get("source") or {}).get("relative_path") or "").strip()
    if source_rel:
        src_path = (ROOT / source_rel).resolve()
        if src_path.exists():
            files.append(src_path)

    for p in REPORTS_DIR.glob("full_extraction_*.json"):
        try:
            j = load_json(p)
        except Exception:
            continue
        if str(j.get("doc_id") or "").strip() == doc_id:
            files.append(p.resolve())

    for directory in [DOCTOR_DIR, RECS_DIR, LABS_DIR]:
        for p in directory.glob("*.json"):
            try:
                j = load_json(p)
            except Exception:
                continue
            if is_doc_match(j, doc_id):
                files.append(p.resolve())

    # Deduplicate while preserving order
    out: list[Path] = []
    seen: set[str] = set()
    for p in files:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def delete_document(doc_id: str) -> dict[str, Any]:
    registry = load_json(REGISTRY_JSON)
    if not isinstance(registry, list):
        raise RuntimeError("Registry has unexpected format.")

    target = next((r for r in registry if str(r.get("id") or "").strip() == doc_id), None)
    if not target:
        raise FileNotFoundError(f"doc_id not found: {doc_id}")

    files = files_for_doc(doc_id=doc_id, registry_row=target)
    deleted_paths: list[str] = []
    for p in files:
        if p.exists() and p.is_file():
            p.unlink()
            deleted_paths.append(str(p))

    new_registry = [r for r in registry if str(r.get("id") or "").strip() != doc_id]
    save_json(REGISTRY_JSON, new_registry)
    save_ndjson(REGISTRY_NDJSON, new_registry)
    ui_builder.build()

    append_audit(
        {
            "ts": now_utc(),
            "event": "document_deleted_from_ui",
            "doc_id": doc_id,
            "file_name": target.get("file_name"),
            "deleted_paths": [p.replace("\\", "/") for p in deleted_paths],
            "active_registry_records": len(new_registry),
            "bundle": str(BUNDLE_FILE).replace("\\", "/"),
        }
    )

    return {
        "ok": True,
        "doc_id": doc_id,
        "deleted_paths": [p.replace("\\", "/") for p in deleted_paths],
        "active_registry_records": len(new_registry),
        "bundle": str(BUNDLE_FILE).replace("\\", "/"),
    }


class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, status: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._set_headers(status, "application/json; charset=utf-8")
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers(HTTPStatus.NO_CONTENT, "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/delete":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON"})
                return

            doc_id = str(payload.get("doc_id") or "").strip()
            if not doc_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "doc_id is required"})
                return

            try:
                result = delete_document(doc_id=doc_id)
            except FileNotFoundError as e:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(e)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if parsed.path == "/api/rebuild":
            ui_builder.build()
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "ui": str(UI_FILE).replace("\\", "/"),
                    "bundle": str(BUNDLE_FILE).replace("\\", "/"),
                    "rebuilt_at": now_utc(),
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/ui"}:
            if not UI_FILE.exists():
                ui_builder.build()
            html_text = UI_FILE.read_text(encoding="utf-8")
            self._set_headers(HTTPStatus.OK, "text/html; charset=utf-8")
            self.wfile.write(html_text.encode("utf-8"))
            return

        if parsed.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "ui": str(UI_FILE).replace("\\", "/"),
                    "registry": str(REGISTRY_JSON).replace("\\", "/"),
                    "bundle": str(BUNDLE_FILE).replace("\\", "/"),
                },
            )
            return

        if parsed.path == "/api/file":
            query = parse_qs(parsed.query or "")
            rel = str((query.get("rel") or [""])[0]).strip()
            if not rel:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "rel is required"})
                return
            try:
                candidate = (ROOT / rel).resolve()
                root_resolved = ROOT.resolve()
                candidate.relative_to(root_resolved)
            except Exception:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid rel path"})
                return
            if not candidate.exists() or not candidate.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "File not found"})
                return

            ctype, _ = mimetypes.guess_type(str(candidate))
            if not ctype:
                ctype = "application/octet-stream"
            self._set_headers(HTTPStatus.OK, f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype)
            self.wfile.write(candidate.read_bytes())
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Documents Review UI server with delete API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    ui_builder.build()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
