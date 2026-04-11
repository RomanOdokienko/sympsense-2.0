# Local API (v0)

Минимальный read-only API поверх локальных JSON в `data/canonical` и `data/derived`.

## Установка зависимостей

```powershell
cd "D:\разработка\Sympsense 2.0"
pip install -e .
```

## Запуск

```powershell
sympsense serve-api --host 127.0.0.1 --port 8000
```

Swagger UI:

- `http://127.0.0.1:8000/docs`

## Переменные окружения

- `SYMPSENSE_DATA_ROOT` - путь к директории `data` (если нужно переопределить автоопределение).

Пример:

```powershell
$env:SYMPSENSE_DATA_ROOT = "D:\разработка\Sympsense 2.0\data"
sympsense serve-api
```

## Доступные endpoints

- `GET /health`
- `GET /v1/overview`
- `GET /v1/quality/latest`
- `GET /v1/selfcheck/latest`
- `POST /v1/selfcheck/run`
- `GET /v1/analytics/body-graph`
- `GET /v1/export/downstream-v1`
- `POST /v1/export/downstream-v1/build`
- `GET /v1/reports/patient-briefing/v1`
- `POST /v1/reports/patient-briefing/v1/build`
- `GET /v1/facts/problem-list/v1`
- `POST /v1/facts/problem-list/v1/build`
- `GET /v1/documents`
- `GET /v1/documents/{doc_id}`
- `GET /v1/review/documents`
- `GET /v1/review/documents/{doc_id}`
- `GET /v1/review/fact-queue`
- `POST /v1/review/fact-queue/decision`
- `GET /v1/facts/{collection}`
- `GET /v1/body-snapshot`

`collection`:
- `lab_results`
- `clinical_findings`
- `recommendation_items`
- `medication_items`
- `condition_mentions`
- `condition_clusters`
- `investigation_events`
- `condition_investigation_links`

## Примечание

Это API-слой чтения для перехода от file-driven UI к backend-driven архитектуре без миграции базы на текущем этапе.

## UI integration

`Documents Review UI` теперь читает данные через:

- `GET /v1/review/documents`
- `GET /v1/review/documents/{doc_id}`

UI доступен прямо на том же сервере:

- `GET /ui`
- URL: `http://127.0.0.1:8000/ui`

Delete/file операции также обслуживаются тем же API:

- `GET /api/health`
- `GET /api/file?rel=...`
- `POST /api/delete`
- `POST /api/rebuild`

Отдельный `run_documents_review_ui_server.py` можно использовать только как legacy-режим совместимости.
