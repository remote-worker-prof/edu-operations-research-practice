# Декларативные extensions для студентов: понятный вход без Python

## Главная идея
Теперь у нас два уровня описания extension:

- `student_v1` — короткий и дружелюбный формат для студентов.
- `expert_v1` — полный явный формат для сложных случаев и внутренней отладки.

Для большинства учебных работ студенту нужен именно `student_v1`.

## Ментальная схема, которую нужно запомнить
- `extension.yaml` отвечает за то, **что пользователь вводит** и **что приложение потом показывает**.
- `model.orx` отвечает за то, **какая математическая модель решается**.
- Python студенту не нужен.

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

## Рекомендуемый старт: scaffold, а не ручное копирование
Теперь основной путь для студента такой:

```bash
make extension-scaffold \
  EXT=consultation_planner \
  TITLE="Планировщик консультаций" \
  ENTITY_SINGULAR_RU="консультация" \
  ENTITY_PLURAL_RU="консультации" \
  RESOURCE_LABEL_RU="часы преподавателя" \
  SET_SYMBOL=CONSULTATIONS
```

Эта команда сразу создаст:

- `extensions/consultation_planner/extension.yaml`
- `extensions/consultation_planner/model.orx`
- `extensions/consultation_planner/presets/demo.yaml`
- `extensions/consultation_planner/tutorial/extension.annotated.yaml`
- `extensions/consultation_planner/tutorial/model.annotated.orx`
- `extensions/consultation_planner/tutorial/README.ru.md`

После генерации сразу проверьте bundle:

```bash
make extension-check EXT=consultation_planner
```

Если всё хорошо, запускайте приложение:

```bash
make dev
```

## Как выглядит `extension.yaml` в режиме `student_v1`
В начале файла ставим:

```yaml
format: student_v1
```

Дальше остаются только понятные разделы:

- `extension` — имя, описание и подписи для вывода.
- `wizard` — шаги ввода.
- `results` — порядок показа итоговых report-ов.
- `presets` — готовые примеры.
- `text` — шаблоны пояснений.

## Как выглядит `wizard`
Каждый шаг — это либо:

- `fields` — обычные поля;
- `table` — один ключевой список плюс связанные с ним списки-колонки.

### Вариант с обычными полями

```yaml
- id: time_budget
  label: Бюджет времени
  fields:
    - id: weekly_hours
      label: Часов в неделю
      help: Реалистичный недельный лимит.
      type: number
      min: 0.0001
      example: 12
```

### Вариант с таблицей

```yaml
- id: courses
  label: Курсы
  table:
    id: course_rows
    set: COURSES
    key:
      id: course_names
      label: Названия курсов
      example: Math
    columns:
      - id: required_hours
        label: Требуемые часы
        type: number
        min: 0.0001
        example: 30
```

### Что система делает сама
В `student_v1` движок сам генерирует:

- линейный порядок шагов;
- стандартные примеры команд;
- простые alias для stage;
- bindings из полей в параметры модели, если имена совпадают;
- стандартный вывод report-ов.

## Как выглядит `model.orx`
В v1 оставляем короткие английские ключевые слова:

- `set`
- `param`
- `var`
- `maximize` / `minimize`
- `st`
- `report`

### Что нового и более удобного
1. Можно писать комментарии через `#`.
2. Можно писать bounds в короткой форме:

```orx
var study_hours[COURSES] in 0..required_hours[COURSES]
```

3. Можно писать табличный report в учебной форме:

```orx
report course_plan by c in COURSES:
    course = c
    allocated_hours = study_hours[c]
```

## Что рекомендуется студенту при чтении модели
Читайте ORX всегда в одном и том же порядке:

1. `set` — какие объекты есть в задаче.
2. `param` — какие числа известны заранее.
3. `var` — какие числа надо подобрать.
4. `maximize` / `minimize` — что оптимизируем.
5. `st` — какими ограничениями связана задача.
6. `report` — что хотим показать после решения.

## Учебный образец
Эталонный пример лежит здесь:

- `extensions/study_planner/extension.yaml` — компактная рабочая версия.
- `extensions/study_planner/model.orx` — компактная математическая модель.
- `extensions/study_planner/tutorial/extension.annotated.yaml` — версия с подробными комментариями.
- `extensions/study_planner/tutorial/model.annotated.orx` — подробно прокомментированная модель.
- `extensions/study_planner/tutorial/README.ru.md` — пошаговое объяснение для начинающих.

## Рабочий поток студента
1. Запустите `make extension-scaffold ...`, чтобы получить готовую заготовку.
2. Отредактируйте рабочие файлы `extension.yaml` и `model.orx`.
3. Обновите `presets/demo.yaml`.
4. Синхронизируйте учебные файлы в `tutorial/`, чтобы комментарии соответствовали рабочей версии.
5. Проверьте bundle:

```bash
make extension-check EXT=<your_alias>
```

6. Запустите приложение:

```bash
make dev
```

`study_planner` полезно держать рядом как reference example, но копировать его вручную для старта теперь не нужно.

## Что проверяет `make extension-check`
Теперь валидатор проверяет не только runtime-файлы, но и tutorial-материалы:

- `extension.yaml`
- `model.orx`
- `tutorial/extension.annotated.yaml`
- `tutorial/model.annotated.orx`
- смысловое совпадение compact и annotated версий
- прохождение preset-ов

## Что важно помнить
- `student_v1` не делает DSL слабее: он просто короче и дружелюбнее.
- Если вашей задаче нужна нестандартная тонкая настройка, можно остаться на `expert_v1`.
- В текущем релизе поддерживается только continuous LP.
- Нелинейные конструкции вроде `x * y`, где обе части зависят от переменных решения, не поддерживаются.
