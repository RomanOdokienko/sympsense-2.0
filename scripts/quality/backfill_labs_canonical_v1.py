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
        "card_number": line_value(raw_text, ["№ карты", "N карты", "Номер карты", "Карта"]) or None,
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
        "medical_organization": line_value(raw_text, ["ЛПУ", "Отделение"]) or None,
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
        "Гормональные исследования",
        "Комплексные исследования",
    ]
    low = line.lower()
    return any(h.lower() in low for h in headers)


def should_skip_line(line: str) -> bool:
    low = line.lower()
    skip_tokens = [
        "наименование исследования",
        "результат ед. изм.",
        "нормальные значения",
        "исследование - (",
        "исследованные биоматериалы",
        "анализы выполнены на оборудовании",
        "дата печати результата",
        "номер заказа",
        "№ направления",
        "карта:",
        "пациент",
        "фамилия:",
        "имя:",
        "отчество:",
        "врач кдл",
        "врач клинической",
        "фельдшер-лаборант",
        "исполнитель",
        "рекомендации европейской ассоциации",
        "уровень тестостерона",
        "страница",
        "стр.",
    ]
    return any(token in low for token in skip_tokens)


def normalize_table_line(line: str) -> str:
    src = clean_text(line)
    if not src:
        return ""
    return src


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except Exception:
        return None


def _split_glued_high_and_result(low_raw: str, tail_raw: str) -> tuple[str, str] | None:
    low_val = _to_float(low_raw)
    candidates: list[tuple[int, str, str]] = []
    for idx in range(1, len(tail_raw)):
        high_raw = tail_raw[:idx]
        res_raw = tail_raw[idx:]
        if not re.fullmatch(r"\d+(?:[.,]\d+)?", high_raw):
            continue
        if not re.fullmatch(r"\d+(?:[.,]\d+)?", res_raw):
            continue
        high_val = _to_float(high_raw)
        res_val = _to_float(res_raw)
        if high_val is None or res_val is None:
            continue

        score = 0
        dec_h = len(high_raw.split(".")[-1]) if "." in high_raw else (len(high_raw.split(",")[-1]) if "," in high_raw else 0)
        dec_r = len(res_raw.split(".")[-1]) if "." in res_raw else (len(res_raw.split(",")[-1]) if "," in res_raw else 0)
        if dec_h in (1, 2):
            score += 2
        elif dec_h == 0:
            score += 1
        else:
            score -= 2
        if 0 <= dec_r <= 4:
            score += 1
        if low_val is not None and low_val <= high_val:
            score += 2
        else:
            score -= 6
        if low_val is not None and low_val <= res_val <= high_val:
            score += 7
        else:
            score -= 2
        if high_val > 0 and res_val > (high_val * 5):
            score -= 3
        candidates.append((score, high_raw, res_raw))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, high_raw, res_raw = candidates[0]
    return high_raw, res_raw


def parse_quant_line(line: str) -> dict[str, Any] | None:
    line = normalize_table_line(line)
    if not line:
        return None
    low = line.lower()
    if "нет значения" in low or "не обнаружено" in low or "рекомендации" in low:
        return None

    unit_pat = (
        r"(?:"
        r"нмоль/л|мкмоль/л|ммоль/л|мг/дл|мг/л|г/л|"
        r"мкг/дл|мкг/л|мме/мл|мме/л|ме/мл|ед/л|u/l|пг|"
        r"10\^?\d+/л|в п/зр|%|пг/мл|нг/мл|млн/мкл|фл"
        r")"
    )
    m = re.search(
        rf"(?P<param>.+?)\s+(?P<unit>{unit_pat})\s+"
        r"(?P<ref>\d+[,.]?\d*\s*-\s*\d+[,.]?\d*)\s+"
        r"(?P<result>[↑↓]?\s*-?\d+[,.]?\d*)$",
        line,
        flags=re.IGNORECASE,
    )
    if m:
        parameter = clean_text(m.group("param"))
        if len(parameter) < 3:
            return None
        if not re.search(r"[A-Za-zА-Яа-яЁё]", parameter):
            return None
        if "наименование исследования" in parameter.lower():
            return None
        return {
            "parameter": parameter,
            "result": clean_text(m.group("result")),
            "reference": clean_text(m.group("ref")),
            "unit": clean_text(m.group("unit")),
        }

    # Glued case: unit + low-highResult (without separator between high and result)
    m2 = re.search(
        rf"(?P<param>.+?)\s+(?P<unit>{unit_pat})\s+"
        r"(?P<low>\d+[,.]?\d*)-(?P<tail>\d[\d.,]+)$",
        line,
        flags=re.IGNORECASE,
    )
    if not m2:
        return None

    parameter = clean_text(m2.group("param"))
    if len(parameter) < 3:
        return None
    if not re.search(r"[A-Za-zА-Яа-яЁё]", parameter):
        return None
    if "наименование исследования" in parameter.lower():
        return None

    split = _split_glued_high_and_result(m2.group("low"), m2.group("tail"))
    if not split:
        return None
    high_raw, result_raw = split
    return {
        "parameter": parameter,
        "result": clean_text(result_raw),
        "reference": clean_text(f"{m2.group('low')}-{high_raw}"),
        "unit": clean_text(m2.group("unit")),
    }


def parse_prefixed_quant_line(line: str) -> dict[str, Any] | None:
    line = normalize_table_line(line)
    if not line:
        return None

    unit_pat = (
        r"(?:"
        r"нмоль/л|мкмоль/л|ммоль/л|мг/дл|мг/л|г/л|"
        r"мкг/дл|мкг/л|мме/мл|мме/л|ме/мл|ед/л|u/l|пг|"
        r"10\^?\d+/л|в п/зр|%|пг/мл|нг/мл|млн/мкл|фл|мм/ч"
        r")"
    )
    m = re.search(
        rf"^(?P<ref>\d+[,.]?\d*\s*-\s*\d+[,.]?\d*)(?P<unit>{unit_pat})(?P<param>.+?)\s+(?P<result>[↑↓]?\s*-?\d+[,.]?\d*)$",
        line,
        flags=re.IGNORECASE,
    )
    if not m:
        # Variant without explicit unit before analyte: "1,010 - 1,025SG (...) 1.025"
        m = re.search(
            r"^(?P<ref>\d+[.,]?\d*\s*-\s*\d+[.,]?\d*)(?P<param>(?:[A-ZА-ЯЁ]{1,10}\s*\([^)]+\)|[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9%\-_/().\s]+))\s+(?P<result>[↑↓]?\s*-?\d+[.,]?\d*)$",
            line,
            flags=re.IGNORECASE,
        )
        if not m:
            return None
        parameter = clean_text(m.group("param"))
        if len(parameter) < 2 or not re.search(r"[A-Za-zА-Яа-яЁё]", parameter):
            return None
        return {
            "parameter": parameter,
            "result": clean_text(m.group("result")),
            "reference": clean_text(m.group("ref")),
            "unit": None,
        }
    parameter = clean_text(m.group("param"))
    if len(parameter) < 2 or not re.search(r"[A-Za-zА-Яа-яЁё]", parameter):
        return None
    return {
        "parameter": parameter,
        "result": clean_text(m.group("result")),
        "reference": clean_text(m.group("ref")),
        "unit": clean_text(m.group("unit")),
    }


def parse_qual_line(line: str) -> dict[str, Any] | None:
    line = normalize_table_line(line)
    if not line or len(line) < 8:
        return None

    low = line.lower()
    # Pattern: "<parameter> Нет значения не обнаруженоне обнаружено"
    if "нет значения" in low:
        idx = low.find("нет значения")
        param = clean_text(line[:idx])
        tail = clean_text(line[idx + len("нет значения") :]).lower()
        if len(param) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", param):
            if "не обнаруж" in tail:
                return {"parameter": param, "result": "не обнаружено", "reference": "не обнаружено", "unit": None}
            if "отрицательно" in tail:
                return {"parameter": param, "result": "отрицательно", "reference": "отрицательно", "unit": None}

    qual_words = [
        "не обнаружены",
        "не обнаружено",
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
    if not any(q in low for q in qual_words):
        return None
    if re.search(r"\d+[,.]?\d*\s*-\s*\d+[,.]?\d*", line):
        return None

    for q in qual_words:
        idx = low.rfind(q)
        if idx > 2:
            param = clean_text(line[:idx])
            res = clean_text(line[idx:])
            if len(param) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]", param):
                return {"parameter": param, "result": res, "reference": None, "unit": None}
    return None


def parse_simple_numeric_line(line: str) -> dict[str, Any] | None:
    line = normalize_table_line(line)
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
        "рекомендации",
        "наименование исследования",
        "нормальные значения",
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


def normalize_numeric_token(value: str | None) -> str | None:
    if not value:
        return value
    token = clean_text(value).replace(",", ".")
    if not re.fullmatch(r"[↑↓]?\s*-?\d+(?:\.\d+)?", token):
        return value
    arrow = ""
    token = token.strip()
    if token[:1] in {"↑", "↓"}:
        arrow = token[:1]
        token = token[1:].strip()
    token = re.sub(r"^(-?)0+(?=\d)", r"\1", token)
    if token.startswith("."):
        token = "0" + token
    return f"{arrow}{token}" if arrow else token


def normalize_lab_item(item: dict[str, Any]) -> dict[str, Any]:
    parameter = clean_text(item.get("parameter") or "")
    original_parameter = parameter
    low = parameter.lower()
    if "(пцр)" in low and "днк " in low:
        idx = low.rfind("днк ")
        if idx != -1:
            parameter = clean_text(parameter[idx:])
    # Strip wrappers and broken tails in analyte names.
    if parameter.startswith("(") and parameter.endswith(")") and len(parameter) > 2:
        parameter = parameter[1:-1].strip()
    if parameter.endswith(")") and "(" not in parameter:
        parameter = parameter[:-1].strip()

    item["result"] = normalize_numeric_token(item.get("result")) or item.get("result")

    reference = clean_text(item.get("reference") or "")
    # Handle glued qualitative prefix in parameter: "отрицательномкмоль/лBIL (билирубин)"
    q = re.match(
        r"^(?P<qual>отрицател\w*|положител\w*|норм\w*|не\s*обнаруж\w*|единич\w*)[A-Za-zА-Яа-яЁё0-9/%\^.,-]*?(?P<rest>(?:[A-ZА-ЯЁ]{2,8}\s*\([^)]+\)|[A-Za-zА-Яа-яЁё].+))$",
        parameter,
        flags=re.IGNORECASE,
    )
    if q:
        qual = q.group("qual").lower()
        parameter = clean_text(q.group("rest"))
        core = re.search(r"([A-ZА-ЯЁ]{2,8}\s*\([^)]+\))", parameter)
        if not core:
            core = re.search(r"([A-ZА-ЯЁ]{2,8}\s*\([^)]+\))", original_parameter)
        if core:
            parameter = clean_text(core.group(1))
        if not reference:
            if qual.startswith("отриц"):
                reference = "отрицательно"
            elif qual.startswith("полож"):
                reference = "положительно"
            elif qual.startswith("норм"):
                reference = "норма"
            elif "обнаруж" in qual:
                reference = "не обнаружено"
            elif qual.startswith("единич"):
                reference = "единично"

    # Handle prefixed range+unit in parameter: "120 - 170г/лHGB (...)"
    pref = re.match(
        r"^(?P<ref>\d+[.,]?\d*\s*-\s*\d+[.,]?\d*)(?P<unit>[A-Za-zА-Яа-яЁё0-9/%\^]+)(?P<rest>[A-Za-zА-Яа-яЁё].+)$",
        parameter,
    )
    if pref:
        if not reference:
            reference = clean_text(pref.group("ref"))
        if not item.get("unit"):
            item["unit"] = clean_text(pref.group("unit"))
        parameter = clean_text(pref.group("rest"))

    item["parameter"] = parameter

    m = re.fullmatch(r"(\d+[.,]?\d*)\s*-\s*(\d+[.,]?\d*)", reference)
    if m:
        lo = normalize_numeric_token(m.group(1)) or m.group(1)
        hi = normalize_numeric_token(m.group(2)) or m.group(2)
        item["reference"] = f"{lo}-{hi}"
    elif reference:
        item["reference"] = reference
    return item


def parse_lab_sections(raw_text: str) -> list[dict[str, Any]]:
    lines = [clean_text(x) for x in raw_text.replace("\r", "\n").split("\n")]
    lines = [x for x in lines if x]

    merged: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            continuation_line = (
                cur.count("(") > cur.count(")")
                and re.search(r"\)\s*[↑↓]?\s*-?\d+[.,]?\d*\s*$", nxt) is not None
            ) or (
                cur.endswith(" в")
                and re.search(r"^[а-яё].+\)\s*[↑↓]?\s*-?\d+[.,]?\d*\s*$", nxt, flags=re.IGNORECASE) is not None
            )
            if "исследование - (" not in cur.lower() and parse_quant_line(cur) is None and (
                parse_quant_line(nxt)
                or ("нет значения" in nxt.lower() and parse_qual_line(f"{cur} {nxt}") is not None)
                or continuation_line
            ):
                cur = f"{cur} {nxt}"
                i += 1
        merged.append(cur)
        i += 1
    lines = merged

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

        item = parse_quant_line(line) or parse_prefixed_quant_line(line) or parse_qual_line(line) or parse_simple_numeric_line(line)
        if item:
            current["items"].append(normalize_lab_item(item))

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


def bad_item_count(sections: list[dict[str, Any]]) -> int:
    bad = 0
    for section in sections:
        for item in (section or {}).get("items") or []:
            parameter = clean_text(item.get("parameter") or "").lower()
            result = clean_text(item.get("result") or "").lower()
            if not parameter:
                bad += 1
                continue
            if len(parameter) < 3:
                bad += 1
                continue
            if "наименование исследования" in parameter:
                bad += 1
                continue
            if "нормальные значения" in result:
                bad += 1
                continue
    return bad


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

        existing_bad = bad_item_count(existing_sections)
        parsed_bad = bad_item_count(parsed_sections)
        prefer_parsed = parsed_count > 0 and (
            parsed_count >= existing_count
            or parsed_bad < existing_bad
        )
        final_sections = parsed_sections if prefer_parsed else existing_sections
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

        out_path = existing_files[0] if existing_files else (ctx.labs_dir / f"lab_full_doc_{stem}.json")
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
