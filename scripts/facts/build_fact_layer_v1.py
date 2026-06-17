from __future__ import annotations

import hashlib
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


def iso_from_registry_date(raw: str | None) -> str | None:
    value = normalize_space(str(raw or ""))
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


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


CBC_SECTION_RE = re.compile(
    r"(?:клиническ\w*\s+анализ\w*\s+кров|общ\w*\s+анализ\w*\s+кров|cbc)",
    flags=re.IGNORECASE,
)

CBC_CODE_RE = re.compile(
    r"\b(?:WBC|RBC|HGB|HB|HCT|MCV|MCHC|MCH|RDW|PLT|MPV|PCT|PDW|NEU|LYM|MONO|EOS|BAS|IG|NRBC)\b",
    flags=re.IGNORECASE,
)

CBC_ANALYTE_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("wbc", "Лейкоциты", ("wbc", "лейкоцит")),
    ("hemoglobin", "Гемоглобин", ("hgb", "гемоглобин")),
    ("hematocrit", "Гематокрит", ("hct", "гематокрит")),
    ("mcv", "Средний объем эритроцита", ("mcv", "средний объем эритроцита", "ср.объем эритроцита")),
    ("mchc", "Средняя концентрация Hb в эритроците", ("mchc", "средняя концентрация", "ср. концентрация")),
    ("mch", "Среднее содержание Hb в эритроците", ("mch", "среднее содержание", "ср. содержание")),
    ("rdw_sd", "RDW-SD", ("rdw-sd",)),
    ("rdw_cv", "RDW-CV", ("rdw-cv", "rdw")),
    ("rbc", "Эритроциты", ("rbc", "эритроцит")),
    ("mpv", "Средний объем тромбоцита", ("mpv", "средний объем тромбоцита")),
    ("plateletcrit", "Тромбокрит", ("тромбокрит", "pct")),
    ("pdw", "PDW", ("pdw", "индекс распределения тромбоцитов", "ширина распределения тромбоцитов")),
    ("platelets", "Тромбоциты", ("plt", "тромбоцит")),
    ("neutrophils", "Нейтрофилы", ("neu", "нейтрофил")),
    ("lymphocytes", "Лимфоциты", ("lym", "лимфоцит")),
    ("monocytes", "Моноциты", ("mono", "моноцит")),
    ("eosinophils", "Эозинофилы", ("eos", "эозинофил")),
    ("basophils", "Базофилы", ("bas", "базофил")),
    ("immature_granulocytes", "Незрелые гранулоциты", ("незрелые гранулоциты",)),
    ("normoblasts", "Нормобласты", ("нормобласт",)),
    ("esr", "СОЭ", ("соэ",)),
)

CBC_DIFFERENTIAL_ANALYTES = {
    "neutrophils",
    "lymphocytes",
    "monocytes",
    "eosinophils",
    "basophils",
    "immature_granulocytes",
    "normoblasts",
}


def is_cbc_context(parameter: str, section_name: str) -> bool:
    return bool(CBC_SECTION_RE.search(section_name or "") or CBC_CODE_RE.search(parameter or ""))


def infer_cbc_lab_normalization(parameter: str, section_name: str, unit: str | None) -> dict[str, str | None]:
    """Return additive normalized lab fields for CBC rows without changing source names."""

    if not is_cbc_context(parameter, section_name):
        return {}

    p = normalize_space(parameter).lower().replace("ё", "е")
    unit_l = normalize_space(unit or "").lower()

    analyte_id: str | None = None
    label: str | None = None
    for candidate_id, candidate_label, tokens in CBC_ANALYTE_RULES:
        if any(token in p for token in tokens):
            analyte_id = candidate_id
            label = candidate_label
            break

    if not analyte_id:
        return {}

    method = "manual_microscopy" if re.search(r"микроскоп|палочкоядер|сегментоядер|сегм\.", p) else "analyzer"

    measurement_kind = "value"
    if analyte_id in CBC_DIFFERENTIAL_ANALYTES:
        if "%" in p or "%" in unit_l:
            measurement_kind = "percent"
        elif "#" in p or "абс" in p or "абсолют" in p or "10*9" in unit_l or "x10^9" in unit_l or "тыс/мкл" in unit_l:
            measurement_kind = "absolute"

    if analyte_id in {"wbc", "rbc", "platelets"} and (
        "10*9" in unit_l or "x10^9" in unit_l or "10^9" in unit_l or "10*12" in unit_l or "x10^12" in unit_l
    ):
        measurement_kind = "count"

    return {
        "analyte_id": analyte_id,
        "measurement_kind": measurement_kind,
        "method": method,
        "specimen": "blood",
        "normalized_label": label,
    }


LAB_DUP_VALUE_TOLERANCE_RELATIVE = 0.08


def lab_duplicate_group_key(row: dict[str, Any], include_method: bool = True) -> tuple[str, ...] | None:
    analyte_id = str(row.get("analyte_id") or "").strip()
    measurement_kind = str(row.get("measurement_kind") or "").strip()
    specimen = str(row.get("specimen") or "").strip()
    if not analyte_id or not measurement_kind:
        return None

    key = [
        str(row.get("doc_id") or ""),
        specimen or "unknown_specimen",
        analyte_id,
        measurement_kind,
    ]
    if include_method:
        key.append(str(row.get("method") or "unknown_method"))
    return tuple(key)


def lab_unit_family(unit: str | None) -> str:
    value = normalize_space(unit or "").lower().replace("x10^", "10*").replace("10^", "10*")
    if "%" in value:
        return "%"
    if "10*9" in value or "тыс/мкл" in value:
        return "10*9/л"
    if "10*12" in value or "млн/мкл" in value:
        return "10*12/л"
    return value


def lab_clean_value_text(value: str | None) -> str:
    return normalize_space(value or "").replace("↑", "").replace("↓", "").replace(",", ".").lower()


def lab_normalize_analyte_name(name: str | None) -> str:
    value = normalize_space(name or "").lower().replace("ё", "е")
    value = re.sub(r"^\(?[a-z]{2,8}\s*[#%]?\)?\s*", "", value)
    value = value.replace("микроскопия:", "")
    value = re.sub(r"[(),]+", " ", value)
    return normalize_space(value)


def lab_canonical_key(row: dict[str, Any]) -> str:
    analyte_id = normalize_space(str(row.get("analyte_id") or ""))
    measurement_kind = normalize_space(str(row.get("measurement_kind") or ""))
    specimen = normalize_space(str(row.get("specimen") or ""))
    if analyte_id:
        return "::".join([specimen or "unknown_specimen", analyte_id, measurement_kind or "value"])
    return "::".join(["raw", lab_normalize_analyte_name(str(row.get("analyte_name") or ""))])


def lab_values_close(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, str]:
    if lab_unit_family(str(left.get("unit") or "")) != lab_unit_family(str(right.get("unit") or "")):
        return False, "different_unit"

    left_text = lab_clean_value_text(str(left.get("value_text") or ""))
    right_text = lab_clean_value_text(str(right.get("value_text") or ""))
    if left_text and left_text == right_text:
        return True, "exact_text"

    left_num = left.get("value_num")
    right_num = right.get("value_num")
    if not isinstance(left_num, (int, float)) or not isinstance(right_num, (int, float)):
        return False, "not_numeric"

    denom = max(abs(float(left_num)), abs(float(right_num)), 1e-9)
    relative_delta = abs(float(left_num) - float(right_num)) / denom
    if relative_delta <= LAB_DUP_VALUE_TOLERANCE_RELATIVE:
        return True, "near_numeric"
    return False, "different_value"


def lab_group_id(prefix: str, rows: list[dict[str, Any]], key: tuple[str, ...]) -> str:
    fact_ids = sorted(str(row.get("fact_id") or "") for row in rows)
    raw = "|".join([prefix, *key, *fact_ids])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def lab_primary_score(row: dict[str, Any]) -> tuple[int, str]:
    name = str(row.get("analyte_name") or "")
    score = 0
    if re.match(r"^\(?[A-Z]{2,8}\s*[#%]?\)?", name):
        score += 100
    if str(row.get("method") or "") == "analyzer":
        score += 10
    if str(row.get("qa_status") or "") == "ok":
        score += 5
    return score, str(row.get("fact_id") or "")


def lab_cross_document_group_key(row: dict[str, Any]) -> tuple[str, str, str, str] | None:
    bundle_id = normalize_space(str(row.get("document_bundle_id") or ""))
    if not bundle_id:
        return None

    canonical_key = lab_canonical_key(row)
    if canonical_key in {"raw::", "raw"}:
        return None

    value_text = lab_clean_value_text(str(row.get("value_text") or ""))
    unit = lab_unit_family(str(row.get("unit") or ""))
    if not value_text:
        return None
    return bundle_id, canonical_key, value_text, unit


def lab_cross_document_primary_score(row: dict[str, Any], rows_by_doc: dict[str, int]) -> tuple[int, int, str]:
    doc_id = str(row.get("doc_id") or "")
    score = rows_by_doc.get(doc_id, 0)
    source = row.get("source") or {}
    file_name = str(source.get("file_name") or "")
    if str(row.get("qa_status") or "") == "ok":
        score += 1
    return score, -len(file_name), str(row.get("fact_id") or "")


def close_components(rows: list[dict[str, Any]], require_different_method: bool = False) -> list[tuple[list[dict[str, Any]], str]]:
    parent = list(range(len(rows)))
    reasons: dict[int, str] = {}

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(left: int, right: int, reason: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            reasons[root_left] = reasons.get(root_left, reason)
            return
        parent[root_right] = root_left
        reasons[root_left] = reason if reason == "exact_text" else reasons.get(root_left, reason)

    for i, left in enumerate(rows):
        for j in range(i + 1, len(rows)):
            right = rows[j]
            if require_different_method and str(left.get("method") or "") == str(right.get("method") or ""):
                continue
            is_close, reason = lab_values_close(left, right)
            if is_close:
                union(i, j, reason)

    grouped: dict[int, list[dict[str, Any]]] = {}
    for idx, row in enumerate(rows):
        grouped.setdefault(find(idx), []).append(row)

    out: list[tuple[list[dict[str, Any]], str]] = []
    for root, component in grouped.items():
        if len(component) > 1:
            out.append((component, reasons.get(find(root), "near_numeric")))
    return out


def annotate_intra_doc_lab_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["duplicate_group_id"] = None
        row["duplicate_role"] = None
        row["duplicate_of_fact_id"] = None
        row["duplicate_reason"] = None

    by_same_method: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    by_analyte: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        same_method_key = lab_duplicate_group_key(row, include_method=True)
        analyte_key = lab_duplicate_group_key(row, include_method=False)
        if same_method_key:
            by_same_method.setdefault(same_method_key, []).append(row)
        if analyte_key:
            by_analyte.setdefault(analyte_key, []).append(row)

    for key, items in by_same_method.items():
        if len(items) < 2:
            continue
        for component, reason in close_components(items):
            group_id = lab_group_id("labdup", component, key)
            primary = max(component, key=lab_primary_score)
            primary["duplicate_group_id"] = group_id
            primary["duplicate_role"] = "primary"
            primary["duplicate_reason"] = f"same_doc_same_method_{reason}"
            for row in component:
                if row is primary:
                    continue
                row["duplicate_group_id"] = group_id
                row["duplicate_role"] = "duplicate"
                row["duplicate_of_fact_id"] = primary.get("fact_id")
                row["duplicate_reason"] = f"same_doc_same_method_{reason}"

    for key, items in by_analyte.items():
        if len(items) < 2:
            continue
        for component, reason in close_components(items, require_different_method=True):
            group_id = lab_group_id("labrel", component, key)
            for row in component:
                if row.get("duplicate_role"):
                    continue
                row["duplicate_group_id"] = group_id
                row["duplicate_role"] = "related"
                row["duplicate_reason"] = f"same_doc_different_method_{reason}"

    return rows


def annotate_cross_document_lab_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["cross_document_duplicate_group_id"] = None
        row["cross_document_duplicate_role"] = None
        row["cross_document_duplicate_of_fact_id"] = None
        row["cross_document_duplicate_reason"] = None

    rows_by_doc: dict[str, int] = {}
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "")
        rows_by_doc[doc_id] = rows_by_doc.get(doc_id, 0) + 1
        key = lab_cross_document_group_key(row)
        if key:
            grouped.setdefault(key, []).append(row)

    for key, items in grouped.items():
        doc_ids = {str(row.get("doc_id") or "") for row in items}
        if len(doc_ids) < 2:
            continue

        group_id = lab_group_id("labxdocdup", items, key)
        primary = max(items, key=lambda row: lab_cross_document_primary_score(row, rows_by_doc))
        primary["cross_document_duplicate_group_id"] = group_id
        primary["cross_document_duplicate_role"] = "primary"
        primary["cross_document_duplicate_reason"] = "same_bundle_same_canonical_value_unit"

        for row in items:
            if row is primary:
                continue
            row["cross_document_duplicate_group_id"] = group_id
            row["cross_document_duplicate_role"] = "duplicate"
            row["cross_document_duplicate_of_fact_id"] = primary.get("fact_id")
            row["cross_document_duplicate_reason"] = "same_bundle_same_canonical_value_unit"

    return rows


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


def build_document_bundle_index(
    registry_by_doc: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in registry_by_doc.values():
        patient_id = str(row.get("patient_id") or "self").strip()
        event_date = (
            iso_from_registry_date(str(row.get("document_date") or ""))
            or iso_from_registry_date(str(row.get("event_date_raw") or ""))
        )
        doc_type = str(row.get("doc_type") or "unknown").strip()
        doc_id = str(row.get("id") or "").strip()
        if not patient_id or not event_date or not doc_type or not doc_id:
            continue
        grouped.setdefault((patient_id, event_date, doc_type), []).append(row)

    bundle_by_doc: dict[str, dict[str, Any]] = {}
    bundles: list[dict[str, Any]] = []
    for (patient_id, event_date, doc_type), docs in sorted(grouped.items()):
        if len(docs) < 2:
            continue
        doc_ids = sorted(str(row.get("id") or "") for row in docs if str(row.get("id") or ""))
        raw_id = "|".join(["docbundle", patient_id, event_date, doc_type, *doc_ids])
        bundle_id = f"docbundle_{hashlib.sha1(raw_id.encode('utf-8')).hexdigest()[:12]}"
        bundle_key = "::".join([patient_id, event_date, doc_type])
        meta = {
            "document_bundle_id": bundle_id,
            "document_bundle_key": bundle_key,
            "patient_id": patient_id,
            "event_date": event_date,
            "doc_type": doc_type,
            "document_count": len(doc_ids),
            "doc_ids": doc_ids,
            "file_names": [str(row.get("file_name") or "") for row in docs],
            "medical_organizations": sorted(
                {
                    str(row.get("medical_organization") or "").strip()
                    for row in docs
                    if str(row.get("medical_organization") or "").strip()
                }
            ),
            "departments": sorted(
                {
                    str(row.get("department") or "").strip()
                    for row in docs
                    if str(row.get("department") or "").strip()
                }
            ),
        }
        bundles.append(meta)
        for doc_id in doc_ids:
            bundle_by_doc[doc_id] = meta
    return bundle_by_doc, bundles


def annotate_document_bundles(
    rows: list[dict[str, Any]],
    bundle_by_doc: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    for row in rows:
        bundle = bundle_by_doc.get(str(row.get("doc_id") or ""))
        row["document_bundle_id"] = bundle.get("document_bundle_id") if bundle else None
        row["document_bundle_key"] = bundle.get("document_bundle_key") if bundle else None
        row["document_bundle_size"] = bundle.get("document_count") if bundle else None
    return rows


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
                lab_norm = infer_cbc_lab_normalization(parameter, section_name, unit)

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
                        "analyte_id": lab_norm.get("analyte_id"),
                        "measurement_kind": lab_norm.get("measurement_kind"),
                        "method": lab_norm.get("method"),
                        "specimen": lab_norm.get("specimen"),
                        "normalized_label": lab_norm.get("normalized_label"),
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


def lab_result_is_display_primary(row: dict[str, Any]) -> bool:
    return row.get("duplicate_role") != "duplicate" and row.get("cross_document_duplicate_role") != "duplicate"


def main() -> None:
    run_ts = now_utc()
    registry = load_json(REGISTRY_PATH)
    registry_by_doc: dict[str, dict[str, Any]] = {
        str(row.get("id") or "").strip(): row
        for row in registry
        if str(row.get("id") or "").strip()
    }
    full_by_doc = collect_full_extraction_by_doc()
    bundle_by_doc, document_bundles = build_document_bundle_index(registry_by_doc)

    lab_rows = annotate_cross_document_lab_duplicates(
        annotate_intra_doc_lab_duplicates(
            annotate_document_bundles(build_lab_facts(registry_by_doc, full_by_doc), bundle_by_doc)
        )
    )
    clinical_rows = annotate_document_bundles(build_clinical_facts(registry_by_doc, full_by_doc), bundle_by_doc)
    reco_rows = annotate_document_bundles(build_recommendation_facts(registry_by_doc, full_by_doc), bundle_by_doc)
    med_rows = annotate_document_bundles(build_medication_facts(registry_by_doc, full_by_doc), bundle_by_doc)
    visible_lab_rows = [row for row in lab_rows if lab_result_is_display_primary(row)]

    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    bundles_path = FACTS_DIR / "document_bundles_v1.json"
    labs_path = FACTS_DIR / "lab_results_v1.ndjson"
    clinical_path = FACTS_DIR / "clinical_findings_v1.ndjson"
    reco_path = FACTS_DIR / "recommendation_items_v1.ndjson"
    meds_path = FACTS_DIR / "medication_items_v1.ndjson"
    summary_path = FACTS_DIR / "fact_layer_v1_summary.json"
    preview_path = REPORTS_DIR / "fact_layer_v1_preview.json"

    save_json(bundles_path, document_bundles)
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
            "document_bundles_count": len(document_bundles),
            "document_bundle_docs_count": len(bundle_by_doc),
            "fact_rows_in_document_bundles_counts": {
                "lab_results": sum(1 for row in lab_rows if row.get("document_bundle_id")),
                "clinical_findings": sum(1 for row in clinical_rows if row.get("document_bundle_id")),
                "recommendation_items": sum(1 for row in reco_rows if row.get("document_bundle_id")),
                "medication_items": sum(1 for row in med_rows if row.get("document_bundle_id")),
            },
            "lab_results_count": len(lab_rows),
            "lab_results_display_primary_count": len(visible_lab_rows),
            "lab_results_hidden_duplicate_count": len(lab_rows) - len(visible_lab_rows),
            "lab_duplicate_role_counts": count_by(lab_rows, "duplicate_role"),
            "lab_cross_document_duplicate_role_counts": count_by(lab_rows, "cross_document_duplicate_role"),
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
            "document_bundles": str(bundles_path).replace("\\", "/"),
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
            "document_bundles": document_bundles[:25],
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
