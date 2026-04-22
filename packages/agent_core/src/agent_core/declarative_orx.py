"""Lark-based ORX v1 parser plus shared LP compiler/solver runtime.

This module keeps backward-compatible parsing for the original ORX surface syntax
while the compiler/solver operates on the explicit metamodel from
`agent_core.orx_metamodel`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from math import isclose
from typing import Any, Literal, cast

from lark import Lark, Token, Transformer, UnexpectedInput
from scipy.optimize import linprog

from agent_core.grammar_loader import load_grammar_text
from agent_core.orx_metamodel import (
    BinaryExpr,
    BoundModelInput,
    CompiledModel,
    ConstraintDecl,
    Expr,
    IndexDomain,
    IndexedExpr,
    IteratorBinding,
    ModelProgram,
    NameExpr,
    NumberExpr,
    ObjectiveDecl,
    ParamDecl,
    ReportFieldDecl,
    ScalarReportDecl,
    SetDecl,
    SolverResult,
    SumExpr,
    TableReportDecl,
    UnaryExpr,
    VarDecl,
    _AffineExpr,
)


class DeclarativeModelError(ValueError):
    """Raised when an ORX model cannot be parsed, validated, or solved."""


_IDENT_RE = r"[A-Za-z_][A-Za-z0-9_]*"
_COMMENT_ONLY_RE = re.compile(r"^\s*#")
_VAR_RANGE_RE = re.compile(
    rf"^(?P<indent>\s*)var\s+(?P<head>{_IDENT_RE}(?:\[{_IDENT_RE}\])?)\s+in\s+"
    r"(?P<lower>.+?)\s*\.\.\s*(?P<upper>.+?)\s*$"
)
_BLOCK_REPORT_RE = re.compile(
    rf"^(?P<indent>\s*)report\s+(?P<name>{_IDENT_RE})\s+by\s+"
    rf"(?P<iterator>{_IDENT_RE})\s+in\s+(?P<set_name>{_IDENT_RE})\s*:\s*$"
)
_REPORT_FIELD_RE = re.compile(rf"^\s*(?P<field>{_IDENT_RE})\s*=\s*(?P<expr>.+?)\s*$")


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _strip_inline_comment(line: str) -> str:
    if "#" not in line:
        return line.rstrip()
    return line.split("#", maxsplit=1)[0].rstrip()


def _normalize_bound_sugar_expr(expr: str, *, index_set: str | None) -> str:
    if index_set is None:
        return expr.strip()
    return expr.replace(f"[{index_set}]", "[_0]").strip()


@dataclass(frozen=True, slots=True)
class _BlockRewriteResult:
    rewritten_lines: tuple[str, ...]
    next_index: int


def _rewrite_block_report(
    *,
    lines: list[str],
    start_index: int,
    header_match: re.Match[str],
) -> _BlockRewriteResult:
    header_indent = _indent_width(lines[start_index])
    field_indexes: list[int] = []
    rewritten: list[str] = []
    index = start_index + 1
    while index < len(lines):
        raw_line = lines[index]
        stripped_commentless = _strip_inline_comment(raw_line)
        stripped = stripped_commentless.strip()
        if not stripped:
            rewritten.append(raw_line)
            index += 1
            continue
        if _COMMENT_ONLY_RE.match(raw_line):
            rewritten.append(raw_line)
            index += 1
            continue
        if _indent_width(raw_line) <= header_indent:
            break
        field_match = _REPORT_FIELD_RE.match(stripped_commentless)
        if field_match is None:
            raise DeclarativeModelError(
                "Ошибка в `report ... by ...:`: каждая строка внутри блока должна иметь вид "
                f"`поле = выражение` (строка {index + 1}).\n"
                "Как исправить: оставьте после двоеточия только строки формата "
                "`name = expr` без лишних слов."
            )
        field_indexes.append(len(rewritten))
        rewritten.append(raw_line)
        index += 1
    if not field_indexes:
        raise DeclarativeModelError(
            "Ошибка в `report ... by ...:`: после заголовка таблицы не найдено ни одной строки "
            f"с полями (строка {start_index + 1}).\n"
            "Как исправить: добавьте хотя бы одну строку вида `name = expr`."
        )

    header = (
        f"{header_match.group('indent')}report {header_match.group('name')}"
        f"[{header_match.group('iterator')} in {header_match.group('set_name')}]: {{"
    )
    rewritten.insert(0, header)
    last_field_position = field_indexes[-1] + 1
    for original_position in field_indexes[:-1]:
        line_position = original_position + 1
        rewritten[line_position] = f"{_strip_inline_comment(rewritten[line_position])},"
    rewritten[last_field_position] = f"{_strip_inline_comment(rewritten[last_field_position])} }}"
    return _BlockRewriteResult(rewritten_lines=tuple(rewritten), next_index=index)


def _normalize_orx_source(source: str) -> str:
    lines = source.splitlines()
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped_for_match = _strip_inline_comment(raw_line)
        stripped = stripped_for_match.strip()
        if not stripped or _COMMENT_ONLY_RE.match(raw_line):
            normalized.append(raw_line)
            index += 1
            continue

        range_match = _VAR_RANGE_RE.match(stripped_for_match)
        if range_match:
            head = range_match.group("head")
            index_set: str | None = None
            if "[" in head and head.endswith("]"):
                index_set = head.split("[", maxsplit=1)[1][:-1]
            lower_expr = _normalize_bound_sugar_expr(
                range_match.group("lower"),
                index_set=index_set,
            )
            upper_expr = _normalize_bound_sugar_expr(
                range_match.group("upper"),
                index_set=index_set,
            )
            normalized.append(
                f"{range_match.group('indent')}var {head} >= {lower_expr} <= {upper_expr}"
            )
            index += 1
            continue

        report_match = _BLOCK_REPORT_RE.match(stripped_for_match)
        if report_match:
            block_lines = _rewrite_block_report(
                lines=lines,
                start_index=index,
                header_match=report_match,
            )
            normalized.extend(block_lines.rewritten_lines)
            index = block_lines.next_index
            continue

        normalized.append(raw_line)
        index += 1
    return "\n".join(normalized) + ("\n" if source.endswith("\n") else "")


def _friendly_parse_error(source: str, exc: UnexpectedInput) -> DeclarativeModelError:
    context = exc.get_context(source, span=40).strip()
    return DeclarativeModelError(
        f"Ошибка синтаксиса ORX в строке {exc.line}, столбце {exc.column}.\n"
        f"Проблемное место: {context}\n"
        "Как исправить: проверьте ключевые слова, двоеточия, скобки и формат строк "
        "вида `name = expr` внутри `report ... by ...:`."
    )


def _friendly_model_error(message: str) -> DeclarativeModelError:
    lowered = message.lower()
    prefix = "Ошибка ORX-модели."
    advice = "Проверьте объявление символов и линейность формул."

    if "must declare exactly one objective" in lowered:
        human = "В модели должна быть ровно одна целевая функция `maximize` или `minimize`."
        advice = "Оставьте одну цель и удалите лишние объявления."
    elif "unknown symbol" in lowered or "references unknown" in lowered:
        human = "Формула использует имя, которое нигде не объявлено через `set`, `param` или `var`."
        advice = "Проверьте опечатки и добавьте недостающее объявление."
    elif "duplicate orx symbol" in lowered:
        human = "Одно и то же имя объявлено в модели больше одного раза."
        advice = "Переименуйте одно из объявлений, чтобы каждое имя было уникальным."
    elif "derived param" in lowered:
        human = "Производный параметр описан в неподдерживаемой форме."
        advice = "Оставьте производный `param` скалярным выражением и не передавайте его из YAML."
    elif "nonlinear" in lowered:
        human = (
            "Обнаружено нелинейное произведение или другая нелинейная конструкция. "
            "В текущем DSL разрешены только линейные LP-формулы."
        )
        advice = (
            "Не умножайте одну переменную решения на другую и не делите "
            "на выражение с переменной."
        )
    elif "division by zero" in lowered:
        human = "В формуле возникло деление на ноль."
        advice = "Измените выражение так, чтобы знаменатель не мог стать нулём."
    elif "duplicate report" in lowered:
        human = "Одно и то же имя отчёта объявлено больше одного раза."
        advice = "Переименуйте один из `report`, чтобы имена отчётов не повторялись."
    elif "table report" in lowered and "at least one field" in lowered:
        human = "Табличный отчёт объявлен без колонок."
        advice = "Добавьте хотя бы одну строку `field = expr` в `report ... by ...:`."
    elif "solve failed" in lowered:
        human = "Солвер не смог найти допустимое решение для этой LP-задачи."
        advice = (
            "Проверьте ограничения: возможно, они противоречат друг другу "
            "или делают задачу неограниченной."
        )
    else:
        human = message

    if "Как исправить:" in human:
        return DeclarativeModelError(human)
    return DeclarativeModelError(f"{prefix} {human}\nКак исправить: {advice}")


class _OrxV1Transformer(Transformer[Token, object]):
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
            else:  # pragma: no cover
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

    def vector_domain(self, items: list[object]) -> tuple[IndexDomain, ...]:
        return (IndexDomain(set_name=str(items[0])),)

    def iterator(self, items: list[object]) -> IteratorBinding:
        return IteratorBinding(name=str(items[0]), set_name=str(items[1]))

    def param_decl(self, items: list[object]) -> ParamDecl:
        name = str(items[0])
        indices: tuple[IndexDomain, ...] = ()
        expr: Expr | None = None
        for item in items[1:]:
            if isinstance(item, tuple) and item and isinstance(item[0], IndexDomain):
                indices = cast(tuple[IndexDomain, ...], item)
            elif isinstance(item, Expr):
                expr = item
        return ParamDecl(name=name, indices=indices, expr=expr)

    def lower_upper_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        return cast(Expr, items[1]), cast(Expr, items[3])

    def lower_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        return cast(Expr, items[1]), None

    def upper_bound(self, items: list[object]) -> tuple[Expr | None, Expr | None]:
        return None, cast(Expr, items[1])

    def var_decl(self, items: list[object]) -> VarDecl:
        name = str(items[0])
        indices: tuple[IndexDomain, ...] = ()
        lower: Expr | None = None
        upper: Expr | None = None
        for item in items[1:]:
            if isinstance(item, tuple) and item and isinstance(item[0], IndexDomain):
                indices = cast(tuple[IndexDomain, ...], item)
            elif isinstance(item, tuple):
                lower, upper = cast(tuple[Expr | None, Expr | None], item)
        return VarDecl(name=name, indices=indices, lower=lower, upper=upper)

    def relation(self, items: list[object]) -> str:
        return str(items[0])

    def objective_decl(self, items: list[object]) -> ObjectiveDecl:
        return ObjectiveDecl(sense=str(items[0]), name=str(items[1]), expr=cast(Expr, items[2]))

    def constraint_decl(self, items: list[object]) -> ConstraintDecl:
        name = str(items[0])
        iterators: tuple[IteratorBinding, ...] = ()
        expr_offset = 1
        if len(items) > 1 and isinstance(items[1], IteratorBinding):
            iterators = (cast(IteratorBinding, items[1]),)
            expr_offset = 2
        return ConstraintDecl(
            name=name,
            iterators=iterators,
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
            iterators=(cast(IteratorBinding, items[1]),),
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
            iterators=(IteratorBinding(name=str(items[0]), set_name=str(items[1])),),
            body=cast(Expr, items[2]),
        )

    def number(self, items: list[object]) -> NumberExpr:
        return NumberExpr(value=float(items[0]))

    def name(self, items: list[object]) -> NameExpr:
        return NameExpr(name=str(items[0]))

    def indexed_ref(self, items: list[object]) -> IndexedExpr:
        return IndexedExpr(name=str(items[0]), index_names=(str(items[1]),))


_PARSER = Lark(load_grammar_text("orx_model_v1.lark"), parser="lalr", start="start")
_TRANSFORMER = _OrxV1Transformer()


def parse_orx_model(source: str) -> ModelProgram:
    """Parse one ORX v1 model into a typed AST candidate."""
    normalized_source = _normalize_orx_source(source)
    try:
        tree = _PARSER.parse(normalized_source)
        program = cast(ModelProgram, _TRANSFORMER.transform(tree))
    except UnexpectedInput as exc:
        raise _friendly_parse_error(normalized_source, exc) from exc
    except DeclarativeModelError as exc:
        raise _friendly_model_error(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise DeclarativeModelError(
            "Ошибка ORX-модели. Парсер не смог разобрать файл.\n"
            f"Как исправить: проверьте синтаксис и сообщение библиотеки: {exc}"
        ) from exc
    if program.objective is None:
        raise _friendly_model_error("ORX model must declare exactly one objective")
    return program


def compile_orx_model(program: ModelProgram) -> CompiledModel:
    try:
        return _compile_orx_model_impl(program)
    except DeclarativeModelError as exc:
        raise _friendly_model_error(str(exc)) from exc


def solve_compiled_model(model: CompiledModel, bound_input: BoundModelInput) -> SolverResult:
    try:
        return _solve_compiled_model_impl(model, bound_input)
    except DeclarativeModelError as exc:
        raise _friendly_model_error(str(exc)) from exc


def _compile_orx_model_impl(program: ModelProgram) -> CompiledModel:
    seen_names: dict[str, str] = {}
    set_names: set[str] = set()
    param_names: set[str] = set()
    var_names: set[str] = set()
    param_arity: dict[str, int] = {}
    var_arity: dict[str, int] = {}

    def register(name: str, kind: str) -> None:
        existing = seen_names.get(name)
        if existing is not None:
            raise DeclarativeModelError(
                f"Duplicate ORX symbol `{name}` declared as {kind}; already declared as {existing}"
            )
        seen_names[name] = kind

    for declaration in program.sets:
        register(declaration.name, "set")
        set_names.add(declaration.name)

    for declaration in program.params:
        register(declaration.name, "param")
        param_names.add(declaration.name)
        param_arity[declaration.name] = len(declaration.index_sets)
        if declaration.expr is not None and declaration.indices:
            raise DeclarativeModelError(
                f"Derived param `{declaration.name}` must be scalar in current ORX"
            )
        for set_name in declaration.index_sets:
            if set_name not in set_names:
                raise DeclarativeModelError(
                    f"Param `{declaration.name}` references unknown set `{set_name}`"
                )

    for declaration in program.vars:
        register(declaration.name, "var")
        var_names.add(declaration.name)
        var_arity[declaration.name] = len(declaration.index_sets)
        for set_name in declaration.index_sets:
            if set_name not in set_names:
                raise DeclarativeModelError(
                    f"Var `{declaration.name}` references unknown set `{set_name}`"
                )

    objective = program.objective
    if objective is None:
        raise DeclarativeModelError("ORX model must declare exactly one objective")

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
                param_arity=param_arity,
                var_arity=var_arity,
                bound_indexes={},
                allow_vars=False,
                context=f"derived param `{param.name}`",
            )

    _validate_numeric_expr(
        expr=objective.expr,
        set_names=symbol_sets,
        param_names=symbol_params,
        var_names=symbol_vars,
        param_arity=param_arity,
        var_arity=var_arity,
        bound_indexes={},
        allow_vars=True,
        context=f"objective `{objective.name}`",
    )

    for constraint in program.constraints:
        bound_indexes: dict[str, str] = {}
        for iterator in constraint.iterators:
            if iterator.set_name not in set_names:
                raise DeclarativeModelError(
                    f"Constraint `{constraint.name}` references unknown set `{iterator.set_name}`"
                )
            if iterator.name in bound_indexes:
                raise DeclarativeModelError(
                    f"Constraint `{constraint.name}` reuses iterator `{iterator.name}`"
                )
            bound_indexes[iterator.name] = iterator.set_name
        _validate_numeric_expr(
            expr=constraint.left,
            set_names=symbol_sets,
            param_names=symbol_params,
            var_names=symbol_vars,
            param_arity=param_arity,
            var_arity=var_arity,
            bound_indexes=bound_indexes,
            allow_vars=True,
            context=f"constraint `{constraint.name}`",
        )
        _validate_numeric_expr(
            expr=constraint.right,
            set_names=symbol_sets,
            param_names=symbol_params,
            var_names=symbol_vars,
            param_arity=param_arity,
            var_arity=var_arity,
            bound_indexes=bound_indexes,
            allow_vars=True,
            context=f"constraint `{constraint.name}`",
        )

    for declaration in program.vars:
        bound_indexes = dict(zip(declaration.index_names, declaration.index_sets, strict=True))
        if declaration.lower is not None:
            _validate_numeric_expr(
                expr=declaration.lower,
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                param_arity=param_arity,
                var_arity=var_arity,
                bound_indexes=bound_indexes,
                allow_vars=False,
                context=f"lower bound of var `{declaration.name}`",
            )
        if declaration.upper is not None:
            _validate_numeric_expr(
                expr=declaration.upper,
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                param_arity=param_arity,
                var_arity=var_arity,
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
            param_arity=param_arity,
            var_arity=var_arity,
            bound_indexes={},
            context=f"report `{report.name}`",
        )

    for report in program.table_reports:
        if report.name in report_names:
            raise DeclarativeModelError(f"Duplicate report `{report.name}`")
        report_names.add(report.name)
        if not report.fields:
            raise DeclarativeModelError(
                f"Table report `{report.name}` must declare at least one field"
            )
        bound_indexes: dict[str, str] = {}
        for iterator in report.iterators:
            if iterator.set_name not in set_names:
                raise DeclarativeModelError(
                    f"Table report `{report.name}` references unknown set `{iterator.set_name}`"
                )
            if iterator.name in bound_indexes:
                raise DeclarativeModelError(
                    f"Table report `{report.name}` reuses iterator `{iterator.name}`"
                )
            bound_indexes[iterator.name] = iterator.set_name
        row_field_names: set[str] = set()
        for report_field in report.fields:
            if report_field.name in row_field_names:
                raise DeclarativeModelError(
                    f"Table report `{report.name}` contains duplicate field `{report_field.name}`"
                )
            row_field_names.add(report_field.name)
            _validate_report_expr(
                expr=report_field.expr,
                set_names=symbol_sets,
                param_names=symbol_params,
                var_names=symbol_vars,
                param_arity=param_arity,
                var_arity=var_arity,
                bound_indexes=bound_indexes,
                context=f"report `{report.name}` field `{report_field.name}`",
            )

    required_input_params = tuple(param for param in program.params if param.expr is None)
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


def _iter_index_tuples(
    set_names: tuple[str, ...],
    bound_input: BoundModelInput,
) -> list[tuple[str, ...]]:
    if not set_names:
        return [()]
    return [tuple(values) for values in product(*(bound_input.sets[name] for name in set_names))]


def _iter_envs(
    iterators: tuple[IteratorBinding, ...],
    bound_input: BoundModelInput,
) -> list[dict[str, str]]:
    if not iterators:
        return [{}]
    envs: list[dict[str, str]] = []
    spaces = [bound_input.sets[iterator.set_name] for iterator in iterators]
    for combo in product(*spaces):
        envs.append(
            {
                iterator.name: value
                for iterator, value in zip(iterators, combo, strict=True)
            }
        )
    return envs


def _normalize_param_mapping(
    *,
    declaration: ParamDecl,
    raw_value: object,
    bound_input: BoundModelInput,
) -> dict[str, float] | dict[tuple[str, ...], float]:
    expected_index_tuples = _iter_index_tuples(declaration.index_sets, bound_input)
    if len(declaration.index_sets) == 1:
        if not isinstance(raw_value, dict):
            raise DeclarativeModelError(
                f"Param `{declaration.name}` must resolve to a keyed vector"
            )
        expected_keys = tuple(key[0] for key in expected_index_tuples)
        if tuple(raw_value.keys()) != expected_keys:
            raise DeclarativeModelError(
                f"Param `{declaration.name}` keys must match set `{declaration.index_set}` order"
            )
        return {str(key): float(item) for key, item in raw_value.items()}

    if not isinstance(raw_value, dict):
        raise DeclarativeModelError(
            f"Param `{declaration.name}` must resolve to a tuple-keyed mapping"
        )
    normalized: dict[tuple[str, ...], float] = {}
    for key, item in raw_value.items():
        if not isinstance(key, tuple) or len(key) != len(declaration.index_sets):
            raise DeclarativeModelError(
                "Param "
                f"`{declaration.name}` expects tuple keys of arity "
                f"{len(declaration.index_sets)}"
            )
        normalized[tuple(str(part) for part in key)] = float(item)
    if tuple(normalized.keys()) != tuple(expected_index_tuples):
        raise DeclarativeModelError(
            f"Param `{declaration.name}` keys must match cartesian product of declared sets order"
        )
    return normalized


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
        param.name for param in model.required_input_params if param.name not in bound_input.params
    ]
    if missing_params:
        raise DeclarativeModelError(
            f"Bound input is missing declared params: {', '.join(sorted(missing_params))}"
        )

    for declaration in model.required_input_params:
        raw_value = bound_input.params[declaration.name]
        if not declaration.index_sets:
            if not isinstance(raw_value, (int, float)):
                raise DeclarativeModelError(
                    f"Param `{declaration.name}` must resolve to one number"
                )
            continue
        _normalize_param_mapping(
            declaration=declaration,
            raw_value=raw_value,
            bound_input=bound_input,
        )


def _resolve_param_values(
    *, model: CompiledModel, bound_input: BoundModelInput
) -> dict[str, float | dict[str, float] | dict[tuple[str, ...], float]]:
    resolved: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]] = {}
    for declaration in model.params:
        if declaration.expr is None:
            raw_value = bound_input.params[declaration.name]
            if not declaration.index_sets:
                if not isinstance(raw_value, (int, float)):
                    raise DeclarativeModelError(
                        f"Param `{declaration.name}` must resolve to one number"
                    )
                resolved[declaration.name] = float(raw_value)
            else:
                resolved[declaration.name] = _normalize_param_mapping(
                    declaration=declaration,
                    raw_value=raw_value,
                    bound_input=bound_input,
                )
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
) -> list[tuple[str, tuple[str, ...] | None]]:
    order: list[tuple[str, tuple[str, ...] | None]] = []
    for declaration in model.vars:
        if not declaration.index_sets:
            order.append((declaration.name, None))
            continue
        order.extend(
            (declaration.name, index_tuple)
            for index_tuple in _iter_index_tuples(
                declaration.index_sets,
                bound_input,
            )
        )
    return order


def _value_for_indexed_name(
    *,
    symbol_name: str,
    index_tuple: tuple[str, ...],
    param_values: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]],
    variables: dict[tuple[str, tuple[str, ...] | None], float] | None,
) -> float:
    param_value = param_values.get(symbol_name)
    if isinstance(param_value, dict):
        if index_tuple in param_value:
            return float(param_value[index_tuple])
        if len(index_tuple) == 1 and index_tuple[0] in param_value:
            return float(cast(dict[str, float], param_value)[index_tuple[0]])
    if variables is not None and (symbol_name, index_tuple) in variables:
        return float(variables[(symbol_name, index_tuple)])
    raise DeclarativeModelError(f"Indexed symbol `{symbol_name}` is missing concrete value")


def _compile_affine_expr(
    *,
    expr: Expr,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]],
    env: dict[str, str],
) -> _AffineExpr:
    if isinstance(expr, NumberExpr):
        return _AffineExpr(constant=expr.value)
    if isinstance(expr, NameExpr):
        if expr.name in env:
            raise DeclarativeModelError(f"Loop index `{expr.name}` cannot be used as a number here")
        value = param_values.get(expr.name)
        if value is not None:
            if isinstance(value, dict):
                raise DeclarativeModelError(
                    f"Vector symbol `{expr.name}` requires an explicit index"
                )
            return _AffineExpr(constant=float(value))
        return _AffineExpr(coefficients={(expr.name, None): 1.0})
    if isinstance(expr, IndexedExpr):
        index_tuple = tuple(env.get(name, "") for name in expr.index_names)
        if any(not item for item in index_tuple):
            missing = [name for name in expr.index_names if name not in env]
            raise DeclarativeModelError(
                f"Unknown loop index `{', '.join(missing)}` while compiling `{expr.name}`"
            )
        param_value = param_values.get(expr.name)
        if param_value is not None:
            return _AffineExpr(
                constant=_value_for_indexed_name(
                    symbol_name=expr.name,
                    index_tuple=index_tuple,
                    param_values=param_values,
                    variables=None,
                )
            )
        return _AffineExpr(coefficients={(expr.name, index_tuple): 1.0})
    if isinstance(expr, UnaryExpr):
        return _compile_affine_expr(
            expr=expr.operand,
            bound_input=bound_input,
            param_values=param_values,
            env=env,
        ).scale(-1.0)
    if isinstance(expr, BinaryExpr):
        left = _compile_affine_expr(
            expr=expr.left,
            bound_input=bound_input,
            param_values=param_values,
            env=env,
        )
        right = _compile_affine_expr(
            expr=expr.right,
            bound_input=bound_input,
            param_values=param_values,
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
        for nested_env in _iter_envs(expr.iterators, bound_input):
            merged_env = dict(env)
            merged_env.update(nested_env)
            total = total.add(
                _compile_affine_expr(
                    expr=expr.body,
                    bound_input=bound_input,
                    param_values=param_values,
                    env=merged_env,
                )
            )
        return total
    raise DeclarativeModelError(f"Unsupported affine expression: {expr!r}")


def _evaluate_report_expr(
    *,
    expr: Expr,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]],
    variables: dict[tuple[str, tuple[str, ...] | None], float] | None,
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
        if variables is not None and (expr.name, None) in variables:
            return float(variables[(expr.name, None)])
        raise DeclarativeModelError(f"Unknown scalar symbol `{expr.name}`")
    if isinstance(expr, IndexedExpr):
        index_tuple = tuple(env.get(name, "") for name in expr.index_names)
        if any(not item for item in index_tuple):
            missing = [name for name in expr.index_names if name not in env]
            raise DeclarativeModelError(
                f"Unknown loop index `{', '.join(missing)}` while evaluating `{expr.name}`"
            )
        return _value_for_indexed_name(
            symbol_name=expr.name,
            index_tuple=index_tuple,
            param_values=param_values,
            variables=variables,
        )
    if isinstance(expr, UnaryExpr):
        return -float(
            _evaluate_report_expr(
                expr=expr.operand,
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
        if expr.op == "+":
            return float(left) + float(right)
        if expr.op == "-":
            return float(left) - float(right)
        if expr.op == "*":
            return float(left) * float(right)
        if expr.op == "/":
            denominator = float(right)
            if isclose(denominator, 0.0, abs_tol=1e-12):
                raise DeclarativeModelError("Division by zero in ORX expression")
            return float(left) / denominator
        raise DeclarativeModelError(f"Unsupported binary operator `{expr.op}`")
    if isinstance(expr, SumExpr):
        total = 0.0
        for nested_env in _iter_envs(expr.iterators, bound_input):
            merged_env = dict(env)
            merged_env.update(nested_env)
            total += float(
                _evaluate_report_expr(
                    expr=expr.body,
                    bound_input=bound_input,
                    param_values=param_values,
                    variables=variables,
                    env=merged_env,
                )
            )
        return total
    raise DeclarativeModelError(f"Unsupported ORX expression: {expr!r}")


def _evaluate_numeric_expr(
    expr: Expr,
    *,
    bound_input: BoundModelInput,
    param_values: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]],
    variables: dict[tuple[str, tuple[str, ...] | None], float] | None,
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


def _solve_compiled_model_impl(model: CompiledModel, bound_input: BoundModelInput) -> SolverResult:
    _validate_bound_input(model=model, bound_input=bound_input)
    param_values = _resolve_param_values(model=model, bound_input=bound_input)
    variable_order = _build_variable_order(model=model, bound_input=bound_input)
    variable_index = {key: idx for idx, key in enumerate(variable_order)}

    bounds: list[tuple[float | None, float | None]] = []
    for key in variable_order:
        name, index_tuple = key
        declaration = next(item for item in model.vars if item.name == name)
        env = (
            dict(zip(declaration.index_names, index_tuple, strict=True))
            if index_tuple is not None
            else {}
        )
        lower = (
            _evaluate_numeric_expr(
                declaration.lower,
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
                declaration.upper,
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
        for env in _iter_envs(declaration.iterators, bound_input):
            left = _compile_affine_expr(
                expr=declaration.left,
                bound_input=bound_input,
                param_values=param_values,
                env=env,
            )
            right = _compile_affine_expr(
                expr=declaration.right,
                bound_input=bound_input,
                param_values=param_values,
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
        for env in _iter_envs(report.iterators, bound_input):
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


def _validate_numeric_expr(
    *,
    expr: Expr,
    set_names: frozenset[str],
    param_names: frozenset[str],
    var_names: frozenset[str],
    param_arity: dict[str, int],
    var_arity: dict[str, int],
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
            if param_arity[expr.name] > 0:
                raise DeclarativeModelError(
                    f"{context} references vector param `{expr.name}` without explicit indexes"
                )
            return False
        if expr.name in var_names:
            if var_arity[expr.name] > 0:
                raise DeclarativeModelError(
                    f"{context} references vector var `{expr.name}` without explicit indexes"
                )
            if not allow_vars:
                raise DeclarativeModelError(
                    f"{context} cannot reference decision var `{expr.name}`"
                )
            return True
        raise DeclarativeModelError(f"{context} references unknown symbol `{expr.name}`")
    if isinstance(expr, IndexedExpr):
        for index_name in expr.index_names:
            if index_name not in bound_indexes:
                raise DeclarativeModelError(
                    f"{context} uses unknown index `{index_name}` for `{expr.name}`"
                )
        if expr.name in param_names:
            if param_arity[expr.name] != len(expr.index_names):
                raise DeclarativeModelError(
                    f"{context} uses wrong index arity for param `{expr.name}`"
                )
            return False
        if expr.name in var_names:
            if var_arity[expr.name] != len(expr.index_names):
                raise DeclarativeModelError(
                    f"{context} uses wrong index arity for var `{expr.name}`"
                )
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
            param_arity=param_arity,
            var_arity=var_arity,
            bound_indexes=bound_indexes,
            allow_vars=allow_vars,
            context=context,
        )
    if isinstance(expr, SumExpr):
        nested_indexes = dict(bound_indexes)
        for iterator in expr.iterators:
            if iterator.set_name not in set_names:
                raise DeclarativeModelError(
                    f"{context} sums over unknown set `{iterator.set_name}`"
                )
            nested_indexes[iterator.name] = iterator.set_name
        return _validate_numeric_expr(
            expr=expr.body,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            param_arity=param_arity,
            var_arity=var_arity,
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
            param_arity=param_arity,
            var_arity=var_arity,
            bound_indexes=bound_indexes,
            allow_vars=allow_vars,
            context=context,
        )
        right_has_vars = _validate_numeric_expr(
            expr=expr.right,
            set_names=set_names,
            param_names=param_names,
            var_names=var_names,
            param_arity=param_arity,
            var_arity=var_arity,
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
    param_arity: dict[str, int],
    var_arity: dict[str, int],
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
        param_arity=param_arity,
        var_arity=var_arity,
        bound_indexes=bound_indexes,
        allow_vars=True,
        context=context,
    )


def _clean_number(value: float) -> float:
    if isclose(value, round(value), abs_tol=1e-12):
        return float(round(value))
    return round(value, 10)


def _clean_value(value: Any) -> Any:
    if isinstance(value, float):
        return _clean_number(value)
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_value(item) for key, item in value.items()}
    return value
