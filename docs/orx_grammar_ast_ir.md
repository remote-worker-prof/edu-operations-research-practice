# ORX pipeline: grammar -> AST -> solver IR

## Зачем нужен этот документ
Этот документ нужен, чтобы в проекте было явно видно:
- где лежит грамматика языка;
- где лежит метамодель;
- как текст превращается в solver-ready representation.

## Где лежат grammar-файлы
- `packages/agent_core/src/agent_core/grammars/command_surface.lark`
- `packages/agent_core/src/agent_core/grammars/orx_model_v1.lark`
- `packages/agent_core/src/agent_core/grammars/orx_model_v2.lark`

## Где лежит метамодель
- `packages/agent_core/src/agent_core/orx_metamodel.py`

Ключевые элементы метамодели:
- `SetDecl`
- `ParamDecl`
- `VarDecl`
- `ObjectiveDecl`
- `ConstraintDecl`
- `ScalarReportDecl`
- `TableReportDecl`
- `Expr`-иерархия

## Парсеры
### v1 compatibility path
- модуль: `agent_core.declarative_orx`
- роль: разбирать старый ORX surface syntax и преобразовывать его в shared metamodel

### v2 math-first path
- модуль: `agent_core.declarative_orx_v2`
- роль: разбирать новый AMPL/MathProg-like syntax и преобразовывать его в shared metamodel

## Дальнейшая трансформация
После parsing текст становится `ModelProgram`.
Затем:
1. выполняется статическая валидация объявлений и выражений;
2. строится `CompiledModel`;
3. bound input превращает символическую модель в конкретную LP-инстанцию;
4. из affine expressions собираются матрицы/векторы для solver-а;
5. solver (`scipy.optimize.linprog`) возвращает решение;
6. display-layer или reports превращают решение в user-facing payload.

## Почему это MOF-inspired discipline
Мы не реализуем полный OMG stack вроде XMI/QVT, но придерживаемся важной дисциплины:
- grammar и metamodel отделены;
- моделирующий язык описан явно;
- трансформации между уровнями задокументированы;
- AST / metamodel выступает стабильной промежуточной прослойкой.

## Что важно для дальнейшего развития
Если мы захотим расширять язык дальше, безопаснее делать это в таком порядке:
1. grammar change
2. metamodel change
3. compiler/solver change
4. tests
5. guides/examples/tutorial parity
