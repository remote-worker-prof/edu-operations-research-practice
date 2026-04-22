# Student Math v2 examples

В этой папке лежат эталонные math-first LP-примеры:
- `diet_blending/`
- `production_planning/`
- `transportation/`

У каждого примера есть:
- компактная рабочая версия `model.orx`
- подробная версия `tutorial/model.annotated.orx`
- `demo_data.yaml`
- краткое объяснение в `README.ru.md`

Эти примеры используются не только как документация, но и как реальные golden-cases в тестах.

Если нужен не только math-only пример, а полноценный runnable bundle с `extension.yaml`,
смотрите:
- `extensions/study_planner/` для 1-D allocation-паттерна
- `extensions/transportation/` для 2-D matrix-паттерна
