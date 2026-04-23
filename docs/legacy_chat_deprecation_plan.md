# План вывода legacy chat/bare-команд

## 1. Цель

После cutover основной пользовательский UX работает через `/app` и thread API.
Этот документ фиксирует, как убрать legacy-слой (`/legacy` + bare-команды без `/`)
без регрессий для продукта и тестовой инфраструктуры.

## 2. Текущая граница совместимости

- Primary path:
  - `/app`
  - `/api/chat/threads*`
  - `/api/copilotkit`
  - bare-команды (`start/json/set/run` без `/`) **не исполняются**.
- Legacy-only path:
  - `/legacy`
  - `/chat/turn`
  - `/api/chat/turn`
  - bare-команды остаются совместимыми в deprecation window.

## 3. Этапы удаления

1. Deprecation window (текущий этап):
   - поддерживать legacy path только для внутренних fallback-сценариев и старых тестов;
   - не продвигать bare-синтаксис в документации `/app`.
2. Test migration:
   - перенести продуктовые e2e/integration проверки на `/app` + thread API;
   - оставить только узкий legacy compatibility pack.
3. Hard retirement:
   - удалить `/legacy` UI, bare-command adapter и legacy endpoints;
   - обновить `AgentService` и docs, чтобы остался один primary transport.

## 4. Критерии готовности к hard retirement

- 100% продуктовых acceptance-сценариев проходят через `/app` без legacy fallback.
- В CI нет блокирующих тестов, завязанных на `/legacy` как основной путь.
- Команда согласовала, что внешние пользователи не зависят от `/chat/turn` и `/api/chat/turn`.
- Обновлены onboarding/dev docs и runbooks.

## 5. Политика тестов до удаления

- `/app` тестируется как primary UX (guided + slash + semantics/NL).
- Legacy покрывается только совместимостью:
  - smoke на доступность `/legacy`;
  - ограниченный набор regression-тестов bare-команд.
- Новые продуктовые сценарии в legacy path не добавляются.

## 6. Риски и контроль

- Риск: скрытая зависимость внутренних скриптов от `/api/chat/turn`.
  - Контроль: инвентаризация вызовов перед hard retirement.
- Риск: внезапный разрыв учебных инструкций.
  - Контроль: все student-facing guides должны указывать `/app` и slash как канон.
