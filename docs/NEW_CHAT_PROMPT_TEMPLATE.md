# New Chat Prompt Template

Project root: `D:\разработка\Sympsense 2.0`.

Перед работой:
1. Подтверди `workdir = D:\разработка\Sympsense 2.0`.
2. Подтверди, что `D:\разработка\Health` игнорируется.

Режим работы:
- agent-first.
- Читать реальные файлы из `data/raw/inbox/<batch_id>`.
- Обрабатывать батчами по 5 файлов.
- После каждого батча обновлять registry + canonical + audit + findings.

Если сообщение пользователя: `двигаем дальше`:
1. Возьми следующие 5 новых файлов из `data/raw/inbox/batch_01`.
2. Прогони стандартный цикл (типизация -> извлечение -> canonical -> перенос файла).
3. Сохрани `batch_01_registry_roundN.*` и `batch_01_findings_roundN.json`.
4. Обнови `batch_01_registry_active.*` и `docs/WORKING_STATE_2026-04-08.md`.
5. Верни короткую human-сводку: обработано/типы/добавлено/что под review.

Не начинай с parser-building, если об этом явно не попросили.
