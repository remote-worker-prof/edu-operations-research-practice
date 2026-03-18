# edu-operations-research-practice

Демонстрационный учебный монорепозиторий по дисциплине «Исследование операций»:
интерактивный AI-агент с диалогом, который запускает детерминированный OR-пайплайн из 4 задач.

Важно понимать границы системы с самого начала:

- это не агент для произвольных классов оптимизационных задач;
- это один фиксированный учебный OR-конвейер
  `production -> shipment -> assignment -> routing`;
- внутри каждого этапа входы могут иметь переменную размерность в матрично-векторной форме:
  можно менять число продуктов, ресурсов, складов, клиентов, транспортных средств и узлов маршрутизации,
  пока сохраняются математический тип постановки и межэтапные связи.

Именно так проект и задуман как учебный агент: он остаётся объяснимым,
детерминированным и методически управляемым, но не сводится к одному
жёстко зашитому demo-case.

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
- `tests` — unit/integration/API/browser E2E тесты
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
make test-e2e
make test-e2e-openai
make test-e2e-openai-demo
make test-e2e-openai-demo-record
make test-e2e-openai-video-pack
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

Browser E2E через Selenium + headless Chromium:

```bash
make doctor
make test-e2e
```

Optional real OpenAI smoke:

```bash
make test-e2e-openai
```

Visible screencast-friendly OpenAI demo with long human pauses:

```bash
make test-e2e-openai-demo
```

Visible OpenAI demo with MP4 recording of the Chromium window:

```bash
make test-e2e-openai-demo-record
```

Full OpenAI video pack with 5 recorded Selenium scenarios:

```bash
make test-e2e-openai-video-pack
```

К записанным MP4 теперь есть и подробные текстовые companion-разборы:

- [docs/assets/selenium_videos/README.md](docs/assets/selenium_videos/README.md)
- [docs/video_scenarios/README.md](docs/video_scenarios/README.md)

Visible demo/video target'ы теперь специально замедлены по умолчанию для занятий,
скринкастов и покадрового объяснения. Быстрый regression-контур остаётся таким:

- `make test-e2e`
- `make test-e2e-openai`

Все OpenAI target (`make test-e2e-openai`, `make test-e2e-openai-demo`,
`make test-e2e-openai-demo-record` и `make test-e2e-openai-video-pack`)
запускаются через login `bash`, чтобы подхватить `OPENAI_API_KEY`
из `~/.bash_profile`, `~/.profile` или `~/.bashrc`.

Prerequisites и override-переменные для browser harness:

- нужен локальный Chromium/Chrome с рабочим headless-режимом;
- по умолчанию Selenium использует Selenium Manager для поиска/скачивания driver;
- `E2E_CHROMIUM_BINARY` — явный путь к browser binary;
- `E2E_CHROMEDRIVER_PATH` — явный путь к `chromedriver`, если нужен ручной override;
- `E2E_HEADLESS=0` — отключить headless-режим;
- `E2E_OPENAI_SMOKE=1` и `OPENAI_API_KEY` — включить real-provider smoke.
- `E2E_DEMO_MODE=1` — включает screencast/demo режим с “человеческими” паузами.
- `E2E_DEMO_INITIAL_DELAY_SECONDS` — пауза после открытия страницы.
- `E2E_DEMO_STEP_DELAY_SECONDS` — пауза между действиями и после HTMX-обновлений.
- `E2E_DEMO_TYPE_DELAY_SECONDS` — задержка между символами при наборе текста.
- `E2E_DEMO_FINAL_DELAY_SECONDS` — сколько держать финальный кадр перед закрытием окна.
- `E2E_RECORD_VIDEO=1` — включает запись видимого окна Chromium в MP4.
- `E2E_VIDEO_OUTPUT_DIR` — каталог для `.mp4` артефактов.
- `E2E_VIDEO_FPS` — частота кадров при записи окна.
- `VIDEO_CASE=<slug>` — фильтр одного сценария внутри full video pack.

Запись теперь идёт по реальному X11 `window_id` Chromium, а не по ручному
координатному crop. Это убирает проблемы HiDPI/scale, когда в MP4 попадал
только левый верхний фрагмент окна.

Параметры для `make test-e2e-openai-demo` можно переопределять:

```bash
make test-e2e-openai-demo DEMO_STEP_DELAY=3.5 DEMO_TYPE_DELAY=0.12 DEMO_FINAL_DELAY=12
```

Чтобы ускорить demo-таргеты для локальной отладки, можно явно уменьшить задержки:

```bash
make test-e2e-openai-demo DEMO_INITIAL_DELAY=1 DEMO_STEP_DELAY=1.5 DEMO_TYPE_DELAY=0.06 DEMO_FINAL_DELAY=4
```

Параметры для записи одного ролика можно переопределять:

```bash
make test-e2e-openai-demo-record \
  DEMO_INITIAL_DELAY=3 \
  DEMO_STEP_DELAY=4 \
  DEMO_TYPE_DELAY=0.14 \
  DEMO_FINAL_DELAY=15 \
  VIDEO_FPS=20
```

Полный video pack можно сузить до одного сценария:

```bash
make test-e2e-openai-video-pack VIDEO_CASE=manual_json_flow
```

Доступные recorded OpenAI video scenarios:

- `preset_overview`
- `manual_json_flow`
- `nl_confirm_flow`
- `validation_recovery_flow`
- `ambiguity_resolution_flow`

Пять основных режимов запуска Selenium:

- `make test-e2e` — быстрый deterministic headless regression suite.
- `make test-e2e-openai` — быстрый real-provider smoke без записи.
- `make test-e2e-openai-demo` — видимый demo-запуск с паузами, без записи.
- `make test-e2e-openai-demo-record` — видимый demo-запуск с записью одного ролика.
- `make test-e2e-openai-video-pack` — записывает полный набор из 5 OpenAI роликов.

При падении browser E2E screenshot и HTML page source сохраняются в `.pytest_artifacts/e2e/`.
MP4-файлы recorded demo сохраняются в `.pytest_artifacts/e2e/videos/` по умолчанию.

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
- сбор структурированных OR-входов идёт через детерминированный parser/wizard;
- объяснение результата строится детерминированным шаблоном.

## Интерактивный сбор OR-входов

Перед запуском OR-подграфа пользователь заполняет все независимые входы в чате.
Можно работать в двух режимах:
- natural-language: свободная реплика -> candidate patches -> подтверждение `да/нет`;
- command fallback: явные команды для точного контроля.

Основные команды:

```bash
start
show input
json <stage> { ... }
set <stage>.<field> <value>
edit <stage>
next
load preset demo
run
```

`data/scenarios/base_scenario.json` используется только как опциональный preset (`load preset demo`),
а не как обязательная автоподстановка runtime.

Если нужен подробный beginner-friendly reference по языку ввода, уровню строгости,
piece-by-piece вводу и stage-by-stage примерам, смотрите
[docs/chat_input_language_for_beginners_ru.md](docs/chat_input_language_for_beginners_ru.md).
Если нужны практические разборы уже готовых Selenium-демо с математикой,
exact сообщениями в чат и ожидаемыми checkpoints, смотрите
[docs/video_scenarios/README.md](docs/video_scenarios/README.md).

## API

- `GET /` — HTML интерфейс
- `POST /chat/turn` — HTMX endpoint
- `POST /api/chat/turn` — JSON endpoint
- `GET /api/session/{session_id}` — состояние сессии
- `GET /healthz` — health check

## Review Outcome

- [docs/video_scenarios/README.md](docs/video_scenarios/README.md) — текстовые companion-разборы для 5 демонстрационных Selenium-видео: постановка задачи, математика, exact ввод и ожидаемые результаты.
- [docs/architecture_for_beginners_ru.md](docs/architecture_for_beginners_ru.md) — длинное простое введение в архитектуру проекта для новичка.
- [docs/chat_usage_for_beginners_ru.md](docs/chat_usage_for_beginners_ru.md) — подробный guide по тому, как общаться с чатом и в каком виде отправлять данные.
- [docs/chat_input_language_for_beginners_ru.md](docs/chat_input_language_for_beginners_ru.md) — отдельный beginner-friendly reference по языку ввода чата, DSL-формам и safe-практикам.
- [docs/assets/selenium_videos/README.md](docs/assets/selenium_videos/README.md) — набор записанных Selenium/Chromium MP4-роликов для демонстрации.
- `docs/review_outcome_v1.md` — краткий итог завершённого remediation после Code Review v1.
- `docs/documentation_standard_ru.md` — стандарт учебной кодовой документации для Python-кода проекта.
- `docs/or_subgraph_math.md` — формализация 4 оптимизационных этапов OR-подграфа.
- `docs/natural_language_assistant_ru.md` — как работает NL-режим и как исправлять интерпретацию в чате.
- `docs/epics/interactive_or_input_epic.md` — epic по интерактивному сбору OR-входов.

## Как читать код студенту

Если нужен самый мягкий вход, сначала прочитайте
[docs/architecture_for_beginners_ru.md](docs/architecture_for_beginners_ru.md),
а уже потом переходите к коду и технической архитектурной спецификации.

Практический маршрут чтения лучше разделять на два:

- Как устроена система:
  [docs/architecture_for_beginners_ru.md](docs/architecture_for_beginners_ru.md) ->
  [docs/architecture.md](docs/architecture.md) ->
  [docs/or_subgraph_math.md](docs/or_subgraph_math.md)
- Как правильно вводить данные в чат:
  [docs/chat_usage_for_beginners_ru.md](docs/chat_usage_for_beginners_ru.md) ->
  [docs/chat_input_language_for_beginners_ru.md](docs/chat_input_language_for_beginners_ru.md) ->
  [docs/natural_language_assistant_ru.md](docs/natural_language_assistant_ru.md)

Рекомендуемый порядок чтения, чтобы быстро восстановить полный flow системы:

1. Начать с [apps/webapp/src/webapp/main.py](/home/sorcerer/Projects/edu-operations-research-practice/apps/webapp/src/webapp/main.py): какие есть endpoints и как создаётся `AgentService`.
2. Перейти к [packages/agent_core/src/agent_core/service.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/service.py): как обрабатывается один ход диалога.
3. Изучить [packages/agent_core/src/agent_core/dialog_graph.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/dialog_graph.py): логика ветвления `collect -> run -> explain/error`.
4. Посмотреть [packages/agent_core/src/agent_core/input_parser.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/input_parser.py) и [packages/agent_core/src/agent_core/explainer.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/agent_core/src/agent_core/explainer.py): parser команд и fallback-пояснение.
5. Затем прочитать [packages/or_core/src/or_core/scenario.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/or_core/src/or_core/scenario.py): сборка `ORPipelineInput` из draft и загрузка preset.
6. Углубиться в [packages/or_core/src/or_core/pipeline.py](/home/sorcerer/Projects/edu-operations-research-practice/packages/or_core/src/or_core/pipeline.py) и солверы в [packages/or_core/src/or_core/solvers](/home/sorcerer/Projects/edu-operations-research-practice/packages/or_core/src/or_core/solvers).
7. Закрепить понимание через интеграционные тесты в [tests/integration/test_api.py](/home/sorcerer/Projects/edu-operations-research-practice/tests/integration/test_api.py).

## Docker (опционально)

```bash
docker compose up --build
```
