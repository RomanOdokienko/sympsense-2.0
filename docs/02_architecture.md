# Архитектура (текущий scope)

## 1. Слои

1. `data/raw` - исходные документы.
2. `data/canonical` - структурированные факты (source of truth).
3. `data/derived` - отчеты и сводки.
4. `data/audit` - журнал действий.

## 2. Базовая модель

### Document Envelope

Универсальная карточка документа:
- `doc_id`
- `document_date`
- `doc_type`
- `source_path`
- `processing_status`
- `confidence`
- `linked_facts`

### Domain Facts

Отдельные записи по доменам:
- `labs`
- `doctor_conclusions`
- `medications`
- `symptoms_events`
- `recommendations`

## 3. Главный принцип

Сначала агент извлекает факты из реальных документов в сессии.
Только затем решаем, какие части стоит автоматизировать кодом.

## 4. Границы изменений

- UI должен читать реестр и факты, но не ломать контракты canonical.
- Любое изменение правил извлечения должно быть обратимо и трассируемо.
