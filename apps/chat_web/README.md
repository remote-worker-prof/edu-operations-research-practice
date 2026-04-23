# `apps/chat_web`

Новый основной UI-чехол для проекта: `Next.js + CopilotKit` поверх backend-owned
thread/session state и typed semantics declarative extensions.

Сейчас именно этот shell считается основным пользовательским интерфейсом:

- `GET /` делает redirect на `/app/`;
- `/app/` обслуживает экспортированный React chat;
- `/legacy` оставляет старый HTMX/Jinja интерфейс как внутренний fallback.

## Что это даёт

- guided chat для обычного пользователя без необходимости помнить сырые команды;
- slash-команды для преподавателя, power-user режима и тестов;
- автоматические формы и result-view, которые строятся из typed semantics
  extension bundle, а не пишутся вручную под каждый extension;
- единый transport seam до Python backend через `CopilotKit + AG-UI`.

## Локальный запуск

Сначала поднимите Python backend:

```bash
make dev
```

Затем в отдельном терминале запустите новый chat shell:

```bash
make chat-web-install
make chat-web-dev
```

Для локальной разработки фронтенд по умолчанию ожидает backend по адресу
`http://127.0.0.1:8000`.

Если нужен другой адрес, задайте его через `NEXT_PUBLIC_BACKEND_URL`:

```bash
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:9000 make chat-web-dev
```

## Полезные команды

```bash
make chat-web-test
make chat-web-build
```

`make chat-web-build` делает production static export. В production runtime
Node не нужен: экспортированные assets затем отдаёт Python/FastAPI-приложение.

## Текущий scope

- `study_planner` и `transportation` уже проходят через semantics-driven flow;
- `default_or` остаётся на legacy runtime path, но доступен через тот же backend transport;
- in-chat редактирование DSL-файлов пока не входит в scope этого приложения.

## Что считается каноническим контрактом

- primary frontend/backend surfaces:
  - `/api/chat/threads*`
  - `/api/copilotkit`
- typed shared contract:
  - `ExtensionInteractionState`
  - `SlashCommandSpec`
- bare-команды старого shell (`start`, `json`, `run` без `/`) остаются backend-compatible,
  но в новом чате считаются legacy/power-user слоем, а не основным UX.
