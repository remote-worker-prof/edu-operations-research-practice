# Selenium Demo Videos

Этот каталог содержит финальные MP4-ролики, записанные через Selenium + видимый
Chromium для учебной демонстрации чата.

Длинный lecture-friendly набор живёт прямо в этом каталоге. Отдельный компактный
short-pack лежит в [short/README.md](short/README.md).

## Сценарии

- `preset_overview.mp4`
  Базовый walkthrough: выбор `openai_default`, `load preset demo`, `show input`, `run`.
  Текстовый разбор: [docs/video_scenarios/preset_overview_ru.md](../../video_scenarios/preset_overview_ru.md).
- `manual_json_flow.mp4`
  Полный ручной ввод через `json <stage> ...`, затем `set ...`, `show input` и `run`.
  Текстовый разбор: [docs/video_scenarios/manual_json_flow_ru.md](../../video_scenarios/manual_json_flow_ru.md).
- `nl_confirm_flow.mp4`
  Natural-language ввод с показом `candidate patches`, подтверждением `да` и запуском `run`.
  Текстовый разбор: [docs/video_scenarios/nl_confirm_flow_ru.md](../../video_scenarios/nl_confirm_flow_ru.md).
- `validation_recovery_flow.mp4`
  Ошибочный и частичный ввод, показ validation/error состояния, затем исправление и успешный запуск.
  Текстовый разбор: [docs/video_scenarios/validation_recovery_flow_ru.md](../../video_scenarios/validation_recovery_flow_ru.md).
- `ambiguity_resolution_flow.mp4`
  Неоднозначная реплика, уточнение stage, подтверждение patch-а и успешный запуск.
  Текстовый разбор: [docs/video_scenarios/ambiguity_resolution_flow_ru.md](../../video_scenarios/ambiguity_resolution_flow_ru.md).

## Длительности

- `preset_overview.mp4` — около 65 секунд
- `manual_json_flow.mp4` — около 141 секунды
- `nl_confirm_flow.mp4` — около 132 секунд
- `validation_recovery_flow.mp4` — около 128 секунд
- `ambiguity_resolution_flow.mp4` — около 144 секунд

Исходные временные артефакты Selenium по-прежнему появляются в
`.pytest_artifacts/e2e/videos/`, а этот каталог хранит уже отобранные версии с
постоянными именами для репозитория. Короткие polished-ролики лежат в
`docs/assets/selenium_videos/short/`.

Если хочется не просто посмотреть видео, а пошагово разобрать задачу, математику,
ввод в чат и ожидаемые числа, начните с
[docs/video_scenarios/README.md](../../video_scenarios/README.md).
