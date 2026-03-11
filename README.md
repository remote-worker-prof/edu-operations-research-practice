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
- `docs` — архитектура, запуск и итоговые заметки по quality/remediation
- `00-initial-temp/` — черновики (игнорируются Git)

## Быстрый старт

```bash
uv sync --all-packages --group dev
uv run --package webapp uvicorn webapp.main:app --reload
```

Открыть в браузере: `http://127.0.0.1:8000`

## Makefile

Единая точка входа для типовых задач разработки:

```bash
make install
make dev
make check
make check-all
make docker-up
make bd-check
make bd-import
make bd-flush
make docs-check
```

Полезные примеры с override-параметрами:

```bash
make dev HOST=0.0.0.0 PORT=8080
make test PYTEST_ARGS='-k dialog -vv'
```

## Beads Safe Workflow

В этом репозитории beads работает в **flush-only** режиме.

- Не используйте raw `bd sync`.
- Версия `bd` должна быть `>= 0.59.0`.
- На старте сессии:
  ```bash
  git pull --rebase
  make bd-import
  ```
- Перед commit/push:
  ```bash
  make bd-session-close
  git add -A
  git commit -m "[eorp-<id>] ..."
  git push
  ```

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

## Review Outcome

- `docs/review_outcome_v1.md` — краткий итог завершённого remediation после Code Review v1.
- `docs/documentation_standard_ru.md` — стандарт учебной кодовой документации для Python-кода проекта.
- `docs/or_subgraph_math.md` — формализация 4 оптимизационных этапов OR-подграфа.

## Как читать код студенту

Рекомендуемый порядок чтения, чтобы быстро восстановить полный flow системы:

1. Начать с [apps/webapp/src/webapp/main.py](/home/sorcerer/Projects/edu-operations-research-practice/apps/webapp/src/webapp/main.py): какие есть endpoints и как создаётся `AgentService`.
2. Перейти к [packages/agent_core/src/agent_core/service.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/service.py): как обрабатывается один ход диалога.
3. Изучить [packages/agent_core/src/agent_core/dialog_graph.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/dialog_graph.py): логика ветвления `extract -> ask/run -> explain/error`.
4. Посмотреть [packages/agent_core/src/agent_core/extractor.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/extractor.py) и [packages/agent_core/src/agent_core/explainer.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/explainer.py): extraction и fallback-пояснение.
5. Затем прочитать [packages/or_core/src/or_core/pipeline.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/or_core/src/or_core/pipeline.py): последовательность 4 OR-этапов.
6. Углубиться в солверы в [packages/or_core/src/or_core/solvers](/home/sorcerer/Projects/edu-operations-research-practice/packages/or_core/src/or_core/solvers): `production`, `shipment`, `assignment`, `routing`.
7. Закрепить понимание через интеграционные тесты в [tests/integration/test_api.py](/home/sorcerer/Projects/edu-operations-research-practice/tests/integration/test_api.py).

## Docker (опционально)

```bash
docker compose up --build
```
