# Sympsense 2.0

Личный медицинский агент в режиме `agent-first`.

## Текущий сценарий (основной)

1. Ты кладешь документы в:
   - `D:\разработка\Sympsense 2.0\data\raw\inbox\batch_01\`
2. Опционально добавляешь:
   - `D:\разработка\Sympsense 2.0\data\raw\inbox\batch_01\context.txt`
3. Агент в сессии читает файлы с диска и делает:
   - первичную типизацию,
   - извлечение фактов,
   - обновление реестра и базы,
   - короткую сводку по изменениям.

## Что важно

- Приоритет: разбор реальных файлов в папке, а не написание новых парсеров.
- Автоматизация добавляется только там, где реально снижает ручной труд.
- Без медицинских диагнозов и назначений лечения.

## Local API

- Запуск: `sympsense serve-api --host 127.0.0.1 --port 8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Детали: [docs/08_local_api.md](docs/08_local_api.md)

## Self-check

- CLI: `sympsense selfcheck`
- API run: `POST http://127.0.0.1:8000/v1/selfcheck/run`
- API latest: `GET http://127.0.0.1:8000/v1/selfcheck/latest`

## Analytics graph

- API: `GET http://127.0.0.1:8000/v1/analytics/body-graph`
- Назначение: граф `condition_cluster -> investigation -> document` для downstream-аналитики

## Downstream export

- CLI: `sympsense export-downstream`
- API (read): `GET http://127.0.0.1:8000/v1/export/downstream-v1`
- API (build report): `POST http://127.0.0.1:8000/v1/export/downstream-v1/build`

## Patient briefing

- CLI: `sympsense patient-briefing`
- API (read): `GET http://127.0.0.1:8000/v1/reports/patient-briefing/v1`
- API (build report): `POST http://127.0.0.1:8000/v1/reports/patient-briefing/v1/build`

## Problem list (curated)

- CLI: `sympsense problem-list`
- API (read): `GET http://127.0.0.1:8000/v1/facts/problem-list/v1`
- API (build report): `POST http://127.0.0.1:8000/v1/facts/problem-list/v1/build`
- Назначение: разделяет состояния на `stable_problem / episodic_condition / symptom_or_state / uncertain`

## Documents Review UI

- URL: `http://127.0.0.1:8000/ui`
- Запускается в том же процессе `sympsense serve-api`
- Отдельный UI-server больше не обязателен
- В UI доступны блоки `Analytics Snapshot` и `Fact Review Queue`
- В `Fact Review Queue` можно отмечать факты как `resolved/skipped`
- В `Analytics Snapshot` доступен drill-down по condition clusters (связанные исследования/документы)

## Точка входа для нового чата

1. [docs/00_start_here.md](docs/00_start_here.md)
2. [docs/NEW_CHAT_BOOTSTRAP.md](docs/NEW_CHAT_BOOTSTRAP.md)
3. [docs/NEW_CHAT_PROMPT_TEMPLATE.md](docs/NEW_CHAT_PROMPT_TEMPLATE.md)
4. [docs/GIT_BOOTSTRAP.md](docs/GIT_BOOTSTRAP.md)
