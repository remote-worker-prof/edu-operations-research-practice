# Code Review v1: учебный OR-AI проект

Дата: 2026-03-11  
Репозиторий: `edu-operations-research-practice`  
Ревизия: `main` (рабочее дерево на момент ревью)

## 1) Scope и методика

### Scope
- `apps/webapp`
- `packages/agent_core`
- `packages/or_core`
- `tests`
- `docs`

### Критерии и веса
- `C1` Понятность архитектуры/кода для студентов: `40`
- `C2` Корректность и лаконичность практик стека: `35`
- `C3` Русскоязычная учебная кодовая документация: `25`

Шкала подпунктов: `0..5`.  
Формула итогового балла: `sum(weight * criterion_score / 5)`.

### Базовый quality baseline
- `make check`: `ruff check` + `pytest` проходят (`11 passed`).
- `make check-all`: падает на `ruff format --check` (`4 files would be reformatted`).

## 2) Scorecard

### C1. Понятность для студентов (вес 40)

| Subcriterion | Score (0..5) | Evidence | Notes |
|---|---:|---|---|
| Слойность и границы ответственности | 4.5 | `docs/architecture.md:3-19`, `packages/or_core/src/or_core/pipeline.py:110-151` | Разделение `webapp/agent_core/or_core` выдержано.
| Прозрачность диалогового flow | 3.0 | `packages/agent_core/src/agent_core/dialog_graph.py:41-201` | Логика читаема, но перегружена вложенными функциями.
| Учебная читаемость UI | 3.0 | `apps/webapp/src/webapp/templates/_workspace.html:12-14,85-88` | Видны внутренние идентификаторы, не учебные названия.
| Простота старта и запуска | 4.0 | `README.md:24-50`, `Makefile` | Быстрый старт и команды понятны.

Итог C1: `3.63/5` -> `29.0/40`.

### C2. Современные практики стека (вес 35)

| Subcriterion | Score (0..5) | Evidence | Notes |
|---|---:|---|---|
| Типизированные контракты и валидация | 4.5 | `packages/or_core/src/or_core/models.py:10-230`, `packages/agent_core/src/agent_core/models.py` | Хорошая дисциплина Pydantic-моделей.
| Консистентность конфигурации | 3.0 | `apps/webapp/src/webapp/main.py:30,52`, `packages/agent_core/src/agent_core/config.py` | `model_aliases` дублируются в роутерах.
| Устойчивость обработки ошибок | 2.5 | `packages/agent_core/src/agent_core/extractor.py:138-142` | Возможен `ValueError` при нечисловом значении от LLM.
| Тестопригодность и quality gates | 3.5 | `tests/integration/test_api.py:9-57`, `tests/integration/test_dialog_graph.py:4-19` | Happy-path покрыт, но мало негативных сценариев.

Итог C2: `3.38/5` -> `23.6/35`.

### C3. Русская учебная документация (вес 25)

| Subcriterion | Score (0..5) | Evidence | Notes |
|---|---:|---|---|
| Архитектурная документация для обучения | 2.5 | `docs/architecture.md:1-24` | Документ краткий, без детального dataflow/контрактов.
| Документация запуска dev/docker | 4.0 | `docs/dev_build_run.md:1-126` | Практично и достаточно подробно.
| Русскоязычность пояснений в коде | 1.5 | `packages/or_core/src/or_core/pipeline.py:1`, `packages/agent_core/src/agent_core/dialog_graph.py:1` | Docstring в основном англоязычные.
| Пошаговый student walkthrough «концепт -> код -> результат» | 1.5 | отсутствует отдельный документ | Нет целевого учебного code walkthrough.

Итог C3: `2.38/5` -> `11.9/25`.

### Итоговый балл

`29.0 + 23.6 + 11.9 = 64.5/100` (округлённо `65/100`).

## 3) Findings (только с evidence)

Легенда severity: `S0` критично, `S1` высоко, `S2` средне, `S3` низко.

### F01
- `id`: `F01`
- `criterion`: `C2`
- `severity`: `S1`
- `title`: Необработанный `ValueError` в extractor при нечисловом ответе LLM
- `evidence`: `packages/agent_core/src/agent_core/extractor.py:138-142`
- `impact`: один некорректный JSON-параметр от провайдера может сорвать обработку хода.
- `recommendation`: безопасный parse с проверкой типа/диапазона без прямого `float(value)` в error-ветке.
- `effort`: `S`
- `backlog`: `eorp-z0l`

### F02
- `id`: `F02`
- `criterion`: `C1`
- `severity`: `S2`
- `title`: `build_dialog_graph` перегружен вложенными функциями
- `evidence`: `packages/agent_core/src/agent_core/dialog_graph.py:41-201`
- `impact`: студентам сложнее читать и ментально разделять ответственность узлов.
- `recommendation`: декомпозировать узлы графа в отдельные функции/модули.
- `effort`: `M`
- `backlog`: `eorp-wiu`

### F03
- `id`: `F03`
- `criterion`: `C2`
- `severity`: `S2`
- `title`: Дублирование `model_aliases` в web-слое
- `evidence`: `apps/webapp/src/webapp/main.py:30,52`, `packages/agent_core/src/agent_core/config.py`
- `impact`: риск расхождения UI/конфига, лишняя точка сопровождения.
- `recommendation`: единый источник alias в конфиге/сервисе.
- `effort`: `S`
- `backlog`: `eorp-4q2`

### F04
- `id`: `F04`
- `criterion`: `C1`
- `severity`: `S2`
- `title`: UI показывает внутренние поля и технические alias
- `evidence`: `apps/webapp/src/webapp/templates/_workspace.html:12-14,85-88`
- `impact`: ухудшается учебная воспринимаемость и UX для студентов.
- `recommendation`: ввести русские человеко-понятные лейблы/подсказки.
- `effort`: `S`
- `backlog`: `eorp-23o`

### F05
- `id`: `F05`
- `criterion`: `C2`
- `severity`: `S2`
- `title`: Недостаточное покрытие негативных/деградированных сценариев
- `evidence`: `tests/integration/test_api.py:9-57`, `tests/integration/test_dialog_graph.py:4-19`
- `impact`: регрессии в error/fallback-путях могут проходить незамеченными.
- `recommendation`: добавить интеграционные тесты на invalid extraction, OR errors, fallback.
- `effort`: `M`
- `backlog`: `eorp-992`

### F06
- `id`: `F06`
- `criterion`: `C3`
- `severity`: `S2`
- `title`: `docs/architecture.md` слишком краткий для учебной цели
- `evidence`: `docs/architecture.md:1-24`
- `impact`: студентам не хватает пошаговой причинно-следственной схемы.
- `recommendation`: расширить документ контрактами и sequence-описанием.
- `effort`: `M`
- `backlog`: `eorp-8e7`

### F07
- `id`: `F07`
- `criterion`: `C3`
- `severity`: `S2`
- `title`: Недостаточно русскоязычной кодовой документации
- `evidence`: `packages/or_core/src/or_core/pipeline.py:1`, `packages/agent_core/src/agent_core/dialog_graph.py:1`
- `impact`: учебная аудитория не получает локализованных пояснений в коде.
- `recommendation`: добавить русские docstring/комментарии в ключевых точках.
- `effort`: `M`
- `backlog`: `eorp-gr5`

### F08
- `id`: `F08`
- `criterion`: `C2`
- `severity`: `S3`
- `title`: Строгий quality gate не проходит (`check-all`)
- `evidence`: команда `make check-all` -> `4 files would be reformatted`
- `impact`: неполная дисциплина по форматированию, шум в PR/CI.
- `recommendation`: выровнять формат и закрепить это в dev-flow.
- `effort`: `S`
- `backlog`: `eorp-pdk`

## 4) Сильные стороны, риски и приоритеты

### Сильные стороны
- Чёткая модульность монорепо и разделение слоёв (`webapp`, `agent_core`, `or_core`).
- Детерминированный OR-конвейер с `execution_trace` упрощает объяснимость.
- Валидируемые контракты Pydantic в доменной модели.
- Практичные команды для dev-цикла (`Makefile`, `docs/dev_build_run.md`).

### Ключевые риски
- Срыв обработки диалога из-за edge-case в extractor (`F01`).
- Сопровождаемость и учебная читаемость `DialogGraph` (`F02`).
- Документационный разрыв для русскоязычной учебной аудитории (`F06`, `F07`).

### Top-5 quick wins
1. Закрыть `F01` (`eorp-z0l`) — устранить runtime-риск в extractor.
2. Закрыть `F03` (`eorp-4q2`) — убрать дубли alias.
3. Закрыть `F04` (`eorp-23o`) — привести UI-термины к учебному виду.
4. Закрыть `F08` (`eorp-pdk`) — сделать `check-all` зелёным.
5. Добавить минимальные негативные интеграционные тесты (`F05`, `eorp-992`).

### Top-5 high-impact fixes
1. `eorp-z0l` (устойчивость extractor).
2. `eorp-wiu` (декомпозиция dialog graph).
3. `eorp-992` (покрытие error/fallback путей).
4. `eorp-8e7` (расширение архитектурной учебной документации).
5. `eorp-gr5` (русскоязычная кодовая документация).

## 5) Gate проверки плана review

1. Scorecard заполнен по C1/C2/C3: **да**.
2. Каждый finding имеет `criterion + evidence`: **да**.
3. Все `P1/P2` findings имеют backlog issue: **да** (`eorp-z0l`, `eorp-wiu`, `eorp-4q2`, `eorp-23o`, `eorp-992`, `eorp-8e7`, `eorp-gr5`).
4. Итоговый балл и баллы по C1/C2/C3 присутствуют: **да**.
5. Сквозной путь `chat -> extraction -> OR pipeline -> explanation` подтверждён кодом и интеграционными тестами (`packages/agent_core/src/agent_core/dialog_graph.py`, `tests/integration/test_api.py`): **да**.

## 6) Remediation governance (Agile graph)

На 2026-03-11 backlog из findings F01-F08 переведён в управляемый beads-граф.

- Umbrella epic: `eorp-t1p` (`CRv1 Remediation Program`, `in_progress`).
- Criterion epics: `eorp-3ux` (`C1`), `eorp-l7d` (`C2`), `eorp-f7k` (`C3`), все в `in_progress`.
- Work-issues типизированы по смыслу: `bug|feature|task|chore`.
- Общие labels для всех work-issues: `review:v1`, `track:remediation`, плюс `criterion:C*`, `finding:F*`, `severity:S*`.

Согласованный DAG блокеров:

1. `eorp-4q2` blocks `eorp-23o`.
2. `eorp-z0l` blocks `eorp-992`.
3. `eorp-wiu` blocks `eorp-992`, `eorp-8e7`, `eorp-gr5`.
4. `eorp-z0l`, `eorp-4q2`, `eorp-23o`, `eorp-wiu`, `eorp-992` block `eorp-pdk`.

Ожидаемые execution waves для `bd ready`:

1. Wave 1: `eorp-z0l`, `eorp-4q2`, `eorp-wiu`.
2. Wave 2: `eorp-23o`, `eorp-992`, `eorp-8e7`, `eorp-gr5`.
3. Wave 3: `eorp-pdk`.

Проверки governance:

- `bd dep cycles` -> циклов нет.
- `bd blocked` -> блокировки соответствуют DAG (включая `eorp-pdk`).
- `bd ready` -> только Wave 1 work-items.

## 7) Типы артефактов review

```text
ReviewFinding:
  id: str
  criterion: C1|C2|C3
  severity: S0|S1|S2|S3
  title: str
  evidence: str
  impact: str
  recommendation: str
  effort: S|M|L

ScorecardRow:
  criterion: C1|C2|C3
  subcriterion: str
  weight: int
  score_0_5: float
  weighted_score: float
  notes: str

BacklogItem:
  issue_id: str
  priority: P1|P2|P3
  title: str
  acceptance_criteria: str
  linked_findings: list[str]
```
