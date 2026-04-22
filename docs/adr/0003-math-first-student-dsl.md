# ADR 0003: Math-first student DSL with external Lark grammars and explicit metamodel

## Status
Accepted

## Context
После первого декларативного этапа стало видно, что student-facing path всё ещё слишком опирается на UI-обвязку и внутренние runtime-детали. Главные проблемы были такими:
- математическая постановка смешивалась с display/report-логикой;
- grammar definitions были спрятаны внутри Python-кода;
- студенту было сложнее переносить LP-модель из учебника в проект, чем должно быть.

## Decision
Мы принимаем следующие решения:

1. Новый основной student-facing формат называется `student_math_v2`.
2. `model.orx` становится главным student-authored файлом и содержит только оптимизационную постановку.
3. `extension.yaml` становится маленьким sidecar-файлом с четырьмя разделами:
   - `extension`
   - `inputs`
   - `display`
   - `presets`
4. Основной стиль записи математики — AMPL/MathProg-like ASCII algebraic LP notation.
5. Грамматики выносятся в отдельные `.lark` файлы.
6. Между grammar и solver вводится explicit metamodel / AST layer.
7. `student_v1` и `expert_v1` сохраняются как compatibility paths.

## Consequences
### Плюсы
- `model.orx` становится ближе к каноничной LP-записи.
- DSL становится лучше объяснимым студентам и преподавателям.
- grammar files становятся first-class артефактами репозитория.
- появляется более чистый путь для дальнейших преобразований и расширений.

### Минусы
- появляется ещё один поддерживаемый формат в migration-период.
- loader и validator становятся сложнее.
- нужно поддерживать tutorial parity между compact и annotated материалами.

## Implementation notes
- `packages/agent_core/src/agent_core/grammars/` содержит внешние `.lark`-файлы.
- `agent_core.orx_metamodel` содержит explicit AST / metamodel.
- `agent_core.declarative_orx` удерживает v1 compatibility path.
- `agent_core.declarative_orx_v2` реализует новый math-first parser.

## Links
- `docs/research/current_orx_vs_ampl_mathprog_vs_minizinc.md`
- `docs/research/lark_vs_textx_vs_antlr.md`
- `docs/orx_grammar_ast_ir.md`
