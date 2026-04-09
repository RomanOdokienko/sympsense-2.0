from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Ctx:
    registry_path: Path
    reports_dir: Path
    doctor_dir: Path
    rec_dir: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(text: str) -> str:
    return " ".join(text.replace("\r", "\n").replace("\t", " ").split())


def extract_between(text: str, start_keys: list[str], end_keys: list[str]) -> str:
    lower = text.lower()
    start_idx = -1
    matched_key = ""
    for key in start_keys:
        idx = lower.find(key.lower())
        if idx != -1 and (start_idx == -1 or idx < start_idx):
            start_idx = idx
            matched_key = key
    if start_idx == -1:
        return ""

    start = start_idx + len(matched_key)
    if start < len(text) and text[start:start + 1] == ":":
        start += 1

    end = len(text)
    tail = text[start:]
    tail_lower = tail.lower()
    for key in end_keys:
        idx = tail_lower.find(key.lower())
        if idx != -1 and idx < (end - start):
            end = start + idx
    return clean_text(text[start:end])


def fallback_conclusion_from_tail(text: str) -> str:
    skip_tokens = [
        "документ подписан",
        "сведения о сертификате",
        "номер сертификата",
        "владелец:",
        "действителен с",
        "подписи",
        "врач-рентгенолог",
        "рентгенолаборант",
    ]
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln]
    filtered = []
    for ln in lines:
        low = ln.lower()
        if any(token in low for token in skip_tokens):
            continue
        filtered.append(ln)

    if not filtered:
        return ""

    tail = filtered[-4:]
    return clean_text(" ".join(tail))


def specialty_from_doc_type(doc_type: str) -> str:
    if doc_type == "imaging_report_ultrasound":
        return "ultrasound"
    return "radiology"


def main() -> None:
    ctx = Ctx(
        registry_path=Path("data/canonical/documents/batch_01_registry_active.json"),
        reports_dir=Path("data/derived/reports"),
        doctor_dir=Path("data/canonical/doctor_conclusions"),
        rec_dir=Path("data/canonical/recommendations"),
    )

    registry = load_json(ctx.registry_path)
    full_by_doc: dict[str, dict[str, Any]] = {}
    for p in ctx.reports_dir.glob("full_extraction_*.json"):
        try:
            j = load_json(p)
        except Exception:
            continue
        doc_id = str(j.get("doc_id") or "").strip()
        if doc_id:
            full_by_doc[doc_id] = j

    changed_docs: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in registry:
        doc_type = str(row.get("doc_type") or "")
        if not doc_type.startswith("imaging_report_"):
            continue
        doc_id = str(row.get("id") or "").strip()
        if not doc_id:
            continue

        full = full_by_doc.get(doc_id)
        if not full:
            continue

        source_file = str(full.get("source_file") or row.get("file_name") or "")
        source_path = str(full.get("source_path") or row.get("source", {}).get("relative_path") or "")
        event_date = str(full.get("event_date") or "").strip() or None
        text = str(full.get("raw_text_excerpt") or "")

        conclusion = extract_between(
            text=text,
            start_keys=["Заключение", "Impression", "Conclusion"],
            end_keys=["Рекомендовано", "Рекомендации", "Recommendations", "ПОДПИСИ", "ДОКУМЕНТ ПОДПИСАН"],
        )
        findings = extract_between(
            text=text,
            start_keys=["Протокол", "Описание", "Findings"],
            end_keys=["Заключение", "Impression", "Conclusion", "Рекомендовано", "Рекомендации", "Recommendations", "ПОДПИСИ"],
        )
        if not conclusion:
            conclusion = fallback_conclusion_from_tail(text)
        if not conclusion:
            conclusion = "Imaging findings extracted from report; needs review."

        recommendation = extract_between(
            text=text,
            start_keys=["Рекомендовано", "Рекомендации", "Recommendations"],
            end_keys=["ПОДПИСИ", "ДОКУМЕНТ ПОДПИСАН", "СВЕДЕНИЯ О СЕРТИФИКАТЕ", "Врач-рентгенолог"],
        )
        if recommendation and len(recommendation) < 12:
            recommendation = ""

        stem = doc_id.replace("doc_", "")
        doctor_path = ctx.doctor_dir / f"doctor_conclusion_{stem}.json"
        doctor_payload = {
            "id": f"doctor_conclusion_{stem}",
            "patient_id": "self",
            "event_date": event_date,
            "status": "needs_review",
            "source": {
                "document_id": doc_id,
                "file_name": source_file,
                "relative_path": source_path,
                "ingested_at": now,
            },
            "specialty": specialty_from_doc_type(doc_type),
            "conclusion_text": conclusion,
            "findings_text": findings or None,
            "diagnosis_text": None,
        }
        save_json(doctor_path, doctor_payload)

        rec_path = ctx.rec_dir / f"recommendation_{stem}.json"
        rec_created = False
        if recommendation:
            rec_payload = {
                "id": f"recommendation_{stem}",
                "patient_id": "self",
                "event_date": event_date,
                "status": "needs_review",
                "source": {
                    "document_id": doc_id,
                    "file_name": source_file,
                    "relative_path": source_path,
                    "ingested_at": now,
                },
                "recommendation_text": recommendation,
                "priority": None,
                "due_date": None,
            }
            save_json(rec_path, rec_payload)
            rec_created = True

        changed_docs.append(
            {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "doctor_conclusion_file": str(doctor_path).replace("\\", "/"),
                "recommendation_created": rec_created,
                "conclusion_len": len(conclusion),
                "recommendation_len": len(recommendation),
            }
        )

    print(json.dumps({"processed": len(changed_docs), "docs": changed_docs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
