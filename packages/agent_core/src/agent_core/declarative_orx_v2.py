"""Math-first ORX v2 parser with AMPL/MathProg-like LP notation."""

from __future__ import annotations

from typing import cast

from lark import Lark, Token, Transformer, UnexpectedInput

from agent_core.declarative_orx import (
    DeclarativeModelError,
    _friendly_model_error,
    _friendly_parse_error,
)
from agent_core.grammar_loader import load_grammar_text
from agent_core.orx_metamodel import (
    BinaryExpr,
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
    SetDecl,
    SumExpr,
    UnaryExpr,
    VarDecl,
)


class _OrxV2Transformer(Transformer[Token, object]):
    def statement(self, items: list[object]) -> object:
        return items[0]

    def start(self, items: list[object]) -> ModelProgram:
        sets: list[SetDecl] = []
        params: list[ParamDecl] = []
        vars_: list[VarDecl] = []
        constraints: list[ConstraintDecl] = []
        objective: ObjectiveDecl | None = None
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
            else:  # pragma: no cover
                raise DeclarativeModelError(f"Unsupported ORX v2 statement node: {item!r}")
        return ModelProgram(
            sets=tuple(sets),
            params=tuple(params),
            vars=tuple(vars_),
            objective=objective,
            constraints=tuple(constraints),
        )

    def set_decl(self, items: list[object]) -> SetDecl:
        return SetDecl(name=str(items[0]))

    def domain_set(self, items: list[object]) -> IndexDomain:
        return IndexDomain(set_name=str(items[0]))

    def iterator_binding(self, items: list[object]) -> IteratorBinding:
        return IteratorBinding(name=str(items[0]), set_name=str(items[1]))

    def domain_clause(self, items: list[object]) -> tuple[IndexDomain, ...]:
        return tuple(cast(IndexDomain, item) for item in items)

    def iterator_domain(self, items: list[object]) -> tuple[IndexDomain, ...]:
        return tuple(
            IndexDomain(
                set_name=cast(IteratorBinding, item).set_name,
                name=cast(IteratorBinding, item).name,
            )
            for item in items
        )

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
        cursor = 1  # skip SUBJECT_TO token
        name = str(items[cursor])
        cursor += 1
        iterators: tuple[IteratorBinding, ...] = ()
        if cursor < len(items) and isinstance(items[cursor], tuple):
            domains = cast(tuple[IndexDomain, ...], items[cursor])
            iterators = tuple(
                IteratorBinding(name=domain.name or f"_{idx}", set_name=domain.set_name)
                for idx, domain in enumerate(domains)
            )
            cursor += 1
        return ConstraintDecl(
            name=name,
            iterators=iterators,
            left=cast(Expr, items[cursor]),
            relation=cast(str, items[cursor + 1]),
            right=cast(Expr, items[cursor + 2]),
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
        *bindings, body = items
        return SumExpr(
            iterators=tuple(cast(IteratorBinding, item) for item in bindings),
            body=cast(Expr, body),
        )

    def number(self, items: list[object]) -> NumberExpr:
        return NumberExpr(value=float(items[0]))

    def name(self, items: list[object]) -> NameExpr:
        return NameExpr(name=str(items[0]))

    def expr_index_list(self, items: list[object]) -> tuple[str, ...]:
        return tuple(str(item) for item in items)

    def indexed_ref(self, items: list[object]) -> IndexedExpr:
        return IndexedExpr(name=str(items[0]), index_names=cast(tuple[str, ...], items[1]))


_MODEL_PARSER = Lark(load_grammar_text("orx_model_v2.lark"), parser="lalr", start="start")
_EXPR_PARSER = Lark(load_grammar_text("orx_model_v2.lark"), parser="lalr", start="expr")
_TRANSFORMER = _OrxV2Transformer()


def parse_orx_model_v2(source: str) -> ModelProgram:
    """Parse one math-first ORX v2 model into the shared metamodel."""
    try:
        tree = _MODEL_PARSER.parse(source)
        program = cast(ModelProgram, _TRANSFORMER.transform(tree))
    except UnexpectedInput as exc:
        raise _friendly_parse_error(source, exc) from exc
    except DeclarativeModelError as exc:
        raise _friendly_model_error(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise DeclarativeModelError(
            "Ошибка ORX v2-модели. Парсер не смог разобрать файл.\n"
            f"Как исправить: проверьте синтаксис и сообщение библиотеки: {exc}"
        ) from exc
    if program.objective is None:
        raise _friendly_model_error("ORX model must declare exactly one objective")
    return program


def parse_orx_expr_v2(source: str) -> Expr:
    """Parse one standalone ORX v2 expression, for display-sidecar formulas."""
    try:
        tree = _EXPR_PARSER.parse(source.strip())
        return cast(Expr, _TRANSFORMER.transform(tree))
    except UnexpectedInput as exc:
        raise _friendly_parse_error(source, exc) from exc
    except DeclarativeModelError as exc:
        raise _friendly_model_error(str(exc)) from exc
