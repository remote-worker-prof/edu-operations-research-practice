# Текстовые разборы демонстрационных видео

Этот раздел дополняет MP4-ролики из
[docs/assets/selenium_videos](../assets/selenium_videos/README.md)
подробными учебными разборками.

Идея простая:

- видео показывает живой walkthrough в Selenium + Chromium;
- текстовый сценарий объясняет задачу, математику, exact ввод в чат и ожидаемые checkpoints;
- источником истины считаются детерминированные результаты OR-пайплайна и устойчивые UI-состояния;
- дословный текст OpenAI explanation в эти сценарии не включается, потому что он не обязан быть побайтно одинаковым.

Если вы только входите в проект, удобный порядок чтения такой:

1. [architecture_for_beginners_ru.md](../architecture_for_beginners_ru.md)
2. [chat_usage_for_beginners_ru.md](../chat_usage_for_beginners_ru.md)
3. [chat_input_language_for_beginners_ru.md](../chat_input_language_for_beginners_ru.md)
4. один из сценариев ниже

## Набор сценариев

| Видео | Текстовый разбор | Чему учит |
| --- | --- | --- |
| [preset_overview.mp4](../assets/selenium_videos/preset_overview.mp4) | [preset_overview_ru.md](preset_overview_ru.md) | Как читать готовый preset, смотреть `show input` и связывать draft с 4 OR-этапами |
| [manual_json_flow.mp4](../assets/selenium_videos/manual_json_flow.mp4) | [manual_json_flow_ru.md](manual_json_flow_ru.md) | Как полностью пройти цепочку через строгий DSL: `json`, `set`, `show input`, `run` |
| [nl_confirm_flow.mp4](../assets/selenium_videos/nl_confirm_flow.mp4) | [nl_confirm_flow_ru.md](nl_confirm_flow_ru.md) | Как работает natural-language ввод, `candidate patches` и подтверждение `да` |
| [validation_recovery_flow.mp4](../assets/selenium_videos/validation_recovery_flow.mp4) | [validation_recovery_flow_ru.md](validation_recovery_flow_ru.md) | Как выглядят partial JSON, malformed JSON и восстановление после ошибки |
| [ambiguity_resolution_flow.mp4](../assets/selenium_videos/ambiguity_resolution_flow.mp4) | [ambiguity_resolution_flow_ru.md](ambiguity_resolution_flow_ru.md) | Как система обрабатывает многозначный ввод, уточнение stage и последующее подтверждение |

## Как пользоваться этими разборами

Во всех пяти документах структура одинаковая:

- что это за видео и чему оно учит;
- постановка прикладной задачи;
- данные по каждому stage;
- математика `LP -> Min-Cost Flow -> Assignment -> CVRP`;
- конкретные арифметические проверки;
- exact сообщения, которые надо вводить в чат;
- UI-checkpoints;
- ожидаемые детерминированные результаты;
- типичные ошибки и педагогический смысл сценария.

Если нужен полный reference по синтаксису `json`, `set`, raw JSON shortcut,
подтверждениям `да/нет` и степени строгости языка ввода, смотрите
[chat_input_language_for_beginners_ru.md](../chat_input_language_for_beginners_ru.md).

