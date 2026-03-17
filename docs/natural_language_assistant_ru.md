# Natural-Language Ассистент (v1.1)

Этот документ остаётся коротким contract/ADR-описанием NL-режима.
Если нужен подробный beginner-friendly guide по тому, как именно общаться с чатом,
какие команды и форматы поддерживаются и как отправлять данные по stage,
смотрите [chat_usage_for_beginners_ru.md](chat_usage_for_beginners_ru.md).
Если нужен отдельный точный reference по языку ввода, строгости синтаксиса,
кусочному вводу и DSL-практикам, смотрите
[chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).

## Как это работает

Ассистент работает в гибридном режиме:

1. Студент пишет реплику обычным языком.
2. NL-слой извлекает `candidate patches` (структурированные изменения draft).
3. Ассистент показывает, что именно понял, и просит подтверждение `да/нет`.
4. Только после подтверждения параметры применяются в `ScenarioDraft`.
5. Команда `run` разрешена, когда все stage валидны и нет неподтверждённых patch-ей.

Политика приоритетов NL intent (ADR):
- если в реплике есть признаки структурированных полей, сначала выполняется extraction;
- `run`-intent принимается только когда из реплики не извлечено ни одного поля;
- любое извлечение из NL требует подтверждения `да/нет` перед применением.

LLM-assisted fallback:
- при низкой уверенности детерминированного парсера можно подключить LLM для предложения candidate patches;
- LLM никогда не пишет draft напрямую;
- при недоступном провайдере агент остаётся в детерминированном режиме и предлагает `json/set`.

Почему есть подтверждение:
- это защита от ошибок интерпретации;
- это учебная прозрачность: студент видит связку “текст -> формальный параметр модели”.

## Типовые реплики студентов и трансформация в stage-patches

1. `production profits [40,30], products ["A","B"]`
- `production.profits = [40, 30]`
- `production.products = ["A", "B"]`

2. `production resource_limits [240,180]`
- `production.resource_limits = [240, 180]`

3. `shipment warehouses ["W1","W2"], clients ["C1","C2","C3"]`
- `shipment.warehouses = ["W1", "W2"]`
- `shipment.clients = ["C1", "C2", "C3"]`

4. `shipment client_demand [42,38,40]`
- `shipment.client_demand = [42, 38, 40]`

5. `assignment resources ["truck_1","truck_2","truck_3"]`
- `assignment.resources = ["truck_1", "truck_2", "truck_3"]`

6. `assignment cost_matrix [[8,6,7],[5,8,6],[7,5,9]]`
- `assignment.cost_matrix = [[8,6,7],[5,8,6],[7,5,9]]`

7. `routing depot_index 0, client_nodes [1,2,3]`
- `routing.depot_index = 0`
- `routing.client_nodes = [1,2,3]`

8. `routing distance_matrix [[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]]`
- `routing.distance_matrix = [[...]]`

9. `routing vehicle_capacities [55,45,45]`
- `routing.vehicle_capacities = [55,45,45]`

10. `запусти расчёт`
- intent `run` (запуск только после полной валидации и подтверждений)

## Ошибки интерпретации и как исправлять

- Если реплика неоднозначна (например, упомянуто несколько stage), ассистент задаёт один уточняющий вопрос.
- Если confidence низкий, ассистент просит уточнить конкретное поле.
- Если реплика содержит и маркер запуска, и параметры (`"запусти ... profits [...]"`), агент сначала попросит подтвердить извлечённые параметры.
- Если удобно, всегда можно перейти на безопасный режим:
  - `json <stage> {...}`
  - `set <stage>.<field> <value>`

## Учебные акценты для начинающих

- Для ключевых полей ассистент показывает краткие подсказки:
  - что это за параметр,
  - в каких единицах задаётся,
  - пример корректного значения.
- Перед запуском выводится короткий предрасчётный конспект по 4 этапам OR-подграфа.

Для пошагового пользовательского tutorial-режима см. также
[chat_usage_for_beginners_ru.md](chat_usage_for_beginners_ru.md).
Для отдельного stage-by-stage reference по языку ввода см.
[chat_input_language_for_beginners_ru.md](chat_input_language_for_beginners_ru.md).
