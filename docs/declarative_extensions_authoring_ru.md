# Student Math v2: guide для начинающих

## Зачем мы поменяли DSL
Старый путь был полезным промежуточным шагом, но у него были три проблемы:
- математическая постановка смешивалась с логикой показа результата;
- `extension.yaml` заставлял думать про UI раньше, чем про саму задачу;
- грамматика была хуже читаема, чем привычная algebraic notation из учебников.

Теперь основной student-facing путь такой:
- `model.orx` — только математическая постановка LP-задачи;
- `extension.yaml` — только ввод, подписи, presets и display-описание;
- Python студенту не нужен.

## Ментальная схема, которую надо запомнить
1. Сначала вы думаете про математику.
2. Потом только описываете, как эти математические символы вводятся в приложении.
3. И только потом настраиваете, что именно приложение покажет после решения.

Коротко:
- `model.orx` отвечает за вопрос: **что считает модель**.
- `extension.yaml` отвечает за вопросы: **что вводит пользователь** и **что показывает приложение**.

## Минимальная структура папки

```text
extensions/
  my_extension/
    extension.yaml
    model.orx
    presets/
      demo.yaml
    tutorial/
      extension.annotated.yaml
      model.annotated.orx
      README.ru.md
```

## Рекомендуемый старт
Начинать теперь нужно не с копирования старой папки, а со scaffold-команды.

### 1-D шаблон распределения

```bash
make extension-scaffold \
  EXT=consultation_planner \
  TITLE="Планировщик консультаций" \
  ENTITY_SINGULAR_RU="консультация" \
  ENTITY_PLURAL_RU="консультации" \
  RESOURCE_LABEL_RU="часы преподавателя" \
  SET_SYMBOL=CONSULTATIONS
```

После этого сразу проверьте bundle:

```bash
make extension-check EXT=consultation_planner
```

### 2-D шаблон транспортной задачи

```bash
make extension-scaffold \
  EXT=transportation_demo \
  TITLE="Транспортная задача" \
  TEMPLATE_FAMILY=transportation \
  RESOURCE_LABEL_RU="груз" \
  ROW_ENTITY_SINGULAR_RU="склад" \
  ROW_ENTITY_PLURAL_RU="склады" \
  COL_ENTITY_SINGULAR_RU="магазин" \
  COL_ENTITY_PLURAL_RU="магазины" \
  ROW_SET_SYMBOL=ORIGINS \
  COL_SET_SYMBOL=DESTINATIONS
```

## Как теперь работать с задачей из учебника
Самый правильный порядок такой:

1. Возьмите обычную постановку LP-задачи на бумаге.
2. Выпишите множества.
3. Выпишите известные параметры.
4. Выпишите переменные решения.
5. Запишите целевую функцию.
6. Запишите ограничения.
7. Только после этого откройте `extension.yaml` и опишите ввод/вывод.

Если вы идёте в обратном порядке, почти всегда становится сложнее.

## Как читать `model.orx`
Читать нужно всегда в одном порядке:

1. `set`
2. `param`
3. `var`
4. `maximize` / `minimize`
5. `subject to`

### Канонический стиль записи
Мы используем ASCII algebraic notation, близкую к AMPL/MathProg:

```orx
set PRODUCTS;

param profit{PRODUCTS};
param labor_hours{PRODUCTS};
param labor_capacity;

var make{p in PRODUCTS} >= 0;

maximize total_profit:
    sum{p in PRODUCTS} profit[p] * make[p];

subject to labor_limit:
    sum{p in PRODUCTS} labor_hours[p] * make[p] <= labor_capacity;
```

### Что означают конструкции
- `set PRODUCTS;` — множество объектов задачи.
- `param profit{PRODUCTS};` — известные заранее числа, зависящие от объекта.
- `var make{p in PRODUCTS} >= 0;` — переменные решения.
- `maximize ...` — целевая функция.
- `subject to ...` — ограничения.
- `sum{p in PRODUCTS} ...` — суммирование по множеству.

### Важная разница с прежним ORX
Теперь в `model.orx` не должно быть student-facing `report`-логики.
Если вы хотите показать итоговую таблицу или summary-значение, это делается в `extension.yaml -> display`.

## Как читать `extension.yaml`
В `student_math_v2` файл intentionally маленький. В нём только четыре раздела:
- `extension`
- `inputs`
- `display`
- `presets`

### `extension`
Здесь лежат:
- `alias`
- `title`
- `description`
- `labels`

`labels` нужны только для русских подписей в интерфейсе.

### `inputs`
Здесь вы описываете, как символы модели вводятся через UI.

Есть три основных варианта шага:
- scalar/vector шаг через `params` и `vectors`;
- табличный шаг через `table`;
- матричный шаг через `matrix`.

#### Пример scalar/vector шага

```yaml
- id: time_budget
  label: Бюджет времени
  params:
    - param: weekly_hours
      field: weekly_hours
      label: Часов в неделю
      type: number
      min: 0.0001
      example: 12
```

Здесь главное поле — `param`. Оно ссылается прямо на символ модели.

#### Пример table-шага

```yaml
- id: courses
  label: Курсы
  table:
    set: COURSES
    key:
      field: course_names
      label: Названия курсов
      example: Math
    columns:
      - param: required_hours
        field: required_hours
        label: Требуемые часы
        type: number
        example: 30
```

Здесь:
- `set` указывает, какое множество мы наполняем;
- `key` задаёт элементы множества;
- каждая колонка ссылается на `param` модели.

#### Пример matrix-шага

```yaml
- id: costs
  label: Матрица тарифов
  matrix:
    rows_set: ORIGINS
    cols_set: DESTINATIONS
    fields:
      - param: cost
        field: cost_matrix
        label: Стоимость перевозки
        type: number
        example:
          - [4, 6]
          - [5, 4]
```

Здесь важно помнить:
- `rows_set` задаёт порядок строк;
- `cols_set` задаёт порядок столбцов;
- вход должен быть именно вложенными списками `[[...], [...]]`;
- значение `[i][j]` относится к паре “строка i, столбец j”.

### `display`
Это слой витрины, а не математики.

Пример:

```yaml
display:
  summary:
    - id: total_available_hours
      expr: available_hours
  tables:
    - id: course_plan
      rows: c in COURSES
      columns:
        - id: course
          expr: c
        - id: allocated_hours
          expr: study_hours[c]
```

Тут важно помнить:
- `summary` — отдельные итоговые числа;
- `tables` — итоговые таблицы по одному множеству;
- `matrices` — матричные витрины для 2-D результатов;
- `expr` использует выражения на языке `model.orx`;
- `display` не меняет саму оптимизационную задачу, а только показывает её результат.

#### Пример `display.matrices`

```yaml
display:
  matrices:
    - id: shipment_plan
      rows: o in ORIGINS
      cols: d in DESTINATIONS
      cell: ship[o, d]
```

### `presets`
Это готовые demo-данные для проверки bundle.

## Как выглядит рабочий цикл студента
1. Создать scaffold.
2. Отредактировать `model.orx`.
3. Привести `extension.yaml` в соответствие с моделью.
4. Обновить `presets/demo.yaml`.
5. Обновить tutorial-файлы с комментариями.
6. Запустить `make extension-check EXT=<alias>`.
7. Запустить `make dev`.

## Как читать ошибки
Если ошибка пришла из `model.orx`, смотрите в таком порядке:
1. строка/столбец;
2. проблемный символ;
3. какой именно идентификатор не объявлен или где нарушена линейность.

Если ошибка пришла из `extension.yaml`, почти всегда причина одна из этих:
- `param` ссылается не на тот символ модели;
- `set` не существует в `model.orx`;
- длина списка не совпадает с размером множества;
- размер матрицы не совпадает с порядком row/col множеств;
- tutorial-версия больше не совпадает с компактной runtime-версией.

## Что смотреть как эталон
- `extensions/study_planner/` — основной reference bundle.
- `extensions/transportation/` — reference bundle для 2-D ввода и матричного вывода.
- `docs/examples/student_math_v2/diet_blending/` — blending/diet example.
- `docs/examples/student_math_v2/production_planning/` — production planning example.
- `docs/examples/student_math_v2/transportation/` — math-only transportation example.

## Старые форматы
В проекте ещё поддерживаются:
- `student_v1`
- `expert_v1`

Это сделано ради мягкой миграции и совместимости.
Но новый рекомендованный путь для студентов — именно `student_math_v2`.
