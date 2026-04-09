# Git Bootstrap (Safe Profile)

Этот проект хранит чувствительные медицинские данные локально.
По умолчанию в Git должны попадать только код, конфиги и документация.

## 1) Инициализация

```powershell
cd "D:\разработка\Sympsense 2.0"
git init
git branch -M main
```

## 2) Безопасное добавление файлов (allowlist)

```powershell
git add .gitignore AGENTS.md README.md pyproject.toml
git add apps configs docs schemas scripts
```

Проверка, что в staged нет `data/`:

```powershell
git diff --cached --name-only | rg "^data/"
```

Команда выше должна вернуть пустой результат.

## 3) Первый коммит

```powershell
git commit -m "chore: bootstrap repository with safe data policy"
```

## 4) Подключение удаленного репозитория

```powershell
git remote add origin <REPO_URL>
git push -u origin main
```

## 5) Рабочий режим дальше

Для каждой задачи:

```powershell
git checkout -b feat/<short-topic>
# ... changes ...
git add <changed files>
git commit -m "<type>: <summary>"
git push -u origin feat/<short-topic>
```

## 6) Быстрый preflight перед push

```powershell
git status --short
git diff --cached --name-only | rg "^data/"
git diff --cached --name-only | rg "\.pdf$"
```

Обе проверки через `rg` должны быть пустыми.
