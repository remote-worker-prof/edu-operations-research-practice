# Сценарий `nl_confirm_flow`: natural-language ввод с обязательным подтверждением

## Что это за видео и чему оно учит

- Видео: [nl_confirm_flow.mp4](../assets/selenium_videos/nl_confirm_flow.mp4)
- Длительность: около 2 мин 12 с
- Главная цель: показать, что natural-language ввод в этом чате свободнее DSL-команд, но не применяется автоматически.

Этот сценарий объясняет:

1. как сначала собрать полностью валидный draft;
2. как поверх него отправить NL-реплику с изменениями;
3. почему появляется `pending-patches-card`;
4. почему `да` является обязательной частью workflow.

## Краткая постановка задачи

Есть два продукта `Nova` и `Orbit`, два склада `East` и `West`,
три клиента `Clinic_1`, `Clinic_2`, `Clinic_3` и три ресурса
`van_1`, `van_2`, `van_3`.

Сначала все 4 stage вводятся строгими JSON-командами.
Потом отправляется natural-language реплика:

```text
production profits [49,37], pallet_factors [1.0,0.95]
```

После неё система не запускает расчёт, а показывает candidate patches и ждёт `да`.

## Исходные данные по stage

### Базовые stage-данные до NL-изменения

#### `production`

| Поле | Значение |
| --- | --- |
| `products` | `["Nova", "Orbit"]` |
| `profits` | `[46, 35]` |
| `resource_matrix` | `[[2, 1], [1, 1.5]]` |
| `resource_limits` | `[240, 180]` |
| `demand_upper_bounds` | `[70, 80]` |
| `pallet_factors` | `[1.0, 0.95]` |

#### `shipment`

| Поле | Значение |
| --- | --- |
| `warehouses` | `["East", "West"]` |
| `warehouse_supply_ratio` | `[0.55, 0.45]` |
| `clients` | `["Clinic_1", "Clinic_2", "Clinic_3"]` |
| `client_demand` | `[42, 38, 40]` |
| `cost_matrix` | `[[5, 6, 7], [4, 5, 4]]` |
| `capacity_matrix` | `[[50, 45, 40], [40, 45, 50]]` |

#### `assignment`

| Поле | Значение |
| --- | --- |
| `resources` | `["van_1", "van_2", "van_3"]` |
| `cost_matrix` | `[[6, 5, 7], [5, 7, 4], [7, 4, 6]]` |

#### `routing`

| Поле | Значение |
| --- | --- |
| `distance_matrix` | `[[0, 11, 12, 9], [11, 0, 7, 6], [12, 7, 0, 8], [9, 6, 8, 0]]` |
| `depot_index` | `0` |
| `client_nodes` | `[1, 2, 3]` |
| `vehicle_capacities` | `[55, 45, 45]` |

### Что меняется в ходе видео

К моменту `run` stage `production` становится таким:

| Поле | Итоговое значение |
| --- | --- |
| `profits` | `[49, 37]` |
| `pallet_factors` | `[1.0, 0.95]` |
| остальные поля | без изменений |

Важно: пока пользователь не отправил `да`, эти изменения ещё не живут в draft.

## Математика по 4 этапам

## 1. Production: LP

### Множества и индексы

- `I = {Nova, Orbit}`
- `R = {1, 2}`

### Переменные

- `x_Nova`
- `x_Orbit`

### Целевая функция

После подтверждения patch-а задача становится такой:

```text
max 49 * x_Nova + 37 * x_Orbit
```

### Ограничения

```text
2 * x_Nova + 1 * x_Orbit <= 240
1 * x_Nova + 1.5 * x_Orbit <= 180
x_Nova <= 70
x_Orbit <= 80
x_Nova, x_Orbit >= 0
```

### Что уходит дальше

```text
total_pallets = round(1.0 * x_Nova + 0.95 * x_Orbit)
```

## 2. Shipment: min-cost flow

### Множества и индексы

- склады: `East`, `West`
- клиенты: `Clinic_1`, `Clinic_2`, `Clinic_3`

### Переменные

- `y_east_1`, `y_east_2`, `y_east_3`
- `y_west_1`, `y_west_2`, `y_west_3`

### Целевая функция

```text
min 5*y_East_1 + 6*y_East_2 + 7*y_East_3
  + 4*y_West_1 + 5*y_West_2 + 4*y_West_3
```

### Ограничения

- `available = min(total_pallets, 120) = 120`
- supply split по складам: `[66, 54]`
- клиентские спросы: `42`, `38`, `40`
- пропускные ограничения задаёт `capacity_matrix`

### Что уходит дальше

- `client_delivery = {"Clinic_1": 42, "Clinic_2": 38, "Clinic_3": 40}`
- `tasks = [("task-1", Clinic_1, 42), ("task-2", Clinic_2, 38), ("task-3", Clinic_3, 40)]`

## 3. Assignment: линейное назначение

### Множества и индексы

- ресурсы: `van_1`, `van_2`, `van_3`
- задачи: `task-1`, `task-2`, `task-3`

### Переменные

- `z_r_t in {0,1}`

### Целевая функция

```text
min 6*z_11 + 5*z_12 + 7*z_13
  + 5*z_21 + 7*z_22 + 4*z_23
  + 7*z_31 + 4*z_32 + 6*z_33
```

### Ограничения

- каждая задача покрывается ровно одним ресурсом;
- один ресурс не назначается на две задачи.

### Что уходит дальше

- assignment pairs;
- `allowed_vehicle_ids_by_client = {1: [0], 2: [2], 3: [1]}`

## 4. Routing: CVRP

### Множества и индексы

- узлы: `0, 1, 2, 3`
- depot: `0`
- клиентские узлы: `1, 2, 3`
- машины: `van_1`, `van_2`, `van_3`

### Переменные

На выходе читаются маршруты:

- узлы маршрута;
- длина;
- нагрузка.

### Целевая функция

```text
min total_distance
```

### Ограничения

- каждый клиент посещается;
- каждая машина соблюдает свою вместимость;
- assignment задаёт допустимые машины для клиентов.

## Конкретная арифметика и sanity-check

### Production

Оптимальные количества:

```text
x_Nova = 70
x_Orbit = 73.33333333333333
```

Проверка прибыли:

```text
49 * 70 + 37 * 73.33333333333333
= 3430 + 2713.333333333333
= 6143.333333333333
```

Проверка паллет:

```text
70 * 1.0 + 73.33333333333333 * 0.95
= 70 + 69.66666666666666
= 139.66666666666666
round(...) = 140
```

### Shipment

Оптимальный план:

- `East -> Clinic_1 = 28` по цене `5`
- `East -> Clinic_2 = 38` по цене `6`
- `West -> Clinic_1 = 14` по цене `4`
- `West -> Clinic_3 = 40` по цене `4`

Проверка стоимости:

```text
28*5 + 38*6 + 14*4 + 40*4
= 140 + 228 + 56 + 160
= 584
```

### Assignment

Оптимальные пары:

- `van_1 -> Clinic_1` со стоимостью `6`
- `van_2 -> Clinic_3` со стоимостью `4`
- `van_3 -> Clinic_2` со стоимостью `4`

Проверка:

```text
6 + 4 + 4 = 14
```

### Routing

Маршруты:

- `van_1: [0, 1, 0]`, расстояние `11 + 11 = 22`
- `van_2: [0, 3, 0]`, расстояние `9 + 9 = 18`
- `van_3: [0, 2, 0]`, расстояние `12 + 12 = 24`

Проверка:

```text
22 + 18 + 24 = 64
max(22, 18, 24) = 24
```

## Что вводить в диалоге с агентом

В видео сообщения идут в таком порядке:

```text
start
json production {"products": ["Nova", "Orbit"], "profits": [46, 35], "resource_matrix": [[2, 1], [1, 1.5]], "resource_limits": [240, 180], "demand_upper_bounds": [70, 80], "pallet_factors": [1.0, 0.95]}
json shipment {"warehouses": ["East", "West"], "warehouse_supply_ratio": [0.55, 0.45], "clients": ["Clinic_1", "Clinic_2", "Clinic_3"], "client_demand": [42, 38, 40], "cost_matrix": [[5, 6, 7], [4, 5, 4]], "capacity_matrix": [[50, 45, 40], [40, 45, 50]]}
json assignment {"resources": ["van_1", "van_2", "van_3"], "cost_matrix": [[6, 5, 7], [5, 7, 4], [7, 4, 6]]}
json routing {"distance_matrix": [[0, 11, 12, 9], [11, 0, 7, 6], [12, 7, 0, 8], [9, 6, 8, 0]], "depot_index": 0, "client_nodes": [1, 2, 3], "vehicle_capacities": [55, 45, 45]}
production profits [49,37], pallet_factors [1.0,0.95]
да
run
```

## На что обращать внимание в UI

1. До NL-реплики:
   - `ready-to-run-value = Да`
   - все четыре stage уже готовы
2. После natural-language сообщения:
   - появляется `pending-patches-card`
   - в `pending-patch-row` видно как минимум `production.profits`
   - новый OR-результат ещё не считается
3. После `да`:
   - `pending-patches-card` исчезает
   - assistant-message подтверждает, что параметры применены
   - draft снова готов к запуску
4. После `run`:
   - появляются result cards и execution trace

## Ожидаемые детерминированные результаты

- `production.objective = 6143.333333333333`
- `production.quantities = {"Nova": 70.0, "Orbit": 73.33333333333333}`
- `total_pallets = 140`
- `shipment.total_cost = 584.0`
- `shipment.total_dispatched = 120`
- `shipment.unmet_demand = {"Clinic_1": 0, "Clinic_2": 0, "Clinic_3": 0}`
- `assignment.total_cost = 14.0`
- assignment pairs:
  - `van_1 -> Clinic_1`
  - `van_2 -> Clinic_3`
  - `van_3 -> Clinic_2`
- `routing.total_distance = 64`
- `routing.max_route_distance = 24`

## Типичные ошибки и зачем сценарий важен

Типичные ошибки:

- считать, что `pending patches` уже записаны в draft;
- отправлять `run` до `да` и удивляться блокировке;
- думать, что NL-режим полностью свободный и не требует stage/field-структуры.

Почему этот сценарий важен:

- он показывает главный safety-инвариант системы: LLM предлагает patch, а не меняет данные сам;
- помогает студенту увидеть границу между “чат понял” и “данные реально применены”;
- даёт хороший шаблон для быстрых экспериментов без отказа от контроля.

