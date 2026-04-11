from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(".")
BATCH_ID = "batch_01"

REGISTRY_PATH = ROOT / "data/canonical/documents/batch_01_registry_active.json"
LABS_DIR = ROOT / "data/canonical/labs"
DOCTOR_DIR = ROOT / "data/canonical/doctor_conclusions"
RECS_DIR = ROOT / "data/canonical/recommendations"
REPORTS_DIR = ROOT / "data/derived/reports"
FACTS_DIR = ROOT / "data/canonical/facts"
AUDIT_FILE = ROOT / "data/audit/logs/batch_01_agent.ndjson"

QUAL_WORDS = (
    "не обнаруж",
    "обнаружено",
    "отриц",
    "полож",
    "норма",
    "единич",
)

MED_STOPWORDS = {
    "назначена",
    "контрольный",
    "консультация",
    "диета",
    "общие",
    "повторный",
    "врач",
    "лфк",
    "мрт",
    "узи",
    "рентген",
    "ограничение",
    "наблюдение",
    "использовать",
    "увлажнитель",
    "увлажняющие",
    "капли",
    "глаза",
    "нос",
    "соблюдение",
    "пищевого",
    "режима",
    "воздуха",
    "спальне",
    "нпвс",
    "данных",
    "рекомендуется",
    "рекомендуется:",
}

EXCLUDED_CONDITION_TERMS = (
    "гельмин",
    "глист",
    "лямбли",
    "токсокар",
    "инваз",
)

MED_SIGNAL_RE = re.compile(
    r"(?:\b\d+[.,]?\d*\s*(?:мг|мл|мкг|г|ед)\b|"
    r"\b(?:таб|капс|кап\.?|саше|гель|мазь|раствор|инъекц)\w*|"
    r"\b(?:per\s*os|внутрь|в/м|внутримыш|в/в|наружно|на\s+кожу)\b)",
    flags=re.IGNORECASE,
)

MED_START_RE = re.compile(
    r"(?P<name>[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9®\-]{2,}"
    r"(?:\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9®\-]{2,}){0,3})"
    r"\s*(?:\(|\d+[.,]?\d*\s*(?:мкг|мг|мл|г)\b)"
)

DOSAGE_RE = re.compile(
    r"\b\d+[.,]?\d*\s*"
    r"(?:мкг|мг|мл|г|ед|таб\.?|капс?\.?|капл?и?|кап\.?|впрыскиван(?:ие|ия))\b",
    flags=re.IGNORECASE,
)
FREQUENCY_RE = re.compile(
    r"(?:\b\d+\s*(?:раз|р)\s*/?\s*(?:дн|сут|д)\b|"
    r"\b\d+\s*-\s*\d+\s*(?:раза?)\s*в\s*(?:день|сутки)\b|"
    r"\b\d+\s*(?:раза?)\s*в\s*(?:день|сутки)\b)",
    flags=re.IGNORECASE,
)
DURATION_RE = re.compile(
    r"(?:"
    r"(?:длительность|курс)\s*\d+\s*(?:дн|дней|нед|недель|мес|месяц\w*)"
    r"|"
    r"\b\d+\s*(?:дн|дней|нед|недель|мес|месяц|месяца|месяцев)\b"
    r")",
    flags=re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_ndjson(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def iso_from_ddmmyyyy(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y")
    except ValueError:
        return None
    return dt.date().isoformat()


def clamp_confidence(value: float) -> float:
    return max(0.05, min(0.99, round(value, 2)))


def parse_numeric_value(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    num = match.group(0).replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def has_abnormal_flag(result_text: str | None) -> bool:
    s = result_text or ""
    return ("↑" in s) or ("↓" in s)


def has_mojibake(text: str | None) -> bool:
    s = text or ""
    if "�" in s:
        return True
    return bool(re.search(r"(?:Р[А-ЯЁ]|С[А-ЯЁ]){4,}", s))


def split_recommendation_items(text: str | None) -> list[str]:
    raw = (text or "").replace("\r", "\n")
    if not normalize_space(raw):
        return []

    work = re.sub(r"[•●▪]", "\n", raw)
    work = re.sub(r"[—–]\s*", "\n", work)
    parts = re.split(r"\n+|;\s+", work)

    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        chunk = normalize_space(part.strip(" -\t"))
        if len(chunk) < 12:
            continue
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out


def make_evidence_excerpt(raw_text: str | None, needle: str | None, radius: int = 130) -> str:
    text = normalize_space(raw_text or "")
    if not text:
        return ""
    if not needle:
        return text[:260]

    key = normalize_space(needle)
    if not key:
        return text[:260]
    key = key[:90]

    idx = text.lower().find(key.lower())
    if idx < 0:
        return text[:260]

    start = max(0, idx - radius)
    end = min(len(text), idx + len(key) + radius)
    return text[start:end]


def qa_from_reasons(reasons: list[str]) -> str:
    return "needs_review" if reasons else "ok"


def recommendation_qa_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    if len(text) < 20:
        reasons.append("short_text")
    if has_mojibake(text):
        reasons.append("mojibake_suspected")
    if "________________" in text or text.strip("_- ") == "":
        reasons.append("signature_noise")
    return reasons


def lab_qa_reasons(parameter: str, result_text: str, value_num: float | None, reference: str) -> list[str]:
    reasons: list[str] = []
    if not parameter:
        reasons.append("missing_analyte")
    if not result_text:
        reasons.append("missing_result")
    if parameter and re.match(r"^[\^<>=/\d\W_]{2,}", parameter):
        reasons.append("suspicious_analyte_prefix")
    if parameter and len(parameter) < 3:
        reasons.append("short_analyte")

    if value_num is None:
        result_low = result_text.lower()
        has_qual_token = any(x in result_low for x in QUAL_WORDS)
        has_textual_value = bool(re.search(r"[A-Za-zА-Яа-яЁё]{2,}", result_text))
        if not has_qual_token and not has_textual_value:
            reasons.append("unparsed_result")

    if not reference:
        reasons.append("missing_reference")
    return reasons


def normalize_lab_parameter_and_reference(parameter: str, reference: str) -> tuple[str, str]:
    p = normalize_space(parameter)
    r = normalize_space(reference)
    if not p:
        return p, r

    p = p.replace("пїЅ", "")
    p = p.replace("в п/зр", " в п/зр ")
    p = normalize_space(p)
    # Unwrap broken tails: "(Базофилы)" -> "Базофилы", "Базофилы)" -> "Базофилы"
    if p.startswith("(") and p.endswith(")") and len(p) > 2:
        p = p[1:-1].strip()
    if p.endswith(")") and "(" not in p:
        p = p[:-1].strip()

    analyte_core = re.search(r"([A-Z]{2,8}\s*\([^)]+\))", p)
    if analyte_core and analyte_core.start() > 0:
        prefix = normalize_space(p[: analyte_core.start()])
        p = normalize_space(analyte_core.group(1))
        if not r and prefix and len(prefix) <= 48:
            r = prefix

    # Prefix reference pattern for non-Latin analytes: "0 - 15мм/чСОЭ"
    pref = re.match(
        r"^(?P<ref>(?:[<>]=?\s*)?\d+[.,]?\d*\s*-\s*\d+[.,]?\d*(?:\s*[A-Za-zА-Яа-яЁё/%\^]+)?)\s*(?P<rest>[A-Za-zА-Яа-яЁё(].+)$",
        p,
    )
    if pref:
        if not r:
            r = normalize_space(pref.group("ref"))
        p = normalize_space(pref.group("rest"))

    p = re.sub(r"^(?:\^?\d+\s*/\s*[A-Za-zА-Яа-я]+)\s*", "", p)
    p = re.sub(r"^(?:[<>]=?\s*\d+[^\wA-Za-zА-Яа-я]*)\s*", "", p)
    p = re.sub(r"^(?:[<>]=?\s*\d+)\s*", "", p)
    p = re.sub(r"^(?:фл|мм/ч|г/л|мкмоль/л|ммоль/л|%)\s*", "", p, flags=re.IGNORECASE)
    p = re.sub(r"^[^A-Za-zА-Яа-я]+", "", p)
    p = normalize_space(p)

    r = normalize_space(r)
    if r:
        r = re.sub(r"\bо\s*трицател\w*", "отрицательно", r, flags=re.IGNORECASE)
        r = re.sub(r"\bн\s*орма\b", "норма", r, flags=re.IGNORECASE)
        r = re.sub(
            r"\b(отрицател\w*|положител\w*|норм\w*|не\s*обнаруж\w*)(?:\s*[A-Za-zА-Яа-яЁё0-9/%\^]+)+\b",
            r"\1",
            r,
            flags=re.IGNORECASE,
        )
        r = re.sub(
            r"^(<=?\s*\d+[.,]?\d*\s*-\s*)норм\w*(?:\s*[A-Za-zА-Яа-яЁё0-9/%\^]+)?$",
            r"\1норма",
            r,
            flags=re.IGNORECASE,
        )
        rl = r.lower()
        if rl.startswith("отрицател"):
            r = "отрицательно"
        elif rl.startswith("положител"):
            r = "положительно"
        elif rl.startswith("не обнаруж"):
            r = "не обнаружено"
        elif rl.startswith("норм"):
            r = "норма"
        r = normalize_space(r)

    return p, r


def clinical_qa_reasons(text: str, finding_type: str) -> list[str]:
    reasons: list[str] = []
    if len(text) < 25:
        reasons.append("short_text")
    if has_mojibake(text):
        reasons.append("mojibake_suspected")
    if finding_type == "diagnosis" and not re.search(r"[A-ZА-Я]\d{1,2}(?:\.\d)?", text):
        reasons.append("no_icd_like_code")
    return reasons


def is_excluded_condition_text(text: str) -> bool:
    t = normalize_space(text).lower()
    if not t:
        return False
    return any(token in t for token in EXCLUDED_CONDITION_TERMS)


def infer_route(text: str) -> str | None:
    s = text.lower()
    if "внутримыш" in s or "в/м" in s:
        return "intramuscular"
    if "внутривенно" in s or "в/в" in s:
        return "intravenous"
    if "внутрь" in s or "per os" in s:
        return "oral"
    if "наружно" in s or "на кожу" in s:
        return "topical"
    return None


def has_medication_signal(text: str) -> bool:
    return bool(MED_SIGNAL_RE.search(text))


def normalize_med_name(name: str) -> str:
    n = normalize_space(name).strip(" ,.;:-")
    return re.sub(r"\s{2,}", " ", n)


def medication_name_allowed(name: str) -> bool:
    token = normalize_space(name).lower()
    if not token:
        return False
    first_word = token.split(" ", 1)[0]
    if first_word in MED_STOPWORDS:
        return False
    words = token.replace(":", " ").replace(",", " ").split()
    if token in MED_STOPWORDS:
        return False
    if any(w in MED_STOPWORDS for w in words):
        return False
    if "/" in token:
        return False
    if re.fullmatch(r"[A-ZА-ЯЁ]{2,5}", name.strip()):
        return False
    if len(token) < 3:
        return False
    return True


def guess_med_name_from_chunk(chunk: str) -> str | None:
    cleaned = re.sub(r"^\d+[.)]\s*", "", chunk.strip())
    pattern = re.compile(
        r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9®\-]{2,}"
        r"(?:\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9®\-]{2,}){0,2}"
    )
    for m in pattern.finditer(cleaned):
        candidate = normalize_med_name(m.group(0))
        if medication_name_allowed(candidate):
            return candidate
    return None


def extract_medication_segments(text: str) -> list[tuple[str, str]]:
    src = normalize_space(text)
    if not src:
        return []

    starts: list[tuple[int, str]] = []
    for m in MED_START_RE.finditer(src):
        name = normalize_med_name(m.group("name"))
        if not medication_name_allowed(name):
            continue
        starts.append((m.start(), name))

    if not starts:
        candidates = split_recommendation_items(src)
        out: list[tuple[str, str]] = []
        for chunk in candidates:
            subparts = re.split(
                r"(?=(?:[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9®\-]{2,}\s*(?:-|,)?\s*по\s+\d))",
                chunk,
            )
            for part in subparts:
                part = normalize_space(part)
                if not part or not has_medication_signal(part):
                    continue
                guess = guess_med_name_from_chunk(part)
                if not guess:
                    continue
                out.append((guess, part))
        return out

    dedup_starts: list[tuple[int, str]] = []
    seen_positions: set[int] = set()
    for pos, name in starts:
        if pos in seen_positions:
            continue
        seen_positions.add(pos)
        dedup_starts.append((pos, name))

    out2: list[tuple[str, str]] = []
    for i, (start, name) in enumerate(dedup_starts):
        end = dedup_starts[i + 1][0] if i + 1 < len(dedup_starts) else len(src)
        seg = normalize_space(src[start:end].strip(" ;,"))
        if len(seg) < 15:
            continue
        if not has_medication_signal(seg):
            continue
        out2.append((name, seg))
    return out2


def extract_medication_fields(text: str) -> dict[str, Any]:
    dosage = DOSAGE_RE.search(text)
    frequency = FREQUENCY_RE.search(text)
    duration = DURATION_RE.search(text)
    return {
        "dosage_text": dosage.group(0) if dosage else None,
        "frequency_text": frequency.group(0) if frequency else None,
        "duration_text": duration.group(0) if duration else None,
        "route": infer_route(text),
    }


def medication_qa_reasons(name: str, instruction: str, dosage_text: str | None) -> list[str]:
    reasons: list[str] = []
    if not medication_name_allowed(name):
        reasons.append("invalid_med_name")
    if name and name[0].islower():
        reasons.append("name_not_capitalized")
    if len(name.split()) > 2:
        reasons.append("long_med_name")
    if len(instruction) < 20:
        reasons.append("short_instruction")
    if not has_medication_signal(instruction):
        reasons.append("no_medication_signal")
    if not dosage_text:
        reasons.append("missing_dosage")
    med_like = set(re.findall(r"[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9®\-]{3,}", instruction))
    if len(med_like) >= 2:
        reasons.append("multi_medication_chunk")
    if len(DOSAGE_RE.findall(instruction)) > 1:
        reasons.append("multi_medication_chunk")
    if has_mojibake(instruction):
        reasons.append("mojibake_suspected")
    return reasons


def collect_full_extraction_by_doc() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in REPORTS_DIR.glob("full_extraction_*.json"):
        try:
            payload = load_json(path)
        except Exception:
            continue
        doc_id = str(payload.get("doc_id") or "").strip()
        if doc_id:
            out[doc_id] = payload
    return out


def source_for_doc(
    doc_id: str,
    registry_by_doc: dict[str, dict[str, Any]],
    fallback_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reg = registry_by_doc.get(doc_id, {})
    source = (fallback_source or {}).copy()
    if not source:
        source = {
            "document_id": doc_id,
            "file_name": reg.get("file_name"),
            "relative_path": ((reg.get("source") or {}).get("relative_path")),
            "ingested_at": ((reg.get("source") or {}).get("registered_at")),
        }
    source.setdefault("document_id", doc_id)
    source.setdefault("file_name", reg.get("file_name"))
    source.setdefault("relative_path", ((reg.get("source") or {}).get("relative_path")))
    return source


def build_lab_facts(
    registry_by_doc: dict[str, dict[str, Any]],
    full_by_doc: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path in sorted(LABS_DIR.glob("lab_full_doc_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue

        doc_id = str(payload.get("doc_id") or "").strip()
        if not doc_id:
            continue
        reg = registry_by_doc.get(doc_id, {})
        source = source_for_doc(doc_id, registry_by_doc)
        legacy_review_required = bool((payload.get("quality") or {}).get("review_required"))
        legacy_review_state = "needs_review" if legacy_review_required else "auto_accepted"
        event_date = iso_from_ddmmyyyy(str(reg.get("event_date_raw") or "")) if reg else None
        raw_text = str((full_by_doc.get(doc_id) or {}).get("raw_text_excerpt") or "")

        idx = 0
        for section in payload.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("name") or "section")
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                idx += 1
                parameter = normalize_space(str(item.get("parameter") or ""))
                result_text = normalize_space(str(item.get("result") or ""))
                reference = normalize_space(str(item.get("reference") or ""))
                parameter, reference = normalize_lab_parameter_and_reference(parameter, reference)
                unit = normalize_space(str(item.get("unit") or "")) or None
                value_num = parse_numeric_value(result_text)

                qa_reasons = lab_qa_reasons(parameter, result_text, value_num, reference)
                qa_status = qa_from_reasons(
                    [x for x in qa_reasons if x not in {"missing_reference", "short_analyte"}]
                )

                confidence = 0.9
                if qa_status == "needs_review":
                    confidence -= 0.22
                if legacy_review_required:
                    confidence -= 0.06
                if "missing_reference" in qa_reasons:
                    confidence -= 0.04

                evidence = make_evidence_excerpt(raw_text, f"{parameter} {result_text}".strip())

                rows.append(
                    {
                        "fact_id": f"fact_lab_{doc_id.replace('doc_', '')}_{idx:04d}",
                        "fact_type": "lab_result",
                        "patient_id": "self",
                        "doc_id": doc_id,
                        "doc_type": str(reg.get("doc_type") or "lab_report"),
                        "event_date": event_date,
                        "legacy_review_state": legacy_review_state,
                        "qa_status": qa_status,
                        "qa_reasons": qa_reasons,
                        "confidence": clamp_confidence(confidence),
                        "source": source,
                        "evidence_excerpt": evidence,
                        "section_name": section_name,
                        "analyte_name": parameter,
                        "value_text": result_text,
                        "value_num": value_num,
                        "unit": unit,
                        "reference_range_text": reference or None,
                        "abnormal_flag": has_abnormal_flag(result_text),
                    }
                )
    return rows


def build_clinical_facts(
    registry_by_doc: dict[str, dict[str, Any]],
    full_by_doc: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path in sorted(DOCTOR_DIR.glob("doctor_conclusion_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue

        source_payload = payload.get("source") or {}
        doc_id = str(source_payload.get("document_id") or payload.get("doc_id") or "").strip()
        if not doc_id:
            continue
        reg = registry_by_doc.get(doc_id, {})
        source = source_for_doc(doc_id, registry_by_doc, source_payload)
        status = str(payload.get("status") or "").strip()
        legacy_review_state = "needs_review" if status == "needs_review" else "auto_accepted"
        event_date = str(payload.get("event_date") or "") or iso_from_ddmmyyyy(str(reg.get("event_date_raw") or ""))
        raw_text = str((full_by_doc.get(doc_id) or {}).get("raw_text_excerpt") or "")
        specialty = str(payload.get("specialty") or "").strip() or None

        pieces: list[tuple[str, str]] = []
        for field_name, fact_subtype in (
            ("conclusion_text", "conclusion"),
            ("diagnosis_text", "diagnosis"),
            ("findings_text", "findings"),
        ):
            text = normalize_space(str(payload.get(field_name) or ""))
            if text:
                pieces.append((fact_subtype, text))

        for idx, (subtype, text) in enumerate(pieces, start=1):
            if is_excluded_condition_text(text):
                continue
            qa_reasons = clinical_qa_reasons(text, subtype)
            qa_status = qa_from_reasons(qa_reasons)

            confidence = 0.88
            if qa_status == "needs_review":
                confidence -= 0.2
            if legacy_review_state == "needs_review":
                confidence -= 0.06

            evidence = make_evidence_excerpt(raw_text, text)
            rows.append(
                {
                    "fact_id": f"fact_clinical_{doc_id.replace('doc_', '')}_{idx:03d}",
                    "fact_type": "clinical_finding",
                    "finding_type": subtype,
                    "patient_id": "self",
                    "doc_id": doc_id,
                    "doc_type": str(reg.get("doc_type") or "doctor_consultation"),
                    "event_date": event_date or None,
                    "legacy_review_state": legacy_review_state,
                    "qa_status": qa_status,
                    "qa_reasons": qa_reasons,
                    "confidence": clamp_confidence(confidence),
                    "source": source,
                    "evidence_excerpt": evidence,
                    "specialty": specialty,
                    "text": text,
                }
            )
    return rows


def build_recommendation_facts(
    registry_by_doc: dict[str, dict[str, Any]],
    full_by_doc: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path in sorted(RECS_DIR.glob("recommendation_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue

        source_payload = payload.get("source") or {}
        doc_id = str(source_payload.get("document_id") or payload.get("doc_id") or "").strip()
        if not doc_id:
            continue
        reg = registry_by_doc.get(doc_id, {})
        source = source_for_doc(doc_id, registry_by_doc, source_payload)
        status = str(payload.get("status") or "").strip()
        legacy_review_state = "needs_review" if status == "needs_review" else "auto_accepted"
        event_date = str(payload.get("event_date") or "") or iso_from_ddmmyyyy(str(reg.get("event_date_raw") or ""))
        raw_text = str((full_by_doc.get(doc_id) or {}).get("raw_text_excerpt") or "")
        full_text = normalize_space(str(payload.get("recommendation_text") or ""))
        parts = split_recommendation_items(full_text) or ([full_text] if full_text else [])

        for idx, part in enumerate(parts, start=1):
            qa_reasons = recommendation_qa_reasons(part)
            qa_status = qa_from_reasons([x for x in qa_reasons if x not in {"signature_noise"}])

            confidence = 0.86
            if qa_status == "needs_review":
                confidence -= 0.18
            if legacy_review_state == "needs_review":
                confidence -= 0.06

            evidence = make_evidence_excerpt(raw_text, part)
            rows.append(
                {
                    "fact_id": f"fact_reco_{doc_id.replace('doc_', '')}_{idx:03d}",
                    "fact_type": "recommendation_item",
                    "patient_id": "self",
                    "doc_id": doc_id,
                    "doc_type": str(reg.get("doc_type") or "doctor_consultation"),
                    "event_date": event_date or None,
                    "legacy_review_state": legacy_review_state,
                    "qa_status": qa_status,
                    "qa_reasons": qa_reasons,
                    "confidence": clamp_confidence(confidence),
                    "source": source,
                    "evidence_excerpt": evidence,
                    "priority": payload.get("priority"),
                    "due_date": payload.get("due_date"),
                    "text": part,
                    "source_recommendation_text": full_text,
                }
            )
    return rows


def build_medication_facts(
    registry_by_doc: dict[str, dict[str, Any]],
    full_by_doc: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dedupe_keys: set[tuple[str, str]] = set()

    for path in sorted(RECS_DIR.glob("recommendation_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue

        source_payload = payload.get("source") or {}
        doc_id = str(source_payload.get("document_id") or payload.get("doc_id") or "").strip()
        if not doc_id:
            continue

        reg = registry_by_doc.get(doc_id, {})
        source = source_for_doc(doc_id, registry_by_doc, source_payload)
        status = str(payload.get("status") or "").strip()
        legacy_review_state = "needs_review" if status == "needs_review" else "auto_accepted"
        event_date = str(payload.get("event_date") or "") or iso_from_ddmmyyyy(str(reg.get("event_date_raw") or ""))
        raw_text = str((full_by_doc.get(doc_id) or {}).get("raw_text_excerpt") or "")
        recommendation_id = str(payload.get("id") or "")
        full_text = normalize_space(str(payload.get("recommendation_text") or ""))
        if not full_text:
            continue

        segments = extract_medication_segments(full_text)
        if not segments:
            continue

        med_idx = 0
        for med_name_raw, segment in segments:
            med_name = normalize_med_name(med_name_raw)
            if not medication_name_allowed(med_name):
                continue

            dedupe_key = (doc_id, normalize_space(segment).lower())
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)

            fields = extract_medication_fields(segment)
            qa_reasons = medication_qa_reasons(med_name, segment, fields["dosage_text"])
            qa_status = qa_from_reasons(
                [x for x in qa_reasons if x not in {"short_instruction"}]
            )

            confidence = 0.82
            if qa_status == "needs_review":
                confidence -= 0.2
            if legacy_review_state == "needs_review":
                confidence -= 0.06
            if "missing_dosage" in qa_reasons:
                confidence -= 0.05

            med_idx += 1
            evidence = make_evidence_excerpt(raw_text, segment)
            rows.append(
                {
                    "fact_id": f"fact_med_{doc_id.replace('doc_', '')}_{med_idx:03d}",
                    "fact_type": "medication_item",
                    "patient_id": "self",
                    "doc_id": doc_id,
                    "doc_type": str(reg.get("doc_type") or "doctor_consultation"),
                    "event_date": event_date or None,
                    "legacy_review_state": legacy_review_state,
                    "qa_status": qa_status,
                    "qa_reasons": qa_reasons,
                    "confidence": clamp_confidence(confidence),
                    "source": source,
                    "source_recommendation_id": recommendation_id or None,
                    "evidence_excerpt": evidence,
                    "medication_name": med_name,
                    "dosage_text": fields["dosage_text"],
                    "frequency_text": fields["frequency_text"],
                    "duration_text": fields["duration_text"],
                    "route": fields["route"],
                    "instruction_text": segment,
                }
            )
    return rows


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        out[name] = out.get(name, 0) + 1
    return out


def main() -> None:
    run_ts = now_utc()
    registry = load_json(REGISTRY_PATH)
    registry_by_doc: dict[str, dict[str, Any]] = {
        str(row.get("id") or "").strip(): row
        for row in registry
        if str(row.get("id") or "").strip()
    }
    full_by_doc = collect_full_extraction_by_doc()

    lab_rows = build_lab_facts(registry_by_doc, full_by_doc)
    clinical_rows = build_clinical_facts(registry_by_doc, full_by_doc)
    reco_rows = build_recommendation_facts(registry_by_doc, full_by_doc)
    med_rows = build_medication_facts(registry_by_doc, full_by_doc)

    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    labs_path = FACTS_DIR / "lab_results_v1.ndjson"
    clinical_path = FACTS_DIR / "clinical_findings_v1.ndjson"
    reco_path = FACTS_DIR / "recommendation_items_v1.ndjson"
    meds_path = FACTS_DIR / "medication_items_v1.ndjson"
    summary_path = FACTS_DIR / "fact_layer_v1_summary.json"
    preview_path = REPORTS_DIR / "fact_layer_v1_preview.json"

    write_ndjson(labs_path, lab_rows)
    write_ndjson(clinical_path, clinical_rows)
    write_ndjson(reco_path, reco_rows)
    write_ndjson(meds_path, med_rows)

    summary = {
        "generated_at": run_ts,
        "batch_id": BATCH_ID,
        "inputs": {
            "active_documents": len(registry_by_doc),
            "full_extraction_docs": len(full_by_doc),
            "lab_docs": len(list(LABS_DIR.glob("lab_full_doc_*.json"))),
            "doctor_conclusion_docs": len(list(DOCTOR_DIR.glob("doctor_conclusion_*.json"))),
            "recommendation_docs": len(list(RECS_DIR.glob("recommendation_*.json"))),
        },
        "outputs": {
            "lab_results_count": len(lab_rows),
            "clinical_findings_count": len(clinical_rows),
            "recommendation_items_count": len(reco_rows),
            "medication_items_count": len(med_rows),
            "legacy_review_state_counts": {
                "lab_results": count_by(lab_rows, "legacy_review_state"),
                "clinical_findings": count_by(clinical_rows, "legacy_review_state"),
                "recommendation_items": count_by(reco_rows, "legacy_review_state"),
                "medication_items": count_by(med_rows, "legacy_review_state"),
            },
            "qa_status_counts": {
                "lab_results": count_by(lab_rows, "qa_status"),
                "clinical_findings": count_by(clinical_rows, "qa_status"),
                "recommendation_items": count_by(reco_rows, "qa_status"),
                "medication_items": count_by(med_rows, "qa_status"),
            },
        },
        "paths": {
            "lab_results": str(labs_path).replace("\\", "/"),
            "clinical_findings": str(clinical_path).replace("\\", "/"),
            "recommendation_items": str(reco_path).replace("\\", "/"),
            "medication_items": str(meds_path).replace("\\", "/"),
            "summary": str(summary_path).replace("\\", "/"),
            "preview": str(preview_path).replace("\\", "/"),
        },
    }
    save_json(summary_path, summary)

    preview = {
        "generated_at": run_ts,
        "counts": summary["outputs"],
        "sample": {
            "lab_results": lab_rows[:25],
            "clinical_findings": clinical_rows[:25],
            "recommendation_items": reco_rows[:25],
            "medication_items": med_rows[:25],
        },
    }
    save_json(preview_path, preview)

    append_ndjson(
        AUDIT_FILE,
        {
            "ts": run_ts,
            "event": "agent_fact_layer_built_v1",
            "batch_id": BATCH_ID,
            "active_documents": len(registry_by_doc),
            "lab_results_count": len(lab_rows),
            "clinical_findings_count": len(clinical_rows),
            "recommendation_items_count": len(reco_rows),
            "medication_items_count": len(med_rows),
            "summary_path": str(summary_path).replace("\\", "/"),
        },
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


