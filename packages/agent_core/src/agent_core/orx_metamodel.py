"""Explicit metamodel / AST for ORX LP DSLs.

The project uses this module as a MOF-inspired internal metamodel layer:
external grammars parse text into a typed AST here, which is then transformed
into solver-oriented IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class IndexDomain:
    """One declared index domain, optionally with an explicit iterator name."""

    set_name: str
    name: str | None = None


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
    index_names: tuple[str, ...]

    @property
    def index_name(self) -> str:
        if len(self.index_names) != 1:
            raise ValueError("IndexedExpr.index_name is only valid for 1-D expressions")
        return self.index_names[0]


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
    iterators: tuple[IteratorBinding, ...]
    body: Expr

    @property
    def iterator(self) -> IteratorBinding:
        if len(self.iterators) != 1:
            raise ValueError("SumExpr.iterator is only valid for 1-D sums")
        return self.iterators[0]


@dataclass(frozen=True, slots=True)
class SetDecl:
    name: str


@dataclass(frozen=True, slots=True)
class ParamDecl:
    name: str
    indices: tuple[IndexDomain, ...] = ()
    expr: Expr | None = None

    @property
    def index_sets(self) -> tuple[str, ...]:
        return tuple(item.set_name for item in self.indices)

    @property
    def index_names(self) -> tuple[str, ...]:
        return tuple(item.name or f"_{idx}" for idx, item in enumerate(self.indices))

    @property
    def index_set(self) -> str | None:
        return self.index_sets[0] if len(self.index_sets) == 1 else None


@dataclass(frozen=True, slots=True)
class VarDecl:
    name: str
    indices: tuple[IndexDomain, ...] = ()
    lower: Expr | None = None
    upper: Expr | None = None

    @property
    def index_sets(self) -> tuple[str, ...]:
        return tuple(item.set_name for item in self.indices)

    @property
    def index_names(self) -> tuple[str, ...]:
        return tuple(item.name or f"_{idx}" for idx, item in enumerate(self.indices))

    @property
    def index_set(self) -> str | None:
        return self.index_sets[0] if len(self.index_sets) == 1 else None


@dataclass(frozen=True, slots=True)
class ObjectiveDecl:
    sense: Literal["maximize", "minimize"]
    name: str
    expr: Expr


@dataclass(frozen=True, slots=True)
class ConstraintDecl:
    name: str
    iterators: tuple[IteratorBinding, ...]
    left: Expr
    relation: Literal["<=", ">=", "="]
    right: Expr

    @property
    def iterator(self) -> IteratorBinding | None:
        if not self.iterators:
            return None
        if len(self.iterators) != 1:
            raise ValueError("ConstraintDecl.iterator is only valid for 1-D constraints")
        return self.iterators[0]


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
    iterators: tuple[IteratorBinding, ...]
    fields: tuple[ReportFieldDecl, ...]

    @property
    def iterator(self) -> IteratorBinding:
        if len(self.iterators) != 1:
            raise ValueError("TableReportDecl.iterator is only valid for 1-D reports")
        return self.iterators[0]


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
    sets: dict[str, tuple[str, ...]]
    params: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]]


@dataclass(frozen=True, slots=True)
class SolverResult:
    objective_value: float
    solver_status: str
    variables: dict[tuple[str, tuple[str, ...] | None], float]
    result_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _AffineExpr:
    constant: float = 0.0
    coefficients: dict[tuple[str, tuple[str, ...] | None], float] = field(default_factory=dict)

    def add(self, other: "_AffineExpr") -> "_AffineExpr":
        coefficients = dict(self.coefficients)
        for key, value in other.coefficients.items():
            coefficients[key] = coefficients.get(key, 0.0) + value
            if abs(coefficients[key]) <= 1e-12:
                coefficients.pop(key)
        return _AffineExpr(constant=self.constant + other.constant, coefficients=coefficients)

    def sub(self, other: "_AffineExpr") -> "_AffineExpr":
        return self.add(other.scale(-1.0))

    def scale(self, factor: float) -> "_AffineExpr":
        if abs(factor) <= 1e-12:
            return _AffineExpr()
        return _AffineExpr(
            constant=self.constant * factor,
            coefficients={key: value * factor for key, value in self.coefficients.items()},
        )

    @property
    def has_variables(self) -> bool:
        return bool(self.coefficients)


def with_reports(
    model: CompiledModel,
    *,
    scalar_reports: tuple[ScalarReportDecl, ...],
    table_reports: tuple[TableReportDecl, ...],
) -> CompiledModel:
    """Return a copy of the compiled model with replacement reports."""
    return replace(
        model,
        scalar_reports=scalar_reports,
        table_reports=table_reports,
    )
