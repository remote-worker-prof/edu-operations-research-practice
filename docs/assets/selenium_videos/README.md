# Selenium Demo Videos

Этот каталог содержит финальные MP4-ролики, записанные через Selenium + видимый
Chromium для учебной демонстрации чата.

## Сценарии

- `preset_overview.mp4`
  Базовый walkthrough: выбор `openai_default`, `load preset demo`, `show input`, `run`.
- `manual_json_flow.mp4`
  Полный ручной ввод через `json <stage> ...`, затем `set ...`, `show input` и `run`.
- `nl_confirm_flow.mp4`
  Natural-language ввод с показом `candidate patches`, подтверждением `да` и запуском `run`.
- `validation_recovery_flow.mp4`
  Ошибочный и частичный ввод, показ validation/error состояния, затем исправление и успешный запуск.
- `ambiguity_resolution_flow.mp4`
  Неоднозначная реплика, уточнение stage, подтверждение patch-а и успешный запуск.

## Длительности

- `preset_overview.mp4` — около 65 секунд
- `manual_json_flow.mp4` — около 141 секунды
- `nl_confirm_flow.mp4` — около 132 секунд
- `validation_recovery_flow.mp4` — около 128 секунд
- `ambiguity_resolution_flow.mp4` — около 144 секунд

Исходные временные артефакты Selenium по-прежнему появляются в
`.pytest_artifacts/e2e/videos/`, а этот каталог хранит уже отобранные версии с
постоянными именами для репозитория.
