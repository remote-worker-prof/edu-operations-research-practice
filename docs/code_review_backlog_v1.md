# Backlog по итогам Code Review v1

Дата обновления графа: 2026-03-11

## Issue Graph (Epic hierarchy)

- Umbrella epic: `eorp-t1p` `CRv1 Remediation Program` (`epic`, `in_progress`).
- Criterion epics:
  - `eorp-3ux` `C1 Student Clarity` (`epic`, parent=`eorp-t1p`, `in_progress`).
  - `eorp-l7d` `C2 Engineering Quality` (`epic`, parent=`eorp-t1p`, `in_progress`).
  - `eorp-f7k` `C3 Russian Learning Docs` (`epic`, parent=`eorp-t1p`, `in_progress`).

Work-issues и их эпики:

- `eorp-z0l` (`bug`) -> parent `eorp-l7d`.
- `eorp-wiu` (`feature`) -> parent `eorp-3ux`.
- `eorp-4q2` (`chore`) -> parent `eorp-l7d`.
- `eorp-23o` (`feature`) -> parent `eorp-3ux`.
- `eorp-992` (`task`) -> parent `eorp-l7d`.
- `eorp-8e7` (`chore`) -> parent `eorp-f7k`.
- `eorp-gr5` (`chore`) -> parent `eorp-f7k`.
- `eorp-pdk` (`chore`) -> parent `eorp-l7d`.

Все work-issues помечены labels:
`review:v1`, `track:remediation`, `criterion:C*`, `finding:F*`, `severity:S*`.

## Связка findings -> issues (с типами и зависимостями)

| Finding | Priority | beads issue | Type | Epic | Blocked by | Blocks |
|---|---|---|---|---|---|---|
| F01 | P1 | `eorp-z0l` | `bug` | `eorp-l7d` | - | `eorp-992`, `eorp-pdk` |
| F02 | P2 | `eorp-wiu` | `feature` | `eorp-3ux` | - | `eorp-992`, `eorp-8e7`, `eorp-gr5`, `eorp-pdk` |
| F03 | P2 | `eorp-4q2` | `chore` | `eorp-l7d` | - | `eorp-23o`, `eorp-pdk` |
| F04 | P2 | `eorp-23o` | `feature` | `eorp-3ux` | `eorp-4q2` | `eorp-pdk` |
| F05 | P2 | `eorp-992` | `task` | `eorp-l7d` | `eorp-z0l`, `eorp-wiu` | `eorp-pdk` |
| F06 | P2 | `eorp-8e7` | `chore` | `eorp-f7k` | `eorp-wiu` | - |
| F07 | P2 | `eorp-gr5` | `chore` | `eorp-f7k` | `eorp-wiu` | - |
| F08 | P3 | `eorp-pdk` | `chore` | `eorp-l7d` | `eorp-z0l`, `eorp-4q2`, `eorp-23o`, `eorp-wiu`, `eorp-992` | - |

## Dependency Edges

Hard blockers (`blocked <- blocker`):

1. `eorp-23o <- eorp-4q2`
2. `eorp-992 <- eorp-z0l`
3. `eorp-992 <- eorp-wiu`
4. `eorp-8e7 <- eorp-wiu`
5. `eorp-gr5 <- eorp-wiu`
6. `eorp-pdk <- eorp-z0l`
7. `eorp-pdk <- eorp-4q2`
8. `eorp-pdk <- eorp-23o`
9. `eorp-pdk <- eorp-wiu`
10. `eorp-pdk <- eorp-992`

## Execution waves

1. Wave 1 (ready now): `eorp-z0l`, `eorp-4q2`, `eorp-wiu`.
2. Wave 2: `eorp-23o`, `eorp-992`, `eorp-8e7`, `eorp-gr5`.
3. Wave 3: `eorp-pdk`.

## Проверки графа

- `bd dep cycles` -> циклов нет.
- `bd blocked` -> блокировки соответствуют design DAG.
- `bd ready` -> только work-items Wave 1.
