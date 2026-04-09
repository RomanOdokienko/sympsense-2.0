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

## Точка входа для нового чата

1. [docs/00_start_here.md](docs/00_start_here.md)
2. [docs/NEW_CHAT_BOOTSTRAP.md](docs/NEW_CHAT_BOOTSTRAP.md)
3. [docs/NEW_CHAT_PROMPT_TEMPLATE.md](docs/NEW_CHAT_PROMPT_TEMPLATE.md)
4. [docs/GIT_BOOTSTRAP.md](docs/GIT_BOOTSTRAP.md)
