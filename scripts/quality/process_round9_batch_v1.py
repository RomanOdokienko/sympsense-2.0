from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ROUND = 9
BATCH_ID = "batch_01"
ROUND_FILES = [
    "report-15644-2310389.pdf",
    "report-15644-2359088.pdf",
    "report-15644-2381314.pdf",
    "report-15644-2381423.pdf",
    "report-15644-2397204.pdf",
    "report-15644-2775188.pdf",
    "report-15644-2822573.pdf",
    "report-15644-2825816.pdf",
    "report-15644-2829326 (1).pdf",
    "report-15644-2829326.pdf",
]


@dataclass
class Ctx:
    inbox_dir: Path
    recognized_dir: Path
    needs_review_dir: Path
    reports_dir: Path
    docs_dir: Path
    doctor_dir: Path
    rec_dir: Path
    audit_file: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(x, ensure_ascii=False) for x in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def append_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_text(text: str) -> str:
    return " ".join((text or "").replace("\r", "\n").replace("\t", " ").split())


def strip_signature_tail(text: str) -> str:
    src = (text or "").strip()
    if not src:
        return ""
    markers = [
        "\u041f\u041e\u0414\u041f\u0418\u0421\u0418",
        "\u0414\u041e\u041a\u0423\u041c\u0415\u041d\u0422 \u041f\u041e\u0414\u041f\u0418\u0421\u0410\u041d",
        "\u0421\u0412\u0415\u0414\u0415\u041d\u0418\u042f \u041e \u0421\u0415\u0420\u0422\u0418\u0424\u0418\u041a\u0410\u0422\u0415",
        "\u041d\u041e\u041c\u0415\u0420 \u0421\u0415\u0420\u0422\u0418\u0424\u0418\u041a\u0410\u0422\u0410",
        "\u0412\u041b\u0410\u0414\u0415\u041b\u0415\u0426:",
        "\u0420\u0415\u041d\u0422\u0413\u0415\u041d\u041e\u041b\u0410\u0411\u041e\u0420\u0410\u041d\u0422",
    ]
    lower = src.lower()
    cut = len(src)
    for marker in markers:
        idx = lower.find(marker.lower())
        if idx != -1 and idx < cut:
            cut = idx
    return src[:cut].strip(" \n\r\t:;,-")


def to_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", value.strip())
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    return f"{yyyy}-{mm}-{dd}"


def first_match(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_date_raw(text: str) -> str | None:
    m = re.search(r"По\s+направлению\s+от:\s*(\d{2}\.\d{2}\.\d{4})", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r"Дата\s*:\s*(\d{2}\.\d{2}\.\d{4})", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
    # Prefer not to return birth date when possible.
    for d in dates:
        if d != "23.10.1989":
            return d
    return dates[0] if dates else None


def extract_between(text: str, starts: list[str], ends: list[str]) -> str:
    lower = text.lower()
    start_idx = -1
    start_key = ""
    for key in starts:
        idx = lower.find(key.lower())
        if idx != -1 and (start_idx == -1 or idx < start_idx):
            start_idx = idx
            start_key = key
    if start_idx == -1:
        return ""

    body_start = start_idx + len(start_key)
    if body_start < len(text) and text[body_start:body_start + 1] == ":":
        body_start += 1

    body = text[body_start:]
    body_lower = body.lower()
    body_end = len(body)
    for key in ends:
        idx = body_lower.find(key.lower())
        if idx != -1 and idx < body_end:
            body_end = idx
    return clean_text(body[:body_end])


def fallback_tail(text: str, lines_count: int = 4) -> str:
    skip = (
        "документ подписан",
        "сведения о сертификате",
        "номер сертификата",
        "владелец:",
        "действителен с",
        "подписи",
        "врач",
        "исполнитель",
    )
    lines = [x.strip() for x in text.replace("\r", "\n").split("\n") if x.strip()]
    lines = [x for x in lines if not any(tok in x.lower() for tok in skip)]
    if not lines:
        return ""
    return clean_text(" ".join(lines[-lines_count:]))


def normalize_specialty(visit_type: str, doc_type: str) -> str:
    vt = (visit_type or "").lower()
    if doc_type == "imaging_report_ultrasound":
        return "ultrasound"
    if doc_type.startswith("imaging_report_"):
        return "radiology"
    if "физиотерапевт" in vt:
        return "physiotherapy"
    if "ревматолог" in vt:
        return "rheumatology"
    if "травматолог" in vt or "ортопед" in vt:
        return "traumatology_orthopedics"
    if "оториноларинголог" in vt or "лор" in vt:
        return "otolaryngology"
    if "терапевт" in vt:
        return "internal_medicine"
    if "хирург" in vt:
        return "surgery"
    if "офтальмолог" in vt:
        return "ophthalmology"
    return "unknown"


def classify_doc_type(file_name: str, text: str) -> tuple[str, str, float]:
    fn = (file_name or "").lower()
    low = f"{file_name}\\n{text}".lower()
    if "\\u043a\\u043e\\u043d\\u0441\\u0443\\u043b\\u044c\\u0442\\u0430\\u0446" in fn or "\\u043e\\u0441\\u043c\\u043e\\u0442\\u0440" in fn:
        return "doctor_consultation", "filename_consultation", 0.96
    if (
        "\\u043f\\u0440\\u0438\\u0435\\u043c \\u0432\\u0440\\u0430\\u0447\\u0430" in low
        or "\\u043e\\u0441\\u043c\\u043e\\u0442\\u0440 \\u0442\\u0440\\u0430\\u0432\\u043c\\u0430\\u0442\\u043e\\u043b\\u043e\\u0433\\u0430" in low
        or "\\u043a\\u043e\\u043d\\u0441\\u0443\\u043b\\u044c\\u0442\\u0430\\u0446\\u0438\\u044f \\u0432\\u0440\\u0430\\u0447\\u0430" in low
    ):
        return "doctor_consultation", "content_consultation", 0.94
    if any(x in low for x in ["магнитно-резонанс", "мрт"]):
        return "imaging_report_mri", "content_imaging_mri", 0.95
    if any(x in low for x in ["рентген", "рентгенограф"]):
        return "imaging_report_xray", "content_imaging_xray", 0.95
    if any(x in low for x in ["ультразвук", "узи", "дуплекс", "эхография", "эхокарди"]):
        return "imaging_report_ultrasound", "content_imaging_ultrasound", 0.95
    if "параметр результат" in low or "референсные значения" in low:
        return "lab_report", "keyword_or_filename_labs", 0.82
    return "doctor_consultation", "content_doctor_consultation", 0.9


def parse_visit_type(text: str, doc_type: str) -> str | None:
    if doc_type == "doctor_consultation":
        return first_match(
            text,
            [
                r"Прием\s+врача\s*-\s*[^\n\r]+",
                r"Прием\s+врача\s+[^\n\r]+",
                r"Осмотр\s+[^\n\r]+",
            ],
        )
    if doc_type == "imaging_report_ultrasound":
        return first_match(
            text,
            [
                r"Дуплекс[^\n\r]+",
                r"Ультразвуков[^\n\r]+",
            ],
        ) or "Инструментальное исследование (ultrasound)"
    if doc_type == "imaging_report_xray":
        return first_match(text, [r"Рентген[^\n\r]+"]) or "Инструментальное исследование (xray)"
    if doc_type == "imaging_report_mri":
        return first_match(text, [r"Магнитно-резонанс[^\n\r]+", r"МРТ[^\n\r]+"]) or "Инструментальное исследование (mri)"
    return None


def extract_doctor_fields(text: str, visit_type: str | None) -> tuple[str, str | None, str | None]:
    diagnosis = extract_between(
        text,
        starts=["Диагноз"],
        ends=["Заключение", "Общее", "Рекомендации", "Назначения", "Режим", "Документ подписан", "Сведения о сертификате"],
    )
    conclusion = extract_between(
        text,
        starts=["Заключение", "Врачебное заключение"],
        ends=["Рекомендации", "Назначения", "Режим", "Документ подписан", "Сведения о сертификате"],
    )
    if not conclusion:
        conclusion = diagnosis
    if not conclusion:
        conclusion = visit_type or ""
    if not conclusion:
        conclusion = fallback_tail(text)

    recommendation = extract_between(
        text,
        starts=["Рекомендации", "Общее", "Назначения"],
        ends=["Документ подписан", "Сведения о сертификате", "Владелец:", "Подписи"],
    )
    if recommendation and clean_text(recommendation).lower() == clean_text(conclusion).lower():
        recommendation = ""
    if recommendation and len(recommendation) < 16:
        recommendation = ""

    conclusion_clean = strip_signature_tail(clean_text(conclusion))
    diagnosis_clean = strip_signature_tail(clean_text(diagnosis)) if diagnosis else ""
    recommendation_clean = strip_signature_tail(clean_text(recommendation)) if recommendation else ""
    return conclusion_clean, diagnosis_clean or None, recommendation_clean or None


def extract_imaging_fields(text: str) -> tuple[str, str | None, str | None]:
    findings = extract_between(
        text,
        starts=["Инструментальные исследования", "Описание", "Протокол"],
        ends=["Заключение", "Рекомендовано", "Рекомендации", "Документ подписан", "Сведения о сертификате"],
    )
    conclusion = extract_between(
        text,
        starts=["Заключение"],
        ends=["Рекомендовано", "Рекомендации", "Документ подписан", "Сведения о сертификате"],
    )
    recommendation = extract_between(
        text,
        starts=["Рекомендовано", "Рекомендации"],
        ends=["Документ подписан", "Сведения о сертификате", "Владелец:", "Подписи"],
    )

    if not conclusion:
        conclusion = fallback_tail(text)
    if recommendation and clean_text(recommendation).lower() == clean_text(conclusion).lower():
        recommendation = ""
    if recommendation and len(recommendation) < 16:
        recommendation = ""
    conclusion_clean = strip_signature_tail(clean_text(conclusion))
    findings_clean = strip_signature_tail(clean_text(findings)) if findings else ""
    recommendation_clean = strip_signature_tail(clean_text(recommendation)) if recommendation else ""
    return conclusion_clean, findings_clean or None, recommendation_clean or None


def sha1_doc_id(pdf_path: Path) -> str:
    digest = hashlib.sha1(pdf_path.read_bytes()).hexdigest()[:16]
    return f"doc_{digest}"


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def write_full_extraction(
    reports_dir: Path,
    file_name: str,
    doc_id: str,
    source_rel: str,
    doc_type: str,
    event_iso: str | None,
    specialty: str,
    visit_type: str | None,
    recommendation: str | None,
    raw_text: str,
    parse_mode: str,
    parsed_at: str,
) -> Path:
    stem = Path(file_name).stem
    out = reports_dir / f"full_extraction_{stem}.json"
    payload = {
        "record_id": f"{doc_type}_{doc_id.replace('doc_', '')}",
        "doc_id": doc_id,
        "source_file": file_name,
        "source_path": source_rel,
        "doc_type": doc_type,
        "parsed_at": parsed_at,
        "event_date": event_iso,
        "encounter": {
            "medical_organization": "Клиника К+31" if "Клиника К+31" in raw_text else None,
            "facility": None,
            "specialty": specialty if specialty != "unknown" else None,
        },
        "summary": {
            "visit_type": visit_type,
            "plan": None,
            "recommendation": recommendation,
        },
        "quality": {
            "extraction_mode": f"agent_round{ROUND}_from_pdf_text_layer" if parse_mode == "text_layer" else f"agent_round{ROUND}_multimodal_vision",
            "review_required": parse_mode != "text_layer",
            "notes": f"Round{ROUND} extraction from local source document; discuss clinical interpretation with a licensed physician.",
        },
        "raw_text_excerpt": raw_text,
    }
    save_json(out, payload)
    return out


def build_registry_row(
    doc_id: str,
    file_name: str,
    doc_type: str,
    confidence: float,
    reason: str,
    event_date_raw: str | None,
    parse_mode: str,
    text: str,
    source_rel: str,
    registered_at: str,
) -> dict[str, Any]:
    return {
        "id": doc_id,
        "patient_id": "self",
        "batch_id": BATCH_ID,
        "file_name": file_name,
        "doc_type": doc_type,
        "confidence": confidence,
        "reason": reason,
        "event_date_raw": event_date_raw,
        "status": "typed",
        "parse_mode": parse_mode,
        "text_len": len(text),
        "source": {
            "relative_path": source_rel,
            "registered_at": registered_at,
        },
        "summary_preview": clean_text(text)[:2200],
    }


def build_doctor_conclusion(
    doc_id: str,
    file_name: str,
    source_rel: str,
    ingested_at: str,
    event_iso: str | None,
    specialty: str,
    conclusion_text: str,
    diagnosis_text: str | None,
    findings_text: str | None,
) -> dict[str, Any]:
    stem = doc_id.replace("doc_", "")
    payload: dict[str, Any] = {
        "id": f"doctor_conclusion_{stem}",
        "patient_id": "self",
        "event_date": event_iso,
        "status": "needs_review",
        "source": {
            "document_id": doc_id,
            "file_name": file_name,
            "relative_path": source_rel,
            "ingested_at": ingested_at,
        },
        "specialty": specialty,
        "conclusion_text": conclusion_text,
        "diagnosis_text": diagnosis_text,
    }
    if findings_text:
        payload["findings_text"] = findings_text
    return payload


def build_recommendation(
    doc_id: str,
    file_name: str,
    source_rel: str,
    ingested_at: str,
    event_iso: str | None,
    recommendation_text: str,
) -> dict[str, Any]:
    stem = doc_id.replace("doc_", "")
    return {
        "id": f"recommendation_{stem}",
        "patient_id": "self",
        "event_date": event_iso,
        "status": "needs_review",
        "source": {
            "document_id": doc_id,
            "file_name": file_name,
            "relative_path": source_rel,
            "ingested_at": ingested_at,
        },
        "recommendation_text": recommendation_text,
        "priority": None,
        "due_date": None,
    }


def main() -> None:
    ctx = Ctx(
        inbox_dir=Path("data/raw/inbox") / BATCH_ID,
        recognized_dir=Path("data/raw/recognized") / BATCH_ID,
        needs_review_dir=Path("data/raw/needs_review") / BATCH_ID,
        reports_dir=Path("data/derived/reports"),
        docs_dir=Path("data/canonical/documents"),
        doctor_dir=Path("data/canonical/doctor_conclusions"),
        rec_dir=Path("data/canonical/recommendations"),
        audit_file=Path("data/audit/logs/batch_01_agent.ndjson"),
    )

    registry_active_json = ctx.docs_dir / "batch_01_registry_active.json"
    registry_active_ndjson = ctx.docs_dir / "batch_01_registry_active.ndjson"
    round_json = ctx.docs_dir / f"batch_01_registry_round{ROUND}.json"
    round_ndjson = ctx.docs_dir / f"batch_01_registry_round{ROUND}.ndjson"
    findings_json = ctx.reports_dir / f"batch_01_findings_round{ROUND}.json"

    active_rows: list[dict[str, Any]] = load_json(registry_active_json)
    existing_ids = {str(x.get("id") or "") for x in active_rows}

    round_rows: list[dict[str, Any]] = []
    findings_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for file_name in ROUND_FILES:
        src = ctx.inbox_dir / file_name
        if not src.exists():
            skipped.append({"file": file_name, "reason": "not_found_in_inbox"})
            continue

        doc_id = sha1_doc_id(src)
        if doc_id in existing_ids:
            skipped.append({"file": file_name, "doc_id": doc_id, "reason": "already_in_registry"})
            continue

        parsed_at = now_utc()
        text = extract_pdf_text(src)
        parse_mode = "text_layer" if len(clean_text(text)) >= 120 else "multimodal_vision"
        target_dir = ctx.recognized_dir if parse_mode == "text_layer" else ctx.needs_review_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / file_name
        shutil.move(str(src), str(dst))

        source_rel = str(dst).replace("\\", "/")
        doc_type, reason, confidence = classify_doc_type(file_name=file_name, text=text)
        event_date_raw = extract_date_raw(text)
        event_iso = to_iso_date(event_date_raw)
        visit_type = parse_visit_type(text, doc_type)

        if doc_type == "doctor_consultation":
            conclusion, diagnosis, recommendation = extract_doctor_fields(text=text, visit_type=visit_type)
            findings = None
        elif doc_type.startswith("imaging_report_"):
            conclusion, findings, recommendation = extract_imaging_fields(text=text)
            diagnosis = None
        else:
            conclusion = visit_type or "Extracted from report; needs review."
            diagnosis = None
            findings = None
            recommendation = None

        specialty = normalize_specialty(visit_type=visit_type or "", doc_type=doc_type)

        full_path = write_full_extraction(
            reports_dir=ctx.reports_dir,
            file_name=file_name,
            doc_id=doc_id,
            source_rel=source_rel,
            doc_type=doc_type,
            event_iso=event_iso,
            specialty=specialty,
            visit_type=visit_type,
            recommendation=recommendation,
            raw_text=text,
            parse_mode=parse_mode,
            parsed_at=parsed_at,
        )

        row = build_registry_row(
            doc_id=doc_id,
            file_name=file_name,
            doc_type=doc_type,
            confidence=confidence,
            reason=reason,
            event_date_raw=event_date_raw,
            parse_mode=parse_mode,
            text=text,
            source_rel=source_rel,
            registered_at=parsed_at,
        )
        round_rows.append(row)

        stem = doc_id.replace("doc_", "")
        doctor_payload = build_doctor_conclusion(
            doc_id=doc_id,
            file_name=file_name,
            source_rel=source_rel,
            ingested_at=parsed_at,
            event_iso=event_iso,
            specialty=specialty,
            conclusion_text=conclusion,
            diagnosis_text=diagnosis,
            findings_text=findings,
        )
        save_json(ctx.doctor_dir / f"doctor_conclusion_{stem}.json", doctor_payload)

        rec_created = False
        if recommendation:
            rec_payload = build_recommendation(
                doc_id=doc_id,
                file_name=file_name,
                source_rel=source_rel,
                ingested_at=parsed_at,
                event_iso=event_iso,
                recommendation_text=recommendation,
            )
            save_json(ctx.rec_dir / f"recommendation_{stem}.json", rec_payload)
            rec_created = True

        findings_rows.append(
            {
                "file": file_name,
                "doc_type": doc_type,
                "reason": reason,
                "event_date_raw": event_date_raw,
                "text_len": len(text),
                "moved_to": source_rel,
                "summary_preview": clean_text(text)[:2200],
            }
        )

        audit_rows.append(
            {
                "ts": parsed_at,
                "event": "agent_batch_processed_file",
                "batch_id": BATCH_ID,
                "file_name": file_name,
                "doc_id": doc_id,
                "doc_type": doc_type,
                "status": "typed",
                "target": source_rel,
                "parse_mode": parse_mode,
                "text_len": len(text),
                "round": ROUND,
            }
        )
        audit_rows.append(
            {
                "ts": parsed_at,
                "event": "agent_round_full_extraction_written",
                "batch_id": BATCH_ID,
                "round": ROUND,
                "doc_id": doc_id,
                "source": source_rel,
                "full_extraction": str(full_path).replace("\\", "/"),
                "doctor_conclusion": str((ctx.doctor_dir / f"doctor_conclusion_{stem}.json")).replace("\\", "/"),
                "recommendation_created": rec_created,
            }
        )

    if round_rows:
        active_rows.extend(round_rows)
        save_json(registry_active_json, active_rows)
        save_ndjson(registry_active_ndjson, active_rows)
        save_json(round_json, round_rows)
        save_ndjson(round_ndjson, round_rows)
        save_json(findings_json, findings_rows)
        append_ndjson(ctx.audit_file, audit_rows)
        append_ndjson(
            ctx.audit_file,
            [
                {
                    "ts": now_utc(),
                    "event": "batch_round_completed",
                    "batch_id": BATCH_ID,
                    "round": ROUND,
                    "processed": len(round_rows),
                    "skipped": skipped,
                    "artifacts": {
                        "round_registry_json": str(round_json).replace("\\", "/"),
                        "round_registry_ndjson": str(round_ndjson).replace("\\", "/"),
                        "active_registry_json": str(registry_active_json).replace("\\", "/"),
                        "findings": str(findings_json).replace("\\", "/"),
                    },
                }
            ],
        )

    print(
        json.dumps(
            {
                "round": ROUND,
                "processed": len(round_rows),
                "skipped": skipped,
                "active_total": len(active_rows),
                "round_registry": str(round_json).replace("\\", "/"),
                "findings": str(findings_json).replace("\\", "/"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
