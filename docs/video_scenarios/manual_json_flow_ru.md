# Сценарий `manual_json_flow`: полный безопасный DSL-workflow без natural-language

## Что это за видео и чему оно учит

- Видео: [manual_json_flow.mp4](../assets/selenium_videos/manual_json_flow.mp4)
- Длительность: около 2 мин 21 с
- Главная цель: показать самый строгий и предсказуемый способ пройти всю цепочку через чат.

Этот сценарий полезен, когда студенту нужно:

- ввести все данные руками без NL-догадок;
- понять разницу между полным stage-вводом и точечной правкой;
- увидеть, как `show input` отражает уже изменённые значения.

## Краткая постановка задачи

Есть два продукта `Atlas` и `Beacon`, два склада `North` и `South`,
три клиента `Retail_A`, `Retail_B`, `Retail_C` и три ресурса
`truck_red`, `truck_blue`, `truck_green`.

Сначала все четыре stage вводятся через `json <stage> {...}`.
Потом отдельной командой меняется только одно поле:

```text
set production.profits [53,39]
```

Именно эта обновлённая прибыль участвует в финальном `run`.

## Исходные данные по stage

### Что вводится сначала

#### `production`

| Поле | Значение |
| --- | --- |
| `products` | `["Atlas", "Beacon"]` |
| `profits` | `[52, 37]` |
| `resource_matrix` | `[[2, 1], [1, 1.5]]` |
| `resource_limits` | `[240, 180]` |
| `demand_upper_bounds` | `[70, 80]` |
| `pallet_factors` | `[1.05, 0.9]` |

#### `shipment`

| Поле | Значение |
| --- | --- |
| `warehouses` | `["North", "South"]` |
| `warehouse_supply_ratio` | `[0.55, 0.45]` |
| `clients` | `["Retail_A", "Retail_B", "Retail_C"]` |
| `client_demand` | `[42, 38, 40]` |
| `cost_matrix` | `[[3, 6, 7], [6, 4, 5]]` |
| `capacity_matrix` | `[[50, 45, 40], [40, 45, 50]]` |

#### `assignment`

| Поле | Значение |
| --- | --- |
| `resources` | `["truck_red", "truck_blue", "truck_green"]` |
| `cost_matrix` | `[[7, 4, 6], [5, 7, 4], [6, 5, 8]]` |

#### `routing`

| Поле | Значение |
| --- | --- |
| `distance_matrix` | `[[0, 9, 13, 7], [9, 0, 5, 8], [13, 5, 0, 10], [7, 8, 10, 0]]` |
| `depot_index` | `0` |
| `client_nodes` | `[1, 2, 3]` |
| `vehicle_capacities` | `[55, 45, 45]` |

### Что реально участвует в `run`

После команды `set production.profits [53,39]` итоговые данные stage `production`
в этом видео становятся такими:

| Поле | Значение к моменту `run` |
| --- | --- |
| `profits` | `[53, 39]` |
| остальные поля | без изменений |

Это важная часть сценария: `set` не заменяет весь stage, а переписывает только
один путь `production.profits`.

## Математика по 4 этапам

## 1. Production: LP

### Множества и индексы

- `I = {Atlas, Beacon}`
- `R = {1, 2}`

### Переменные

- `x_Atlas`
- `x_Beacon`

### Целевая функция

К моменту `run` максимизируется уже обновлённая прибыль:

```text
max 53 * x_Atlas + 39 * x_Beacon
```

### Ограничения

```text
2 * x_Atlas + 1 * x_Beacon <= 240
1 * x_Atlas + 1.5 * x_Beacon <= 180
x_Atlas <= 70
x_Beacon <= 80
x_Atlas, x_Beacon >= 0
```

### Что уходит дальше

```text
total_pallets = round(1.05 * x_Atlas + 0.9 * x_Beacon)
```

## 2. Shipment: min-cost flow

### Множества и индексы

- склады: `North`, `South`
- клиенты: `Retail_A`, `Retail_B`, `Retail_C`

### Переменные

- `y_north_a`, `y_north_b`, `y_north_c`
- `y_south_a`, `y_south_b`, `y_south_c`

### Целевая функция

```text
min 3*y_North_A + 6*y_North_B + 7*y_North_C
  + 6*y_South_A + 4*y_South_B + 5*y_South_C
```

### Ограничения

- доступно к отгрузке: `min(total_pallets, 120)`
- supply split по складам: `[66, 54]`
- клиентские спросы: `42`, `38`, `40`
- ограничения на рёбрах из `capacity_matrix`

### Что уходит дальше

- `client_delivery`
- `tasks = [("task-1", Retail_A, 42), ("task-2", Retail_B, 38), ("task-3", Retail_C, 40)]`

## 3. Assignment: линейное назначение

### Множества и индексы

- ресурсы: `truck_red`, `truck_blue`, `truck_green`
- задачи: `task-1`, `task-2`, `task-3`

### Переменные

- `z_r_t in {0,1}`

### Целевая функция

```text
min 7*z_11 + 4*z_12 + 6*z_13
  + 5*z_21 + 7*z_22 + 4*z_23
  + 6*z_31 + 5*z_32 + 8*z_33
```

### Ограничения

- каждая задача получает ровно один ресурс;
- один ресурс не может покрыть две задачи сразу.

### Что уходит дальше

- assignment pairs;
- `allowed_vehicle_ids_by_client = {1: [2], 2: [0], 3: [1]}`

## 4. Routing: CVRP

### Множества и индексы

- узлы: `0, 1, 2, 3`
- depot: `0`
- клиентские узлы: `1, 2, 3`
- машины: `truck_red`, `truck_blue`, `truck_green`

### Переменные

На выходе читаются маршруты вида:

- список узлов;
- расстояние;
- загрузка.

### Целевая функция

```text
min total_distance
```

### Ограничения

- каждую клиентскую точку с ненулевым спросом нужно обслужить;
- маршрут не может нарушать вместимость машины;
- клиент обслуживается только разрешённой машиной из assignment.

## Конкретная арифметика и sanity-check

### Production

Оптимальные объёмы выпуска здесь такие же по структуре, как и в базовом preset:

```text
x_Atlas = 70
x_Beacon = 73.33333333333333
```

Проверка целевой функции:

```text
53 * 70 + 39 * 73.33333333333333
= 3710 + 2860
= 6570
```

Проверка паллет:

```text
70 * 1.05 + 73.33333333333333 * 0.9
= 73.5 + 66
= 139.5
round(...) = 140
```

### Shipment

Оптимальные legs:

- `North -> Retail_A = 42` по цене `3`
- `North -> Retail_C = 24` по цене `7`
- `South -> Retail_B = 38` по цене `4`
- `South -> Retail_C = 16` по цене `5`

Проверка стоимости:

```text
42*3 + 24*7 + 38*4 + 16*5
= 126 + 168 + 152 + 80
= 526
```

### Assignment

Оптимальные пары:

- `truck_red -> Retail_B` со стоимостью `4`
- `truck_blue -> Retail_C` со стоимостью `4`
- `truck_green -> Retail_A` со стоимостью `6`

Проверка:

```text
4 + 4 + 6 = 14
```

### Routing

Маршруты:

- `truck_red: [0, 2, 0]`, расстояние `13 + 13 = 26`
- `truck_blue: [0, 3, 0]`, расстояние `7 + 7 = 14`
- `truck_green: [0, 1, 0]`, расстояние `9 + 9 = 18`

Проверка:

```text
26 + 14 + 18 = 58
max(26, 14, 18) = 26
```

## Что вводить в диалоге с агентом

В видео сообщения идут именно в таком порядке:

```text
start
json production {"products": ["Atlas", "Beacon"], "profits": [52, 37], "resource_matrix": [[2, 1], [1, 1.5]], "resource_limits": [240, 180], "demand_upper_bounds": [70, 80], "pallet_factors": [1.05, 0.9]}
json shipment {"warehouses": ["North", "South"], "warehouse_supply_ratio": [0.55, 0.45], "clients": ["Retail_A", "Retail_B", "Retail_C"], "client_demand": [42, 38, 40], "cost_matrix": [[3, 6, 7], [6, 4, 5]], "capacity_matrix": [[50, 45, 40], [40, 45, 50]]}
json assignment {"resources": ["truck_red", "truck_blue", "truck_green"], "cost_matrix": [[7, 4, 6], [5, 7, 4], [6, 5, 8]]}
json routing {"distance_matrix": [[0, 9, 13, 7], [9, 0, 5, 8], [13, 5, 0, 10], [7, 8, 10, 0]], "depot_index": 0, "client_nodes": [1, 2, 3], "vehicle_capacities": [55, 45, 45]}
set production.profits [53,39]
show input
run
```

## На что обращать внимание в UI

1. После `start`:
   - `current-stage-value = production`
   - начинается режим drafting
2. После каждого `json <stage> ...`:
   - соответствующий stage получает статус `готов`
   - список `missing_fields` уменьшается
3. После `set production.profits [53,39]`:
   - assistant-message подтверждает обновление именно `production.profits`
   - `ready-to-run-value` остаётся `Да`
4. После `show input`:
   - в draft уже видны обновлённые прибыли `[53, 39]`, а не исходные `[52, 37]`
5. После `run`:
   - появляются четыре result cards и execution trace

## Ожидаемые детерминированные результаты

- `production.objective = 6570.0`
- `production.quantities = {"Atlas": 70.0, "Beacon": 73.33333333333333}`
- `total_pallets = 140`
- `shipment.total_dispatched = 120`
- `shipment.total_cost = 526.0`
- `shipment.unmet_demand = {"Retail_A": 0, "Retail_B": 0, "Retail_C": 0}`
- `assignment.total_cost = 14.0`
- assignment pairs:
  - `truck_red -> Retail_B`
  - `truck_blue -> Retail_C`
  - `truck_green -> Retail_A`
- `routing.total_distance = 58`
- `routing.max_route_distance = 26`
- маршруты:
  - `truck_red: [0, 2, 0]`
  - `truck_blue: [0, 3, 0]`
  - `truck_green: [0, 1, 0]`

## Типичные ошибки и зачем сценарий важен

Типичные ошибки:

- думать, что `json <stage> {...}` дописывает только недостающие поля, хотя он заменяет stage целиком;
- забывать, что `set` меняет итоговую модель даже после того, как stage уже был готов;
- запускать `run` не посмотрев `show input`, из-за чего легко пропустить собственную ошибку в числах.

Почему этот сценарий важен:

- это самый безопасный путь для студента, который ещё не доверяет NL-режиму;
- он показывает best practice: сначала полный stage JSON, потом точечная коррекция через `set`;
- он хорошо иллюстрирует, что чат здесь работает как управляемый интерфейс к данным, а не как “разговор без правил”.
