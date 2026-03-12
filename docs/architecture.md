# Архитектура v1

## 1. Слои и ответственность

- `apps/webapp`:
  - HTTP-слой (`FastAPI` + `HTMX`), рендеринг страницы и partial-ответов.
  - Не содержит бизнес-логики OR, только вызывает `AgentService`.
- `packages/agent_core`:
  - Диалоговый граф (`DialogGraph`), интерактивный сбор входов, объяснение результата.
  - Управление сессиями и интеграция с `LiteLLM`.
- `packages/or_core`:
  - Детерминированный OR-пайплайн из 4 солверов.
  - Доменные модели входов/выходов и строгая валидация.

Ключевой принцип: `LLM` не является источником истины для структурированных OR-входов.
Сбор входов выполняется детерминированным parser/wizard, а `LLM` используется для объяснения.

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
  - `scenario_draft` — текущий черновик всех независимых OR-входов;
  - `collection_state` — состояние wizard (`current_stage`, `ready_to_run`);
  - `missing_fields` — какие stage ещё не готовы;
  - `validation_errors_by_stage` — ошибки валидации по stage;
  - `pending_question` — следующий вопрос для пользователя;
  - `or_result` — результат OR-пайплайна (или `null`);
  - `warnings`, `errors` — диагностические сообщения для пользователя.

### Контракт OR-пайплайна

- Вход: `or_core.models.ORPipelineInput`.
- Выход: `or_core.models.ORResult`:
  - `production`, `shipment`, `assignment`, `routing`;
  - `final_report`;
  - `execution_trace` (порядок только оптимизационных шагов OR-подграфа).

## 3. Sequence: `chat -> collect_inputs -> run_or -> explanation`

1. Пользователь отправляет сообщение в `webapp`.
2. `AgentService.handle_turn()` поднимает/получает сессию и вызывает `DialogGraph`.
3. Узел `collect_inputs`:
  - сначала пытается интерпретировать свободный текст через `parse_nl_turn`;
  - применяет policy приоритетов: если в реплике есть структурированные поля, сначала extraction; intent `run` рассматривается только когда поля не извлечены;
  - формирует `candidate patches`, confidence и уточнения;
  - при низкой уверенности может использовать optional LLM-assisted fallback, но всё равно не применяет patch автоматически;
  - применяет patch только после явного подтверждения `да/нет`;
  - при необходимости переключается на детерминированные команды (`start`, `json`, `set`, `run`, ...);
  - обновляет `ScenarioDraft`;
  - валидирует stage и вычисляет `ready_to_run`.
4. Пока `ready_to_run = false`, агент продолжает задавать уточняющие вопросы по stage.
5. По явной команде `run` и при `ready_to_run = true` узел `run_or_subgraph`:
  - собирает `ORPipelineInput` из `ScenarioDraft`;
  - запускает 4 OR-этапа.
  - запуск блокируется, если есть неподтверждённые `candidate patches`.
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
  - вход: `client_delivery`, mapping назначений `client -> resource`, routing-template;
  - внутри: из `AssignmentOutput.pairs` строится ограничение `allowed_vehicle_ids_by_client`;
  - выход: `RoutingOutput` (маршруты и метрики).

`final_report` собирается после завершения OR-подграфа как пост-обработка и не считается узлом оптимизации.

## 4.1 Математическая формализация 4 этапов

1. `Production (LP)`:
  - переменные: объёмы выпуска `x_p` для произвольного числа продуктов `p in P`;
  - цель: `max profit`;
  - ограничения: ресурсы и верхние границы спроса.
2. `Shipment (Min-Cost Flow)`:
  - переменные: потоки `f_{warehouse, client}`;
  - цель: `min transport cost`;
  - ограничения: баланс потоков, пропускные способности дуг, доступный объём паллет.
3. `Assignment (Linear Assignment)`:
  - переменные: бинарные назначения `y_{resource, task}`;
  - цель: `min assignment cost`;
  - ограничения: каждая задача закреплена ровно за одним ресурсом, ресурс назначается не более чем на одну задачу.
4. `Routing (CVRP)`:
  - переменные: дуги маршрутов и загрузка ТС;
  - цель: `min total_distance`;
  - ограничения: ёмкости ТС, покрытие обязательных клиентов, и ограничения допустимых ТС по клиентам из этапа assignment;
  - `client_demands` для solver-а не вводится вручную в draft и вычисляется из `ShipmentOutput.client_delivery`.

## 5. Ошибки и деградация

- Невалидный stage input:
  - не приводит к 500;
  - отображается в `validation_errors_by_stage` и `pending_question`.
- Неоднозначная NL-интерпретация:
  - не применяется автоматически;
  - отображается в `nl_uncertainties` и переводит диалог в уточняющий шаг.
- Mixed-реплика (`посчитай + параметры`):
  - параметры извлекаются в `candidate patches`;
  - запуск расчёта до подтверждения patch-ей блокируется.
- Ошибка OR-пайплайна:
  - сохраняется в `session.errors`;
  - пользователю возвращается корректный assistant-response с описанием ошибки.
- Недоступный LLM-провайдер:
  - создаёт предупреждение (`session.warnings`);
  - объяснение формируется fallback-логикой.

## 6. Учебный UX (веб-экран)

- Левая панель:
  - прогресс заполнения 4 stage;
  - статус `ready_to_run`;
  - карточки 4 OR-этапов;
  - предупреждения и ошибки.
- Правая панель:
  - история диалога;
  - ввод сообщения и выбор модели человеко-понятными названиями.
- Если входы не полны, интерфейс явно показывает следующий шаг (`pending_question`).

## 7. Рекомендуемый порядок чтения кода

1. `apps/webapp/src/webapp/main.py`:
  - как HTTP-запросы превращаются в вызовы прикладного сервиса.
2. `packages/agent_core/src/agent_core/service.py`:
  - как организован lifecycle одного хода диалога.
3. `packages/agent_core/src/agent_core/dialog_graph.py`:
  - ветвление сценария `collect -> run -> explain/error`.
4. `packages/agent_core/src/agent_core/input_parser.py` и `explainer.py`:
  - parser команд/patch и генерация объяснения.
5. `packages/or_core/src/or_core/pipeline.py`:
  - последовательность 4 OR-этапов.
6. `packages/or_core/src/or_core/solvers/*.py`:
  - детали каждого математического решателя.
7. `tests/integration/*.py`:
  - как проверяется сквозной user flow и деградированные ветки.

## 8. Смежная документация

- `docs/dev_build_run.md` — локальный/dev/docker запуск.
- `docs/git_ssh_github.md` — Git/SSH/GitHub workflow для репозитория.
- `docs/or_subgraph_math.md` — краткая формализация оптимизационных моделей OR-подграфа.
- `docs/natural_language_assistant_ru.md` — учебный контракт NL-режима (реплика -> patch -> подтверждение).
- `docs/epics/interactive_or_input_epic.md` — план и контракт интерактивного сбора входов.
