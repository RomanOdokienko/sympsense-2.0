# Working State (2026-04-08)

## Текущее состояние данных

- `data/raw/inbox/batch_01`: 0 файлов
- `data/raw/recognized/batch_01`: 69 файлов
- `data/raw/non_medical/batch_01`: 1 файл
- `data/raw/needs_review/batch_01`: 0 файлов

## Canonical состояние

- `data/canonical/documents/batch_01_registry_active.json`: 66 записей
- `data/canonical/labs`: 14 записей
- `data/canonical/doctor_conclusions`: 52 записей
- `data/canonical/recommendations`: 26 записей

## Что сделано в последних раундах

- `round2` (5 файлов): стоматология, 2014 год, документы `report-15644-1909018...1909022`
- `round3` (5 файлов): офтальмология/хирургия/травматология, документы `report-15644-1909023...2029047`
- `round4` (5 файлов): рентген + УЗИ + 3 консультации, документы `report-15644-2029077...2057384`
- `round5` (5 файлов): 3 imaging + 2 консультации, документы `report-15644-2083943...2114372`
- `round6` (5 файлов): 2 imaging + 3 консультации физиотерапевта, документы `report-15644-2114401...2162113`
- `round7` (5 файлов): 5 консультаций, документы `report-15644-2166156...2258057`
- `round8` (10 файлов): лабораторные отчеты `Rezul*` за 2022-2024
- `round9` (10 файлов): 9 консультаций + 1 УЗИ (`report-15644-2310389...2829326`)
- `round10` (6 файлов): остаток `inbox` (`report-15644-2836699...4254892` + `Консультация физиотерапевта (1).pdf`)
- Обновлены правила распознавания: `text_layer` + обязательный fallback на `multimodal_vision` для image-only/низкокачественного слоя.
- `quality rerun` (17 проблемных документов):
  - восстановлены пути `recognized` для 10 документов;
  - перегенерированы `full_extraction` и domain-facts для проблемных записей;
  - архивированы orphan labs (4 файла);
  - quality-gates зелёные по `data/derived/reports/preflight_rerun_check_2026-04-08.json`:
    - `source_path_missing_count = 0`
    - `missing_full_extraction_count = 0`
    - `missing_expected_domain_fact_count = 0`
    - `qmark_docs_count = 0`
    - `audit_coverage_missing_count = 0`
- зафиксированы артефакты quality-процесса v1:
  - `configs/section_map_v1.json`
  - `configs/quality_gates_v1.json`
  - `configs/goldset_v1.json`
  - `scripts/quality/run_quality_gates_v1.py`
  - `docs/07_quality_delivery_plan.md`
- baseline quality-gates по `data/derived/reports/quality_gates_v1_2026-04-08.json`:
  - `source_path_missing_count = 0`
  - `missing_full_extraction_count = 0`
  - `multiple_full_extraction_count = 0`
  - `missing_required_domain_fact_count = 0`
  - `missing_event_date_count = 0`
  - `mojibake_suspected_count = 0`
  - `duplicated_conclusion_recommendation_count = 0` (после remediation 9 документов)
  - `goldset = 10/10 pass`
- remediation для imaging-документов:
  - выполнен backfill canonical по `scripts/quality/backfill_imaging_canonical_v1.py`;
  - создано `doctor_conclusions` для 9 документов `imaging_report_*`;
  - создано 2 `recommendations` там, где в тексте есть соответствующая секция;
  - для imaging в `doctor_conclusions` добавлен `findings_text` (описательная часть протокола);
  - перегенерирован UI `data/derived/reports/ui_documents_registry.html` скриптом `scripts/reports/build_documents_review_ui_v2.py`;
  - для `imaging_report_*` в `quality_gates_v1` теперь обязательны `doctor_conclusions`.
- remediation для lab-документов:
  - выполнен backfill canonical по `scripts/quality/backfill_labs_canonical_v1.py`;
  - для `lab_report` заполнены `labs.sections[].items` из `full_extraction.raw_text_excerpt`;
  - добавлен dedupe canonical-labs по `doc_id` (`scripts/quality/dedupe_labs_by_docid_v1.py`), архив дублей: `data/canonical/labs/_orphaned_dedupe_2026-04-09/`;
  - обновлен UI: в правой панели показываются конкретные лабораторные маркеры (не только `labs: present`);
  - quality-gate расширен: `lab_reports_without_items_count`;
  - выполнена ретипизация `doc_606811c981ccf5da` из `lab_report` в `doctor_consultation` с canonical-remediation;
  - расширен lab-parser для строк формата `IgG 0,1 Ед`, после чего `doc_c77a304a4dfef2a7` получил валидный marker;
  - актуальный отчет: `data/derived/reports/quality_gates_v1_2026-04-09.json` (`all green`).
- по раундам `round2..round10` обновлены:
  - `data/canonical/documents/batch_01_registry_round2.*`
  - `data/canonical/documents/batch_01_registry_round3.*`
  - `data/canonical/documents/batch_01_registry_round4.*`
  - `data/canonical/documents/batch_01_registry_round5.*`
  - `data/canonical/documents/batch_01_registry_round6.*`
  - `data/canonical/documents/batch_01_registry_round7.*`
  - `data/canonical/documents/batch_01_registry_round8.*`
  - `data/canonical/documents/batch_01_registry_round9.*`
  - `data/canonical/documents/batch_01_registry_round10.*`
  - `data/canonical/documents/batch_01_registry_active.*`
  - `data/derived/reports/batch_01_findings_round2.json`
  - `data/derived/reports/batch_01_findings_round3.json`
  - `data/derived/reports/batch_01_findings_round4.json`
  - `data/derived/reports/batch_01_findings_round5.json`
  - `data/derived/reports/batch_01_findings_round6.json`
  - `data/derived/reports/batch_01_findings_round7.json`
  - `data/derived/reports/batch_01_findings_round8.json`
  - `data/derived/reports/batch_01_findings_round9.json`
  - `data/derived/reports/batch_01_findings_round10.json`
  - `data/audit/logs/batch_01_agent.ndjson`

## Следующий шаг в новом чате

На команду `двигаем дальше`:
1. перейти к детальной ручной QA-проверке извлечения в `ui_documents_registry.html`;
2. собрать список точечных дефектов качества;
3. выполнить targeted-remediation и повторный quality-check.

Ожидаемые файлы на следующий проход:
- `inbox/batch_01` пуст (новых файлов нет).
