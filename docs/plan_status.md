# Plan Status

## Current status (2026-04-09)

- [x] Agent-first flow зафиксирован.
- [x] Проектная область зафиксирована на `D:\разработка\Sympsense 2.0`.
- [x] Batch processing идет раундами; при стабильном качестве используем по 10 файлов.
- [x] Зафиксирована политика распознавания: `text_layer` + обязательный fallback на `multimodal_vision` для сканов/плохого слоя.
- [x] Завершены `round2`, `round3`, `round4`, `round5`, `round6`, `round7`, `round8`, `round9`, `round10`.
- [x] Выполнен quality rerun проблемного подмножества (17 документов) с закрытием preflight-гейтов.
- [x] Зафиксирован `section_map_v1` для `doctor_consultation`, `lab_report`, `imaging_report_*`.
- [x] Добавлены `quality_gates_v1` + `goldset_v1` и исполняемая проверка baseline.
- [x] Выполнен remediation blocker-дефектов по `quality_gates_v1` (дубли `conclusion/recommendation` устранены).
- [x] Выполнен imaging backfill: для `imaging_report_*` добавлены canonical `doctor_conclusions` (и `recommendations`, где есть в источнике).
- [x] Выполнен lab backfill: для `lab_report` добавлено извлечение markers в `labs.sections[].items` и обновлен UI-показ значений.
- [x] Закрыты blocker-документы по gate `lab_reports_without_items` (ретипизация `doc_606...`, парсинг маркера в `doc_c77...`).
- [x] Выполнена детальная ручная QA-проверка и чистка лишних документов через UI.
- [x] В UI добавлен явный обзор review-флагов (`needs_review`/`ok`) и фильтрация по ним.
- [x] Актуальный активный набор после ручной чистки: `51` документов (`doctor_consultation=29`, `lab_report=12`, `imaging=10`).

## Next phase: Fact-first transition

- [x] Зафиксировать новый рабочий этап в плане (этот документ).
- [x] Снят baseline-снимок текущего active-набора перед миграцией:
  - `data/audit/snapshots/fact_layer_baseline_20260409T143328Z`
- [x] Построен `fact-layer v1` из текущего canonical:
  - [x] `lab_results` (1 анализ = 1 запись)
  - [x] `clinical_findings` (conclusion/diagnosis/findings поштучно)
  - [x] `recommendation_items` (атомарные рекомендации)
- [x] Для каждой fact-записи сохраняются `doc_id + evidence_excerpt + confidence + review_state`.
- [x] Добавлен артефакт-сводка `data/canonical/facts/fact_layer_v1_summary.json`.
- [x] Добавлено audit-событие о сборке fact-layer в `data/audit/logs/batch_01_agent.ndjson`.
- [x] Добавлен просмотр fact-layer в отчетах:
  - `data/derived/reports/fact_layer_v1_preview.json`
- [x] Введен отдельный QA-статус на уровне фактов:
  - `qa_status` и `qa_reasons` в `lab_results`, `clinical_findings`, `recommendation_items`, `medication_items`.
  - в сводке добавлены `qa_status_counts` отдельно от `legacy_review_state_counts`.
- [x] Вынесены отдельные medication-факты из текстовых рекомендаций:
  - `data/canonical/facts/medication_items_v1.ndjson` (v1, rule-based).
- [ ] Следующий шаг (low priority): доработать мед-парсер v2 для сложных многокомпонентных схем.
- [x] Усилен fact-layer по диагнозам/исследованиям и связям между ними (timeline + cross-links):
  - `data/canonical/facts/body_snapshot_v1.json`
  - `data/canonical/facts/condition_mentions_v1.ndjson`
  - `data/canonical/facts/investigation_events_v1.ndjson`
  - `data/canonical/facts/condition_investigation_links_v1.ndjson`
  - `data/canonical/facts/body_snapshot_v1_summary.json`
- [x] Повышена точность нормализации condition-text и quality ранжирования links:
  - в `condition_mentions` добавлены `condition_key`, `condition_group_key`;
  - добавлены кластеры состояний `condition_clusters_v1.ndjson`;
  - в links добавлены `link_priority` и `score_reasons`.
- [x] Доочищено ICD-like извлечение:
  - исключены анатомические уровни типа `C3-C4` из `icd_codes`;
  - сохранены валидные ICD-коды (`M50.1`, `M53.1`, `M54.8`, ...).
- [x] Улучшена канонизация condition-text:
  - добавлена нормализация фраз/токенов, стемминг и маппинг медицинских терминов;
  - добавлено восстановление cp1251-моджибейка для condition-полей;
  - `condition_key/group_key` стали стабильнее и читабельнее.
- [x] Введен прицельный quality-gate для body_snapshot (`condition_clusters` и `links`) и авто-репорт регрессий.
  - `scripts/quality/run_body_snapshot_quality_gates_v1.py`
  - `configs/body_snapshot_quality_gates_v1.json`
  - актуальный отчет: `data/derived/reports/body_snapshot_quality_gates_v1_20260409T150506Z.json`

## Focus (актуально)

- Реестр документов как единая точка видимости.
- Стабильное извлечение фактов в canonical + переход к атомарному fact-layer.
- Review на уровне фактов (а не только документа): что именно сомнительно и почему.
- Контроль качества по формальным gate-метрикам до масштабирования новых batch.
- Понятная сводка: что извлечено, что проверено, что требует ручного ревью.
- Приоритет качества: диагнозы/исследования/лабы/клинические выводы; medications — non-blocking слой.

## Operational notes

- После обработки каждый файл обязательно переносится в `recognized|needs_review|non_medical`.
- После каждого раунда обязательно обновляются:
  - `data/canonical/documents/batch_01_registry_roundN.*`
  - `data/canonical/documents/batch_01_registry_active.*`
  - `data/derived/reports/batch_01_findings_roundN.json`
  - `data/audit/logs/batch_01_agent.ndjson`
