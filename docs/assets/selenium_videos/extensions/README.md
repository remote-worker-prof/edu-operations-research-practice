# Selenium Extension Demo Videos

Этот каталог содержит короткий deterministic mini-pack MP4-роликов про platform
slice с extensions и переключением между ними в UI.

В отличие от OpenAI demo-pack'ов, эти ролики не требуют внешнего провайдера:
они показывают selector extensions, policy `reset -> switch`, sample extension
`study_planner` и возврат к built-in `default_or`.

Важно: в selector модели в этих роликах используется `openai_default`, то есть
облачный OpenAI. При этом сам `study_planner` остаётся детерминированным extension,
поэтому в части роликов облачный провайдер просто выбран в UI для единообразия,
а в сценарии возврата к `default_or` он уже участвует и в полном OR-flow.

## Сценарии

- `extensions_selector_overview.mp4`
  Короткий обзор selector'а и переключения на `study_planner`.
- `switch_to_sample_and_run.mp4`
  Полный deterministic walkthrough sample extension `study_planner`.
- `blocked_switch_until_reset.mp4`
  Демонстрация policy: непустую сессию нельзя переключить без `reset`.
- `switch_back_to_default_or.mp4`
  Возврат с `study_planner` на `default_or`, затем `load preset demo` и `run`.

## Что важно заметить

- extension выбирается **на сессию**;
- selector меняет `extension_alias`, но сам по себе не запускает ход диалога;
- если сессия непустая, UI/API сохраняют старый extension и просят сначала `reset`;
- `study_planner` использует тот же общий command-DSL (`start`, `edit`, `json`, `set`, `run`),
  но со своими stage-ами: `courses`, `time_budget`, `priorities`.
