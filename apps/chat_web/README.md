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
- open-ended NL поверх typed semantics с guarded confirm/auto-apply policy;
- автоматические формы и result-view, которые строятся из typed semantics
  extension bundle, а не пишутся вручную под каждый extension;
- grounded explain-mode для `/explain model|extension|result|step`;
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
`http://127.0.0.1:8000`, а production static export использует same-origin
relative API-paths.

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
- `default_or` уже подключён к тому же semantics-first conversation stack, что и
  declarative extensions, хотя его OR backend остаётся legacy-compatible;
- режимы `guided` и `power` используют один и тот же backend conversation core;
- read-only DSL awareness уже есть: можно объяснять `model.orx`, `extension.yaml`
  и текущие semantics без in-chat редактирования файлов;
- in-chat редактирование DSL-файлов пока не входит в scope этого приложения.

## Что считается каноническим контрактом

- primary frontend/backend surfaces:
  - `/api/chat/threads*`
  - `/api/copilotkit`
- typed shared contract:
  - `ExtensionInteractionState`
  - `SlashCommandSpec`
  - `SemanticIntent`
  - `PatchProposal`
  - `IntentResolution`
- canonical slash contract:
  - `/use`
  - `/show`
  - `/solve`
  - `/validate`
  - `/reset`
  - `/explain model|extension|result|step`
  - `/mode guided|power`
- bare-команды старого shell (`start`, `json`, `run` без `/`) остаются
  backend-compatible только за legacy boundary и больше не считаются основным UX.
