# Сценарий `validation_recovery_flow`: как выглядят partial JSON, malformed JSON и исправление ввода

## Что это за видео и чему оно учит

- Видео: [validation_recovery_flow.mp4](../assets/selenium_videos/validation_recovery_flow.mp4)
- Длительность: около 2 мин 08 с
- Главная цель: показать, что чат не просто “ест всё подряд”, а валидирует ввод и не даёт незаметно испортить pipeline.

Этот сценарий отвечает на три частых студентческих вопроса:

1. что будет, если отправить неполный `json <stage> {...}`;  
2. что будет, если JSON вообще синтаксически сломан;  
3. как восстановиться после ошибки и всё равно дойти до успешного `run`.

## Краткая постановка задачи

Есть два продукта `Delta` и `Echo`, склады `Hub_A`, `Hub_B`,
клиенты `School_1`, `School_2`, `School_3` и ресурсы
`carrier_1`, `carrier_2`, `carrier_3`.

Видео специально построено как recovery-сценарий:

1. сначала вводится неполный `production`;
2. потом вводится malformed JSON;
3. потом пользователь последовательно вводит правильные stage-данные;
4. только после этого выполняется нормальный `run`.

## Исходные данные по stage

### Первый, заведомо неполный ввод

```json
{"products": ["Delta", "Echo"]}
```

Этого недостаточно, потому что для `production` ещё обязательны:

- `profits`
- `resource_matrix`
- `resource_limits`
- `demand_upper_bounds`
- `pallet_factors`

### Второй, заведомо ошибочный ввод

```text
json production {"products":["Delta","Echo"]
```

Это уже синтаксическая ошибка JSON.

### Корректные данные, которые в итоге участвуют в `run`

#### `production`

| Поле | Значение |
| --- | --- |
| `products` | `["Delta", "Echo"]` |
| `profits` | `[50, 33]` |
| `resource_matrix` | `[[2, 1], [1, 1.5]]` |
| `resource_limits` | `[240, 180]` |
| `demand_upper_bounds` | `[70, 80]` |
| `pallet_factors` | `[1.1, 0.85]` |

#### `shipment`

| Поле | Значение |
| --- | --- |
| `warehouses` | `["Hub_A", "Hub_B"]` |
| `warehouse_supply_ratio` | `[0.55, 0.45]` |
| `clients` | `["School_1", "School_2", "School_3"]` |
| `client_demand` | `[42, 38, 40]` |
| `cost_matrix` | `[[4, 7, 6], [5, 4, 5]]` |
| `capacity_matrix` | `[[50, 45, 40], [40, 45, 50]]` |

#### `assignment`

| Поле | Значение |
| --- | --- |
| `resources` | `["carrier_1", "carrier_2", "carrier_3"]` |
| `cost_matrix` | `[[7, 5, 6], [6, 7, 4], [5, 6, 8]]` |

#### `routing`

| Поле | Значение |
| --- | --- |
| `distance_matrix` | `[[0, 8, 11, 10], [8, 0, 7, 6], [11, 7, 0, 9], [10, 6, 9, 0]]` |
| `depot_index` | `0` |
| `client_nodes` | `[1, 2, 3]` |
| `vehicle_capacities` | `[55, 45, 45]` |

## Математика по 4 этапам

## 1. Production: LP

### Множества и индексы

- `I = {Delta, Echo}`
- `R = {1, 2}`

### Переменные

- `x_Delta`
- `x_Echo`

### Целевая функция

```text
max 50 * x_Delta + 33 * x_Echo
```

### Ограничения

```text
2 * x_Delta + 1 * x_Echo <= 240
1 * x_Delta + 1.5 * x_Echo <= 180
x_Delta <= 70
x_Echo <= 80
x_Delta, x_Echo >= 0
```

### Что уходит дальше

```text
total_pallets = round(1.1 * x_Delta + 0.85 * x_Echo)
```

## 2. Shipment: min-cost flow

### Множества и индексы

- склады: `Hub_A`, `Hub_B`
- клиенты: `School_1`, `School_2`, `School_3`

### Переменные

- `y_huba_1`, `y_huba_2`, `y_huba_3`
- `y_hubb_1`, `y_hubb_2`, `y_hubb_3`

### Целевая функция

```text
min 4*y_A_1 + 7*y_A_2 + 6*y_A_3
  + 5*y_B_1 + 4*y_B_2 + 5*y_B_3
```

### Ограничения

- `available = min(total_pallets, 120) = 120`
- supplies по складам: `[66, 54]`
- спросы клиентов: `42`, `38`, `40`
- рёбра ограничены `capacity_matrix`

### Что уходит дальше

- `client_delivery = {"School_1": 42, "School_2": 38, "School_3": 40}`
- `tasks = [("task-1", School_1, 42), ("task-2", School_2, 38), ("task-3", School_3, 40)]`

## 3. Assignment: линейное назначение

### Множества и индексы

- ресурсы: `carrier_1`, `carrier_2`, `carrier_3`
- задачи: `task-1`, `task-2`, `task-3`

### Переменные

- `z_r_t in {0,1}`

### Целевая функция

```text
min 7*z_11 + 5*z_12 + 6*z_13
  + 6*z_21 + 7*z_22 + 4*z_23
  + 5*z_31 + 6*z_32 + 8*z_33
```

### Ограничения

- каждая задача должна быть назначена;
- каждый ресурс используется не более одного раза.

### Что уходит дальше

- assignment pairs;
- `allowed_vehicle_ids_by_client = {1: [2], 2: [0], 3: [1]}`

## 4. Routing: CVRP

### Множества и индексы

- узлы: `0, 1, 2, 3`
- depot: `0`
- клиентские узлы: `1, 2, 3`
- машины: `carrier_1`, `carrier_2`, `carrier_3`

### Переменные

На выходе получаем маршруты с:

- последовательностью узлов;
- длиной;
- загрузкой.

### Целевая функция

```text
min total_distance
```

### Ограничения

- каждый клиент должен быть обслужен;
- вместимость транспорта не нарушается;
- routing уважает assignment-ограничения по допустимым машинам.

## Конкретная арифметика и sanity-check

### Production

Оптимальные количества:

```text
x_Delta = 70
x_Echo = 73.33333333333333
```

Проверка прибыли:

```text
50 * 70 + 33 * 73.33333333333333
= 3500 + 2420
= 5920
```

Проверка паллет:

```text
70 * 1.1 + 73.33333333333333 * 0.85
= 77 + 62.33333333333333
= 139.33333333333331
round(...) = 139
```

### Shipment

Оптимальные legs:

- `Hub_A -> School_1 = 42` по цене `4`
- `Hub_A -> School_3 = 24` по цене `6`
- `Hub_B -> School_2 = 38` по цене `4`
- `Hub_B -> School_3 = 16` по цене `5`

Проверка стоимости:

```text
42*4 + 24*6 + 38*4 + 16*5
= 168 + 144 + 152 + 80
= 544
```

### Assignment

Оптимальные пары:

- `carrier_1 -> School_2` со стоимостью `5`
- `carrier_2 -> School_3` со стоимостью `4`
- `carrier_3 -> School_1` со стоимостью `5`

Проверка:

```text
5 + 4 + 5 = 14
```

### Routing

Маршруты:

- `carrier_1: [0, 2, 0]`, расстояние `11 + 11 = 22`
- `carrier_2: [0, 3, 0]`, расстояние `10 + 10 = 20`
- `carrier_3: [0, 1, 0]`, расстояние `8 + 8 = 16`

Проверка:

```text
22 + 20 + 16 = 58
max(22, 20, 16) = 22
```

## Что вводить в диалоге с агентом

В видео сообщения идут именно так:

```text
start
json production {"products": ["Delta", "Echo"]}
json production {"products":["Delta","Echo"]
json production {"products": ["Delta", "Echo"], "profits": [50, 33], "resource_matrix": [[2, 1], [1, 1.5]], "resource_limits": [240, 180], "demand_upper_bounds": [70, 80], "pallet_factors": [1.1, 0.85]}
json shipment {"warehouses": ["Hub_A", "Hub_B"], "warehouse_supply_ratio": [0.55, 0.45], "clients": ["School_1", "School_2", "School_3"], "client_demand": [42, 38, 40], "cost_matrix": [[4, 7, 6], [5, 4, 5]], "capacity_matrix": [[50, 45, 40], [40, 45, 50]]}
json assignment {"resources": ["carrier_1", "carrier_2", "carrier_3"], "cost_matrix": [[7, 5, 6], [6, 7, 4], [5, 6, 8]]}
json routing {"distance_matrix": [[0, 8, 11, 10], [8, 0, 7, 6], [11, 7, 0, 9], [10, 6, 9, 0]], "depot_index": 0, "client_nodes": [1, 2, 3], "vehicle_capacities": [55, 45, 45]}
run
```

## На что обращать внимание в UI

1. После первого partial JSON:
   - stage `production` остаётся в статусе `не готов`
   - появляется `validation-errors-card`
   - `ready-to-run-value = Нет`
2. После malformed JSON:
   - assistant-message содержит `Ошибка ввода: Некорректный JSON:`
   - ложного перехода в `ready_to_run` не происходит
3. После полного корректного набора stage:
   - все четыре stage становятся `готов`
   - появляется `pre-run-summary-card`
4. После `run`:
   - pipeline собирается end-to-end и показывает результат

## Ожидаемые детерминированные результаты

- `production.objective = 5920.0`
- `production.quantities = {"Delta": 70.0, "Echo": 73.33333333333333}`
- `total_pallets = 139`
- `shipment.total_dispatched = 120`
- `shipment.total_cost = 544.0`
- `shipment.unmet_demand = {"School_1": 0, "School_2": 0, "School_3": 0}`
- `assignment.total_cost = 14.0`
- assignment pairs:
  - `carrier_1 -> School_2`
  - `carrier_2 -> School_3`
  - `carrier_3 -> School_1`
- `routing.total_distance = 58`
- `routing.max_route_distance = 22`

## Типичные ошибки и зачем сценарий важен

Типичные ошибки:

- ожидать, что partial JSON “допишется потом сам”, хотя stage после такого ввода считается неполным;
- путать синтаксическую ошибку JSON с доменной валидацией полей;
- не замечать, что старый `or_result` после изменений становится неактуальным.

Почему этот сценарий важен:

- он учит не бояться ошибок и понимать, что именно система считает ошибкой;
- он показывает, что validation и parsing ошибки видимы в UI и не маскируются;
- это лучший учебный кейс для объяснения разницы между “неполные данные” и “битый JSON”.

