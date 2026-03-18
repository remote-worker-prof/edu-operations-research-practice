# ADR 0002: Grammar, Compatibility, And Session-Scoped Extension Policy

## Status

Accepted

## Context

Текущий чат работает на фиксированном DSL вокруг четырёх stage:

- `production`
- `shipment`
- `assignment`
- `routing`

Для платформы расширений этого недостаточно:

- grammar должна поддерживать произвольные extension stage IDs и field paths;
- новый DSL не должен ломать существующий учебный синтаксис;
- выбор extension должен быть понятным в UI/API и не разрушать уже набранный draft.

## Decision

Мы принимаем следующие архитектурные решения:

1. Formal grammar engine:

- общий DSL строится поверх `Lark`;
- grammar становится schema-driven и получает stage/field metadata из extension manifest.

2. Backward compatibility:

- существующие команды `start`, `show input`, `next`, `run`, `reset`,
  `load preset demo`, `edit <stage>`, `json <stage> {...}`, `set <stage>.<field> <value>`
  должны остаться полностью совместимыми для default extension;
- старый DSL трактуется как частный случай нового grammar stack.

3. NL policy:

- extension-aware NL остаётся в проекте;
- stage/field aliases и примеры должны приходить из manifest/runtime metadata, а не быть жёстко вшитыми в parser.

4. Extension selection policy:

- extension выбирается `per session` через UI/API;
- в непустой сессии переключение extension запрещено, если пользователь не сделал `reset`;
- выбор extension не становится новой чат-командой в v1.

## Consequences

Плюсы:

- платформа сможет поддерживать произвольные extension-задачи без жёсткой stage-centric прошивки;
- текущая учебная документация и видео по default flow останутся валидными;
- session state останется методически понятным: одна сессия соответствует одному extension-контексту.

Минусы:

- compatibility-layer заметно усложнит parser и runtime-модели;
- generic grammar придётся вводить постепенно, не ломая текущий deterministic flow;
- часть старых контрактов придётся временно держать как deprecated mirrors ради безболезненной миграции.
