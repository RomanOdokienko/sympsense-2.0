from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Ctx:
    registry_path: Path
    reports_dir: Path
    labs_dir: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(text: str) -> str:
    return " ".join(str(text or "").replace("\r", "\n").replace("\t", " ").split())


def line_value(text: str, labels: list[str]) -> str | None:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*:\s*(.+)", text, flags=re.IGNORECASE)
        if m:
            return clean_text(m.group(1))
    return None


def extract_patient_and_encounter(raw_text: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    patient = {
        "full_name": line_value(raw_text, ["Пациент"]) or None,
        "sex": None,
        "birth_date": None,
        "age_years": None,
        "card_number": line_value(raw_text, ["№ карты", "N карты", "Номер карты"]) or None,
        "sample_number": line_value(raw_text, ["Номер пробы"]) or None,
    }

    birth_line = line_value(raw_text, ["Дата рождения"])
    if birth_line:
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})", birth_line)
        patient["birth_date"] = m.group(1) if m else None
        m_age = re.search(r"\((\d+)\s*г", birth_line)
        patient["age_years"] = int(m_age.group(1)) if m_age else None
        m_sex = re.search(r"Пол\s*:\s*([А-Яа-яA-Za-z]+)", raw_text)
        patient["sex"] = clean_text(m_sex.group(1)) if m_sex else None

    encounter = {
        "facility": line_value(raw_text, ["Отделение"]) or None,
        "medical_organization": line_value(raw_text, ["Отделение"]) or None,
        "department": None,
        "ordering_doctor": line_value(raw_text, ["Врач"]) or None,
        "sample_taken_at": line_value(raw_text, ["Дата взятия образца"]) or None,
        "result_issued_at": line_value(raw_text, ["Дата выдачи результата"]) or None,
        "result_printed_at": line_value(raw_text, ["Дата печати результата"]) or None,
    }

    metadata = {
        "biomaterial": line_value(raw_text, ["Исследованные биоматериалы"]) or None,
        "equipment": line_value(raw_text, ["Анализы выполнены на оборудовании"]) or None,
        "lab_doctor": None,
        "lab_technician": None,
    }
    return patient, encounter, metadata


def is_section_header(line: str) -> bool:
    headers = [
        "Биохимия крови",
        "Общий анализ крови",
        "Общий анализ мочи",
        "Микроскопия осадка мочи",
        "Копрология",
        "Серологическая диагностика",
        "Глистные инвазии",
        "Протозоозы",
    ]
    line_l = line.lower()
    return any(h.lower() in line_l for h in headers)


def should_skip_line(line: str) -> bool:
    low = line.lower()
    skip_tokens = [
        "параметр результат референсные",
        "исследованные биоматериалы",
        "анализы выполнены на оборудовании",
        "дата печати результата",
        "врач клинической",
        "фельдшер-лаборант",
        "исполнитель",
        "страница",
        "стр.",
    ]
    return any(token in low for token in skip_tokens)


def parse_quant_line(line: str) -> dict[str, Any] | None:
    line = clean_text(line)
    # OCR often glues unit and parameter: "...ммоль/лМочевая..." -> "...ммоль/л Мочевая..."
    line = re.sub(
        r"(ммоль/л|мкмоль/л|г/л|мг/л|ед/л|Ед/л|10\^?\d+/л|в п/зр)([A-ZА-ЯЁ])",
        r"\1 \2",
        line,
    )
    if not line:
        return None

    ref_match = re.search(
        r"(\d+[,.]?\d*\s*-\s*\d+[,.]?\d*(?:\s*(?:ммоль/л|мкмоль/л|г/л|мг/л|ед/л|Ед/л|10\^?\d+/л|в п/зр|%))?)",
        line,
    )
    result_match = re.search(r"([↑↓]?\s*-?\d+[,.]?\d*)\s*$", line)
    if not ref_match or not result_match:
        return None
    if result_match.start() <= ref_match.end():
        return None

    parameter = clean_text(line[ref_match.end(): result_match.start()])
    if len(parameter) < 2:
        return None
    if not re.search(r"[A-Za-zА-Яа-яЁё]", parameter):
        return None

    return {
        "parameter": parameter,
        "result": clean_text(result_match.group(1)),
        "reference": clean_text(ref_match.group(1)),
        "unit": None,
    }


def parse_qual_line(line: str) -> dict[str, Any] | None:
    line = clean_text(line)
    if not line or len(line) < 8:
        return None

    qual_words = [
        "не обнаружены",
        "не обнаружен",
        "отрицательно",
        "норма",
        "прозрачная",
        "янтарный",
        "желтый",
        "единичный",
        "отсутствуют",
        "отсутствует",
    ]
    low = line.lower()
    if not any(q in low for q in qual_words):
        return None
    if re.search(r"\d+[,.]?\d*\s*-\s*\d+[,.]?\d*", line):
        return None

    # Pattern: "<parameter> <result_word>".
    for q in qual_words:
        idx = low.rfind(q)
        if idx > 2:
            param = clean_text(line[:idx])
            res = clean_text(line[idx:])
            if len(param) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", param):
                return {
                    "parameter": param,
                    "result": res,
                    "reference": None,
                    "unit": None,
                }

    # Pattern: "<result_word><parameter><result_word>" (OCR glued).
    for q in qual_words:
        ql = q.lower()
        if low.startswith(ql) and low.endswith(ql) and len(line) > (2 * len(q)) + 2:
            mid = clean_text(line[len(q): len(line) - len(q)])
            if len(mid) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", mid):
                return {
                    "parameter": mid,
                    "result": q,
                    "reference": q,
                    "unit": None,
                }

    # Pattern: "<result_word><parameter>" (OCR glued, no trailing repeated token).
    for q in qual_words:
        ql = q.lower()
        if low.startswith(ql) and len(line) > len(q) + 2:
            tail = clean_text(line[len(q):])
            if len(tail) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", tail):
                return {
                    "parameter": tail,
                    "result": q,
                    "reference": q,
                    "unit": None,
                }
    return None


def normalize_glued_qual_item(item: dict[str, Any]) -> dict[str, Any]:
    parameter = clean_text(item.get("parameter"))
    result = clean_text(item.get("result"))
    reference = clean_text(item.get("reference")) if item.get("reference") else None

    # Example: "не обнаруженыПростейшие" + result "не обнаружены"
    if parameter and result and parameter.startswith(result) and len(parameter) > len(result):
        tail = parameter[len(result):]
        if tail and not tail[:1].isspace() and tail[:1].isupper():
            tail = clean_text(tail.lstrip(":-–—,.;"))
            if len(tail) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", tail):
                item["parameter"] = tail
                item["result"] = result
                item["reference"] = reference or result

    return item


def parse_simple_numeric_line(line: str) -> dict[str, Any] | None:
    line = clean_text(line)
    if not line:
        return None

    low = line.lower()
    skip_tokens = [
        "дата",
        "заказ",
        "пациент",
        "пол",
        "рождения",
        "страница",
        "стр.",
        "референсные",
        "не обнаружено",
        "погранич",
        "обнаружено",
    ]
    if any(tok in low for tok in skip_tokens):
        return None

    m = re.search(
        r"(?P<param>[A-Za-zА-Яа-яЁё0-9\-\(\),\s\./]+?)\s+(?P<result>[↑↓]?\s*-?\d+[,.]?\d*)\s*(?P<unit>[A-Za-zА-Яа-яЁё/%\.]+)?$",
        line,
    )
    if not m:
        return None
    param = clean_text(m.group("param"))
    if len(param) < 4:
        return None
    if not re.search(r"[A-Za-zА-Яа-яЁё]", param):
        return None

    return {
        "parameter": param,
        "result": clean_text(m.group("result")),
        "reference": None,
        "unit": clean_text(m.group("unit")) if m.group("unit") else None,
    }


def parse_lab_sections(raw_text: str) -> list[dict[str, Any]]:
    lines = [clean_text(x) for x in raw_text.replace("\r", "\n").split("\n")]
    lines = [x for x in lines if x]

    sections: list[dict[str, Any]] = []
    current = {"name": "Лабораторные показатели", "items": []}
    sections.append(current)

    for line in lines:
        if is_section_header(line):
            if current["items"]:
                current = {"name": line, "items": []}
                sections.append(current)
            else:
                current["name"] = line
            continue
        if should_skip_line(line):
            continue

        item = parse_quant_line(line) or parse_qual_line(line) or parse_simple_numeric_line(line)
        if item:
            current["items"].append(normalize_glued_qual_item(item))

    # De-duplicate items within each section.
    for section in sections:
        seen: set[tuple[str, str, str]] = set()
        uniq: list[dict[str, Any]] = []
        for item in section["items"]:
            key = (
                str(item.get("parameter") or "").lower(),
                str(item.get("result") or "").lower(),
                str(item.get("reference") or "").lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)
        section["items"] = uniq

    return [s for s in sections if s["items"]]


def section_item_count(sections: list[dict[str, Any]]) -> int:
    return sum(len((s or {}).get("items") or []) for s in sections)


def main() -> None:
    ctx = Ctx(
        registry_path=Path("data/canonical/documents/batch_01_registry_active.json"),
        reports_dir=Path("data/derived/reports"),
        labs_dir=Path("data/canonical/labs"),
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

    changed: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in registry:
        if str(row.get("doc_type") or "") != "lab_report":
            continue
        doc_id = str(row.get("id") or "").strip()
        if not doc_id:
            continue

        full = full_by_doc.get(doc_id)
        if not full:
            continue
        raw_text = str(full.get("raw_text_excerpt") or "")
        if not raw_text:
            continue

        stem = doc_id.replace("doc_", "")
        existing_files = list(ctx.labs_dir.glob(f"*{stem}*.json"))
        existing = load_json(existing_files[0]) if existing_files else {}
        existing_sections = existing.get("sections") or []
        existing_count = section_item_count(existing_sections)

        parsed_sections = parse_lab_sections(raw_text)
        parsed_count = section_item_count(parsed_sections)

        final_sections = parsed_sections if parsed_count >= existing_count else existing_sections
        final_count = section_item_count(final_sections)

        patient, encounter, metadata = extract_patient_and_encounter(raw_text)
        quality_old = existing.get("quality") or {}
        quality = {
            "extraction_mode": quality_old.get("extraction_mode") or "agent_backfill_from_full_extraction_text",
            "review_required": bool(quality_old.get("review_required", True)),
            "notes": "Backfilled lab markers from full_extraction raw text; verify numeric markers with source.",
        }

        payload = {
            "record_id": f"lab_{stem}",
            "doc_id": doc_id,
            "source_file": str(full.get("source_file") or row.get("file_name") or ""),
            "source_path": str(full.get("source_path") or (row.get("source") or {}).get("relative_path") or ""),
            "doc_type": "lab_report",
            "parsed_at": str(full.get("parsed_at") or now),
            "patient": patient,
            "encounter": encounter,
            "sections": final_sections,
            "metadata": metadata,
            "quality": quality,
        }

        if existing_files:
            out_path = existing_files[0]
        else:
            out_path = ctx.labs_dir / f"lab_full_doc_{stem}.json"
        save_json(out_path, payload)

        changed.append(
            {
                "doc_id": doc_id,
                "file": str(out_path).replace("\\", "/"),
                "existing_items": existing_count,
                "parsed_items": parsed_count,
                "final_items": final_count,
            }
        )

    print(json.dumps({"processed": len(changed), "docs": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
