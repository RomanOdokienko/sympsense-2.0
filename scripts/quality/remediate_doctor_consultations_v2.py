from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.quality.process_round9_batch_v1 as parser
import scripts.quality.run_quality_gates_v1 as qg


@dataclass
class Ctx:
    registry_path: Path
    reports_dir: Path
    doctor_dir: Path
    rec_dir: Path
    quality_cfg_path: Path
    audit_file: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def find_full_extraction_by_doc_id(reports_dir: Path, doc_id: str) -> Path | None:
    for p in reports_dir.glob("full_extraction_*.json"):
        try:
            j = load_json(p)
        except Exception:
            continue
        if str(j.get("doc_id") or "").strip() == doc_id:
            return p
    return None


def should_remediate(
    current_fe: dict[str, Any],
    current_dc: dict[str, Any] | None,
    parsed_visit_type: str | None,
    parsed_conclusion: str,
    parsed_diagnosis: str | None,
    parsed_recommendation: str | None,
    mojibake_cfg: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    raw = str(current_fe.get("raw_text_excerpt") or "")
    if qg.looks_like_mojibake(raw, mojibake_cfg):
        reasons.append("mojibake_raw_text")

    cur_dc = current_dc or {}
    cur_conclusion = str(cur_dc.get("conclusion_text") or "").strip()
    cur_diagnosis = str(cur_dc.get("diagnosis_text") or "").strip()
    cur_visit_type = str((current_fe.get("summary") or {}).get("visit_type") or "").strip()
    cur_recommendation = str((current_fe.get("summary") or {}).get("recommendation") or "").strip()

    if len(cur_conclusion) < 40 and len((parsed_conclusion or "").strip()) >= 80:
        reasons.append("short_conclusion")
    if not cur_diagnosis and parsed_diagnosis:
        reasons.append("missing_diagnosis")
    if not cur_visit_type and parsed_visit_type:
        reasons.append("missing_visit_type")
    if not cur_recommendation and parsed_recommendation:
        reasons.append("missing_recommendation")

    return (len(reasons) > 0), reasons


def main() -> None:
    ctx = Ctx(
        registry_path=Path("data/canonical/documents/batch_01_registry_active.json"),
        reports_dir=Path("data/derived/reports"),
        doctor_dir=Path("data/canonical/doctor_conclusions"),
        rec_dir=Path("data/canonical/recommendations"),
        quality_cfg_path=Path("configs/quality_gates_v1.json"),
        audit_file=Path("data/audit/logs/batch_01_agent.ndjson"),
    )

    registry = load_json(ctx.registry_path)
    quality_cfg = load_json(ctx.quality_cfg_path)
    mojibake_cfg = quality_cfg.get("mojibake_detection", {})

    changed_docs: list[dict[str, Any]] = []
    now = now_utc()

    for row in registry:
        if str(row.get("doc_type") or "") != "doctor_consultation":
            continue
        doc_id = str(row.get("id") or "").strip()
        if not doc_id:
            continue

        source_rel = str((row.get("source") or {}).get("relative_path") or "").strip()
        if not source_rel:
            continue
        source_path = Path(source_rel)
        if not source_path.exists():
            continue

        fe_path = find_full_extraction_by_doc_id(ctx.reports_dir, doc_id)
        if not fe_path:
            continue
        fe = load_json(fe_path)

        raw_text = extract_pdf_text(source_path)
        visit_type = parser.parse_visit_type(raw_text, "doctor_consultation")
        conclusion_text, diagnosis_text, recommendation_text = parser.extract_doctor_fields(raw_text, visit_type)
        specialty = parser.normalize_specialty(visit_type or "", "doctor_consultation")

        stem = doc_id.replace("doc_", "")
        dc_path = ctx.doctor_dir / f"doctor_conclusion_{stem}.json"
        current_dc = load_json(dc_path) if dc_path.exists() else None

        do_fix, reasons = should_remediate(
            current_fe=fe,
            current_dc=current_dc,
            parsed_visit_type=visit_type,
            parsed_conclusion=conclusion_text,
            parsed_diagnosis=diagnosis_text,
            parsed_recommendation=recommendation_text,
            mojibake_cfg=mojibake_cfg,
        )
        if not do_fix:
            continue

        # full_extraction refresh from source text + normalized summary fields
        fe["raw_text_excerpt"] = raw_text
        fe["parsed_at"] = now
        fe.setdefault("summary", {})
        fe["summary"]["visit_type"] = visit_type
        fe["summary"]["recommendation"] = recommendation_text
        fe.setdefault("encounter", {})
        fe["encounter"]["specialty"] = specialty if specialty != "unknown" else fe["encounter"].get("specialty")
        fe["quality"] = {
            "extraction_mode": "agent_doctor_consultation_remediation_v2_from_pdf_text_layer",
            "review_required": False,
            "notes": "Doctor consultation remediation v2 from source PDF text layer; discuss clinical interpretation with a licensed physician.",
        }
        save_json(fe_path, fe)

        # doctor_conclusion refresh
        ingested_at = str((current_dc or {}).get("source", {}).get("ingested_at") or now)
        dc_payload = {
            "id": f"doctor_conclusion_{stem}",
            "patient_id": "self",
            "event_date": str(fe.get("event_date") or None),
            "status": "needs_review",
            "source": {
                "document_id": doc_id,
                "file_name": str(fe.get("source_file") or row.get("file_name") or ""),
                "relative_path": source_rel,
                "ingested_at": ingested_at,
            },
            "specialty": specialty,
            "conclusion_text": conclusion_text,
            "diagnosis_text": diagnosis_text,
        }
        save_json(dc_path, dc_payload)

        # recommendation refresh/create
        rec_path = ctx.rec_dir / f"recommendation_{stem}.json"
        rec_written = False
        if recommendation_text:
            rec_payload = load_json(rec_path) if rec_path.exists() else {
                "id": f"recommendation_{stem}",
                "patient_id": "self",
                "event_date": str(fe.get("event_date") or None),
                "status": "needs_review",
                "source": {
                    "document_id": doc_id,
                    "file_name": str(fe.get("source_file") or row.get("file_name") or ""),
                    "relative_path": source_rel,
                    "ingested_at": now,
                },
                "priority": None,
                "due_date": None,
            }
            rec_payload["event_date"] = str(fe.get("event_date") or rec_payload.get("event_date"))
            rec_payload["recommendation_text"] = recommendation_text
            save_json(rec_path, rec_payload)
            rec_written = True

        changed_docs.append(
            {
                "doc_id": doc_id,
                "file_name": row.get("file_name"),
                "reasons": reasons,
                "full_extraction": str(fe_path).replace("\\", "/"),
                "doctor_conclusion": str(dc_path).replace("\\", "/"),
                "recommendation_written": rec_written,
                "conclusion_len": len(conclusion_text or ""),
                "diagnosis_len": len(diagnosis_text or ""),
                "recommendation_len": len(recommendation_text or ""),
            }
        )

    if changed_docs:
        audit_rows: list[dict[str, Any]] = []
        for d in changed_docs:
            audit_rows.append(
                {
                    "ts": now,
                    "event": "agent_doctor_consultation_remediated_v2",
                    "batch_id": "batch_01",
                    "doc_id": d["doc_id"],
                    "file_name": d.get("file_name"),
                    "reasons": d.get("reasons"),
                    "full_extraction": d.get("full_extraction"),
                    "doctor_conclusion": d.get("doctor_conclusion"),
                    "recommendation_written": d.get("recommendation_written"),
                }
            )
        audit_rows.append(
            {
                "ts": now,
                "event": "agent_doctor_consultation_remediation_v2_completed",
                "batch_id": "batch_01",
                "processed": len(changed_docs),
            }
        )
        append_ndjson(ctx.audit_file, audit_rows)

    print(json.dumps({"processed": len(changed_docs), "docs": changed_docs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
