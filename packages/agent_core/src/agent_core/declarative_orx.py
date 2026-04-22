"""Lark-based teaching DSL for declarative LP-oriented extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import Any, Literal, cast

from lark import Lark, Token, Transformer
from scipy.optimize import linprog


class DeclarativeModelError(ValueError):
    """Raised when an ORX model cannot be parsed, validated, or solved."""


@dataclass(frozen=True, slots=True)
class IteratorBinding:
    """One loop variable bound to one declared set."""

    name: str
    set_name: str


class Expr:
    """Marker base class for ORX expressions."""


@dataclass(frozen=True, slots=True)
class NumberExpr(Expr):
    value: float


@dataclass(frozen=True, slots=True)
class NameExpr(Expr):
    name: str


@dataclass(frozen=True, slots=True)
class IndexedExpr(Expr):
    name: str
    index_name: str


@dataclass(frozen=True, slots=True)
class UnaryExpr(Expr):
    op: Literal["-"]
    operand: Expr


@dataclass(frozen=True, slots=True)
class BinaryExpr(Expr):
    op: Literal["+", "-", "*", "/"]
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class SumExpr(Expr):
    iterator: IteratorBinding
    body: Expr


@dataclass(frozen=True, slots=True)
class SetDecl:
    name: str


@dataclass(frozen=True, slots=True)
class ParamDecl:
    name: str
    index_set: str | None = None
    expr: Expr | None = None


@dataclass(frozen=True, slots=True)
class VarDecl:
    name: str
    index_set: str | None = None
    lower: Expr | None = None
    upper: Expr | None = None


@dataclass(frozen=True, slots=True)
class ObjectiveDecl:
    sense: Literal["maximize", "minimize"]
    name: str
    expr: Expr


@dataclass(frozen=True, slots=True)
class ConstraintDecl:
    name: str
    iterator: IteratorBinding | None
    left: Expr
    relation: Literal["<=", ">=", "="]
    right: Expr


@dataclass(frozen=True, slots=True)
class ReportFieldDecl:
    name: str
    expr: Expr


@dataclass(frozen=True, slots=True)
class ScalarReportDecl:
    name: str
    expr: Expr


@dataclass(frozen=True, slots=True)
class TableReportDecl:
    name: str
    iterator: IteratorBinding
    fields: tuple[ReportFieldDecl, ...]


@dataclass(frozen=True, slots=True)
class ModelProgram:
    sets: tuple[SetDecl, ...] = ()
    params: tuple[ParamDecl, ...] = ()
    vars: tuple[VarDecl, ...] = ()
    objective: ObjectiveDecl | None = None
    constraints: tuple[ConstraintDecl, ...] = ()
    scalar_reports: tuple[ScalarReportDecl, ...] = ()
    table_reports: tuple[TableReportDecl, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledModel:
    """Validated symbolic IR for a declarative LP model."""

    sets: tuple[SetDecl, ...]
    params: tuple[ParamDecl, ...]
    vars: tuple[VarDecl, ...]
    objective: ObjectiveDecl
    constraints: tuple[ConstraintDecl, ...]
    scalar_reports: tuple[ScalarReportDecl, ...]
    table_reports: tuple[TableReportDecl, ...]
    set_names: frozenset[str]
    param_names: frozenset[str]
    var_names: frozenset[str]
    required_input_params: tuple[ParamDecl, ...]


@dataclass(frozen=True, slots=True)
class BoundModelInput:
    """Concrete set/parameter values resolved from one extension draft."""

    sets: dict[str, tuple[str, ...]]
    params: dict[str, float | dict[str, float]]


@dataclass(frozen=True, slots=True)
class SolverResult:
    """Deterministic solved state for one compiled LP instance."""

    objective_value: float
    solver_status: str
    variables: dict[tuple[str, str | None], float]
    result_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _AffineExpr:
    constant: float = 0.0
    coefficients: dict[tuple[str, str | None], float] = field(default_factory=dict)

    def add(self, other: "_AffineExpr") -> "_AffineExpr":
        coefficients = dict(self.coefficients)
        for key, value in other.coefficients.items():
            coefficients[key] = coefficients.get(key, 0.0) + value
            if isclose(coefficients[key], 0.0, abs_tol=1e-12):
                coefficients.pop(key)
        return _AffineExpr(constant=self.constant + other.constant, coefficients=coefficients)

    def sub(self, other: "_AffineExpr") -> "_AffineExpr":
        return self.add(other.scale(-1.0))

    def scale(self, factor: float) -> "_AffineExpr":
        if isclose(factor, 0.0, abs_tol=1e-12):
            return _AffineExpr()
        return _AffineExpr(
            constant=self.constant * factor,
            coefficients={key: value * factor for key, value in self.coefficients.items()},
        )

    @property
    def has_variables(self) -> bool:
        return bool(self.coefficients)


_GRAMMAR = r"""
start: statement*

statement: set_decl
         | param_decl
         | var_decl
         | objective_decl
         | constraint_decl
         | scalar_report_decl
         | table_report_decl

set_decl: "set" IDENT
param_decl: "param" IDENT vector_domain? ("=" expr)?
var_decl: "var" IDENT vector_domain? bound_clause?
vector_domain: "[" IDENT "]"
iterator: "[" IDENT "in" IDENT "]"
bound_clause: GE expr LE expr        -> lower_upper_bound
            | GE expr                -> lower_bound
            | LE expr                -> upper_bound
objective_decl: SENSE IDENT ":" expr
constraint_decl: "st" IDENT iterator? ":" expr relation expr
scalar_report_decl: "report" IDENT "=" expr
table_report_decl: "report" IDENT iterator ":" "{" report_field ("," report_field)* "}"
report_field: IDENT "=" expr

?expr: add_expr
?add_expr: add_expr "+" mul_expr   -> add
         | add_expr "-" mul_expr   -> sub
         | mul_expr
?mul_expr: mul_expr "*" unary_expr -> mul
         | mul_expr "/" unary_expr -> div
         | unary_expr
?unary_expr: "-" unary_expr        -> neg
           | sum_expr
?sum_expr: "sum" "(" IDENT "in" IDENT "," expr ")" -> sum_expr
         | atom
?atom: NUMBER                      -> number
     | IDENT "[" IDENT "]"       -> indexed_ref
     | IDENT                       -> name
     | "(" expr ")"

SENSE: "maximize" | "minimize"
LE: "<="
GE: ">="
EQ: "="
relation: LE | GE | EQ
IDENT: /[A-Za-z_][A-Za-z0-9_]*/
COMMENT: /#[^\n]*/

%import common.SIGNED_NUMBER -> NUMBER
%import common.WS
%ignore WS
%ignore COMMENT
"""


class _OrxTransformer(Transformer[Token, object]):
    def statement(self, items: list[object]) -> object:
        return items[0]

    def start(self, items: list[object]) -> ModelProgram:
        sets: list[SetDecl] = []
        params: list[ParamDecl] = []
        vars_: list[VarDecl] = []
        objective: ObjectiveDecl | None = None
        constraints: list[ConstraintDecl] = []
        scalar_reports: list[ScalarReportDecl] = []
        table_reports: list[TableReportDecl] = []
        for item in items:
            if isinstance(item, SetDecl):
                sets.append(item)
            elif isinstance(item, ParamDecl):
                params.append(item)
            elif isinstance(item, VarDecl):
                vars_.append(item)
            elif isinstance(item, ObjectiveDecl):
                if objective is not None:
                    raise DeclarativeModelError("ORX model must declare exactly one objective")
                objective = item
            elif isinstance(item, ConstraintDecl):
                constraints.append(item)
            elif isinstance(item, ScalarReportDecl):
                scalar_reports.append(item)
            elif isinstance(item, TableReportDecl):
                table_reports.append(item)
            else:  # pragma: no cover - defensive transformer guard
                raise DeclarativeModelError(f"Unsupported ORX statement node: {item!r}")
        return ModelProgram(
            sets=tuple(sets),
            params=tuple(params),
            vars=tuple(vars_),
            objective=objective,
            constraints=tuple(constraints),
            scalar_reports=tuple(scalar_reports),
            table_reports=tuple(table_reports),
        )

    def set_decl(self, items: list[object]) -> SetDecl:
        return SetDecl(name=str(items[0]))

    def vector_domain(self, items: list[object]) -> str:
        return str(items[0])

    def iterator(self, items: list[object]) -> IteratorBinding:
        return IteratorBinding(name=str(items[0]), set_name=str(items[1]))

    def param_decl(self, items: list[object]) -> ParamDecl:
        name = str(items[0])
        index_set: str | None = None
        expr: Expr | None = None
        for item in items[1:]:
            if isinstance(item, str):
                index_set = item
            elif isinstance(item, Expr):
                expr = item
        return ParamDecl(name=name, index_set=index_set, expr=expr)

    def lower_upper_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        if len(items) != 4:
            raise DeclarativeModelError("Unsupported lower/upper variable bound clause")
        return cast(Expr, items[1]), cast(Expr, items[3])

    def lower_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        if len(items) != 2:
            raise DeclarativeModelError("Unsupported lower-only variable bound clause")
        return cast(Expr, items[1]), None

    def upper_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        if len(items) != 2:
            raise DeclarativeModelError("Unsupported upper-only variable bound clause")
        return None, cast(Expr, items[1])

    def var_decl(self, items: list[object]) -> VarDecl:
        name = str(items[0])
        index_set: str | None = None
        lower: Expr | None = None
        upper: Expr | None = None
        for item in items[1:]:
            if isinstance(item, str):
                index_set = item
            elif isinstance(item, tuple):
                lower, upper = cast(tuple[Expr | None, Expr | None], item)
        return VarDecl(name=name, index_set=index_set, lower=lower, upper=upper)

    def relation(self, items: list[object]) -> str:
        return str(items[0])

    def objective_decl(self, items: list[object]) -> ObjectiveDecl:
        return ObjectiveDecl(
            sense=str(items[0]),
            name=str(items[1]),
            expr=cast(Expr, items[2]),
        )

    def constraint_decl(self, items: list[object]) -> ConstraintDecl:
        name = str(items[0])
        iterator: IteratorBinding | None = None
        expr_offset = 1
        if isinstance(items[1], IteratorBinding):
            iterator = cast(IteratorBinding, items[1])
            expr_offset = 2
        return ConstraintDecl(
            name=name,
            iterator=iterator,
            left=cast(Expr, items[expr_offset]),
            relation=cast(Literal["<=", ">=", "="], items[expr_offset + 1]),
            right=cast(Expr, items[expr_offset + 2]),
        )

    def scalar_report_decl(self, items: list[object]) -> ScalarReportDecl:
        return ScalarReportDecl(name=str(items[0]), expr=cast(Expr, items[1]))

    def report_field(self, items: list[object]) -> ReportFieldDecl:
        return ReportFieldDecl(name=str(items[0]), expr=cast(Expr, items[1]))

    def table_report_decl(self, items: list[object]) -> TableReportDecl:
        return TableReportDecl(
            name=str(items[0]),
            iterator=cast(IteratorBinding, items[1]),
            fields=tuple(cast(ReportFieldDecl, item) for item in items[2:]),
        )

    def add(self, items: list[object]) -> BinaryExpr:
        return BinaryExpr(op="+", left=cast(Expr, items[0]), right=cast(Expr, items[1]))

    def sub(self, items: list[object]) -> BinaryExpr:
        return BinaryExpr(op="-", left=cast(Expr, items[0]), right=cast(Expr, items[1]))

    def mul(self, items: list[object]) -> BinaryExpr:
        return BinaryExpr(op="*", left=cast(Expr, items[0]), right=cast(Expr, items[1]))

    def div(self, items: list[object]) -> BinaryExpr:
        return BinaryExpr(op="/", left=cast(Expr, items[0]), right=cast(Expr, items[1]))

    def neg(self, items: list[object]) -> UnaryExpr:
        return UnaryExpr(op="-", operand=cast(Expr, items[0]))

    def sum_expr(self, items: list[object]) -> SumExpr:
        return SumExpr(
            iterator=IteratorBinding(name=str(items[0]), set_name=str(items[1])),
            body=cast(Expr, items[2]),
        )

    def number(self, items: list[object]) -> NumberExpr:
        return NumberExpr(value=float(items[0]))

    def name(self, items: list[object]) -> NameExpr:
        return NameExpr(name=str(items[0]))

    def indexed_ref(self, items: list[object]) -> IndexedExpr:
        return IndexedExpr(name=str(items[0]), index_name=str(items[1]))


_PARSER = Lark(_GRAMMAR, parser="lalr", start="start")
_TRANSFORMER = _OrxTransformer()


def parse_orx_model(source: str) -> ModelProgram:
    """Parse one ORX model into a typed AST/IR candidate."""
    try:
        tree = _PARSER.parse(source)
        program = cast(ModelProgram, _TRANSFORMER.transform(tree))
    except DeclarativeModelError:
        raise
    except Exception as exc:  # pragma: no cover - parser library details are unstable
        raise DeclarativeModelError(f"Invalid ORX model: {exc}") from exc
    if program.objective is None:
        raise DeclarativeModelError("ORX model must declare exactly one objective")
    return program


def compile_orx_model(program: ModelProgram) -> CompiledModel:
    """Validate one parsed ORX model and return compiled symbolic IR."""
    seen_names: dict[str, str] = {}
    set_names: set[str] = set()
    param_names: set[str] = set()
    var_names: set[str] = set()

    def register(name: str, kind: str) -> None:
        existing = seen_names.get(name)
        if existing is not None:
            raise DeclarativeModelError(f"Duplicate ORX symbol `{name}` ({existing} vs {kind})")
        seen_names[name] = kind

    for declaration in program.sets:
        register(declaration.name, "set")
        set_names.add(declaration.name)

    for declaration in program.params:
        register(declaration.name, "param")
        param_names.add(declaration.name)
        if declaration.index_set is not None and declaration.index_set not in set_names:
            raise DeclarativeModelError(
                f"Param `{declaration.name}` references unknown set `{declaration.index_set}`"
            )
        if declaration.index_set is not None and declaration.expr is not None:
            raise DeclarativeModelError(
                f"Derived param `{declaration.name}` cannot be indexed in ORX v1"
            )

    for declaration in program.vars:
        register(declaration.name, "var")
        var_names.add(declaration.name)
        if declaration.index_set is not None and declaration.index_set not in set_names:
            raise DeclarativeModelError(
                f"Var `{declaration.name}` references unknown set `{declaration.index_set}`"
            )

    objective = program.objective
    assert objective is not None

    symbol_sets = frozenset(set_names)
    symbol_params = frozenset(param_names)
    symbol_vars = frozenset(var_names)

    for param in program.params:
        if param.expr is not None:
            _validate_numeric_expr(
                expr=param.expr,
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                bound_indexes={},
                allow_vars=False,
                context=f"derived param `{param.name}`",
            )

    _validate_numeric_expr(
        expr=objective.expr,
        set_names=symbol_sets,
        param_names=symbol_params,
        var_names=symbol_vars,
        bound_indexes={},
        allow_vars=True,
        context=f"objective `{objective.name}`",
    )

    for constraint in program.constraints:
        bound_indexes = {}
        if constraint.iterator is not None:
            if constraint.iterator.set_name not in set_names:
                raise DeclarativeModelError(
                    f"Constraint `{constraint.name}` references unknown set "
                    f"`{constraint.iterator.set_name}`"
                )
            bound_indexes[constraint.iterator.name] = constraint.iterator.set_name
        _validate_numeric_expr(
            expr=constraint.left,
            set_names=symbol_sets,
            param_names=symbol_params,
            var_names=symbol_vars,
            bound_indexes=bound_indexes,
            allow_vars=True,
            context=f"constraint `{constraint.name}`",
        )
        _validate_numeric_expr(
            expr=constraint.right,
            set_names=symbol_sets,
            param_names=symbol_params,
            var_names=symbol_vars,
            bound_indexes=bound_indexes,
            allow_vars=True,
            context=f"constraint `{constraint.name}`",
        )

    for declaration in program.vars:
        bound_indexes = {}
        if declaration.index_set is not None:
            bound_indexes = {"_index": declaration.index_set}
        if declaration.lower is not None:
            _validate_numeric_expr(
                expr=_rewrite_var_bound_expr(declaration.lower),
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                bound_indexes=bound_indexes,
                allow_vars=False,
                context=f"lower bound of var `{declaration.name}`",
            )
        if declaration.upper is not None:
            _validate_numeric_expr(
                expr=_rewrite_var_bound_expr(declaration.upper),
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                bound_indexes=bound_indexes,
                allow_vars=False,
                context=f"upper bound of var `{declaration.name}`",
            )

    report_names: set[str] = set()
    for report in program.scalar_reports:
        if report.name in report_names:
            raise DeclarativeModelError(f"Duplicate report `{report.name}`")
        report_names.add(report.name)
        _validate_report_expr(
            expr=report.expr,
            set_names=symbol_sets,
            param_names=symbol_params,
            var_names=symbol_vars,
            bound_indexes={},
            context=f"report `{report.name}`",
        )

    for report in program.table_reports:
        if report.name in report_names:
            raise DeclarativeModelError(f"Duplicate report `{report.name}`")
        report_names.add(report.name)
        if report.iterator.set_name not in set_names:
            raise DeclarativeModelError(
                f"Table report `{report.name}` references unknown set `{report.iterator.set_name}`"
            )
        if not report.fields:
            raise DeclarativeModelError(
                f"Table report `{report.name}` must declare at least one field"
            )
        row_field_names: set[str] = set()
        bound_indexes = {report.iterator.name: report.iterator.set_name}
        for report_field in report.fields:
            if report_field.name in row_field_names:
                raise DeclarativeModelError(
                    f"Table report `{report.name}` contains duplicate field "
                    f"`{report_field.name}`"
                )
            row_field_names.add(report_field.name)
            _validate_report_expr(
                expr=report_field.expr,
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                bound_indexes=bound_indexes,
                context=f"report `{report.name}` field `{report_field.name}`",
            )

    required_input_params = tuple(
        param for param in program.params if param.expr is None
    )
    return CompiledModel(
        sets=program.sets,
        params=program.params,
        vars=program.vars,
        objective=objective,
        constraints=program.constraints,
        scalar_reports=program.scalar_reports,
        table_reports=program.table_reports,
        set_names=symbol_sets,
        param_names=symbol_params,
        var_names=symbol_vars,
        required_input_params=required_input_params,
    )


def solve_compiled_model(model: CompiledModel, bound_input: BoundModelInput) -> SolverResult:
    """Compile one bound symbolic model into LP matrices and solve it with SciPy."""
    _validate_bound_input(model=model, bound_input=bound_input)
    param_values = _resolve_param_values(model=model, bound_input=bound_input)
    variable_order = _build_variable_order(model=model, bound_input=bound_input)
    variable_index = {key: idx for idx, key in enumerate(variable_order)}

    bounds: list[tuple[float | None, float | None]] = []
    for key in variable_order:
        name, element = key
        declaration = next(item for item in model.vars if item.name == name)
        env = {"_index": element} if element is not None else {}
        lower = (
            _evaluate_numeric_expr(
                _rewrite_var_bound_expr(declaration.lower),
                bound_input=bound_input,
                param_values=param_values,
                variables=None,
                env=env,
            )
            if declaration.lower is not None
            else None
        )
        upper = (
            _evaluate_numeric_expr(
                _rewrite_var_bound_expr(declaration.upper),
                bound_input=bound_input,
                param_values=param_values,
                variables=None,
                env=env,
            )
            if declaration.upper is not None
            else None
        )
        bounds.append((lower, upper))

    objective_affine = _compile_affine_expr(
        expr=model.objective.expr,
        bound_input=bound_input,
        param_values=param_values,
        variable_index=variable_index,
        env={},
    )
    objective_offset = objective_affine.constant
    c = [0.0 for _ in variable_order]
    for key, coefficient in objective_affine.coefficients.items():
        c[variable_index[key]] = coefficient
    if model.objective.sense == "maximize":
        c = [-value for value in c]

    a_ub: list[list[float]] = []
    b_ub: list[float] = []
    a_eq: list[list[float]] = []
    b_eq: list[float] = []

    for declaration in model.constraints:
        envs = [{}]
        if declaration.iterator is not None:
            envs = [
                {declaration.iterator.name: element}
                for element in bound_input.sets[declaration.iterator.set_name]
            ]
        for env in envs:
            left = _compile_affine_expr(
                expr=declaration.left,
                bound_input=bound_input,
                param_values=param_values,
                variable_index=variable_index,
                env=env,
            )
            right = _compile_affine_expr(
                expr=declaration.right,
                bound_input=bound_input,
                param_values=param_values,
                variable_index=variable_index,
                env=env,
            )
            diff = left.sub(right)
            row = [0.0 for _ in variable_order]
            for key, coefficient in diff.coefficients.items():
                row[variable_index[key]] = coefficient
            if declaration.relation == "<=":
                a_ub.append(row)
                b_ub.append(-diff.constant)
            elif declaration.relation == ">=":
                a_ub.append([-value for value in row])
                b_ub.append(diff.constant)
            else:
                a_eq.append(row)
                b_eq.append(-diff.constant)

    result = linprog(
        c=c,
        A_ub=a_ub or None,
        b_ub=b_ub or None,
        A_eq=a_eq or None,
        b_eq=b_eq or None,
        bounds=bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        detail = result.message or "unknown LP solver failure"
        raise DeclarativeModelError(f"Declarative LP solve failed: {detail}")

    variables = {
        key: _clean_number(float(value))
        for key, value in zip(variable_order, result.x, strict=True)
    }
    objective_value = float(result.fun)
    if model.objective.sense == "maximize":
        objective_value = -objective_value
    objective_value += objective_offset

    result_payload: dict[str, Any] = {
        "objective_value": _clean_number(objective_value),
        "solver_status": result.message or "ok",
    }
    for report in model.scalar_reports:
        result_payload[report.name] = _clean_value(
            _evaluate_report_expr(
                expr=report.expr,
                bound_input=bound_input,
                param_values=param_values,
                variables=variables,
                env={},
            )
        )
    for report in model.table_reports:
        rows: list[dict[str, Any]] = []
        for element in bound_input.sets[report.iterator.set_name]:
            env = {report.iterator.name: element}
            row: dict[str, Any] = {}
            for report_field in report.fields:
                row[report_field.name] = _clean_value(
                    _evaluate_report_expr(
                        expr=report_field.expr,
                        bound_input=bound_input,
                        param_values=param_values,
                        variables=variables,
                        env=env,
                    )
                )
            rows.append(row)
        result_payload[report.name] = rows

    return SolverResult(
        objective_value=_clean_number(objective_value),
        solver_status=result.message or "ok",
        variables=variables,
        result_payload=result_payload,
    )


def _validate_bound_input(*, model: CompiledModel, bound_input: BoundModelInput) -> None:
    missing_sets = sorted(model.set_names - bound_input.sets.keys())
    if missing_sets:
        raise DeclarativeModelError(
            f"Bound input is missing declared sets: {', '.join(missing_sets)}"
        )
    for set_name, values in bound_input.sets.items():
        if set_name not in model.set_names:
            raise DeclarativeModelError(f"Bound input contains unknown set `{set_name}`")
        if not values:
            raise DeclarativeModelError(f"Set `{set_name}` must not be empty")
        if len(set(values)) != len(values):
            raise DeclarativeModelError(f"Set `{set_name}` contains duplicate keys")
    missing_params = [
        param.name
        for param in model.required_input_params
        if param.name not in bound_input.params
    ]
    if missing_params:
        raise DeclarativeModelError(
            f"Bound input is missing declared params: {', '.join(sorted(missing_params))}"
        )


def _resolve_param_values(
    *, model: CompiledModel, bound_input: BoundModelInput
) -> dict[str, float | dict[str, float]]:
    resolved: dict[str, float | dict[str, float]] = {}
    for declaration in model.params:
        if declaration.expr is None:
            value = bound_input.params[declaration.name]
            if declaration.index_set is None:
                if not isinstance(value, (int, float)):
                    raise DeclarativeModelError(
                        f"Param `{declaration.name}` must resolve to one number"
                    )
                resolved[declaration.name] = float(value)
            else:
                if not isinstance(value, dict):
                    raise DeclarativeModelError(
                        f"Param `{declaration.name}` must resolve to a keyed vector"
                    )
                expected_keys = bound_input.sets[declaration.index_set]
                if tuple(value.keys()) != expected_keys:
                    raise DeclarativeModelError(
                        f"Param `{declaration.name}` keys must match set "
                        f"`{declaration.index_set}` order"
                    )
                resolved[declaration.name] = {
                    key: float(item) for key, item in value.items()
                }
            continue

        resolved[declaration.name] = _evaluate_numeric_expr(
            declaration.expr,
            bound_input=bound_input,
            param_values=resolved,
            variables=None,
            env={},
        )
    return resolved


def _build_variable_order(
    *, model: CompiledModel, bound_input: BoundModelInput
) -> list[tuple[str, str | None]]:
    order: list[tuple[str, str | None]] = []
    for declaration in model.vars:
        if declaration.index_set is None:
            order.append((declaration.name, None))
            continue
        order.extend(
            (declaration.name, element)
            for element in bound_input.sets[declaration.index_set]
        )
    return order


def _validate_numeric_expr(
    *,
    expr: Expr,
    set_names: frozenset[str],
    param_names: frozenset[str],
    var_names: frozenset[str],
    bound_indexes: dict[str, str],
    allow_vars: bool,
    context: str,
) -> bool:
    if isinstance(expr, NumberExpr):
        return False
    if isinstance(expr, NameExpr):
        if expr.name in bound_indexes:
            raise DeclarativeModelError(
                f"{context} uses index `{expr.name}` as a scalar number; use it only as a row label"
            )
        if expr.name in set_names:
            raise DeclarativeModelError(f"{context} references set `{expr.name}` as a scalar value")
        if expr.name in param_names:
            return False
        if expr.name in var_names:
            if not allow_vars:
                raise DeclarativeModelError(
                    f"{context} cannot reference decision var `{expr.name}`"
                )
            return True
        raise DeclarativeModelError(f"{context} references unknown symbol `{expr.name}`")
    if isinstance(expr, IndexedExpr):
        if expr.index_name not in bound_indexes:
            raise DeclarativeModelError(
                f"{context} uses unknown index `{expr.index_name}` for `{expr.name}`"
            )
        if expr.name in param_names:
            return False
        if expr.name in var_names:
            if not allow_vars:
                raise DeclarativeModelError(
                    f"{context} cannot reference decision var `{expr.name}`"
                )
            return True
        raise DeclarativeModelError(f"{context} references unknown indexed symbol `{expr.name}`")
    if isinstance(expr, UnaryExpr):
        return _validate_numeric_expr(
            expr=expr.operand,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            bound_indexes=bound_indexes,
            allow_vars=allow_vars,
            context=context,
        )
    if isinstance(expr, SumExpr):
        if expr.iterator.set_name not in set_names:
            raise DeclarativeModelError(
                f"{context} sums over unknown set `{expr.iterator.set_name}`"
            )
        nested_indexes = dict(bound_indexes)
        nested_indexes[expr.iterator.name] = expr.iterator.set_name
        return _validate_numeric_expr(
            expr=expr.body,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            bound_indexes=nested_indexes,
            allow_vars=allow_vars,
            context=context,
        )
    if isinstance(expr, BinaryExpr):
        left_has_vars = _validate_numeric_expr(
            expr=expr.left,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            bound_indexes=bound_indexes,
            allow_vars=allow_vars,
            context=context,
        )
        right_has_vars = _validate_numeric_expr(
            expr=expr.right,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            bound_indexes=bound_indexes,
            allow_vars=allow_vars,
            context=context,
        )
        if expr.op in {"+", "-"}:
            return left_has_vars or right_has_vars
        if expr.op == "*":
            if left_has_vars and right_has_vars:
                raise DeclarativeModelError(
                    f"{context} contains a nonlinear product of two variable-bearing terms"
                )
            return left_has_vars or right_has_vars
        if expr.op == "/":
            if right_has_vars:
                raise DeclarativeModelError(
                    f"{context} divides by a variable-bearing expression, which is nonlinear"
                )
            return left_has_vars
        raise DeclarativeModelError(f"Unsupported numeric operator `{expr.op}` in {context}")
    raise DeclarativeModelError(f"Unsupported ORX expression in {context}: {expr!r}")


def _validate_report_expr(
    *,
    expr: Expr,
    set_names: frozenset[str],
    param_names: frozenset[str],
    var_names: frozenset[str],
    bound_indexes: dict[str, str],
    context: str,
) -> None:
    if isinstance(expr, NameExpr) and expr.name in bound_indexes:
        return
    _validate_numeric_expr(
        expr=expr,
        set_names=set_names,
        param_names=param_names,
        var_names=var_names,
        bound_indexes=bound_indexes,
        allow_vars=True,
        context=context,
    )


def _rewrite_var_bound_expr(expr: Expr | None) -> Expr:
    if expr is None:
        return NumberExpr(0.0)
    return _replace_index_placeholder(expr)


def _replace_index_placeholder(expr: Expr) -> Expr:
    if isinstance(expr, IndexedExpr):
        return IndexedExpr(
            name=expr.name,
            index_name="_index" if expr.index_name == "_" else expr.index_name,
        )
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(op=expr.op, operand=_replace_index_placeholder(expr.operand))
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(
            op=expr.op,
            left=_replace_index_placeholder(expr.left),
            right=_replace_index_placeholder(expr.right),
        )
    if isinstance(expr, SumExpr):
        return SumExpr(
            iterator=expr.iterator,
            body=_replace_index_placeholder(expr.body),
        )
    return expr


def _compile_affine_expr(
    *,
    expr: Expr,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float]],
    variable_index: dict[tuple[str, str | None], int],
    env: dict[str, str],
) -> _AffineExpr:
    if isinstance(expr, NumberExpr):
        return _AffineExpr(constant=expr.value)
    if isinstance(expr, NameExpr):
        if expr.name in env:
            raise DeclarativeModelError(f"Loop index `{expr.name}` cannot be used as a number here")
        value = param_values.get(expr.name)
        if isinstance(value, dict):
            raise DeclarativeModelError(
                f"Vector symbol `{expr.name}` requires an explicit index"
            )
        if value is None:
            return _AffineExpr(coefficients={(expr.name, None): 1.0})
        return _AffineExpr(constant=float(value))
    if isinstance(expr, IndexedExpr):
        element = env.get(expr.index_name)
        if element is None:
            raise DeclarativeModelError(
                f"Unknown loop index `{expr.index_name}` while compiling `{expr.name}`"
            )
        value = param_values.get(expr.name)
        if isinstance(value, dict):
            return _AffineExpr(constant=float(value[element]))
        return _AffineExpr(coefficients={(expr.name, element): 1.0})
    if isinstance(expr, UnaryExpr):
        return _compile_affine_expr(
            expr=expr.operand,
            bound_input=bound_input,
            param_values=param_values,
            variable_index=variable_index,
            env=env,
        ).scale(-1.0)
    if isinstance(expr, BinaryExpr):
        left = _compile_affine_expr(
            expr=expr.left,
            bound_input=bound_input,
            param_values=param_values,
            variable_index=variable_index,
            env=env,
        )
        right = _compile_affine_expr(
            expr=expr.right,
            bound_input=bound_input,
            param_values=param_values,
            variable_index=variable_index,
            env=env,
        )
        if expr.op == "+":
            return left.add(right)
        if expr.op == "-":
            return left.sub(right)
        if expr.op == "*":
            if left.has_variables and right.has_variables:
                raise DeclarativeModelError("Nonlinear product reached numeric compiler")
            if left.has_variables:
                return left.scale(right.constant)
            if right.has_variables:
                return right.scale(left.constant)
            return _AffineExpr(constant=left.constant * right.constant)
        if expr.op == "/":
            if right.has_variables:
                raise DeclarativeModelError("Nonlinear division reached numeric compiler")
            if isclose(right.constant, 0.0, abs_tol=1e-12):
                raise DeclarativeModelError("Division by zero in ORX expression")
            return left.scale(1.0 / right.constant)
        raise DeclarativeModelError(f"Unsupported binary operator `{expr.op}`")
    if isinstance(expr, SumExpr):
        total = _AffineExpr()
        for element in bound_input.sets[expr.iterator.set_name]:
            nested_env = dict(env)
            nested_env[expr.iterator.name] = element
            total = total.add(
                _compile_affine_expr(
                    expr=expr.body,
                    bound_input=bound_input,
                    param_values=param_values,
                    variable_index=variable_index,
                    env=nested_env,
                )
            )
        return total
    raise DeclarativeModelError(f"Unsupported affine expression: {expr!r}")


def _evaluate_numeric_expr(
    expr: Expr,
    *,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float]],
    variables: dict[tuple[str, str | None], float] | None,
    env: dict[str, str],
) -> float:
    value = _evaluate_report_expr(
        expr=expr,
        bound_input=bound_input,
        param_values=param_values,
        variables=variables,
        env=env,
    )
    if not isinstance(value, (int, float)):
        raise DeclarativeModelError(f"Expected numeric ORX expression, got {value!r}")
    return float(value)


def _evaluate_report_expr(
    *,
    expr: Expr,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float]],
    variables: dict[tuple[str, str | None], float] | None,
    env: dict[str, str],
) -> Any:
    if isinstance(expr, NumberExpr):
        return expr.value
    if isinstance(expr, NameExpr):
        if expr.name in env:
            return env[expr.name]
        value = param_values.get(expr.name)
        if value is not None:
            if isinstance(value, dict):
                raise DeclarativeModelError(
                    f"Vector symbol `{expr.name}` requires an explicit index"
                )
            return float(value)
        if variables is None:
            raise DeclarativeModelError(f"Unknown ORX symbol `{expr.name}` during evaluation")
        variable_value = variables.get((expr.name, None))
        if variable_value is None:
            raise DeclarativeModelError(f"Unknown decision var `{expr.name}` during evaluation")
        return float(variable_value)
    if isinstance(expr, IndexedExpr):
        element = env.get(expr.index_name)
        if element is None:
            raise DeclarativeModelError(
                f"Unknown loop index `{expr.index_name}` while evaluating `{expr.name}`"
            )
        value = param_values.get(expr.name)
        if isinstance(value, dict):
            return float(value[element])
        if variables is None:
            raise DeclarativeModelError(
                f"Unknown ORX indexed symbol `{expr.name}` during evaluation"
            )
        variable_value = variables.get((expr.name, element))
        if variable_value is None:
            raise DeclarativeModelError(
                f"Unknown indexed decision var `{expr.name}[{element}]` during evaluation"
            )
        return float(variable_value)
    if isinstance(expr, UnaryExpr):
        return -float(
            _evaluate_numeric_expr(
                expr.operand,
                bound_input=bound_input,
                param_values=param_values,
                variables=variables,
                env=env,
            )
        )
    if isinstance(expr, BinaryExpr):
        left = _evaluate_report_expr(
            expr=expr.left,
            bound_input=bound_input,
            param_values=param_values,
            variables=variables,
            env=env,
        )
        right = _evaluate_report_expr(
            expr=expr.right,
            bound_input=bound_input,
            param_values=param_values,
            variables=variables,
            env=env,
        )
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise DeclarativeModelError(
                f"Binary operator `{expr.op}` requires numeric operands, got {left!r} and {right!r}"
            )
        left_number = float(left)
        right_number = float(right)
        if expr.op == "+":
            return left_number + right_number
        if expr.op == "-":
            return left_number - right_number
        if expr.op == "*":
            return left_number * right_number
        if expr.op == "/":
            if isclose(right_number, 0.0, abs_tol=1e-12):
                raise DeclarativeModelError("Division by zero in ORX report expression")
            return left_number / right_number
        raise DeclarativeModelError(f"Unsupported report operator `{expr.op}`")
    if isinstance(expr, SumExpr):
        total = 0.0
        for element in bound_input.sets[expr.iterator.set_name]:
            nested_env = dict(env)
            nested_env[expr.iterator.name] = element
            total += float(
                _evaluate_numeric_expr(
                    expr.body,
                    bound_input=bound_input,
                    param_values=param_values,
                    variables=variables,
                    env=nested_env,
                )
            )
        return total
    raise DeclarativeModelError(f"Unsupported report expression: {expr!r}")


def _clean_number(value: float, *, digits: int = 4) -> float:
    rounded = round(float(value), digits)
    if isclose(rounded, 0.0, abs_tol=10 ** (-(digits + 1))):
        return 0.0
    return float(rounded)


def _clean_value(value: Any) -> Any:
    if isinstance(value, float):
        return _clean_number(value)
    return value
