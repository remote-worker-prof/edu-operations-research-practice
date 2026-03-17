# Сценарий `ambiguity_resolution_flow`: как система снимает многозначность stage

## Что это за видео и чему оно учит

- Видео: [ambiguity_resolution_flow.mp4](../assets/selenium_videos/ambiguity_resolution_flow.mp4)
- Длительность: около 2 мин 24 с
- Главная цель: показать, что чат не обязан угадывать, к какому stage относится неоднозначное поле.

Этот сценарий демонстрирует:

1. ситуацию, где одно и то же имя поля может относиться к нескольким stage;
2. появление `uncertainties-card` вместо автоматического patch-а;
3. уточняющую реплику пользователя;
4. возвращение в обычный confirmation flow через `pending-patches-card`.

## Краткая постановка задачи

Есть два продукта `Flux` и `Glow`, два склада `Depot_A` и `Depot_B`,
три клиента `Market_1`, `Market_2`, `Market_3` и три ресурса
`route_1`, `route_2`, `route_3`.

Пользователь сначала вводит валидную базу через строгие `json`-команды.
Потом он пишет неоднозначную реплику:

```text
для production и shipment задай cost_matrix [[5,6,8],[4,5,3]]
```

Проблема в том, что `cost_matrix` встречается и в `shipment`, и в `assignment`,
а у пользователя в тексте ещё и упомянуты сразу несколько stage. Система поэтому
не применяет patch, а просит уточнение.

## Исходные данные по stage

### База до ambiguity-реплики

#### `production`

| Поле | Значение |
| --- | --- |
| `products` | `["Flux", "Glow"]` |
| `profits` | `[48, 34]` |
| `resource_matrix` | `[[2, 1], [1, 1.5]]` |
| `resource_limits` | `[240, 180]` |
| `demand_upper_bounds` | `[70, 80]` |
| `pallet_factors` | `[1.0, 0.88]` |

#### `shipment`

| Поле | Значение до уточнения |
| --- | --- |
| `warehouses` | `["Depot_A", "Depot_B"]` |
| `warehouse_supply_ratio` | `[0.55, 0.45]` |
| `clients` | `["Market_1", "Market_2", "Market_3"]` |
| `client_demand` | `[42, 38, 40]` |
| `cost_matrix` | `[[6, 5, 7], [5, 6, 4]]` |
| `capacity_matrix` | `[[50, 45, 40], [40, 45, 50]]` |

#### `assignment`

| Поле | Значение |
| --- | --- |
| `resources` | `["route_1", "route_2", "route_3"]` |
| `cost_matrix` | `[[5, 7, 6], [6, 5, 7], [7, 4, 5]]` |

#### `routing`

| Поле | Значение |
| --- | --- |
| `distance_matrix` | `[[0, 12, 10, 9], [12, 0, 6, 8], [10, 6, 0, 7], [9, 8, 7, 0]]` |
| `depot_index` | `0` |
| `client_nodes` | `[1, 2, 3]` |
| `vehicle_capacities` | `[55, 45, 45]` |

### Что меняется после уточнения

После второй реплики и подтверждения `да` меняется только одно поле:

| Поле | Итоговое значение к `run` |
| --- | --- |
| `shipment.cost_matrix` | `[[5, 6, 8], [4, 5, 3]]` |

Остальные stage остаются без изменений.

## Математика по 4 этапам

## 1. Production: LP

### Множества и индексы

- `I = {Flux, Glow}`
- `R = {1, 2}`

### Переменные

- `x_Flux`
- `x_Glow`

### Целевая функция

```text
max 48 * x_Flux + 34 * x_Glow
```

### Ограничения

```text
2 * x_Flux + 1 * x_Glow <= 240
1 * x_Flux + 1.5 * x_Glow <= 180
x_Flux <= 70
x_Glow <= 80
x_Flux, x_Glow >= 0
```

### Что уходит дальше

```text
total_pallets = round(1.0 * x_Flux + 0.88 * x_Glow)
```

## 2. Shipment: min-cost flow

### Множества и индексы

- склады: `Depot_A`, `Depot_B`
- клиенты: `Market_1`, `Market_2`, `Market_3`

### Переменные

- `y_a_1`, `y_a_2`, `y_a_3`
- `y_b_1`, `y_b_2`, `y_b_3`

### Целевая функция

После уточнения stage задача на shipment уже такая:

```text
min 5*y_A_1 + 6*y_A_2 + 8*y_A_3
  + 4*y_B_1 + 5*y_B_2 + 3*y_B_3
```

### Ограничения

- `available = min(total_pallets, 120) = 120`
- supplies по складам: `[66, 54]`
- спросы клиентов: `42`, `38`, `40`
- ограничения на отгрузки задаёт `capacity_matrix`

### Что уходит дальше

- `client_delivery = {"Market_1": 42, "Market_2": 38, "Market_3": 40}`
- `tasks = [("task-1", Market_1, 42), ("task-2", Market_2, 38), ("task-3", Market_3, 40)]`

## 3. Assignment: линейное назначение

### Множества и индексы

- ресурсы: `route_1`, `route_2`, `route_3`
- задачи: `task-1`, `task-2`, `task-3`

### Переменные

- `z_r_t in {0,1}`

### Целевая функция

```text
min 5*z_11 + 7*z_12 + 6*z_13
  + 6*z_21 + 5*z_22 + 7*z_23
  + 7*z_31 + 4*z_32 + 5*z_33
```

### Ограничения

- каждая задача назначается ровно один раз;
- каждый ресурс используется не более одного раза.

### Что уходит дальше

- assignment pairs;
- `allowed_vehicle_ids_by_client = {1: [0], 2: [1], 3: [2]}`

## 4. Routing: CVRP

### Множества и индексы

- узлы: `0, 1, 2, 3`
- depot: `0`
- клиентские узлы: `1, 2, 3`
- машины: `route_1`, `route_2`, `route_3`

### Переменные

На выходе видны маршруты:

- последовательность узлов;
- длина;
- загрузка.

### Целевая функция

```text
min total_distance
```

### Ограничения

- все клиенты должны быть обслужены;
- вместимость машин соблюдается;
- назначение assignment ограничивает, какая машина может ехать к какому клиенту.

## Конкретная арифметика и sanity-check

### Production

Оптимальные количества:

```text
x_Flux = 70
x_Glow = 73.33333333333333
```

Проверка прибыли:

```text
48 * 70 + 34 * 73.33333333333333
= 3360 + 2493.333333333333
= 5853.333333333333
```

Проверка паллет:

```text
70 * 1.0 + 73.33333333333333 * 0.88
= 70 + 64.53333333333333
= 134.53333333333333
round(...) = 135
```

### Shipment

Оптимальные legs после уточнения `shipment.cost_matrix`:

- `Depot_A -> Market_1 = 28` по цене `5`
- `Depot_A -> Market_2 = 38` по цене `6`
- `Depot_B -> Market_1 = 14` по цене `4`
- `Depot_B -> Market_3 = 40` по цене `3`

Проверка стоимости:

```text
28*5 + 38*6 + 14*4 + 40*3
= 140 + 228 + 56 + 120
= 544
```

### Assignment

Оптимальные пары:

- `route_1 -> Market_1` со стоимостью `5`
- `route_2 -> Market_2` со стоимостью `5`
- `route_3 -> Market_3` со стоимостью `5`

Проверка:

```text
5 + 5 + 5 = 15
```

### Routing

Маршруты:

- `route_1: [0, 1, 0]`, расстояние `12 + 12 = 24`
- `route_2: [0, 2, 0]`, расстояние `10 + 10 = 20`
- `route_3: [0, 3, 0]`, расстояние `9 + 9 = 18`

Проверка:

```text
24 + 20 + 18 = 62
max(24, 20, 18) = 24
```

## Что вводить в диалоге с агентом

В видео сообщения идут так:

```text
start
json production {"products": ["Flux", "Glow"], "profits": [48, 34], "resource_matrix": [[2, 1], [1, 1.5]], "resource_limits": [240, 180], "demand_upper_bounds": [70, 80], "pallet_factors": [1.0, 0.88]}
json shipment {"warehouses": ["Depot_A", "Depot_B"], "warehouse_supply_ratio": [0.55, 0.45], "clients": ["Market_1", "Market_2", "Market_3"], "client_demand": [42, 38, 40], "cost_matrix": [[6, 5, 7], [5, 6, 4]], "capacity_matrix": [[50, 45, 40], [40, 45, 50]]}
json assignment {"resources": ["route_1", "route_2", "route_3"], "cost_matrix": [[5, 7, 6], [6, 5, 7], [7, 4, 5]]}
json routing {"distance_matrix": [[0, 12, 10, 9], [12, 0, 6, 8], [10, 6, 0, 7], [9, 8, 7, 0]], "depot_index": 0, "client_nodes": [1, 2, 3], "vehicle_capacities": [55, 45, 45]}
для production и shipment задай cost_matrix [[5,6,8],[4,5,3]]
для shipment cost_matrix [[5,6,8],[4,5,3]]
да
run
```

## На что обращать внимание в UI

1. До ambiguity-реплики:
   - все stage уже готовы;
   - draft готов к `run`
2. После первой неоднозначной NL-реплики:
   - появляется `uncertainties-card`
   - `pending-patches-card` ещё нет
   - patch не применяется автоматически
3. После уточняющей реплики:
   - появляется `pending-patches-card`
   - в нём видно именно `shipment.cost_matrix`
4. После `да`:
   - patch применяется
   - draft снова готов к запуску
5. После `run`:
   - отображаются OR-результаты для уже обновлённого `shipment.cost_matrix`

## Ожидаемые детерминированные результаты

- `production.objective = 5853.333333333333`
- `production.quantities = {"Flux": 70.0, "Glow": 73.33333333333333}`
- `total_pallets = 135`
- `shipment.total_dispatched = 120`
- `shipment.total_cost = 544.0`
- `shipment.unmet_demand = {"Market_1": 0, "Market_2": 0, "Market_3": 0}`
- `assignment.total_cost = 15.0`
- assignment pairs:
  - `route_1 -> Market_1`
  - `route_2 -> Market_2`
  - `route_3 -> Market_3`
- `routing.total_distance = 62`
- `routing.max_route_distance = 24`

## Типичные ошибки и зачем сценарий важен

Типичные ошибки:

- ожидать, что неоднозначная реплика сразу станет patch-ем;
- не различать `uncertainties-card` и `pending-patches-card`;
- уточнить stage, но забыть после этого отправить `да`.

Почему этот сценарий важен:

- он показывает, что система не должна угадывать в неоднозначных местах;
- он учит работать с уточнениями как с нормальной частью диалога;
- это хороший пример безопасного поведения агента при конфликте между несколькими stage.

