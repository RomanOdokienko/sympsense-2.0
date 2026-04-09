# New Chat Bootstrap

Минимальный контекст для нового чата.

## Активный проект

- `D:\разработка\Sympsense 2.0`
- legacy `D:\разработка\Health` не использовать

## Базовое ТЗ

1. Пользователь кладет документы в `data/raw/inbox/<batch_id>`.
2. Агент сам читает файлы с диска в сессии.
3. Агент обрабатывает батчами по 5 файлов: типизация + извлечение фактов.
4. Агент обновляет реестр + canonical записи.
5. Агент делает понятную сводку и помечает `needs_review` где нужно.
6. Распознавание: сначала `text_layer`, но при отсутствии/низком качестве текстового слоя обязательно fallback на `multimodal_vision` для локальных страниц.

## Текущая рабочая точка (2026-04-08)

- Активный batch: `data/raw/inbox/batch_01`
- Уже выполнены раунды:
  - `batch_01_registry_round1.*` (исторический старт)
  - `batch_01_registry_round2.*` (5 файлов)
  - `batch_01_registry_round3.*` (5 файлов)
- Актуальный реестр: `data/canonical/documents/batch_01_registry_active.json` (20 записей)
- Текущие счетчики:
  - `inbox`: 56 файлов
  - `recognized`: 13 файлов
  - `needs_review`: 0
  - `non_medical`: 1

## Что делать на команду "двигаем дальше"

1. Подтвердить `workdir = D:\разработка\Sympsense 2.0`.
2. Взять следующие 5 новых файлов из `data/raw/inbox/batch_01` (которых еще нет в `batch_01_registry_active.json`).
3. Для каждого файла:
   - извлечь текст (с обязательным fallback `text_layer -> multimodal_vision` при проблемах слоя),
   - типизировать,
   - записать в реестр (`documents`) и domain-facts (`doctor_conclusions/recommendations/labs/...`),
   - перенести исходник в `recognized|needs_review|non_medical`.
4. Создать следующий `batch_01_registry_roundN.json` + `batch_01_findings_roundN.json`.
5. Обновить `batch_01_registry_active.*` и `docs/WORKING_STATE_2026-04-08.md`.

## Что не делать по умолчанию

- Не начинать с разработки новых парсеров.
- Не уводить фокус в абстрактные этапные формулировки.
- Не подменять user flow техническим планом.
