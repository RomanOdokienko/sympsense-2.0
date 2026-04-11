from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sympsense.problem_list import build_problem_list


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_audit(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _report_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "missing"
    status = str(payload.get("status") or "").strip().lower()
    if status in {"pass", "fail"}:
        return status
    gate_statuses = [
        str((gate or {}).get("status") or "").strip().lower()
        for gate in (payload.get("gates") or {}).values()
    ]
    gate_statuses = [x for x in gate_statuses if x]
    if not gate_statuses:
        return "unknown"
    if any(x == "fail" for x in gate_statuses):
        return "fail"
    if all(x == "pass" for x in gate_statuses):
        return "pass"
    return "unknown"


def _overall_status(statuses: list[str]) -> str:
    s = [x for x in statuses if x]
    if not s:
        return "unknown"
    if any(x == "fail" for x in s):
        return "fail"
    if all(x == "pass" for x in s):
        return "pass"
    return "unknown"


def _cluster_domain(text: str) -> str:
    s = str(text or "").lower()
    if any(k in s for k in ["позвоноч", "мениск", "сустав", "артроз", "эпиконд", "теносинов"]):
        return "musculoskeletal"
    if any(k in s for k in ["миоп", "глаз", "офтальм"]):
        return "ophthalmology"
    if any(k in s for k in ["голов", "вестиб", "дорсалг", "невралг", "шейно-плечев"]):
        return "neurology"
    if any(k in s for k in ["варикоз", "вен"]):
        return "vascular"
    if any(k in s for k in ["ринит", "оториноларинг", "лор"]):
        return "ent"
    return "other"


def _normalize_lab_theme(analyte_name: str) -> str:
    s = str(analyte_name or "").lower()
    if "креатинин" in s:
        return "Креатинин"
    if "мочевин" in s:
        return "Мочевина"
    if "лпнп" in s:
        return "ЛПНП"
    if "лпвп" in s:
        return "ЛПВП"
    if "холестерин" in s:
        return "Общий холестерин"
    if "моноцит" in s or "mon%" in s:
        return "Моноциты"
    if "эозинофил" in s or "eo%" in s:
        return "Эозинофилы"
    if "тромбокрит" in s or "pct" in s:
        return "PCT (тромбокрит)"
    if "удельная плотность" in s or s.startswith("sg "):
        return "Удельная плотность мочи"
    return (analyte_name or "").strip()[:90] or "Нераспознанный показатель"


def _lab_signal(value_text: str) -> str:
    text = str(value_text or "")
    if "↑" in text:
        return "выше референса"
    if "↓" in text:
        return "ниже референса"
    return "отклонение зафиксировано"


def _parse_iso_date(value: str | None) -> date | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except Exception:
        return None


def _days_since(ref_date: date, value: str | None) -> int | None:
    parsed = _parse_iso_date(value)
    if parsed is None:
        return None
    return max(0, (ref_date - parsed).days)


def _clean_state_title(text: str | None) -> str:
    s = str(text or "").replace("( )", " ").replace("(  )", " ")
    s = s.replace("Заключение:", " ").replace("по диагнозу:", " ")
    s = s.replace("Основное заболевание:", " ").replace("Сопутствующее заболевание:", " ")
    # Drop long service tails that often pollute labels.
    for marker in [
        "должно быть интерпретировано лечащим врачом",
        "рекомендовано консервативное лечени",
        "интерпретировано лечащим врачом",
        "не является диагнозом",
        "данных лабораторных и других методов исследования",
    ]:
        idx = s.lower().find(marker)
        if idx > 0:
            s = s[:idx]
    # Deduplicate repeated leading token fragments: "Ганглион Гигрома ..." or "X X ..."
    parts = [x for x in s.split() if x]
    if len(parts) >= 2 and parts[0].lower() == parts[1].lower():
        parts = parts[1:]
    if len(parts) >= 4 and " ".join(parts[:2]).lower() == " ".join(parts[2:4]).lower():
        parts = parts[2:]
    s = " ".join(parts)
    s = " ".join(s.split()).strip(" ,.;:-")
    # Remove dangling conjunction tails after service-text trimming.
    while s.lower() in {"и", "а", "с", "по", "ом и"} or s.lower().endswith((" и", " а", " с", " по")):
        s = s[:-2].strip(" ,.;:-")
        if len(s) < 3:
            break
    return s


def _is_noise_condition_title(text: str) -> bool:
    low = str(text or "").lower().strip()
    if not low:
        return True
    noise_hints = [
        "должно быть",
        "интерпретировано лечащим врачом",
        "данных лабораторных и других методов исследования",
        "с учетом анамнеза заболевания",
        "клинической картины",
        "выбора тактики лечения",
        "тактики лечения",
        "не является диагнозом",
        "протокол",
        "исследования услуги",
    ]
    if any(h in low for h in noise_hints):
        return True
    if len(low) < 12:
        return True
    return False


def _infer_functional_limits(label: str) -> list[str]:
    s = str(label or "").lower()
    out: list[str] = []
    if any(k in s for k in ["шейн", "позвоноч", "кореш", "невралг", "дорсалг"]):
        out.append(
            "Шея/спина: избегать длительной статической нагрузки и резких движений; режим активности обсудить с лицензированным врачом."
        )
    if any(k in s for k in ["плеч", "эпиконд", "локт", "кист", "запяст", "ротатор"]):
        out.append(
            "Верхняя конечность: дозировать повторные силовые движения и провоцирующие нагрузки до согласования с врачом."
        )
    if any(k in s for k in ["мениск", "колен", "бедр", "тазобедр"]):
        out.append(
            "Нижняя конечность/колено: ограничивать ударные и скручивающие нагрузки, контролировать реакцию на активность."
        )
    if any(k in s for k in ["варикоз", "вен", "варикоцеле"]):
        out.append(
            "Венозный блок: избегать длительной неподвижности; профилактический режим и контроль обсуждать с врачом."
        )
    if any(k in s for k in ["миоп", "глаз"]):
        out.append(
            "Зрение: учитывать зрительную нагрузку и планировать периодический офтальмологический контроль."
        )
    return out


def _build_current_state_payload(
    *,
    problem_payload: dict[str, Any],
    lab_attention: list[dict[str, Any]],
    as_of_date: str | None,
) -> dict[str, Any]:
    items = list(problem_payload.get("items") or [])
    ref_date = _parse_iso_date(as_of_date) or datetime.now(timezone.utc).date()

    active_conditions: list[dict[str, Any]] = []
    long_term_conditions: list[dict[str, Any]] = []
    monitoring_items: list[dict[str, Any]] = []
    history_items: list[dict[str, Any]] = []
    uncertain_items: list[dict[str, Any]] = []
    all_limits: list[str] = []

    def classify_condition(row: dict[str, Any]) -> str:
        category = str(row.get("category") or "").strip()
        support = row.get("support") or {}
        timeline = row.get("timeline") or {}
        label_text = _clean_state_title(str(row.get("label_clean") or row.get("label") or ""))
        label_lower = label_text.lower()
        last_seen = str(timeline.get("last_date") or "")
        days = _days_since(ref_date, last_seen)
        qa_status = str(support.get("qa_status") or "needs_review").strip().lower()
        reasons = [str(x).strip().lower() for x in (row.get("category_reasons") or []) if str(x).strip()]
        has_icd = bool(row.get("icd_codes") or [])
        doc_count = int(support.get("doc_ids_count") or 0)

        if category == "uncertain" or "noise_marker" in reasons:
            return "uncertain"
        if _is_noise_condition_title(label_text):
            return "uncertain"
        if qa_status != "ok" and not has_icd and doc_count <= 1:
            return "uncertain"
        if days is None:
            return "monitor"

        if category == "stable_problem":
            if days <= 90:
                return "active"
            if days <= 730:
                return "long_term"
            if has_icd and doc_count >= 2:
                return "long_term"
            return "history"
        if category == "episodic_condition":
            if days <= 60:
                return "active"
            if days <= 730 and doc_count >= 2:
                return "monitor"
            return "history"
        if category == "symptom_or_state":
            if days <= 60:
                return "active"
            if days <= 365:
                return "monitor"
            return "history"
        return "monitor"

    for row in items:
        support = row.get("support") or {}
        timeline = row.get("timeline") or {}
        title = _clean_state_title(str(row.get("label_clean") or row.get("label") or ""))
        if not title:
            continue
        if _is_noise_condition_title(title):
            uncertain_items.append(
                {
                    "kind": "condition",
                    "problem_id": row.get("problem_id"),
                    "title": title,
                    "status": "uncertain",
                    "certainty": "low",
                    "first_seen": str((timeline or {}).get("first_date") or ""),
                    "last_seen": str((timeline or {}).get("last_date") or ""),
                    "days_since_last": _days_since(ref_date, str((timeline or {}).get("last_date") or "")),
                    "icd_codes": [str(x).strip() for x in (row.get("icd_codes") or []) if str(x).strip()],
                    "doc_ids_count": int((support or {}).get("doc_ids_count") or 0),
                    "mentions_count": int((support or {}).get("mentions_count") or 0),
                    "qa_status": str((support or {}).get("qa_status") or "needs_review").strip().lower(),
                    "source_category": str(row.get("category") or ""),
                    "category_reasons": list(row.get("category_reasons") or []),
                    "functional_limits": [],
                    "why_in_state": "Шумовая или служебная формулировка, исключена из клинической повестки.",
                }
            )
            continue
        state = classify_condition(row)
        last_seen = str(timeline.get("last_date") or "")
        first_seen = str(timeline.get("first_date") or "")
        days = _days_since(ref_date, last_seen)
        doc_count = int(support.get("doc_ids_count") or 0)
        mentions_count = int(support.get("mentions_count") or 0)
        icd_codes = [str(x).strip() for x in (row.get("icd_codes") or []) if str(x).strip()]
        qa_status = str(support.get("qa_status") or "needs_review").strip().lower()
        certainty = (
            "high"
            if (qa_status == "ok" and (bool(icd_codes) or doc_count >= 2))
            else ("medium" if qa_status == "ok" else "low")
        )
        limits = _infer_functional_limits(title)
        all_limits.extend(limits)

        state_row = {
            "kind": "condition",
            "problem_id": row.get("problem_id"),
            "title": title,
            "status": state,
            "certainty": certainty,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "days_since_last": days,
            "icd_codes": icd_codes,
            "doc_ids_count": doc_count,
            "mentions_count": mentions_count,
            "qa_status": qa_status,
            "source_category": str(row.get("category") or ""),
            "category_reasons": list(row.get("category_reasons") or []),
            "functional_limits": limits,
        }

        if state == "active":
            active_conditions.append(
                {
                    **state_row,
                    "why_in_state": "Свежие подтверждения в документах, состояние влияет на текущую клиническую картину.",
                    "discussion_prompt": f"Уточнить текущую активность состояния «{title}» и критерии контроля динамики.",
                }
            )
        elif state == "long_term":
            long_term_conditions.append(
                {
                    **state_row,
                    "why_in_state": "Повторяющееся/кодированное состояние с долгосрочной значимостью.",
                    "discussion_prompt": f"Проверить долгосрочный план наблюдения по состоянию «{title}».",
                }
            )
        elif state == "monitor":
            monitoring_items.append(
                {
                    "kind": "condition_monitor",
                    "title": title,
                    "priority": "medium",
                    "last_seen": last_seen,
                    "days_since_last": days,
                    "monitoring_reason": "Состояние эпизодическое/пограничное и требует периодического контроля.",
                    "discussion_prompt": f"Уточнить, нужно ли активное наблюдение по «{title}».",
                }
            )
        elif state == "history":
            history_items.append(
                {
                    **state_row,
                    "why_in_state": "Исторический эпизод без свежих подтверждений.",
                }
            )
        else:
            uncertain_items.append(
                {
                    **state_row,
                    "why_in_state": "Формулировка требует ручного уточнения и не должна влиять на ключевые выводы.",
                }
            )

    for row in lab_attention:
        theme = str(row.get("theme") or "").strip()
        if not theme:
            continue
        episodes = int(row.get("episodes") or 0)
        latest_date = str(row.get("latest_date") or "")
        days = _days_since(ref_date, latest_date)
        latest_value = str(row.get("latest_value") or "").strip()
        latest_ref = str(row.get("latest_reference") or "").strip()
        latest_doc_id = str(row.get("latest_doc_id") or "").strip()

        if days is None:
            priority = "medium"
            reason = "Есть исторические отклонения, но дата последнего эпизода не определена."
            monitor_bucket = "unknown"
        elif days <= 180:
            priority = "high"
            reason = "Отклонение зафиксировано недавно, нужно обсудить клиническую значимость сейчас."
            monitor_bucket = "recent"
        elif days <= 540:
            priority = "medium"
            reason = "Отклонение было в последние 6-18 месяцев, желательно контрольное наблюдение."
            monitor_bucket = "stale"
        elif days <= 900:
            priority = "low"
            reason = "Отклонение давнее; можно включить в плановый контроль без срочности."
            monitor_bucket = "stale"
        else:
            priority = "low"
            reason = "Отклонение историческое; нужен обновляющий контроль для оценки текущего статуса."
            monitor_bucket = "archive"

        monitoring_items.append(
            {
                "kind": "lab_monitor",
                "title": theme,
                "priority": priority,
                "episodes": episodes,
                "latest_value": latest_value,
                "latest_reference": latest_ref,
                "latest_date": latest_date,
                "days_since_last": days,
                "latest_doc_id": latest_doc_id,
                "monitoring_reason": reason,
                "monitor_bucket": monitor_bucket,
                "discussion_prompt": f"Обсудить, нужен ли контроль показателя «{theme}» и в какие сроки его пересдать.",
            }
        )

    def _sort_by_last_seen_desc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda x: (
                str(x.get("last_seen") or x.get("latest_date") or ""),
                -int(x.get("doc_ids_count") or 0),
                str(x.get("title") or ""),
            ),
            reverse=True,
        )

    active_conditions = _sort_by_last_seen_desc(active_conditions)
    long_term_conditions = _sort_by_last_seen_desc(long_term_conditions)
    history_items = _sort_by_last_seen_desc(history_items)
    uncertain_items = _sort_by_last_seen_desc(uncertain_items)
    monitoring_items = sorted(
        monitoring_items,
        key=lambda x: (
            {"high": 0, "medium": 1, "low": 2}.get(str(x.get("priority") or "medium"), 9),
            int(x.get("days_since_last") or 10**9),
            str(x.get("title") or ""),
        ),
    )
    dedup_monitor: list[dict[str, Any]] = []
    seen_monitor_keys: set[str] = set()
    for row in monitoring_items:
        key = f"{str(row.get('kind') or '').strip().lower()}::{str(row.get('title') or '').strip().lower()}"
        if not key or key in seen_monitor_keys:
            continue
        seen_monitor_keys.add(key)
        dedup_monitor.append(row)
    monitoring_items = dedup_monitor

    unique_limits: list[str] = []
    seen_limits: set[str] = set()
    for text in all_limits:
        key = text.strip().lower()
        if not key or key in seen_limits:
            continue
        seen_limits.add(key)
        unique_limits.append(text)

    return {
        "generated_at": _now_utc(),
        "version": "current_state_v1",
        "as_of_date": ref_date.isoformat(),
        "counters": {
            "active_conditions": len(active_conditions),
            "long_term_conditions": len(long_term_conditions),
            "monitoring_items": len(monitoring_items),
            "history_items": len(history_items),
            "uncertain_items": len(uncertain_items),
        },
        "active_conditions": active_conditions[:12],
        "long_term_conditions": long_term_conditions[:16],
        "monitoring_items": monitoring_items[:20],
        "functional_limits": unique_limits[:12],
        "history_items": history_items[:20],
        "uncertain_items": uncertain_items[:10],
    }


def _build_clinical_findings_payload(
    *,
    problem_payload: dict[str, Any],
    lab_attention: list[dict[str, Any]],
    current_state: dict[str, Any] | None,
    quality_status: str,
    documents_total: int,
    date_min: str | None,
    date_max: str | None,
) -> dict[str, Any]:
    items = list(problem_payload.get("items") or [])
    stable = [x for x in items if str(x.get("category") or "") == "stable_problem"]
    uncertain = [x for x in items if str(x.get("category") or "") == "uncertain"]

    cs = current_state or {}
    active_conditions = list(cs.get("active_conditions") or [])
    long_term_conditions = list(cs.get("long_term_conditions") or [])
    monitoring_items = list(cs.get("monitoring_items") or [])
    uncertain_items = list(cs.get("uncertain_items") or [])

    prioritized: list[dict[str, Any]] = []
    for row in active_conditions[:5]:
        prioritized.append(
            {
                "priority": "high",
                "kind": "condition_active",
                "title": str(row.get("title") or ""),
                "icd_codes": list(row.get("icd_codes") or []),
                "why_it_matters": f"Последнее подтверждение: {row.get('last_seen') or 'н/д'}. Состояние актуально для текущего визита.",
                "discussion_prompt": str(
                    row.get("discussion_prompt")
                    or f"Уточнить текущее состояние и план наблюдения по «{row.get('title') or ''}»."
                ),
                "evidence": {
                    "doc_ids_count": int(row.get("doc_ids_count") or 0),
                    "mentions_count": int(row.get("mentions_count") or 0),
                    "last_seen": row.get("last_seen"),
                },
            }
        )

    medium_budget = 6
    low_budget = 3
    used_medium = 0
    used_low = 0
    for row in monitoring_items:
        kind = str(row.get("kind") or "")
        priority = str(row.get("priority") or "medium")
        title = str(row.get("title") or "")
        if kind == "lab_monitor":
            if str(row.get("monitor_bucket") or "") == "archive":
                continue
            reason = str(row.get("monitoring_reason") or "")
            latest_value = str(row.get("latest_value") or "")
            latest_ref = str(row.get("latest_reference") or "")
            latest_date = str(row.get("latest_date") or "")
            if not latest_date:
                latest_date = str(row.get("last_seen") or "")
            p = "high" if priority == "high" else ("low" if priority == "low" else "medium")
            if p == "medium" and used_medium >= medium_budget:
                continue
            if p == "low" and used_low >= low_budget:
                continue
            prioritized.append(
                {
                    "priority": p,
                    "kind": kind,
                    "title": title,
                    "icd_codes": [],
                    "why_it_matters": f"Последнее отклонение: {latest_date or 'н/д'}; значение: {latest_value or 'н/д'}; референс: {latest_ref or 'н/д'}. {reason}",
                    "discussion_prompt": str(
                        row.get("discussion_prompt")
                        or f"Определить, нужен ли актуальный контроль показателя «{title}»."
                    ),
                    "evidence": {
                        "episodes": int(row.get("episodes") or 0),
                        "latest_date": latest_date,
                        "latest_doc_id": row.get("latest_doc_id"),
                    },
                }
            )
            if p == "medium":
                used_medium += 1
            elif p == "low":
                used_low += 1
        elif kind == "condition_monitor":
            if _is_noise_condition_title(title):
                continue
            days = int(row.get("days_since_last") or 10**9)
            p = "medium" if days <= 900 else "low"
            if p == "medium" and used_medium >= medium_budget:
                continue
            if p == "low" and used_low >= low_budget:
                continue
            prioritized.append(
                {
                    "priority": p,
                    "kind": kind,
                    "title": title,
                    "icd_codes": [],
                    "why_it_matters": str(row.get("monitoring_reason") or ""),
                    "discussion_prompt": str(
                        row.get("discussion_prompt")
                        or f"Подтвердить актуальность состояния «{title}»."
                    ),
                    "evidence": {
                        "last_seen": row.get("last_seen"),
                        "days_since_last": row.get("days_since_last"),
                    },
                }
            )
            if p == "medium":
                used_medium += 1
            elif p == "low":
                used_low += 1

    def _prio_key(x: dict[str, Any]) -> tuple[int, str]:
        p = str(x.get("priority") or "medium")
        rank = 0 if p == "high" else (1 if p == "medium" else 2)
        return (rank, str(x.get("title") or ""))

    prioritized = sorted(prioritized, key=_prio_key)[:12]
    high_count = sum(1 for x in prioritized if str(x.get("priority")) == "high")
    medium_count = sum(1 for x in prioritized if str(x.get("priority")) == "medium")
    low_count = sum(1 for x in prioritized if str(x.get("priority")) == "low")

    summary_bullets: list[str] = [
        f"В базе: {documents_total} документов за период {date_min or 'н/д'} — {date_max or 'н/д'}.",
        f"Текущая картина: активных состояний {len(active_conditions)}, устойчивых {len(long_term_conditions)}, пунктов мониторинга {len(monitoring_items)}.",
        f"Повестка к обсуждению: {len(prioritized)} пунктов (high: {high_count}, medium: {medium_count}, low: {low_count}).",
    ]
    if uncertain_items:
        summary_bullets.append(f"Формулировок с низкой достоверностью (вынесены из приоритетов): {len(uncertain_items)}.")
    if lab_attention:
        top_labs = ", ".join(str(x.get("theme") or "") for x in lab_attention[:3] if str(x.get("theme") or "").strip())
        if top_labs:
            summary_bullets.append(f"В истории отмечались лабораторные отклонения: {top_labs}.")

    visit_agenda: list[str] = []
    for row in prioritized:
        prompt = str(row.get("discussion_prompt") or "").strip()
        if prompt and prompt not in visit_agenda:
            visit_agenda.append(prompt)
    visit_agenda = visit_agenda[:8]

    quality_note = (
        "Качество данных снижено: часть автоматических проверок не пройдена."
        if quality_status == "fail"
        else "Качество данных допустимое для аналитической сводки."
    )
    if uncertain_items:
        quality_note += " Отдельные формулировки требуют ручного уточнения перед клиническими выводами."

    return {
        "generated_at": _now_utc(),
        "version": "clinical_findings_v1",
        "summary_bullets": summary_bullets,
        "prioritized_findings": prioritized,
        "visit_agenda": visit_agenda,
        "quality_note": quality_note,
        "safety_notes": [
            "Материал не является диагнозом и не заменяет очный прием.",
            "Красные флаги и любые изменения состояния обсуждать с лицензированным врачом.",
        ],
        "disclaimer": "Аналитическая сводка для подготовки к приему. Не назначает лечение.",
    }


def _build_html(payload: dict[str, Any]) -> str:
    scope = payload.get("scope") or {}
    quality = payload.get("quality") or {}
    domains = payload.get("top_domains") or []
    clusters = payload.get("top_condition_clusters") or []
    labs = payload.get("lab_attention_items") or []
    investigations = payload.get("recent_investigations") or []
    actions = payload.get("suggested_discussion_points") or []

    def esc(s: Any) -> str:
        return (
            str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def li(items: list[str]) -> str:
        if not items:
            return "<li>none</li>"
        return "".join(f"<li>{esc(x)}</li>" for x in items)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Patient Briefing v1</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f7f8fb;color:#111827}}
.wrap{{max-width:1200px;margin:0 auto;padding:20px}}
.h1{{font-size:34px;font-weight:800;margin:0 0 6px}}
.muted{{color:#6b7280}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:14px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:10px}}
.num{{font-size:24px;font-weight:700}}
.panel{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:12px;margin-top:12px}}
.row{{border-bottom:1px dashed #eceff3;padding:7px 0}}
.row:last-child{{border-bottom:none}}
ul{{margin:8px 0 0 18px}}
@media (max-width:980px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="h1">Patient Briefing v1</div>
  <div class="muted">Generated at {esc(payload.get("generated_at"))}</div>
  <div class="muted">Этот документ аналитический и не является медицинским назначением/диагнозом.</div>
  <div class="grid">
    <div class="card"><div class="muted">Documents</div><div class="num">{esc(scope.get("documents_total"))}</div></div>
    <div class="card"><div class="muted">Date range</div><div class="num" style="font-size:16px">{esc(scope.get("date_min"))} -> {esc(scope.get("date_max"))}</div></div>
    <div class="card"><div class="muted">Condition clusters</div><div class="num">{esc(scope.get("condition_clusters_count"))}</div></div>
    <div class="card"><div class="muted">Quality status</div><div class="num" style="font-size:20px">{esc(quality.get("overall_status"))}</div></div>
  </div>
  <div class="panel">
    <b>Top clinical domains</b>
    {"".join(f'<div class="row">{esc(x.get("domain"))}: mentions={esc(x.get("mentions"))}, clusters={esc(x.get("clusters"))}</div>' for x in domains) or '<div class="row">none</div>'}
  </div>
  <div class="panel">
    <b>Top condition clusters</b>
    {"".join(f'<div class="row"><div><b>{esc(x.get("example"))}</b></div><div class="muted">mentions={esc(x.get("mention_count"))}, docs={esc(x.get("doc_count"))}, first={esc(x.get("first_date"))}, last={esc(x.get("last_date"))}</div></div>' for x in clusters) or '<div class="row">none</div>'}
  </div>
  <div class="panel">
    <b>Lab attention items (repeated abnormal flags)</b>
    {"".join(f'<div class="row"><div><b>{esc(x.get("theme"))}</b> (episodes={esc(x.get("episodes"))})</div><div class="muted">dates: {esc(", ".join(x.get("dates") or []))}</div><div class="muted">latest: {esc(x.get("latest_value"))} | ref: {esc(x.get("latest_reference"))}</div></div>' for x in labs) or '<div class="row">none</div>'}
  </div>
  <div class="panel">
    <b>Recent investigations</b>
    {"".join(f'<div class="row">{esc(x.get("event_date"))}: {esc(x.get("doc_type"))} | {esc(x.get("title"))}</div>' for x in investigations) or '<div class="row">none</div>'}
  </div>
  <div class="panel">
    <b>Suggested discussion points with licensed physician</b>
    <ul>{li([str(x) for x in actions])}</ul>
  </div>
</div>
</body>
</html>"""


def build_patient_briefing(
    project_root: Path,
    *,
    write_report: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    data_root = root / "data"
    reports_dir = data_root / "derived/reports"

    registry = _load_json(data_root / "canonical/documents/batch_01_registry_active.json")
    body_summary = _load_json(data_root / "canonical/facts/body_snapshot_v1_summary.json")
    clusters = _load_ndjson(data_root / "canonical/facts/condition_clusters_v1.ndjson")
    investigations = _load_ndjson(data_root / "canonical/facts/investigation_events_v1.ndjson")
    labs = _load_ndjson(data_root / "canonical/facts/lab_results_v1.ndjson")

    quality_report_path = sorted(
        reports_dir.glob("quality_gates_v1_*.json"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    quality_report = _load_json(quality_report_path)
    body_quality_report_path = sorted(
        reports_dir.glob("body_snapshot_quality_gates_v1_*.json"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    body_quality_report = _load_json(body_quality_report_path)

    q_status = _report_status(quality_report if isinstance(quality_report, dict) else None)
    bq_status = _report_status(body_quality_report if isinstance(body_quality_report, dict) else None)

    date_range = (body_summary.get("outputs") or {}).get("date_range") or {}
    domain_mentions: Counter[str] = Counter()
    domain_clusters: Counter[str] = Counter()
    for c in clusters:
        example = str((c.get("examples") or [""])[0] or "")
        domain = _cluster_domain(example)
        m = int(c.get("mention_count") or 0)
        domain_mentions[domain] += m
        domain_clusters[domain] += 1

    domain_rows = []
    for domain, mentions in domain_mentions.most_common(5):
        domain_rows.append(
            {
                "domain": domain,
                "mentions": mentions,
                "clusters": int(domain_clusters.get(domain) or 0),
            }
        )

    top_clusters = sorted(
        clusters,
        key=lambda x: (
            -int(x.get("mention_count") or 0),
            -int(x.get("doc_count") or 0),
        ),
    )[:10]
    top_cluster_rows = [
        {
            "cluster_id": x.get("cluster_id"),
            "example": str((x.get("examples") or [""])[0] or ""),
            "mention_count": int(x.get("mention_count") or 0),
            "doc_count": int(x.get("doc_count") or 0),
            "first_date": x.get("first_date"),
            "last_date": x.get("last_date"),
            "icd_codes": x.get("icd_codes") or [],
        }
        for x in top_clusters
    ]

    abnormal_labs = [x for x in labs if bool(x.get("abnormal_flag"))]
    grouped_labs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in abnormal_labs:
        grouped_labs[_normalize_lab_theme(str(row.get("analyte_name") or ""))].append(row)
    lab_attention = []
    for theme, rows in grouped_labs.items():
        rows_sorted = sorted(rows, key=lambda x: str(x.get("event_date") or ""))
        dates = sorted({str(x.get("event_date") or "") for x in rows_sorted if str(x.get("event_date") or "")})
        latest = rows_sorted[-1]
        latest_date = str(latest.get("event_date") or "")
        lab_attention.append(
            {
                "theme": theme,
                "episodes": len(rows_sorted),
                "dates": dates[:8],
                "latest_date": latest_date,
                "latest_value": str(latest.get("value_text") or ""),
                "latest_reference": str(latest.get("reference_range_text") or ""),
                "latest_doc_id": latest.get("doc_id"),
            }
        )
    lab_attention.sort(key=lambda x: (-int(x.get("episodes") or 0), str(x.get("theme") or "")))

    recent_investigations = sorted(
        investigations,
        key=lambda x: str(x.get("event_date") or ""),
        reverse=True,
    )[:12]
    recent_rows = [
        {
            "event_date": x.get("event_date"),
            "doc_id": x.get("doc_id"),
            "doc_type": x.get("doc_type"),
            "title": x.get("title"),
            "highlights": x.get("highlights") or [],
        }
        for x in recent_investigations
    ]

    try:
        problem_payload = build_problem_list(root, write_report=False)
    except Exception:
        problem_payload = {"items": [], "summary": {"total_items": 0, "category_counts": {}}}

    current_state = _build_current_state_payload(
        problem_payload=problem_payload,
        lab_attention=lab_attention,
        as_of_date=str(date_range.get("max") or ""),
    )

    overall_quality = _overall_status([q_status, bq_status])
    clinical_findings = _build_clinical_findings_payload(
        problem_payload=problem_payload,
        lab_attention=lab_attention,
        current_state=current_state,
        quality_status=overall_quality,
        documents_total=len(registry),
        date_min=str(date_range.get("min") or ""),
        date_max=str(date_range.get("max") or ""),
    )
    suggested_points = list(clinical_findings.get("visit_agenda") or [])

    payload: dict[str, Any] = {
        "generated_at": _now_utc(),
        "version": "patient_briefing_v1",
        "scope": {
            "documents_total": len(registry),
            "date_min": date_range.get("min"),
            "date_max": date_range.get("max"),
            "condition_mentions_count": int((body_summary.get("outputs") or {}).get("condition_mentions_count") or 0),
            "condition_clusters_count": int((body_summary.get("outputs") or {}).get("condition_clusters_count") or 0),
            "investigation_events_count": int((body_summary.get("outputs") or {}).get("investigation_events_count") or 0),
        },
        "quality": {
            "overall_status": overall_quality,
            "quality_gates_status": q_status,
            "body_snapshot_quality_status": bq_status,
            "quality_report_path": str(quality_report_path).replace("\\", "/"),
            "body_quality_report_path": str(body_quality_report_path).replace("\\", "/"),
        },
        "top_domains": domain_rows,
        "top_condition_clusters": top_cluster_rows,
        "lab_attention_items": lab_attention[:10],
        "recent_investigations": recent_rows,
        "suggested_discussion_points": suggested_points,
        "problem_list_summary": problem_payload.get("summary") or {},
        "current_state": current_state,
        "clinical_findings": clinical_findings,
        "disclaimer": "Этот материал аналитический, не является диагнозом или назначением лечения.",
    }

    if write_report:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = reports_dir / f"patient_briefing_v1_{ts}.json"
        html_path = reports_dir / f"patient_briefing_v1_{ts}.html"
        latest_json = reports_dir / "patient_briefing_v1_latest.json"
        latest_html = reports_dir / "patient_briefing_v1_latest.html"
        findings_json = reports_dir / f"clinical_findings_v1_{ts}.json"
        findings_latest = reports_dir / "clinical_findings_v1_latest.json"
        current_state_json = reports_dir / f"current_state_v1_{ts}.json"
        current_state_latest = reports_dir / "current_state_v1_latest.json"
        current_state_canonical = data_root / "canonical/facts/current_state_v1.json"
        reports_dir.mkdir(parents=True, exist_ok=True)

        body_json = json.dumps(payload, ensure_ascii=False, indent=2)
        body_html = _build_html(payload)
        findings_body = json.dumps(clinical_findings, ensure_ascii=False, indent=2)
        current_state_body = json.dumps(current_state, ensure_ascii=False, indent=2)

        json_path.write_text(body_json, encoding="utf-8")
        html_path.write_text(body_html, encoding="utf-8")
        latest_json.write_text(body_json, encoding="utf-8")
        latest_html.write_text(body_html, encoding="utf-8")
        findings_json.write_text(findings_body, encoding="utf-8")
        findings_latest.write_text(findings_body, encoding="utf-8")
        current_state_json.write_text(current_state_body, encoding="utf-8")
        current_state_latest.write_text(current_state_body, encoding="utf-8")
        current_state_canonical.parent.mkdir(parents=True, exist_ok=True)
        current_state_canonical.write_text(current_state_body, encoding="utf-8")

        payload["report_paths"] = {
            "json": str(json_path).replace("\\", "/"),
            "html": str(html_path).replace("\\", "/"),
            "latest_json": str(latest_json).replace("\\", "/"),
            "latest_html": str(latest_html).replace("\\", "/"),
            "clinical_findings_json": str(findings_json).replace("\\", "/"),
            "clinical_findings_latest": str(findings_latest).replace("\\", "/"),
            "current_state_json": str(current_state_json).replace("\\", "/"),
            "current_state_latest": str(current_state_latest).replace("\\", "/"),
            "current_state_canonical": str(current_state_canonical).replace("\\", "/"),
        }
        _append_audit(
            data_root / "audit/logs/batch_01_agent.ndjson",
            {
                "ts": _now_utc(),
                "event": "patient_briefing_built_v1",
                "documents_total": len(registry),
                "quality_overall": overall_quality,
                "clinical_findings_total": len(clinical_findings.get("prioritized_findings") or []),
                "current_state_active": len(current_state.get("active_conditions") or []),
                "current_state_monitoring": len(current_state.get("monitoring_items") or []),
                "report_json": payload["report_paths"]["json"],
                "clinical_findings_latest": payload["report_paths"]["clinical_findings_latest"],
                "current_state_latest": payload["report_paths"]["current_state_latest"],
            },
        )

    return payload

