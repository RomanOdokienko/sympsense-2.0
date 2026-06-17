from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


TARGET_AGE = 100
STALE_AFTER_DAYS = 365

STATUS_LABELS = {
    "green": "под контролем",
    "amber": "пробелы данных",
    "red": "требует внимания",
    "gray": "нет данных",
}

STATUS_ORDER = {"red": 0, "amber": 1, "gray": 2, "green": 3}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _load_json(path)


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _lab_result_is_display_primary(row: dict[str, Any]) -> bool:
    return row.get("duplicate_role") != "duplicate" and row.get("cross_document_duplicate_role") != "duplicate"


def _append_audit(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _norm(text: Any) -> str:
    return " ".join(str(text or "").replace("ё", "е").lower().split())


def _contains_any(text: Any, aliases: list[str]) -> bool:
    hay = _norm(text)
    for alias in aliases:
        norm_alias = _norm(alias)
        if " " in norm_alias:
            # multi-word phrase: substring match is fine
            if norm_alias in hay:
                return True
        else:
            # single token: must start at a word boundary (not inside another word)
            if re.search(r"(?<![а-яёa-z])" + re.escape(norm_alias), hay):
                return True
    return False


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:10], pattern).date()
        except Exception:
            continue
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    return None


def _iso(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _days_since(as_of: date, value: Any) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max(0, (as_of - parsed).days)


def _add_months(base: date, months: int) -> date:
    month = base.month - 1 + months
    year = base.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(base.day, days[month - 1]))


def _read_birth_year(config_path: Path) -> int | None:
    if not config_path.exists():
        return None
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("birth_year:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _read_birth_date_from_config(config_path: Path) -> date | None:
    if not config_path.exists():
        return None
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("birth_date:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            return _parse_date(value)
    return None


def _infer_birth_date(registry: list[dict[str, Any]]) -> date | None:
    pattern = re.compile(r"Дата рождения:\s*(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
    for row in registry:
        match = pattern.search(str(row.get("summary_preview") or ""))
        if match:
            return _parse_date(match.group(1))
    return None


def _current_age(as_of: date, birth_year: int | None, birth_date: date | None) -> int | None:
    if birth_date:
        years = as_of.year - birth_date.year
        if (as_of.month, as_of.day) < (birth_date.month, birth_date.day):
            years -= 1
        return years
    if birth_year:
        return as_of.year - birth_year
    return None


def _data_range(registry: list[dict[str, Any]], body_summary: dict[str, Any] | None) -> dict[str, Any]:
    summary_range = ((body_summary or {}).get("outputs") or {}).get("date_range") or {}
    dates = [
        _parse_date(summary_range.get("min")),
        _parse_date(summary_range.get("max")),
    ]
    for row in registry:
        dates.append(_parse_date(row.get("event_date_raw")))
    clean = sorted(d for d in dates if d is not None)
    if not clean:
        return {"min": None, "max": None, "years": 0}
    years = round(max(0, (clean[-1] - clean[0]).days) / 365.25, 1)
    return {"min": clean[0].isoformat(), "max": clean[-1].isoformat(), "years": years}


def _source_from_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    source = row.get("source") or {}
    return {
        "doc_id": row.get("doc_id") or source.get("document_id"),
        "file_name": source.get("file_name"),
        "relative_path": source.get("relative_path"),
        "source_type": row.get("source_type") or "canonical",
    }


def _record_date(row: dict[str, Any]) -> date | None:
    return _parse_date(row.get("event_date") or row.get("date") or row.get("measurement_date"))


def _latest_record(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda x: (_record_date(x) or date.min, str(x.get("fact_id") or "")))[-1]


def _marker_status(*, has_data: bool, abnormal: bool, event_date: str | None, as_of: date) -> tuple[str, list[str], int | None]:
    if not has_data:
        return "gray", ["missing_data"], None
    days = _days_since(as_of, event_date)
    reasons: list[str] = []
    if abnormal:
        reasons.append("abnormal_flag")
    if days is None:
        reasons.append("missing_date")
        return "amber", reasons, None
    if days > STALE_AFTER_DAYS:
        reasons.append("stale")
    if abnormal and days > STALE_AFTER_DAYS:
        return "red", reasons, days
    if abnormal or days > STALE_AFTER_DAYS:
        return "amber", reasons, days
    return "green", reasons or ["recent_normal"], days


def _empty_marker(marker_id: str, label: str, *, source_kind: str = "missing") -> dict[str, Any]:
    return {
        "id": marker_id,
        "label": label,
        "status": "gray",
        "status_label": STATUS_LABELS["gray"],
        "value": None,
        "value_num": None,
        "unit": None,
        "reference": None,
        "event_date": None,
        "days_since": None,
        "abnormal_flag": None,
        "reason_codes": ["missing_data"],
        "source_kind": source_kind,
        "source": None,
    }


def _lab_marker(marker_id: str, label: str, rows: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    latest = _latest_record(rows)
    if latest is None:
        return _empty_marker(marker_id, label, source_kind="lab_results")
    event_date = _iso(latest.get("event_date"))
    abnormal = bool(latest.get("abnormal_flag"))
    status, reasons, days = _marker_status(
        has_data=True,
        abnormal=abnormal,
        event_date=event_date,
        as_of=as_of,
    )
    return {
        "id": marker_id,
        "label": label,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "value": latest.get("value_text"),
        "value_num": latest.get("value_num"),
        "unit": latest.get("unit"),
        "reference": latest.get("reference_range_text"),
        "event_date": event_date,
        "days_since": days,
        "abnormal_flag": abnormal,
        "reason_codes": reasons,
        "source_kind": "lab_results",
        "source": _source_from_row(latest),
    }


def _condition_marker(
    marker_id: str,
    label: str,
    terms: list[str],
    *,
    condition_rows: list[dict[str, Any]],
    current_state: dict[str, Any] | None,
    problem_list: dict[str, Any] | None,
    as_of: date,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for row in condition_rows:
        if _contains_any(row.get("condition_text"), terms):
            candidates.append(
                {
                    "event_date": _iso(row.get("event_date")),
                    "text": row.get("condition_text"),
                    "qa_status": row.get("qa_status"),
                    "source": row.get("source"),
                    "doc_id": row.get("doc_id"),
                    "source_type": "condition_mentions",
                }
            )
    for bucket in ["active_conditions", "long_term_conditions", "history_items", "monitoring_items"]:
        for row in (current_state or {}).get(bucket) or []:
            if _contains_any(row.get("title"), terms):
                candidates.append(
                    {
                        "event_date": _iso(row.get("last_seen") or row.get("latest_date")),
                        "text": row.get("title"),
                        "qa_status": row.get("qa_status"),
                        "source_type": f"current_state.{bucket}",
                    }
                )
    for row in (problem_list or {}).get("items") or []:
        if _contains_any(row.get("label_clean") or row.get("label"), terms):
            timeline = row.get("timeline") or {}
            candidates.append(
                {
                    "event_date": _iso(timeline.get("last_date")),
                    "text": row.get("label_clean") or row.get("label"),
                    "qa_status": (row.get("support") or {}).get("qa_status"),
                    "source_type": "problem_list",
                }
            )
    latest = _latest_record(candidates)
    if not latest:
        return _empty_marker(marker_id, label, source_kind="condition_mentions")
    event_date = _iso(latest.get("event_date"))
    days = _days_since(as_of, event_date)
    status = "amber"
    reasons = ["documented_history"]
    if days is not None and days <= STALE_AFTER_DAYS:
        reasons.append("recent")
    elif days is not None:
        reasons.append("stale")
    return {
        "id": marker_id,
        "label": label,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "value": latest.get("text"),
        "value_num": None,
        "unit": None,
        "reference": None,
        "event_date": event_date,
        "days_since": days,
        "abnormal_flag": None,
        "reason_codes": reasons,
        "source_kind": latest.get("source_type"),
        "source": _source_from_row(latest),
    }


def _find_lab_rows(labs: list[dict[str, Any]], aliases: list[str], *, exclude_urine_glucose: bool = False) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in labs:
        name = str(row.get("analyte_name") or "")
        if not _contains_any(name, aliases):
            continue
        if exclude_urine_glucose:
            section = _norm(row.get("section_name"))
            reference = _norm(row.get("reference_range_text"))
            if "моч" in section or "отрицательно" in reference:
                continue
        matched.append(row)
    return matched


def _load_checkup_indicators(longevity_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(longevity_dir.glob("longevity_checkup_*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        checkup_date = _iso(payload.get("date") or payload.get("event_date") or payload.get("checkup_date"))
        source = payload.get("source")
        indicators = payload.get("indicators") or payload.get("markers") or payload.get("items") or []
        if not isinstance(indicators, list):
            continue
        for item in indicators:
            if not isinstance(item, dict):
                continue
            deviation = _norm(item.get("deviation") or item.get("abnormality"))
            rows.append(
                {
                    "event_date": _iso(item.get("date") or item.get("event_date")) or checkup_date,
                    "analyte_name": item.get("name") or item.get("title") or item.get("marker"),
                    "value_text": item.get("value"),
                    "value_num": item.get("value_num"),
                    "unit": item.get("unit") or item.get("units"),
                    "reference_range_text": item.get("reference") or item.get("reference_range"),
                    "abnormal_flag": deviation in {"выше", "ниже", "above", "below", "high", "low", "abnormal"},
                    "source_type": "longevity_checkup",
                    "source": {"file_name": path.name, "relative_path": str(path).replace("\\", "/"), "label": source},
                }
            )
    return rows


def _metric(
    marker_id: str,
    label: str,
    aliases: list[str],
    *,
    labs: list[dict[str, Any]],
    checkups: list[dict[str, Any]],
    as_of: date,
    exclude_urine_glucose: bool = False,
) -> dict[str, Any]:
    rows = _find_lab_rows(labs, aliases, exclude_urine_glucose=exclude_urine_glucose)
    rows.extend(_find_lab_rows(checkups, aliases))
    return _lab_marker(marker_id, label, rows, as_of)


def _zone_plan(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    _SKIP_KINDS = {"screening_calendar", "condition_mentions", "current_state"}
    refresh: list[str] = []
    first_time: list[str] = []
    for m in metrics:
        if (m.get("source_kind") or "") in _SKIP_KINDS:
            continue
        status = m.get("status")
        reasons = m.get("reason_codes") or []
        label = m.get("label") or m.get("id") or ""
        if status == "gray":
            first_time.append(label)
        elif "stale" in reasons:
            yr = (m.get("event_date") or "")[:4]
            refresh.append(f"{label} ({yr})" if yr else label)
    return {"refresh": refresh, "first_time": first_time}


def _zone(zone_id: str, title: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(m.get("status") or "gray") for m in metrics]
    if statuses and all(s == "gray" for s in statuses):
        status = "gray"
    elif any(s == "red" for s in statuses):
        status = "red"
    elif any(s in {"amber", "gray"} for s in statuses):
        status = "amber"
    else:
        status = "green"
    return {
        "id": zone_id,
        "title": title,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "metrics": metrics,
    }


def _read_longevity_files(longevity_dir: Path, prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not longevity_dir.exists():
        return rows
    for path in sorted(longevity_dir.glob(f"{prefix}*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    rows.append({**item, "source_file": path.name})
        elif isinstance(payload, dict):
            rows.append({**payload, "source_file": path.name})
    return rows


def _normalize_baseline_rows(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        baseline_type = str(row.get("type") or row.get("baseline_type") or row.get("metric_type") or "").strip()
        label = str(row.get("title") or row.get("name") or baseline_type or "baseline").strip()
        event_date = _iso(row.get("measurement_date") or row.get("date") or row.get("event_date"))
        status, reasons, days = _marker_status(
            has_data=True,
            abnormal=False,
            event_date=event_date,
            as_of=as_of,
        )
        out.append(
            {
                "type": baseline_type,
                "label": label,
                "value": row.get("value"),
                "unit": row.get("unit") or row.get("units"),
                "method": row.get("method"),
                "note": row.get("note"),
                "event_date": event_date,
                "days_since": days,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "reason_codes": reasons,
                "source_file": row.get("source_file"),
            }
        )
    return sorted(out, key=lambda x: (str(x.get("type") or ""), str(x.get("event_date") or "")))


def _baseline_marker(
    marker_id: str,
    label: str,
    baseline_type: str,
    baselines: list[dict[str, Any]],
    as_of: date,
) -> dict[str, Any]:
    rows = [x for x in baselines if str(x.get("type") or "").strip() == baseline_type]
    latest = _latest_record(rows)
    if not latest:
        return _empty_marker(marker_id, label, source_kind="longevity_baseline")
    event_date = _iso(latest.get("event_date"))
    status, reasons, days = _marker_status(
        has_data=True,
        abnormal=False,
        event_date=event_date,
        as_of=as_of,
    )
    return {
        "id": marker_id,
        "label": label,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "value": latest.get("value"),
        "value_num": None,
        "unit": latest.get("unit"),
        "reference": latest.get("method"),
        "event_date": event_date,
        "days_since": days,
        "abnormal_flag": None,
        "reason_codes": reasons,
        "source_kind": "longevity_baseline",
        "source": {"file_name": latest.get("source_file")},
    }


def _musculoskeletal_status(current_state: dict[str, Any] | None, as_of: date) -> dict[str, Any]:
    terms = [
        "шея",
        "спина",
        "позвоноч",
        "плеч",
        "локт",
        "кисть",
        "запяст",
        "колен",
        "мениск",
        "бурсит",
        "эпиконд",
        "импиджмент",
    ]
    rows: list[dict[str, Any]] = []
    for bucket in ["active_conditions", "long_term_conditions", "monitoring_items"]:
        for row in (current_state or {}).get(bucket) or []:
            if _contains_any(row.get("title"), terms):
                rows.append(row)
    if not rows:
        return _empty_marker("musculoskeletal_status", "Опорно-двигат. статус", source_kind="current_state")
    latest_date = max((_parse_date(row.get("last_seen") or row.get("latest_date")) or date.min) for row in rows)
    active_count = len([x for x in rows if str(x.get("status") or x.get("kind") or "").lower() == "active"])
    days = None if latest_date == date.min else max(0, (as_of - latest_date).days)
    status = "amber" if rows else "gray"
    part_map = [
        (["шея", "шейн", "цервикал", "позвоноч"], "шея"),
        (["плеч", "импиджмент"], "плечо"),
        (["локт", "эпиконд"], "локоть"),
        (["кисть", "запяст"], "кисть"),
        (["колен", "мениск"], "колено"),
        (["пояснич", "люмб"], "спина"),
        (["бурсит"], "бурсит"),
    ]
    parts: list[str] = []
    seen_parts: set[str] = set()
    for row in rows:
        t = _norm(row.get("title") or "")
        for keywords, label in part_map:
            if label not in seen_parts and any(k in t for k in keywords):
                parts.append(label)
                seen_parts.add(label)
    parts_str = ", ".join(parts[:4]) if parts else "множественные"
    value_str = f"активные проблемы ({parts_str})" if active_count > 0 else f"в наблюдении ({parts_str})"
    return {
        "id": "musculoskeletal_status",
        "label": "Опорно-двигат. статус",
        "status": status,
        "status_label": STATUS_LABELS[status],
        "value": value_str,
        "value_num": len(rows),
        "unit": None,
        "reference": None,
        "event_date": None if latest_date == date.min else latest_date.isoformat(),
        "days_since": days,
        "abnormal_flag": None,
        "reason_codes": ["documented_current_state"],
        "source_kind": "current_state",
        "source": None,
        "items": rows[:8],
    }


def _latest_document_date(
    registry: list[dict[str, Any]],
    investigations: list[dict[str, Any]],
    terms: list[str],
) -> tuple[str | None, dict[str, Any] | None]:
    candidates: list[dict[str, Any]] = []
    for row in registry:
        hay = " ".join(
            [
                str(row.get("file_name") or ""),
                str(row.get("doc_type") or ""),
                str(row.get("summary_preview") or ""),
            ]
        )
        if _contains_any(hay, terms):
            candidates.append(
                {
                    "event_date": _iso(row.get("event_date_raw")),
                    "doc_id": row.get("id"),
                    "file_name": row.get("file_name"),
                    "source_type": "documents",
                }
            )
    for row in investigations:
        hay = " ".join([str(row.get("title") or ""), " ".join(str(x) for x in row.get("highlights") or [])])
        if _contains_any(hay, terms):
            candidates.append(
                {
                    "event_date": _iso(row.get("event_date")),
                    "doc_id": row.get("doc_id"),
                    "file_name": (row.get("source") or {}).get("file_name"),
                    "source_type": "investigation_events",
                }
            )
    latest = _latest_record(candidates)
    if not latest:
        return None, None
    return _iso(latest.get("event_date")), latest


def _screening_calendar(
    *,
    registry: list[dict[str, Any]],
    investigations: list[dict[str, Any]],
    labs: list[dict[str, Any]],
    checkups: list[dict[str, Any]],
    birth_year: int | None,
    current_age: int | None,
    as_of: date,
) -> list[dict[str, Any]]:
    psa_marker = _metric("psa", "ПСА", ["пса", "psa"], labs=labs, checkups=checkups, as_of=as_of)
    rules = [
        {
            "id": "colonoscopy",
            "title": "Колоноскопия",
            "start_age": 40,
            "start_age_display": "40-45",
            "interval_months": 120,
            "terms": ["колоноскоп"],
        },
        {
            "id": "coronary_calcium_score",
            "title": "Кальциевый скоринг коронаров",
            "start_age": 35,
            "start_age_display": "35-40",
            "interval_months": None,
            "terms": ["кальциев", "коронар", "calcium score"],
        },
        {
            "id": "psa",
            "title": "ПСА (простата)",
            "start_age": 40,
            "start_age_display": "40",
            "interval_months": 12,
            "terms": ["пса", "psa", "простата"],
            "lab_marker": psa_marker,
        },
        {
            "id": "dermatoscopy",
            "title": "Дерматоскопия",
            "start_age": 30,
            "start_age_display": "30",
            "interval_months": 12,
            "terms": ["дерматоскоп", "дерматолог"],
        },
        {
            "id": "abdominal_ultrasound",
            "title": "УЗИ органов брюшной полости",
            "start_age": 35,
            "start_age_display": "35",
            "interval_months": 48,
            "terms": ["брюшн", "печень", "желч", "поджелуд", "селезен"],
        },
        {
            "id": "ophthalmology",
            "title": "Офтальмолог",
            "start_age": 25,
            "start_age_display": "25",
            "interval_months": 12,
            "terms": ["офтальмолог", "миоп", "глаз"],
        },
        {
            "id": "dentistry",
            "title": "Стоматолог",
            "start_age": 0,
            "start_age_display": "любой",
            "interval_months": 6,
            "terms": ["стоматолог", "челюст", "зуб"],
        },
    ]
    out: list[dict[str, Any]] = []
    for rule in rules:
        last_date, source = _latest_document_date(registry, investigations, list(rule["terms"]))
        lab_marker = rule.get("lab_marker")
        if isinstance(lab_marker, dict) and lab_marker.get("event_date"):
            lab_date = str(lab_marker.get("event_date") or "")
            if not last_date or (_parse_date(lab_date) or date.min) > (_parse_date(last_date) or date.min):
                last_date = lab_date
                source = {"source_type": "lab_results", "doc_id": ((lab_marker.get("source") or {}).get("doc_id"))}

        interval = rule["interval_months"]
        status = "age_unknown"
        next_due = None
        days_until_due = None
        if current_age is not None:
            if current_age < int(rule["start_age"]):
                status = "not_yet_due"
            elif last_date is None:
                status = "due"
            elif interval is None:
                status = "done"
            else:
                due_date = _add_months(_parse_date(last_date) or as_of, int(interval))
                next_due = due_date.isoformat()
                days_until_due = (due_date - as_of).days
                if due_date < as_of:
                    status = "overdue"
                elif days_until_due <= 120:
                    status = "upcoming"
                else:
                    status = "ok"

        out.append(
            {
                "screening_id": rule["id"],
                "title": rule["title"],
                "start_age": rule["start_age_display"],
                "periodicity_months": interval,
                "birth_year": birth_year,
                "current_age": current_age,
                "last_date": last_date,
                "next_due_date": next_due,
                "days_until_due": days_until_due,
                "status": status,
                "source": source,
            }
        )
    return out


def _status_counts(markers: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(x.get("status") or "gray") for x in markers))


def _build_gaps(
    *,
    markers: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    screening_calendar: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for row in markers:
        if row.get("status") == "gray":
            gaps.append(
                {
                    "gap_id": f"marker_{row.get('id')}",
                    "category": "marker_missing",
                    "title": str(row.get("label") or ""),
                    "priority": "gray",
                    "reason": "Нет данных в canonical/facts или longevity-checkup.",
                }
            )
    present_baseline_types = {str(x.get("type") or "") for x in baselines if str(x.get("type") or "")}
    for baseline_type, label in [
        ("vo2max", "VO2max"),
        ("grip_strength", "Сила хвата"),
        ("balance", "Баланс на одной ноге"),
        ("body_composition", "Состав тела"),
        ("bone_density", "Плотность костей"),
        ("cognitive", "Когнитивный baseline"),
    ]:
        if baseline_type not in present_baseline_types:
            gaps.append(
                {
                    "gap_id": f"baseline_{baseline_type}",
                    "category": "baseline_missing",
                    "title": label,
                    "priority": "gray",
                    "reason": "Нет baseline-файла в data/canonical/longevity.",
                }
            )
    for row in screening_calendar:
        if row.get("status") in {"due", "overdue"}:
            gaps.append(
                {
                    "gap_id": f"screening_{row.get('screening_id')}",
                    "category": "screening_gap",
                    "title": str(row.get("title") or ""),
                    "priority": "amber" if row.get("status") == "due" else "red",
                    "reason": "В календаре нет свежего подтверждения прохождения.",
                }
            )
    return sorted(gaps, key=lambda x: (STATUS_ORDER.get(str(x.get("priority")), 9), str(x.get("title") or "")))


def _build_priority_actions(markers: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(markers, key=lambda x: STATUS_ORDER.get(str(x.get("status") or "gray"), 9)):
        status = str(row.get("status") or "gray")
        if status == "green":
            continue
        marker_id = str(row.get("id") or row.get("label") or "")
        if marker_id in seen:
            continue
        seen.add(marker_id)
        label = str(row.get("label") or marker_id)
        if status == "red":
            title = f"Обсудить с лицензированным врачом обновление контроля: {label}"
            priority = "red"
        elif status == "amber":
            title = f"Уточнить актуальность данных: {label}"
            priority = "amber"
        else:
            title = f"Добавить исходные данные: {label}"
            priority = "gray"
        actions.append(
            {
                "action_id": f"action_{len(actions) + 1:02d}",
                "title": title,
                "priority": priority,
                "reason": ", ".join(str(x) for x in row.get("reason_codes") or []),
                "source_marker_id": marker_id,
            }
        )
        if len(actions) >= 10:
            break

    for gap in gaps:
        if len(actions) >= 14:
            break
        if gap.get("category") != "screening_gap":
            continue
        actions.append(
            {
                "action_id": f"action_{len(actions) + 1:02d}",
                "title": f"Уточнить скрининг: {gap.get('title')}",
                "priority": gap.get("priority"),
                "reason": gap.get("reason"),
                "source_gap_id": gap.get("gap_id"),
            }
        )
    return actions


def build_longevity_overview(
    project_root: Path,
    *,
    write_report: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    data_root = root / "data"
    facts_dir = data_root / "canonical/facts"
    reports_dir = data_root / "derived/reports"
    longevity_dir = data_root / "canonical/longevity"
    as_of = _today_utc()

    registry = _read_json(data_root / "canonical/documents/batch_01_registry_active.json") or []
    if not isinstance(registry, list):
        registry = []
    body_summary = _read_json(facts_dir / "body_snapshot_v1_summary.json")
    lab_rows_all = _load_ndjson(facts_dir / "lab_results_v1.ndjson")
    labs = [row for row in lab_rows_all if _lab_result_is_display_primary(row)]
    condition_rows = _load_ndjson(facts_dir / "condition_mentions_v1.ndjson")
    investigations = _load_ndjson(facts_dir / "investigation_events_v1.ndjson")
    current_state = _read_json(facts_dir / "current_state_v1.json")
    problem_list = _read_json(facts_dir / "problem_list_v1.json")
    checkups = _load_checkup_indicators(longevity_dir)

    baseline_rows = _normalize_baseline_rows(
        _read_longevity_files(longevity_dir, "baseline"),
        as_of,
    )
    protocols = sorted(
        _read_longevity_files(longevity_dir, "protocol_"),
        key=lambda x: (str(x.get("status") or ""), str(x.get("start_date") or x.get("date") or ""), str(x.get("name") or "")),
    )

    birth_year = _read_birth_year(root / "configs/app.yaml")
    birth_date = _read_birth_date_from_config(root / "configs/app.yaml") or _infer_birth_date(registry)
    age = _current_age(as_of, birth_year, birth_date)
    data_span = _data_range(registry, body_summary if isinstance(body_summary, dict) else None)

    horsemen = {
        "cardiovascular": _zone(
            "cardiovascular",
            "Сердечно-сосудистые",
            [
                _metric("ldl", "ЛПНП", ["лпнп", "ldl", "низкой плотности"], labs=labs, checkups=checkups, as_of=as_of),
                _metric("total_cholesterol", "Общий холестерин", ["холестерин общий", "общий холестерин"], labs=labs, checkups=checkups, as_of=as_of),
                _condition_marker("varicose", "Варикоз / вены", ["варикоз", "хвн", "варикозн", "венозн"], condition_rows=condition_rows, current_state=current_state if isinstance(current_state, dict) else None, problem_list=problem_list if isinstance(problem_list, dict) else None, as_of=as_of),
                _empty_marker("coronary_calcium_score", "Кальциевый скоринг", source_kind="screening_calendar"),
                _metric("blood_pressure", "АД, ЧСС покоя", ["артериальное давление", "ад", "blood pressure", "чсс"], labs=[], checkups=checkups, as_of=as_of),
            ],
        ),
        "metabolic": _zone(
            "metabolic",
            "Метаболическое здоровье",
            [
                _metric("hba1c", "HbA1c", ["hba1c", "гликирован"], labs=labs, checkups=checkups, as_of=as_of),
                _metric("fasting_insulin", "Инсулин натощак", ["инсулин"], labs=labs, checkups=checkups, as_of=as_of),
                _metric("glucose", "Глюкоза", ["глюкоза", "glu"], labs=labs, checkups=checkups, as_of=as_of, exclude_urine_glucose=True),
                _metric("creatinine_egfr", "Креатинин / СКФ", ["креатинин", "скф", "egfr"], labs=labs, checkups=checkups, as_of=as_of),
                _metric("urea", "Мочевина", ["мочевина"], labs=labs, checkups=checkups, as_of=as_of),
            ],
        ),
        "cancer": _zone(
            "cancer",
            "Онкология",
            [
                _metric("psa", "ПСА", ["пса", "psa"], labs=labs, checkups=checkups, as_of=as_of),
                _empty_marker("colonoscopy", "Колоноскопия", source_kind="screening_calendar"),
                _empty_marker("dermatoscopy", "Дерматоскопия", source_kind="screening_calendar"),
                _empty_marker("abdominal_ultrasound", "УЗИ органов", source_kind="screening_calendar"),
                _metric("tumor_markers", "Онкомаркеры", ["онкомаркер", "ca-", "ca 19", "ca 125", "рэа"], labs=labs, checkups=checkups, as_of=as_of),
            ],
        ),
        "neuro": _zone(
            "neuro",
            "Нейродегенерация",
            [
                _baseline_marker("cognitive_baseline", "Когнитивный baseline", "cognitive", baseline_rows, as_of),
                _metric("sleep_quality", "Качество сна", ["сон", "sleep quality"], labs=[], checkups=checkups, as_of=as_of),
                _metric("homocysteine", "Гомоцистеин", ["гомоцистеин", "homocysteine"], labs=labs, checkups=checkups, as_of=as_of),
                _condition_marker("headaches", "Головные боли", ["головная боль", "головн"], condition_rows=condition_rows, current_state=current_state if isinstance(current_state, dict) else None, problem_list=problem_list if isinstance(problem_list, dict) else None, as_of=as_of),
                _condition_marker("dizziness", "Головокружения", ["головокруж"], condition_rows=condition_rows, current_state=current_state if isinstance(current_state, dict) else None, problem_list=problem_list if isinstance(problem_list, dict) else None, as_of=as_of),
            ],
        ),
    }

    screening_calendar = _screening_calendar(
        registry=registry,
        investigations=investigations,
        labs=labs,
        checkups=checkups,
        birth_year=birth_year,
        current_age=age,
        as_of=as_of,
    )
    screening_marker_dates = {str(x.get("screening_id")): x for x in screening_calendar}
    for zone_id, marker_id in [
        ("cardiovascular", "coronary_calcium_score"),
        ("cancer", "colonoscopy"),
        ("cancer", "dermatoscopy"),
        ("cancer", "abdominal_ultrasound"),
    ]:
        for marker in horsemen[zone_id]["metrics"]:
            if marker.get("id") == marker_id:
                screen = screening_marker_dates.get(marker_id)
                if screen and screen.get("last_date"):
                    status, reasons, days = _marker_status(
                        has_data=True,
                        abnormal=False,
                        event_date=str(screen.get("last_date") or ""),
                        as_of=as_of,
                    )
                    marker.update(
                        {
                            "status": status,
                            "status_label": STATUS_LABELS[status],
                            "event_date": screen.get("last_date"),
                            "days_since": days,
                            "reason_codes": reasons,
                            "source": screen.get("source"),
                        }
                    )

    for zone in horsemen.values():
        zone["plan"] = _zone_plan(zone["metrics"])

    physical_baselines = [
        _baseline_marker("vo2max", "VO2max", "vo2max", baseline_rows, as_of),
        _baseline_marker("grip_strength", "Сила хвата", "grip_strength", baseline_rows, as_of),
        _baseline_marker("balance", "Баланс на одной ноге", "balance", baseline_rows, as_of),
        _baseline_marker("body_composition", "Состав тела", "body_composition", baseline_rows, as_of),
        _baseline_marker("bone_density", "Плотность костей", "bone_density", baseline_rows, as_of),
        _musculoskeletal_status(current_state if isinstance(current_state, dict) else None, as_of),
    ]

    inflammation = [
        _metric("hs_crp", "CRP высокочувствительный", ["crp", "срб", "с-реактив", "c-реактив"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("monocytes", "Моноциты", ["моноцит", "mon%"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("eosinophils", "Эозинофилы", ["эозинофил", "eo%"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("homocysteine_inflammation", "Гомоцистеин", ["гомоцистеин", "homocysteine"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("ferritin", "Ферритин", ["ферритин", "ferritin"], labs=labs, checkups=checkups, as_of=as_of),
    ]
    monocyte_rows = sorted(
        _find_lab_rows(labs, ["моноцит", "mon%"]),
        key=lambda x: (_parse_date(x.get("event_date")) or date.min),
        reverse=True,
    )
    for marker in inflammation:
        if marker.get("id") == "monocytes":
            marker["trend"] = [
                {
                    "date": _iso(row.get("event_date")),
                    "value": row.get("value_text"),
                    "abnormal": bool(row.get("abnormal_flag")),
                }
                for row in monocyte_rows[:5]
            ]

    hormones = [
        _metric("testosterone", "Тестостерон", ["тестостерон", "testosterone"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("tsh", "ТТГ", ["ттг", "тиреотроп"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("vitamin_d", "Витамин D", ["витамин d", "25-oh", "25 oh"], labs=labs, checkups=checkups, as_of=as_of),
        _metric("hrv_sleep", "HRV / сон", ["hrv", "вариабельность", "сон"], labs=[], checkups=checkups, as_of=as_of),
        _condition_marker("reproductive_status", "Репродуктивный статус", ["варикоцеле", "тератозоо"], condition_rows=condition_rows, current_state=current_state if isinstance(current_state, dict) else None, problem_list=problem_list if isinstance(problem_list, dict) else None, as_of=as_of),
    ]

    all_markers: list[dict[str, Any]] = []
    for zone in horsemen.values():
        all_markers.extend(zone.get("metrics") or [])
    all_markers.extend(physical_baselines)
    all_markers.extend(inflammation)
    all_markers.extend(hormones)

    gaps = _build_gaps(markers=all_markers, baselines=baseline_rows, screening_calendar=screening_calendar)
    priority_actions = _build_priority_actions(all_markers, gaps)

    zones_under_control = sum(1 for zone in horsemen.values() if zone.get("status") == "green")
    attention_actions = sum(1 for action in priority_actions if action.get("priority") in {"red", "amber"})

    payload: dict[str, Any] = {
        "generated_at": _now_utc(),
        "version": "longevity_overview_v1",
        "scope": {
            "documents_total": len(registry),
            "date_min": data_span.get("min"),
            "date_max": data_span.get("max"),
            "as_of_date": as_of.isoformat(),
        },
        "horizon": {
            "birth_year": birth_year,
            "birth_date_detected": birth_date.isoformat() if birth_date else None,
            "current_age": age,
            "age_is_approximate": birth_date is None and birth_year is not None,
            "target_age": TARGET_AGE,
            "data_years": data_span.get("years"),
            "tracked_markers": len(all_markers),
            "zones_under_control": zones_under_control,
            "actions_need_attention": attention_actions,
        },
        "horsemen": horsemen,
        "physical_baselines": physical_baselines,
        "baseline_measurements": baseline_rows,
        "inflammation": inflammation,
        "hormones": hormones,
        "priority_actions": priority_actions,
        "screening_calendar": screening_calendar,
        "protocols": protocols,
        "gaps": gaps,
        "status_counts": {
            "all_markers": _status_counts(all_markers),
            "horsemen": dict(Counter(str(x.get("status") or "gray") for x in horsemen.values())),
        },
        "sources": {
            "registry": "data/canonical/documents/batch_01_registry_active.json",
            "lab_results": "data/canonical/facts/lab_results_v1.ndjson",
            "condition_mentions": "data/canonical/facts/condition_mentions_v1.ndjson",
            "current_state": "data/canonical/facts/current_state_v1.json",
            "longevity_dir": "data/canonical/longevity",
        },
        "disclaimer": "Этот материал является навигационной сводкой по данным и не является диагнозом или назначением лечения. Красные и желтые пункты стоит обсуждать с лицензированным врачом.",
    }

    if write_report:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        reports_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = reports_dir / f"longevity_overview_v1_{ts}.json"
        latest_path = reports_dir / "longevity_overview_v1_latest.json"
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        snapshot_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")
        payload["report_paths"] = {
            "snapshot": str(snapshot_path).replace("\\", "/"),
            "latest": str(latest_path).replace("\\", "/"),
        }
        _append_audit(
            data_root / "audit/logs/batch_01_agent.ndjson",
            {
                "ts": _now_utc(),
                "event": "longevity_overview_built_v1",
                "snapshot_path": payload["report_paths"]["snapshot"],
                "latest_path": payload["report_paths"]["latest"],
                "markers_total": len(all_markers),
                "gaps_total": len(gaps),
            },
        )

    return payload
