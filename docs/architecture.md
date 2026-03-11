# Архитектура v1

## 1. Слои и ответственность

- `apps/webapp`:
  - HTTP-слой (`FastAPI` + `HTMX`), рендеринг страницы и partial-ответов.
  - Не содержит бизнес-логики OR, только вызывает `AgentService`.
- `packages/agent_core`:
  - Диалоговый граф (`DialogGraph`), извлечение параметров, объяснение результата.
  - Управление сессиями и интеграция с `LiteLLM`.
- `packages/or_core`:
  - Детерминированный OR-пайплайн из 4 солверов.
  - Доменные модели входов/выходов и строгая валидация.

Ключевой принцип: `LLM` отвечает только за извлечение и объяснение, а расчёт делает только `or_core`.

## 2. Контракты данных

### Вход веб-хода диалога

- `POST /api/chat/turn`
- JSON:
  - `session_id: str | null`
  - `model_alias: str`
  - `message: str`
- Модель: `agent_core.models.ChatTurnRequest`.

### Состояние сессии агента

- Модель: `agent_core.models.AgentSession`.
- Ключевые поля:
  - `messages` — история диалога;
  - `scenario_params` — коэффициенты сценария;
  - `missing_fields` — какие параметры ещё запросить;
  - `or_result` — результат OR-пайплайна (или `null`);
  - `warnings`, `errors` — диагностические сообщения для пользователя.

### Контракт OR-пайплайна

- Вход: `or_core.models.ORPipelineInput`.
- Выход: `or_core.models.ORResult`:
  - `production`, `shipment`, `assignment`, `routing`;
  - `final_report`;
  - `execution_trace` (порядок шагов).

## 3. Sequence: `chat -> extraction -> OR -> explanation`

1. Пользователь отправляет сообщение в `webapp`.
2. `AgentService.handle_turn()` поднимает/получает сессию и вызывает `DialogGraph`.
3. Узел `extract_params`:
  - пробует LLM-extraction;
  - при необходимости применяет regex-парсер;
  - валидирует коэффициенты.
4. Если параметров не хватает, `ask_missing` возвращает уточняющий вопрос.
5. Если параметры валидны, `run_or_subgraph`:
  - строит `ORPipelineInput` из seed-сценария;
  - запускает 4 OR-этапа.
6. Узел `explain`:
  - пытается получить объяснение через LLM;
  - при недоступности провайдера использует детерминированный fallback.
7. `webapp` возвращает обновлённый workspace (HTMX) или JSON-ответ API.

## 4. Dataflow между OR-этапами

1. `optimize_production`:
  - вход: `ProductionInput`;
  - выход: `ProductionOutput` (`total_pallets`).
2. `allocate_shipments`:
  - вход: шаблон отгрузки + `total_pallets`;
  - выход: `ShipmentOutput` (`client_delivery`, `tasks`).
3. `assign_resources`:
  - вход: `tasks` + список ресурсов + `cost_matrix`;
  - выход: `AssignmentOutput` (пары `resource -> task`).
4. `build_routes`:
  - вход: `client_delivery`, назначенные ресурсы, routing-template;
  - выход: `RoutingOutput` (маршруты и метрики).

## 5. Ошибки и деградация

- Невалидные коэффициенты:
  - не приводят к 500;
  - попадают в `session.errors` с понятным текстом.
- Ошибка OR-пайплайна:
  - сохраняется в `session.errors`;
  - пользователю возвращается корректный assistant-response с описанием ошибки.
- Недоступный LLM-провайдер:
  - создаёт предупреждение (`session.warnings`);
  - объяснение формируется fallback-логикой.

## 6. Учебный UX (веб-экран)

- Левая панель:
  - коэффициенты сценария;
  - карточки 4 OR-этапов;
  - предупреждения и ошибки.
- Правая панель:
  - история диалога;
  - ввод сообщения и выбор модели человеко-понятными названиями.
- Если параметров не хватает, интерфейс явно запрашивает:
  - `Коэффициент спроса`;
  - `Коэффициент ресурсов`.

## 7. Где смотреть код

- Оркестрация диалога: `packages/agent_core/src/agent_core/dialog_graph.py`.
- Извлечение параметров: `packages/agent_core/src/agent_core/extractor.py`.
- OR-пайплайн: `packages/or_core/src/or_core/pipeline.py`.
- Веб-эндпоинты: `apps/webapp/src/webapp/main.py`.
- Интеграционные тесты: `tests/integration/test_api.py`, `tests/integration/test_dialog_graph.py`.

## 8. Смежная документация

- `docs/dev_build_run.md` — локальный/dev/docker запуск.
- `docs/git_ssh_github.md` — Git/SSH/GitHub workflow для репозитория.
