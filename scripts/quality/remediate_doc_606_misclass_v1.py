from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


DOC_ID = "doc_606811c981ccf5da"
DOC_STEM = DOC_ID.replace("doc_", "")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    root = Path(".")
    registry_json = root / "data/canonical/documents/batch_01_registry_active.json"
    registry_ndjson = root / "data/canonical/documents/batch_01_registry_active.ndjson"
    reports_dir = root / "data/derived/reports"
    doctor_dir = root / "data/canonical/doctor_conclusions"
    labs_dir = root / "data/canonical/labs"

    rows = load_json(registry_json)
    row = next((r for r in rows if r.get("id") == DOC_ID), None)
    if not row:
        raise RuntimeError(f"Registry row not found: {DOC_ID}")

    row["doc_type"] = "doctor_consultation"
    row["confidence"] = 0.91
    row["reason"] = "content_dentistry"
    row["event_date_raw"] = "05.04.2014"
    save_json(registry_json, rows)

    ndjson_rows = []
    for ln in registry_ndjson.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        obj = json.loads(ln)
        if obj.get("id") == DOC_ID:
            obj["doc_type"] = "doctor_consultation"
            obj["confidence"] = 0.91
            obj["reason"] = "content_dentistry"
            obj["event_date_raw"] = "05.04.2014"
        ndjson_rows.append(obj)
    registry_ndjson.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ndjson_rows) + "\n",
        encoding="utf-8",
    )

    full_path = None
    full_obj = None
    for p in reports_dir.glob("full_extraction_*.json"):
        j = load_json(p)
        if j.get("doc_id") == DOC_ID:
            full_path = p
            full_obj = j
            break
    if not full_path or not full_obj:
        raise RuntimeError(f"full_extraction not found for {DOC_ID}")

    full_obj["record_id"] = f"doctor_consultation_{DOC_STEM}"
    full_obj["doc_type"] = "doctor_consultation"
    full_obj["event_date"] = "2014-04-05"
    encounter = full_obj.get("encounter") or {}
    encounter["specialty"] = "dentistry"
    full_obj["encounter"] = encounter
    save_json(full_path, full_obj)

    raw_text = str(full_obj.get("raw_text_excerpt") or "")
    plan = ""
    marker = "План обследования:"
    if marker in raw_text:
        plan = raw_text.split(marker, 1)[1].strip()
    conclusion = "Прием врача стоматолога."
    if plan:
        conclusion = f"{conclusion} План обследования: {plan}"

    doctor_payload = {
        "id": f"doctor_conclusion_{DOC_STEM}",
        "patient_id": "self",
        "event_date": "2014-04-05",
        "status": "needs_review",
        "source": {
            "document_id": DOC_ID,
            "file_name": str(full_obj.get("source_file") or row.get("file_name") or ""),
            "relative_path": str(full_obj.get("source_path") or (row.get("source") or {}).get("relative_path") or ""),
            "ingested_at": str(full_obj.get("parsed_at") or ""),
        },
        "specialty": "dentistry",
        "conclusion_text": conclusion,
        "diagnosis_text": None,
    }
    doctor_path = doctor_dir / f"doctor_conclusion_{DOC_STEM}.json"
    save_json(doctor_path, doctor_payload)

    lab_path = labs_dir / f"lab_full_doc_{DOC_STEM}.json"
    moved_lab = None
    if lab_path.exists():
        archive_dir = labs_dir / "_orphaned_dedupe_2026-04-09"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dst = archive_dir / lab_path.name
        shutil.move(str(lab_path), str(dst))
        moved_lab = str(dst).replace("\\", "/")

    print(
        json.dumps(
            {
                "doc_id": DOC_ID,
                "full_extraction": str(full_path).replace("\\", "/"),
                "doctor_conclusion": str(doctor_path).replace("\\", "/"),
                "moved_lab_file": moved_lab,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
