# edu-operations-research-practice

Демонстрационный учебный монорепозиторий по дисциплине «Исследование операций»:
интерактивный AI-агент с диалогом, который запускает детерминированный OR-пайплайн из 4 задач.

## Технологии

- Python 3.11 + `uv`
- `LangGraph` (детерминированные графы)
- `LiteLLM` (OpenAI, GigaChat, local OpenAI-compatible)
- `SciPy`, `NetworkX`, `OR-Tools` (реальные OR-солверы)
- `FastAPI` + `Jinja2` + `HTMX` (легковесный веб-интерфейс)

## Структура монорепо

- `apps/webapp` — веб-приложение и API
- `packages/agent_core` — диалоговый агент, сессии, LLM-адаптер
- `packages/or_core` — доменные модели и OR-солверы
- `data/scenarios` — учебные сценарии
- `tests` — unit/integration/API/E2E-light тесты
- `docs` — архитектурные заметки
- `00-initial-temp/` — черновики (игнорируются Git)

## Быстрый старт

```bash
uv sync --all-packages --group dev
uv run --package webapp uvicorn webapp.main:app --reload
```

Открыть в браузере: `http://127.0.0.1:8000`

## Тесты

```bash
uv run --all-packages pytest
```

## Провайдеры моделей через LiteLLM

Доступные alias:

- `openai_default`
- `gigachat_default`
- `local_default`

Переменные окружения:

- OpenAI: `OPENAI_API_KEY`, опционально `OPENAI_MODEL`
- GigaChat: `GIGACHAT_API_KEY`, опционально `GIGACHAT_MODEL`, `GIGACHAT_BASE_URL`
- Local: `LOCAL_LLM_BASE_URL`, опционально `LOCAL_LLM_MODEL`, `LOCAL_LLM_API_KEY`

Если провайдер недоступен, приложение продолжает работу с fallback-логикой:
- извлечение параметров идёт через локальный парсер;
- объяснение результата строится детерминированным шаблоном.

## API

- `GET /` — HTML интерфейс
- `POST /chat/turn` — HTMX endpoint
- `POST /api/chat/turn` — JSON endpoint
- `GET /api/session/{session_id}` — состояние сессии
- `GET /healthz` — health check

## Docker (опционально)

```bash
docker compose up --build
```
