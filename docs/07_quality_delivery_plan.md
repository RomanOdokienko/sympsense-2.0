# Quality Delivery Plan (v1)

## Цель

Стабилизировать качество распознавания и наполнения `data/canonical` до масштабирования следующих раундов batch-обработки.

## Принципы

- Сначала качество и воспроизводимость, потом скорость.
- Любой факт должен быть трассируем до источника.
- Любой сомнительный результат автоматически уходит в `needs_review`.
- Документ не должен дублировать один и тот же смысл в разных сущностях canonical.

## Этап 1. Контракт структуры документа

Артефакт:
- `configs/section_map_v1.json`

Что фиксируем:
- `doctor_consultation`: секции и правила маппинга в `doctor_conclusions`, `recommendations`, `medications`, `symptoms_events`.
- `lab_report`: секции таблиц/метаданных и маппинг в `labs`.
- `imaging_report_*`: секции `findings/impression/recommendations`.
- anti-duplication правила (например, `recommendation` не дублируется в `conclusion`).

Критерий готовности:
- есть формальный маппинг `section -> canonical target` для каждого целевого типа документа.

## Этап 2. Quality-gates перед записью в canonical

Артефакты:
- `configs/quality_gates_v1.json`
- `scripts/quality/run_quality_gates_v1.py`

Блокирующие проверки:
- отсутствующий `source_path`;
- отсутствующий или неуникальный `full_extraction`;
- отсутствующие обязательные domain-факты по `doc_type`;
- отсутствующая `event_date`;
- признаки mojibake (битая кодировка);
- дублирование `doctor_conclusion` и `recommendation`.

Критерий готовности:
- есть исполняемый отчет quality-gates в `data/derived/reports/*.json`.

## Этап 3. Gold-set для приемки качества

Артефакт:
- `configs/goldset_v1.json`

Что фиксируем:
- репрезентативные документы (`doctor_consultation`, `lab_report`, `imaging_report_*`);
- ожидаемый `doc_type`;
- обязательные сущности;
- требование на чистый текст (`must_have_clean_text`).

Критерий готовности:
- gold-set проверяется автоматически в quality-отчете.

## Этап 4. Baseline и remediation

Что делаем:
- прогоняем quality-gates на текущей базе;
- фиксируем baseline и список дефектов;
- исправляем дефекты пакетно (с аудитом операций).

Критерий готовности:
- все blocker-gates зеленые на active-registry.

## Этап 5. Scale policy для batch-обработки

Правило:
- по 10 документов только если предыдущий раунд прошел quality-gates;
- при провале качества автоматически снижаем размер следующего раунда до 3-5.

Критерий готовности:
- минимум два успешных раунда подряд без blocker-дефектов.
