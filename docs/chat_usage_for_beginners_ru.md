# Как общаться с чатом и отправлять данные

Этот документ подробно объясняет, как именно пользоваться чатом в учебном OR-приложении:

- какие сообщения он понимает;
- когда лучше писать свободным текстом, а когда использовать точные команды;
- в каком виде передавать массивы, числа, JSON-объекты и отдельные поля;
- почему чат иногда просит подтверждение `да/нет`;
- что делать, если он не понял реплику или не даёт запустить расчёт.

Это beginner-friendly guide, но по содержанию он специально близок к реальному контракту системы.
Здесь не придумываются новые команды и форматы. Ниже описано то, что чат уже поддерживает.

Если вам нужен общий архитектурный контекст, сначала полезно прочитать
[architecture_for_beginners_ru.md](architecture_for_beginners_ru.md).
Если нужен именно точный reference по языку ввода, строгости синтаксиса,
кусочному вводу и stage-by-stage DSL-примерам, смотрите
[chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).
Если нужны практические сценарии ровно по тем же шагам, что и в демонстрационных
Selenium-видео, смотрите [video_scenarios/README.md](video_scenarios/README.md).
Если нужен короткий технический контракт именно NL-режима, смотрите
[natural_language_assistant_ru.md](natural_language_assistant_ru.md).

## TL;DR

Если запомнить только самое главное, то вот короткая версия:

- Сначала чат собирает входы для 4 stage: `production`, `shipment`, `assignment`, `routing`.
- Потом расчёт запускается только по явной команде `run`.
- Есть 2 основных способа общения:
  - natural-language: пишете обычным языком, потом подтверждаете `да` или `нет`;
  - exact commands: `json <stage> {...}` или `set <stage>.<field> <value>` для точного контроля.
- Если нужен полный reference по этому полу-DSL, лучше сразу открыть
  [chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).
- Если в сообщении есть и фраза “запусти”, и параметры, чат сначала извлечёт параметры и попросит подтверждение, а не побежит считать.
- Если вы не уверены, используйте безопасный режим:
  - `json <stage> {...}`
  - `set <stage>.<field> <value>`
- `routing.client_demands` вручную вводить не нужно: это derived-поле, его система получает из этапа `shipment`.
- Если хочется не только reference, но и готовые walkthrough-разборы с exact сообщениями,
  UI-checkpoints и ожидаемыми числами, откройте
  [video_scenarios/README.md](video_scenarios/README.md).

## 1. Что вообще умеет этот чат

Чат здесь нужен не для “болтовни”, а для управляемого сбора структурированных OR-входов.

Его задача:

1. помочь пользователю заполнить все независимые входы;
2. показать, что именно он понял из сообщения;
3. не дать случайно запустить расчёт на сыром или неоднозначном вводе;
4. после `run` вернуть результат и объяснение.

Если сказать совсем просто:

- до `run` чат работает как умный сборщик данных;
- после `run` чат показывает результат расчёта и объяснение.

## 2. Какие есть 2 режима общения

### 2.1 Natural-language режим

Вы пишете почти “по-человечески”, например:

```text
production profits [40,30], products ["A","B"]
```

Тогда чат:

1. пытается извлечь `candidate patches`;
2. показывает, что он понял;
3. ждёт подтверждение `да` или отклонение `нет`;
4. только после подтверждения записывает данные в `ScenarioDraft`.

Этот режим удобен, когда:

- вы мыслите параметрами модели, а не командами;
- хотите быстро написать несколько полей в одной реплике;
- готовы глазами проверить, что чат всё понял правильно.

### 2.2 Детерминированный command-режим

Вы используете точные команды:

- `json <stage> {...}`
- `set <stage>.<field> <value>`
- `show input`
- `next`
- `run`
- и так далее.

Этот режим удобен, когда:

- нужна точность без догадок;
- нужно исправить одно поле;
- хочется вставить готовый JSON;
- natural-language режим ошибается или задаёт слишком много уточнений.

### Что рекомендовать новичку

Самая безопасная стратегия такая:

- если хотите быстро и естественно писать данные, используйте natural-language;
- если чат не понял вас или если вы хотите полный контроль, переходите на `json` и `set`.

## 3. Как чат обрабатывает одно сообщение

Ниже упрощённый, но точный flow одного user message:

```text
[Сообщение пользователя]
          |
          v
  Это явная команда-prefix?
          |
     +----+----+
     |         |
    да        нет
     |         |
     v         v
[command      [NL parser]
 parser]          |
     |            +--> нашёл intent confirm/reject/help/run?
     |            |        |
     |            |        +--> да: special handling
     |            |
     |            +--> нашёл candidate patches?
     |                     |
     |                     +--> да: показать, что понял -> ждать `да/нет`
     |                     +--> нет: уточнить ошибку / предложить json/set
     |
     +--> update draft / show draft / move stage / load preset / try run
                         |
                         v
              recompute missing_fields / ready_to_run
                         |
                         +--> если ещё рано: следующий вопрос
                         +--> если можно run: запуск OR + explanation
```

Ключевая идея:

- одно сообщение не идёт напрямую в OR-пайплайн;
- сначала чат решает, это команда, natural-language ввод или подтверждение;
- затем пересчитывает состояние draft;
- и только потом решает, можно ли считать.

## 4. Как выбрать режим ввода

Ниже practical decision tree:

```text
Хотите просто начать новую сессию?
  -> start

Хотите увидеть текущий черновик?
  -> show input

У вас уже есть готовый JSON для целого stage?
  -> json <stage> { ... }

Хотите отправить чистый JSON для уже выбранного stage?
  -> edit <stage>
  -> затем просто { ... }

Хотите поправить одно конкретное поле?
  -> set <stage>.<field> <value>

Хотите писать почти обычным языком?
  -> natural-language реплика
  -> потом подтвердить `да` или отклонить `нет`

Хотите перейти к следующему незаполненному stage?
  -> next

Хотите готовый демонстрационный пример?
  -> load preset demo

Все данные уже готовы и валидны?
  -> run
```

## 5. Когда сообщение считается командой, а когда natural-language

Это важная часть поведения чата.

### Явные команды

Если сообщение выглядит как точная команда, чат отправляет его в command parser.
Практически это относится к сообщениям вроде:

- `start`
- `reset`
- `show input`
- `show`
- `next`
- `json ...`
- `set ...`
- `edit ...`
- `load preset demo`

### Natural-language сообщения

Если сообщение не выглядит как точная команда, чат пытается понять его как:

- обычный ввод параметров;
- `run`-intent;
- `help`-intent;
- подтверждение;
- отклонение.

### Важный нюанс про `run`

Сообщение:

```text
run
```

или:

```text
запусти расчёт
```

может быть понято как intent запуска.

Но если в сообщении одновременно есть маркер запуска и реальные поля модели, приоритет у извлечения данных, а не у запуска.

Пример:

```text
запусти production profits [41,31], products ["A","B"]
```

Такое сообщение не запускает расчёт сразу.
Сначала чат извлечёт параметры, покажет их и попросит `да/нет`.

## 6. Базовые команды, которые реально поддерживает чат

Этот раздел оставлен как обзор.
Если нужен главный reference по синтаксису, alias-ам, строгости языка и различию
между `json`, `set`, raw JSON и NL-вводом, используйте
[chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).

Ниже перечислены пользовательские формы, подтверждённые parser-кодом.

### Команды управления сессией

#### `start`

Начать ввод заново с пустого draft и перейти к `production`.

Пример:

```text
start
```

Русский alias:

```text
старт
```

#### `reset`

Сбросить текущий draft и начать заново.

Пример:

```text
reset
```

Русский alias:

```text
сброс
```

#### `help`

Попросить подсказку по допустимым способам ввода.

Рекомендуемая форма:

```text
help
```

Также понимаются:

```text
помощь
что дальше
как вводить
```

### Команды просмотра и навигации

#### `show input`

Показать весь текущий `ScenarioDraft`.

Рекомендуемая форма:

```text
show input
```

Короткие aliases:

```text
show
показать ввод
показать
```

#### `next`

Перейти к следующему незаполненному stage.

Пример:

```text
next
```

Русский alias:

```text
далее
```

#### `edit <stage>`

Выбрать stage как текущий, чтобы дальше можно было отправить чистый JSON-объект без префикса `json`.

Пример:

```text
edit shipment
```

После этого можно отправить:

```json
{"clients":["C1","C2","C3"],"client_demand":[42,38,40]}
```

### Команды загрузки данных

#### `json <stage> { ... }`

Записывает JSON-объект в выбранный stage целиком.

Общий вид:

```text
json <stage> { ... }
```

Пример:

```text
json production {"products":["A","B"],"profits":[40,30],"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}
```

Важно:

- после `json` stage должен быть JSON-объектом, а не массивом;
- если JSON некорректный, чат вернёт понятную ошибку;
- этот режим хорош, когда у вас уже есть готовый блок данных;
- это не field-by-field merge: новый объект заменяет текущее содержимое stage;
- если вы отправите только часть полей, stage может стать неполным, и тогда чат снова будет считать его неготовым.

#### Чистый JSON-объект для текущего stage

Если текущий stage уже выбран через wizard или через `edit <stage>`, можно отправить просто объект:

```json
{"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}
```

Это shorthand-режим.

Он работает только если у чата уже есть `current_stage`.
Если current stage не определён, чат попросит использовать явную форму:

```text
json <stage> { ... }
```

Как и в обычной `json <stage> { ... }` форме, отправленный объект заменяет текущий payload stage, а не merge-ится поверх него.

#### `set <stage>.<field_path> <value>`

Изменяет одно поле в draft.

Общий вид:

```text
set <stage>.<field_path> <value>
```

Примеры:

```text
set production.profits [40,30]
set routing.depot_index 0
set routing.objective "total_distance"
set shipment.clients ["C1","C2","C3"]
```

Этот режим особенно полезен, когда:

- нужно поправить одно поле;
- не хочется переписывать весь JSON stage;
- natural-language режим что-то понял неверно.

### Команды запуска и preset

#### `load preset demo`

Загружает готовый demo draft.

Рекомендуемая форма:

```text
load preset demo
```

Также понимаются:

```text
preset demo
load demo
загрузить демо
```

#### `run`

Запустить расчёт.

Рекомендуемая форма:

```text
run
```

Также чат понимает natural-language аналоги, например:

```text
запусти расчёт
посчитай
рассчитай
```

Но запуск произойдёт только если:

- все stage валидны;
- нет неподтверждённых `candidate patches`.

## 7. Какие значения реально понимает `set`

Команда `set` умеет распознавать не только строки.

### JSON-массивы

Пример:

```text
set shipment.client_demand [42,38,40]
```

### JSON-объекты

Технически поддерживаются и объекты:

```text
set production.some_field {"a":1}
```

В текущих stage-схемах чаще нужны массивы и скаляры, но parser умеет и это.

### Целые числа

Пример:

```text
set routing.depot_index 0
```

### Числа с плавающей точкой

Пример:

```text
set shipment.warehouse_supply_ratio [0.55,0.45]
```

Или для отдельного scalar-поля в общем случае:

```text
set some_stage.some_field 1.5
```

### Булевы значения

Понимаются `true` и `false`.

Пример:

```text
set some_stage.some_flag true
```

### Строки

Строку можно передать:

- как JSON-строку в кавычках;
- как обычный token без кавычек, если в значении нет пробелов.

Безопасный вариант:

```text
set routing.objective "total_distance"
```

Допустим и такой:

```text
set routing.objective total_distance
```

### Что рекомендовать новичку

Самое безопасное правило:

- массивы и объекты всегда пишите как валидный JSON;
- строки, если сомневаетесь, берите в двойные кавычки.

## 8. Какие stage-имена лучше использовать

### Рекомендуемые канонические формы

В командах новичку лучше использовать:

- `production`
- `shipment`
- `assignment`
- `routing`

Так меньше шансов запутаться.

### Командные aliases, которые понимает parser

Для `edit`, `json`, `set` и похожих команд понимаются:

- `production`, `prod`, `производство`
- `shipment`, `ship`, `отгрузка`
- `assignment`, `assign`, `назначение`
- `routing`, `route`, `маршрутизация`

### Дополнительные natural-language слова, которые чат узнаёт

В свободном тексте чат может понять ещё и такие stage-маркеры:

- `выпуск` -> `production`
- `доставка` -> `shipment`
- `маршруты` -> `routing`

Но для beginner-практики всё равно лучше держаться канонических имён stage.

## 9. Что такое `candidate patches` и зачем нужны `да/нет`

Когда вы пишете в natural-language режиме, чат не должен молча менять ваш draft.

Вместо этого он делает промежуточный шаг:

1. извлекает предполагаемые изменения;
2. показывает их;
3. ждёт подтверждение.

Пример:

Вы пишете:

```text
production profits [40,30], products ["A","B"]
```

Чат отвечает примерно так:

```text
Я извлёк параметры:
- production.profits = [40, 30]
- production.products = ["A", "B"]
Подтвердите `да` или отклоните `нет`.
```

### Чем подтверждать

Рекомендуемые формы:

```text
да
нет
```

Дополнительно чат понимает некоторые синонимы:

- для подтверждения: `подтверждаю`, `подтвердить`, `ок`, `согласен`;
- для отклонения: `отмена`, `не подтверждаю`, `отклонить`, `не так`.

Но новичку лучше использовать именно `да` и `нет`.

### Почему это важно

- это защита от неверной интерпретации;
- это делает переход “текст -> формальный параметр” прозрачным;
- это не даёт LLM или parser-у незаметно изменить данные.

## 10. Что увидит пользователь на разных шагах

### Когда stage ещё не заполнен

Чат подскажет следующий шаг и обычно покажет пример `json <stage> {...}` для нужного stage.

### Когда natural-language реплика понятна

Чат покажет:

- извлечённые `candidate patches`;
- confidence;
- просьбу ответить `да` или `нет`.

### Когда реплика неоднозначна

Чат не будет применять patch-и автоматически.
Вместо этого он вернёт один точный вопрос или одну точную ошибку.

Типичный случай:

```text
для production и shipment задай cost_matrix [[1,2],[2,1]]
```

Здесь проблема в том, что в одном сообщении найдено несколько stage.

### Когда всё готово к запуску

Чат переводит сессию в состояние `ready_to_run`.
Практически это означает:

- все stage валидны;
- нет неподтверждённых patch-ей;
- следующий разумный шаг — команда `run`.

Пользователь увидит подсказку вроде:

```text
Входы валидны. Для запуска расчёта отправьте `run`.
```

Также система может подготовить короткий `pre_run_summary`.

### Когда `run` заблокирован

Это бывает по двум главным причинам:

1. есть неподтверждённые `candidate patches`;
2. не все stage готовы или валидны.

Примеры сообщений:

- “Нельзя запускать расчёт с неподтверждёнными NL-параметрами. Ответьте `да` или `нет`.”
- “Нельзя запустить OR: не все входы готовы.”

## 11. Подробные copy-paste примеры по каждому stage

Ниже остаются быстрые практические примеры.
Если нужен полный stage-by-stage reference с объяснением, что именно можно вводить
частями и почему `json <stage>` заменяет stage целиком, смотрите
[chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).

Ниже для каждого stage даны примеры:

- natural-language;
- `json <stage> { ... }`;
- `set <stage>.<field> <value>`.

### 11.1 `production`

#### Natural-language

```text
production products ["A","B"], profits [40,30], resource_matrix [[2,1],[1,1.5]], resource_limits [240,180], demand_upper_bounds [70,80], pallet_factors [1.0,0.8]
```

#### JSON

```text
json production {"products":["A","B"],"profits":[40,30],"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}
```

#### `set`

```text
set production.products ["A","B"]
set production.profits [40,30]
set production.resource_matrix [[2,1],[1,1.5]]
set production.resource_limits [240,180]
set production.demand_upper_bounds [70,80]
set production.pallet_factors [1.0,0.8]
```

### 11.2 `shipment`

#### Natural-language

```text
shipment warehouses ["W1","W2"], warehouse_supply_ratio [0.55,0.45], clients ["C1","C2","C3"], client_demand [42,38,40], cost_matrix [[4,6,8],[5,4,3]], capacity_matrix [[50,45,40],[40,45,50]]
```

#### JSON

```text
json shipment {"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],"clients":["C1","C2","C3"],"client_demand":[42,38,40],"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}
```

#### `set`

```text
set shipment.warehouses ["W1","W2"]
set shipment.warehouse_supply_ratio [0.55,0.45]
set shipment.clients ["C1","C2","C3"]
set shipment.client_demand [42,38,40]
set shipment.cost_matrix [[4,6,8],[5,4,3]]
set shipment.capacity_matrix [[50,45,40],[40,45,50]]
```

### 11.3 `assignment`

#### Natural-language

```text
assignment resources ["truck_1","truck_2","truck_3"], cost_matrix [[8,6,7],[5,8,6],[7,5,9]]
```

#### JSON

```text
json assignment {"resources":["truck_1","truck_2","truck_3"],"cost_matrix":[[8,6,7],[5,8,6],[7,5,9]]}
```

#### `set`

```text
set assignment.resources ["truck_1","truck_2","truck_3"]
set assignment.cost_matrix [[8,6,7],[5,8,6],[7,5,9]]
```

### 11.4 `routing`

#### Natural-language

```text
routing distance_matrix [[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]], depot_index 0, client_nodes [1,2,3], vehicle_capacities [55,45,45]
```

#### JSON

```text
json routing {"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}
```

#### `set`

```text
set routing.distance_matrix [[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]]
set routing.depot_index 0
set routing.client_nodes [1,2,3]
set routing.vehicle_capacities [55,45,45]
```

#### Важное замечание про derived-поле

`routing.client_demands` вручную вводить не нужно.
Чат и OR-пайплайн получают эти demand-ы из результатов `shipment`, а не из ручного draft-поля пользователя.

## 12. Три хорошие стратегии работы с чатом

### Стратегия 1. Полностью через natural-language

Подходит, если хотите писать быстро и готовы подтверждать `да/нет`.

Пример:

```text
start
production products ["A","B"], profits [40,30], resource_matrix [[2,1],[1,1.5]], resource_limits [240,180], demand_upper_bounds [70,80], pallet_factors [1.0,0.8]
да
shipment warehouses ["W1","W2"], warehouse_supply_ratio [0.55,0.45], clients ["C1","C2","C3"], client_demand [42,38,40], cost_matrix [[4,6,8],[5,4,3]], capacity_matrix [[50,45,40],[40,45,50]]
да
assignment resources ["truck_1","truck_2","truck_3"], cost_matrix [[8,6,7],[5,8,6],[7,5,9]]
да
routing distance_matrix [[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]], depot_index 0, client_nodes [1,2,3], vehicle_capacities [55,45,45]
да
run
```

### Стратегия 2. Полностью через `json`

Подходит, если данные уже готовы блоками.

Пример:

```text
start
json production {"products":["A","B"],"profits":[40,30],"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}
json shipment {"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],"clients":["C1","C2","C3"],"client_demand":[42,38,40],"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}
json assignment {"resources":["truck_1","truck_2","truck_3"],"cost_matrix":[[8,6,7],[5,8,6],[7,5,9]]}
json routing {"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}
run
```

### Стратегия 3. Preset + точечные правки

Подходит, если хотите стартовать с готового примера и только слегка его адаптировать.

Пример:

```text
load preset demo
show input
set production.profits [45,35]
set routing.vehicle_capacities [60,45,45]
run
```

## 13. Частые ошибки и как из них выходить

### Ошибка 1. В одном сообщении несколько stage

Плохо:

```text
для production и shipment задай cost_matrix [[1,2],[2,1]]
```

Почему плохо:

- непонятно, к какому stage относится поле.

Как исправить:

- разделить на 2 сообщения;
- либо использовать явные команды `set` или `json`.

### Ошибка 2. Хотели запустить расчёт, но чат просит `да/нет`

Причина:

- у вас есть неподтверждённые `candidate patches`.

Что делать:

- подтвердить `да`, если всё верно;
- ответить `нет`, если нужно переписать ввод точнее.

### Ошибка 3. Чат не понял свободный текст

Что делать:

1. добавить stage явно;
2. написать поле и значение в одном сообщении;
3. если не помогло, перейти на `json` или `set`.

### Ошибка 4. `run` не запускается

Типичные причины:

- есть неподтверждённые NL-патчи;
- не все stage валидны;
- в одном из stage не хватает обязательных полей.

Что делать:

- `show input`
- `next`
- при необходимости исправить поля через `set`
- затем снова `run`

### Ошибка 5. Хочется быстро отправить большой JSON, но чат не понимает, к какому stage он относится

Что делать:

- использовать `json <stage> {...}`;
- или сначала `edit <stage>`, затем отправить чистый JSON-объект.

## 14. Мини-cheat sheet

### Самые полезные команды

```text
start
help
show input
next
edit <stage>
json <stage> { ... }
set <stage>.<field> <value>
load preset demo
run
reset
```

### Самые безопасные практики

- Для свободного текста используйте один stage на сообщение.
- После natural-language extraction отвечайте простым `да` или `нет`.
- Если чат сомневается, переходите на `json` или `set`.
- Для команд используйте канонические stage-имена: `production`, `shipment`, `assignment`, `routing`.
- Не вводите `routing.client_demands` вручную.

## 15. Куда читать дальше

Если после этого документа хочется углубиться:

1. [architecture_for_beginners_ru.md](architecture_for_beginners_ru.md) — как чат вписывается в общую архитектуру системы.
2. [chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md) — точный язык ввода, его строгость и safe-практики.
3. [natural_language_assistant_ru.md](natural_language_assistant_ru.md) — короткий контракт NL-режима.
4. [architecture.md](architecture.md) — техническая спецификация runtime flow и state-контрактов.
5. Код:
   - `packages/agent_core/src/agent_core/input_parser.py`
   - `packages/agent_core/src/agent_core/nl_parser.py`
   - `packages/agent_core/src/agent_core/dialog_graph.py`
