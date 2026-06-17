# Sympsense 2.0 — Claude Context

Персональная медицинская карта. Один пользователь, все медданные локально и gitignored.

## Core capabilities

| Что                         | Как запустить                                    | Артефакт                                          |
|-----------------------------|--------------------------------------------------|---------------------------------------------------|
| Обработка новых документов  | Файлы в `data/raw/inbox/`                        | `data/canonical/` + fact layer                    |
| UI                          | `build_documents_review_ui_v2.py`                | `data/derived/reports/ui_documents_registry.html` |
| **Аналитика здоровья**      | Промт из `docs/ANALYST_PROMPT.md`                | `data/derived/reports/analyst_findings_*.json`    |

## Аналитика здоровья — ключевая функция

Запускается вручную раз в ~полгода или после значимого пополнения базы.

Если пользователь говорит что-то вроде:
- "запусти аналитику"
- "проанализируй базу"
- "что нового по здоровью"
- "посмотри паттерны"

→ читай `docs/ANALYST_PROMPT.md` и выполняй инструкции оттуда.

Результаты пишутся в `data/derived/reports/analyst_findings_vN_YYYYMMDD.json`.
Последний отчёт показывается на вкладке "Карта здоровья" в UI.

## Ключевые файлы

- `AGENTS.md` — агентный контракт и правила работы
- `docs/plan_status.md` — полная история изменений проекта
- `docs/ANALYST_PROMPT.md` — промт для аналитики
- `docs/WORKING_STATE_2026-04-08.md` — снимок состояния данных
- `scripts/reports/build_documents_review_ui_v2.py` — основной UI (~2100 строк)
