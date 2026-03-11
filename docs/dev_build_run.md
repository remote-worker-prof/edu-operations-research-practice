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
