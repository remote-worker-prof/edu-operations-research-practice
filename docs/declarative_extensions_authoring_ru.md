# Декларативные extensions: краткое руководство для студентов

## Что изменилось
Теперь новое extension не нужно писать на Python.
Достаточно создать папку `extensions/<alias>/` и положить туда:

- `extension.yaml` — структура wizard-а, поля, bindings, presets, result sections
- `model.orx` — математическая постановка LP-задачи
- `presets/demo.yaml` — необязательный demo preset

## Минимальная структура

```text
extensions/
  my_planner/
    extension.yaml
    model.orx
    presets/
      demo.yaml
```

## Как устроен `extension.yaml`
В этом файле задаются:

- `extension`: alias, title, description, examples, aliases
- `stages`: шаги wizard-а и поля ввода
- `bindings`: как поля UI становятся set/param символами модели
- `results`: какие scalar/table reports показать в UI
- `presets`: готовые YAML-наборы входных данных

Ключевая идея: студент описывает структуру задачи, а не пишет runtime-код.

## Как устроен `model.orx`
Поддерживаемые ключевые слова v1:

- `set`
- `param`
- `var`
- `maximize` / `minimize`
- `st`
- `report`

Пример:

```orx
set COURSES

param weekly_hours
param weeks
param required_hours[COURSES]
param priority[COURSES]
param available_hours = weekly_hours * weeks

var study_hours[COURSES] >= 0

maximize weighted_score:
    sum(c in COURSES, priority[c] * study_hours[c])

st total_hours:
    sum(c in COURSES, study_hours[c]) <= available_hours

st course_cap[c in COURSES]:
    study_hours[c] <= required_hours[c]

report total_available_hours = available_hours
```

## Рабочий поток
1. Скопируйте `extensions/study_planner/` в новую папку `extensions/<your_alias>/`.
2. В `extension.yaml` переименуйте alias/title и адаптируйте stages/fields.
3. В `bindings` свяжите поля со своими `set` и `param` символами.
4. В `model.orx` запишите свою математическую постановку.
5. При желании добавьте `presets/demo.yaml`.
6. Проверьте bundle:

```bash
make extension-check EXT=<your_alias>
```

7. Запустите приложение:

```bash
make dev
```

8. В UI выберите свой extension и пройдите сценарий `start -> ввод -> run`.

## Что важно помнить
- v1 поддерживает только continuous LP.
- Нельзя писать student-authored Python hooks.
- Нельзя использовать нелинейные выражения вида `x * y`, если обе части зависят от decision variables.
- Для табличного вывода используйте `report <name>[i in SET]: { ... }`.

## На что смотреть в образце
Базовый образец находится в `extensions/study_planner/`.
Он показывает полный путь:

- stage-based ввод
- bindings из UI в модель
- LP objective + constraints
- scalar reports
- table report для итоговой таблицы
