# Data Contracts (текущий scope)

## 1) documents (реестр)

Поля:
- `doc_id` (string)
- `document_date` (date | null)
- `doc_type` (string)
- `source_path` (string)
- `medical_organization` (string | null)
- `department` (string | null)
- `processing_status` (`new|typed|extracted|needs_review|confirmed`)
- `confidence` (number 0..1 | null)
- `linked_facts` (array of ids)
- `parse_mode` (`text_layer|multimodal_vision|hybrid`)
- `parse_notes` (string | null, почему выбран/сменен режим)

## 2) domain facts

Активные домены:
- `labs`
- `doctor_conclusions`
- `medications`
- `symptoms_events`
- `recommendations`

Базовые общие поля каждой записи:
- `id`
- `patient_id`
- `event_date`
- `source` (ссылка на исходный документ)
- `status`
- `medical_organization` (если есть в источнике)
- `department` (если есть в источнике)

## 3) требования к изменениям

- Нельзя ломать совместимость уже записанных данных без явной миграции.
- Любая переработка должна быть воспроизводимой.
- Ключевые операции должны попадать в audit-log.
