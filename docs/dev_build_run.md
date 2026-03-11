# Dev build/run guide

Этот документ описывает рабочий dev-процесс для проекта `edu-operations-research-practice`.

## 1. Локальная разработка (localhost)

### Требования

- Python 3.11
- `uv`
- GNU Make

Проверка:

```bash
python3 --version
uv --version
make --version
```

### Установка зависимостей

```bash
make install
```

Эквивалентная команда:

```bash
uv sync --all-packages --group dev
```

### Запуск dev-сервера

```bash
make dev
```

Приложение будет доступно на `http://127.0.0.1:8000`.

Кастомный host/port:

```bash
make dev HOST=0.0.0.0 PORT=8080
```

### Проверки качества и тестов

```bash
make check
make check-all
```

`make check` запускает быстрый baseline (`ruff check` + `pytest`).
`make check-all` дополнительно требует чистое форматирование (`ruff format --check`).

## 1.1 Beads safe workflow (обязательно)

Для этого репозитория включён safe-контракт beads:

- raw `bd sync` не используется;
- используется flush-only экспорт `.beads/issues.jsonl`;
- минимальная версия `bd`: `0.59.0`.

Команды:

```bash
make bd-check
make bd-import
make bd-flush
make bd-session-close
```

Рекомендуемая последовательность:

```bash
git pull --rebase
make bd-import
# ... работа ...
make bd-session-close
git add -A
git commit -m "[eorp-<id>] ..."
git push
```

## 2. Docker dev

### Требования

- Docker Desktop / Docker Engine
- Docker Compose v2

Проверка:

```bash
docker --version
docker compose version
```

### Запуск

```bash
make docker-up
```

Остановка:

```bash
make docker-down
```

Логи:

```bash
make docker-logs
```

## 3. Переменные окружения LLM

Основные переменные:

- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `GIGACHAT_API_KEY`, `GIGACHAT_MODEL`, `GIGACHAT_BASE_URL`
- `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, `LOCAL_LLM_API_KEY`

Для локального запуска (`make dev`) переменные берутся напрямую из shell-окружения процесса.
Для Docker запуска (`make docker-up`) переменные прокидываются через `docker-compose.yml`.

Пример для OpenAI:

```bash
export OPENAI_API_KEY="sk-..."
make dev
```

и для Docker:

```bash
export OPENAI_API_KEY="sk-..."
make docker-up
```

## 4. Диагностика

Быстрая диагностика окружения:

```bash
make doctor
```

Безопасная очистка кэшей:

```bash
make clean
```

## 5. Recovery playbook (beads)

Если после beads-команды вы видите массовые staged `A/D` в `git status`:

1. Зафиксируйте текущее состояние отдельным recovery-коммитом (без потери файлов).
2. Убедитесь, что установлен `bd >= 0.59.0`.
3. Проверьте политику:
   ```bash
   make bd-check
   ```
4. При повреждённой/недоступной beads-базе восстановите из JSONL:
   ```bash
   make bd-recover-from-jsonl
   ```
5. Снова выполните:
   ```bash
   make bd-check
   make bd-flush
   ```
