# Архитектура v1

## Слои

- `packages/or_core`: доменные модели, 4 OR-солвера и детерминированный `ORPipeline` на LangGraph.
- `packages/agent_core`: диалоговый граф, извлечение параметров, LiteLLM-адаптер, сессии.
- `apps/webapp`: FastAPI + HTMX интерфейс и API-эндпоинты.

## Графы

- `DialogGraph`: сбор параметров -> проверка полноты -> запуск OR -> объяснение.
- `ORSubgraph`: `optimize_production -> allocate_shipments -> assign_resources -> build_routes -> finalize_report`.

## Принципы

- Узлы графов чистые: получают state, возвращают patch state.
- OR-вычисления не зависят от LLM.
- LLM используется только для извлечения параметров и объяснения результата.
- При недоступности провайдера включается fallback без падения сессии.

## Смежная документация

- `docs/dev_build_run.md` — как собирать и запускать проект в dev (localhost + docker).
- `docs/git_ssh_github.md` — практический гайд по Git/SSH/GitHub для этого репозитория.
