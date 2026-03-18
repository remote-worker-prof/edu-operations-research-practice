# ADR 0001: Extension Package And Discovery Contract

## Status

Accepted

## Context

Проект переходит от одного встроенного учебного OR-конвейера к платформе расширений.  
Нужно сделать так, чтобы студент мог написать отдельный Python-пакет со своими задачами
и подключить его к приложению без правки core-кода.

При этом важно сохранить несколько ограничений:

- extension считается доверенным локальным Python-кодом;
- extension обнаруживается при старте приложения, а не hot-reload'ится посреди runtime;
- `agent_core` и `webapp` должны зависеть только от стабильного SDK, а не от конкретных student-package реализаций;
- существующий default-flow должен пережить переход без регрессии.

## Decision

Мы вводим отдельный публичный пакет `extension_api` как единственную стабильную SDK-границу
для student-authored extension'ов.

Extension-пакет должен публиковаться через entry point group:

```text
edu_or_agent.extensions
```

Entry point может указывать на:

- provider instance;
- provider class без аргументов конструктора;
- zero-argument factory, возвращающую provider.

Provider обязан реализовать контракт:

- `get_manifest() -> ExtensionManifest`
- `create_runtime() -> ExtensionRuntime`

Startup-discovery выполняется один раз при инициализации процесса через
`importlib.metadata.entry_points(group="edu_or_agent.extensions")`.

В первой версии:

- sandboxing не внедряется;
- restart приложения требуется для появления нового extension-пакета;
- invalid extension считается ошибкой конфигурации окружения и должен ломать startup early.

## Consequences

Плюсы:

- студент пишет обычный installable Python package;
- расширения обнаруживаются без жёсткого списка в коде приложения;
- `extension_api` становится стабильной anti-corruption boundary между платформой и extension'ами.

Минусы:

- startup теперь зависит от корректности всех установленных extension entry points;
- discovery не поддерживает горячее подключение пакетов без рестарта;
- придётся отдельно поддерживать compatibility-layer для текущего встроенного OR-flow.
