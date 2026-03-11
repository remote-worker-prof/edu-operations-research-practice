# Backlog по итогам Code Review v1

## Связка findings -> beads issues

| Finding | Priority | beads issue | Title |
|---|---|---|---|
| F01 | P1 | `eorp-z0l` | Защитить extractor от ValueError при нечисловых значениях LLM |
| F02 | P2 | `eorp-wiu` | Декомпозировать dialog_graph на отдельные узлы и типизированный интерфейс |
| F03 | P2 | `eorp-4q2` | Убрать дублирование model_aliases и связать UI с MODEL_ALIASES |
| F04 | P2 | `eorp-23o` | Сделать UI более учебным: понятные названия полей и моделей |
| F05 | P2 | `eorp-992` | Расширить интеграционные тесты на ошибочные и деградированные сценарии |
| F06 | P2 | `eorp-8e7` | Расширить docs/architecture: контракты, sequence и dataflow для студентов |
| F07 | P2 | `eorp-gr5` | Добавить русскоязычную кодовую документацию по ключевым модулям |
| F08 | P3 | `eorp-pdk` | Привести форматирование к зелёному состоянию для make check-all |

## Порядок реализации (рекомендуемый)

1. `eorp-z0l`
2. `eorp-4q2`
3. `eorp-23o`
4. `eorp-pdk`
5. `eorp-992`
6. `eorp-wiu`
7. `eorp-8e7`
8. `eorp-gr5`
