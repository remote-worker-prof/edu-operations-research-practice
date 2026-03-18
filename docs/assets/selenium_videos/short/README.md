# Selenium Short Demo Videos

Этот каталог содержит короткие polished MP4-ролики, записанные через Selenium +
видимый Chromium. В отличие от основного lecture-pack, здесь каждый ролик
показывает один конкретный приём или одно устойчивое UI-состояние.

## Сценарии

- `preset_overview_short.mp4`
  Самый короткий happy-path: `load preset demo` -> `run`.
- `russian_aliases_short.mp4`
  Русские alias-команды: `загрузить демо`, `показать`, `запуск`.
- `wizard_and_raw_json_short.mp4`
  `start`, `edit shipment`, затем raw JSON shortcut без префикса `json`.
- `manual_json_run_short.mp4`
  Компактный DSL-flow через `json <stage> ...` до успешного `run`.
- `nl_confirm_short.mp4`
  Свободный текст, `pending patches`, подтверждение `да`, затем `run`.
- `nl_reject_short.mp4`
  Свободный текст, `pending patches`, отклонение `нет` и проверка, что draft не изменился.
- `validation_recovery_short.mp4`
  Частичный JSON, malformed JSON и восстановление валидного stage.
- `ambiguity_resolution_short.mp4`
  Неоднозначная NL-реплика, уточнение stage, подтверждение patch-а и успешный `run`.

## Длительности

- `preset_overview_short.mp4` — около 19 секунд
- `russian_aliases_short.mp4` — около 21 секунды
- `wizard_and_raw_json_short.mp4` — около 19 секунд
- `manual_json_run_short.mp4` — около 30 секунд
- `nl_confirm_short.mp4` — около 22 секунд
- `nl_reject_short.mp4` — около 17 секунд
- `validation_recovery_short.mp4` — около 18 секунд
- `ambiguity_resolution_short.mp4` — около 27 секунд

Если нужен длинный пошаговый разбор задачи, математики и exact диалога,
переходите к [../README.md](../README.md) и далее к
[docs/video_scenarios/README.md](../../../video_scenarios/README.md).
