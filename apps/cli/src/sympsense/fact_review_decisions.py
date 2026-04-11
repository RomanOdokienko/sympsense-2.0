from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECISIONS_REL = "data/canonical/facts/fact_review_decisions_v1.ndjson"
AUDIT_REL = "data/audit/logs/batch_01_agent.ndjson"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_ndjson(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_latest_decisions(project_root: Path) -> dict[str, dict[str, Any]]:
    decisions_path = project_root.resolve() / DECISIONS_REL
    out: dict[str, dict[str, Any]] = {}
    for row in _load_ndjson(decisions_path):
        queue_id = str(row.get("queue_id") or "").strip()
        if not queue_id:
            continue
        out[queue_id] = row
    return out


def add_decision(
    project_root: Path,
    *,
    queue_id: str,
    action: str,
    note: str = "",
    actor: str = "user",
) -> dict[str, Any]:
    action_norm = str(action or "").strip().lower()
    if action_norm not in {"resolved", "skipped", "reopened"}:
        raise ValueError("action must be one of: resolved, skipped, reopened")
    queue_id_norm = str(queue_id or "").strip()
    if not queue_id_norm:
        raise ValueError("queue_id is required")

    decisions_path = project_root.resolve() / DECISIONS_REL
    audit_path = project_root.resolve() / AUDIT_REL

    row = {
        "ts": _now_utc(),
        "queue_id": queue_id_norm,
        "action": action_norm,
        "note": str(note or "").strip(),
        "actor": str(actor or "user").strip() or "user",
    }
    _append_ndjson(decisions_path, row)
    _append_ndjson(
        audit_path,
        {
            "ts": row["ts"],
            "event": "fact_review_decision_added_v1",
            "queue_id": queue_id_norm,
            "action": action_norm,
            "actor": row["actor"],
        },
    )
    return row

