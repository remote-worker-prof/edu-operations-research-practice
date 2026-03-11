# Epic: Interactive OR Input Collection

## Цель

Перевести агент на режим, в котором все независимые входы OR-подграфа
(`Production`, `Shipment`, `Assignment`, `Routing`) собираются в чате
до запуска оптимизации.

## Управление

- Umbrella epic (beads): `eorp-850`
- Child issues:
  - `eorp-850.1` — E1 Domain models dynamic dimensions
  - `eorp-850.2` — E2 Scenario draft + assembler
  - `eorp-850.3` — E3 Chat collector/wizard
  - `eorp-850.4` — E4 Deterministic parser stack
  - `eorp-850.5` — E5 Web UX updates
  - `eorp-850.6` — E6 Tests/docs cleanup

## Контракт реализации

1. OR не запускается, пока draft не полон и не валиден.
2. Запуск выполняется только по явной команде `run`.
3. `base_scenario.json` — только опциональный preset (`load preset demo`).
4. Изменение любого входа инвалидирует предыдущий `or_result`.

## Команды чата (v1)

- `start`
- `show input`
- `next`
- `set <stage>.<field> <value>`
- `json <stage> { ... }`
- `edit <stage>`
- `reset`
- `load preset demo`
- `run`

## Acceptance

- `make check-all` проходит.
- Интеграционные тесты подтверждают:
  - сбор входов до run;
  - обязательный explicit run;
  - сохранение API-контракта endpoints.
