"""Typed public models for extension manifests and result presentation."""

from __future__ import annotations

import re
from collections import deque
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _normalize_token(value: str) -> str:
    """Normalize alias/path tokens for case-insensitive lookup and validation."""
    return value.strip().lower()


class FieldSpec(BaseModel):
    """Description of one logical input field inside an extension stage."""

    model_config = ConfigDict(extra="forbid")

    field_path: str
    label: str
    description: str | None = None
    required: bool = True
    value_type: str | None = None
    aliases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class StageSpec(BaseModel):
    """Schema-like description of one stage in an extension DAG."""

    model_config = ConfigDict(extra="forbid")

    stage_id: str
    label: str
    depends_on: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    field_specs: list[FieldSpec] = Field(default_factory=list)

    @field_validator("stage_id")
    @classmethod
    def validate_stage_id(cls, value: str) -> str:
        """Require stable lowercase identifiers for stage IDs."""
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(
                "stage_id must match ^[a-z][a-z0-9_-]*$ for stable manifest-driven routing"
            )
        return value


class SummaryBlock(BaseModel):
    """Single rich-text summary block for extension results."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["summary"] = "summary"
    title: str | None = None
    text: str


class KVItem(BaseModel):
    """Key-value entry for compact result summaries."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any


class KVBlock(BaseModel):
    """Key-value block for deterministic, compact outputs."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["kv"] = "kv"
    title: str | None = None
    items: list[KVItem]


class TableBlock(BaseModel):
    """Tabular block for structured deterministic outputs."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[str]
    rows: list[list[Any]]


class ListBlock(BaseModel):
    """Bullet-list block for short result collections."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["list"] = "list"
    title: str | None = None
    items: list[str]


class JsonBlock(BaseModel):
    """Raw JSON block for structured debugging or advanced drill-down."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["json"] = "json"
    title: str | None = None
    value: Any


ExtensionResultBlock = Annotated[
    SummaryBlock | KVBlock | TableBlock | ListBlock | JsonBlock,
    Field(discriminator="type"),
]


class ExtensionResultSection(BaseModel):
    """One renderable result section produced by an extension runtime."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    blocks: list[ExtensionResultBlock]


class ExtensionManifest(BaseModel):
    """Public manifest for one installable extension package."""

    model_config = ConfigDict(extra="forbid")

    alias: str
    title: str
    description: str
    version: str
    default_preset: str | None = None
    stage_graph: list[StageSpec] = Field(min_length=1)
    labels: dict[str, str] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    stage_aliases: dict[str, list[str]] = Field(default_factory=dict)
    ui_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """Require stable public aliases for registry and session state."""
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(
                "alias must match ^[a-z][a-z0-9_-]*$ for stable discovery and session binding"
            )
        return value

    @model_validator(mode="after")
    def validate_stage_graph(self) -> "ExtensionManifest":
        """Reject malformed graphs early, before runtime wiring."""
        stage_map: dict[str, StageSpec] = {}
        stage_position: dict[str, int] = {}
        for index, stage in enumerate(self.stage_graph):
            if stage.stage_id in stage_map:
                raise ValueError(f"duplicate stage_id in stage_graph: {stage.stage_id}")
            stage_map[stage.stage_id] = stage
            stage_position[stage.stage_id] = index

        inbound: dict[str, int] = {stage_id: 0 for stage_id in stage_map}
        adjacency: dict[str, list[str]] = {stage_id: [] for stage_id in stage_map}

        for stage in self.stage_graph:
            for dependency in stage.depends_on:
                if dependency not in stage_map:
                    raise ValueError(
                        f"stage {stage.stage_id} depends on unknown stage {dependency}"
                    )
                if dependency == stage.stage_id:
                    raise ValueError(f"stage {stage.stage_id} cannot depend on itself")
                inbound[stage.stage_id] += 1
                adjacency[dependency].append(stage.stage_id)

        queue = deque(stage_id for stage_id in self.stage_ids() if inbound.get(stage_id, 0) == 0)
        visited: list[str] = []
        while queue:
            current = queue.popleft()
            visited.append(current)
            for dependent in sorted(
                adjacency[current],
                key=lambda stage_id: stage_position[stage_id],
            ):
                inbound[dependent] -= 1
                if inbound[dependent] == 0:
                    queue.append(dependent)

        if len(visited) != len(stage_map):
            raise ValueError("stage_graph must be acyclic")

        for stage in self.stage_graph:
            normalized_field_paths: set[str] = set()
            for field in stage.field_specs:
                normalized = _normalize_token(field.field_path)
                if not normalized:
                    raise ValueError(
                        f"field_path in stage {stage.stage_id} must not be empty or whitespace"
                    )
                if normalized in normalized_field_paths:
                    raise ValueError(
                        f"duplicate field_path {field.field_path!r} in stage {stage.stage_id}"
                    )
                normalized_field_paths.add(normalized)

        for stage in self.stage_graph:
            self.field_alias_map(stage.stage_id)
        return self

    def stage_ids(self) -> list[str]:
        """Return stage IDs in declaration order."""
        return [stage.stage_id for stage in self.stage_graph]

    def stage_map(self) -> dict[str, StageSpec]:
        """Return a stage lookup table keyed by stage ID."""
        return {stage.stage_id: stage for stage in self.stage_graph}

    def topological_stage_ids(self) -> list[str]:
        """Return a stable topological order derived from `depends_on`."""
        stage_map = self.stage_map()
        stage_position = {stage.stage_id: index for index, stage in enumerate(self.stage_graph)}
        inbound: dict[str, int] = {stage_id: 0 for stage_id in stage_map}
        adjacency: dict[str, list[str]] = {stage_id: [] for stage_id in stage_map}
        for stage in self.stage_graph:
            for dependency in stage.depends_on:
                inbound[stage.stage_id] += 1
                adjacency[dependency].append(stage.stage_id)

        queue = deque(stage_id for stage_id in self.stage_ids() if inbound.get(stage_id, 0) == 0)
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for dependent in sorted(
                adjacency[current],
                key=lambda stage_id: stage_position[stage_id],
            ):
                inbound[dependent] -= 1
                if inbound[dependent] == 0:
                    queue.append(dependent)
        return order

    def canonical_field_paths(self, stage_id: str) -> dict[str, str]:
        """Return normalized -> canonical field paths for one stage."""
        stage = self.stage_map()[stage_id]
        return {
            _normalize_token(field.field_path): field.field_path.strip()
            for field in stage.field_specs
        }

    def _resolve_manifest_field_alias_target(self, target: str) -> tuple[str, str]:
        """Resolve one manifest-level alias target to (stage_id, canonical_field_path)."""
        normalized_target = target.strip()
        if not normalized_target:
            raise ValueError("field_aliases keys must not be empty")

        if "." in normalized_target:
            stage_id, raw_field_path = normalized_target.split(".", maxsplit=1)
            stage = self.stage_map().get(stage_id)
            if stage is None:
                raise ValueError(
                    f"field_aliases target {target!r} references unknown stage {stage_id!r}"
                )
            canonical_paths = self.canonical_field_paths(stage_id)
            canonical = canonical_paths.get(_normalize_token(raw_field_path))
            if canonical is None:
                raise ValueError(
                    f"field_aliases target {target!r} references unknown field "
                    f"{raw_field_path!r} in stage {stage_id!r}"
                )
            return stage_id, canonical

        normalized_lookup = _normalize_token(normalized_target)
        matches: list[tuple[str, str]] = []
        for stage in self.stage_graph:
            canonical = self.canonical_field_paths(stage.stage_id).get(normalized_lookup)
            if canonical is not None:
                matches.append((stage.stage_id, canonical))

        if not matches:
            raise ValueError(
                f"field_aliases target {target!r} does not match any declared field_path"
            )
        if len(matches) > 1:
            matching_stages = ", ".join(stage_id for stage_id, _ in matches)
            raise ValueError(
                f"field_aliases target {target!r} is ambiguous across stages: "
                f"{matching_stages}. Use '<stage_id>.<field_path>' instead."
            )
        return matches[0]

    def field_alias_map(self, stage_id: str) -> dict[str, str]:
        """Return normalized alias -> canonical field path mapping for one stage."""
        if stage_id not in self.stage_map():
            raise KeyError(stage_id)

        canonical_paths = self.canonical_field_paths(stage_id)
        alias_map: dict[str, str] = {}

        def register_alias(alias: str, canonical_field_path: str, *, source: str) -> None:
            normalized_alias = _normalize_token(alias)
            if not normalized_alias:
                raise ValueError(
                    f"empty field alias in stage {stage_id} from {source} is not allowed"
                )
            canonical_conflict = canonical_paths.get(normalized_alias)
            if canonical_conflict is not None and canonical_conflict != canonical_field_path:
                raise ValueError(
                    f"field alias {alias!r} in stage {stage_id} from {source} conflicts with "
                    f"canonical field path {canonical_conflict!r}"
                )
            existing = alias_map.get(normalized_alias)
            if existing is not None and existing != canonical_field_path:
                raise ValueError(
                    f"field alias {alias!r} in stage {stage_id} is ambiguous: "
                    f"{existing!r} vs {canonical_field_path!r}"
                )
            alias_map[normalized_alias] = canonical_field_path

        stage = self.stage_map()[stage_id]
        for field in stage.field_specs:
            canonical_field_path = canonical_paths[_normalize_token(field.field_path)]
            for alias in field.aliases:
                register_alias(
                    alias,
                    canonical_field_path,
                    source=f"FieldSpec({field.field_path})",
                )

        for target, aliases in self.field_aliases.items():
            target_stage_id, canonical_field_path = self._resolve_manifest_field_alias_target(
                target
            )
            if target_stage_id != stage_id:
                continue
            for alias in aliases:
                register_alias(
                    alias,
                    canonical_field_path,
                    source=f"field_aliases[{target!r}]",
                )

        return alias_map


class ExtensionSymbolSemantics(BaseModel):
    """One typed symbol from the declarative math model."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["set", "param", "var", "objective"]
    dimensions: int = 0
    index_sets: list[str] = Field(default_factory=list)
    required_input: bool = False
    derived: bool = False


class ExtensionScalarInputSemantics(BaseModel):
    """One scalar input bound to a scalar model symbol."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["scalar"] = "scalar"
    param: str
    field_path: str
    label: str
    help: str | None = None
    value_type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    aliases: list[str] = Field(default_factory=list)
    example: Any = None


class ExtensionVectorInputSemantics(BaseModel):
    """One 1-D input bound to a vector model symbol over one set."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["vector"] = "vector"
    param: str
    over: str
    field_path: str
    label: str
    help: str | None = None
    value_type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    aliases: list[str] = Field(default_factory=list)
    example: Any = None


class ExtensionTableKeySemantics(BaseModel):
    """One field that populates the elements of a set."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["table_key"] = "table_key"
    set_name: str
    field_path: str
    label: str
    help: str | None = None
    aliases: list[str] = Field(default_factory=list)
    example: Any = None


class ExtensionTableColumnSemantics(BaseModel):
    """One 1-D column bound to a parameter over the table set."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["table_column"] = "table_column"
    param: str
    set_name: str
    field_path: str
    label: str
    help: str | None = None
    value_type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    aliases: list[str] = Field(default_factory=list)
    example: Any = None


class ExtensionTableInputSemantics(BaseModel):
    """One student-facing table step for a single set plus 1-D parameters."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["table"] = "table"
    set_name: str
    key: ExtensionTableKeySemantics
    columns: list[ExtensionTableColumnSemantics] = Field(default_factory=list)


class ExtensionMatrixFieldSemantics(BaseModel):
    """One matrix-valued field bound to a 2-D parameter."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["matrix_field"] = "matrix_field"
    param: str
    row_set: str
    col_set: str
    field_path: str
    label: str
    help: str | None = None
    value_type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    aliases: list[str] = Field(default_factory=list)
    example: Any = None


class ExtensionMatrixInputSemantics(BaseModel):
    """One student-facing matrix step over two already-declared sets."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["matrix"] = "matrix"
    row_set: str
    col_set: str
    fields: list[ExtensionMatrixFieldSemantics] = Field(min_length=1)


ExtensionInputShapeSemantics = Annotated[
    ExtensionTableInputSemantics | ExtensionMatrixInputSemantics,
    Field(discriminator="kind"),
]


class ExtensionInputStepSemantics(BaseModel):
    """One wizard step in the normalized extension semantics layer."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    scalars: list[ExtensionScalarInputSemantics] = Field(default_factory=list)
    vectors: list[ExtensionVectorInputSemantics] = Field(default_factory=list)
    shape: ExtensionInputShapeSemantics | None = None
    example_command: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ExtensionInputStepSemantics":
        variants = int(bool(self.scalars or self.vectors)) + int(self.shape is not None)
        if variants != 1:
            raise ValueError(
                "ExtensionInputStepSemantics must declare either scalars/vectors or one shape"
            )
        return self


class ExtensionSummaryDisplaySemantics(BaseModel):
    """One scalar result view item."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["summary"] = "summary"
    id: str
    label: str | None = None
    expr: str


class ExtensionDisplayColumnSemantics(BaseModel):
    """One display column in a 1-D table result view."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    expr: str


class ExtensionTableDisplaySemantics(BaseModel):
    """One 1-D row-iterated result table."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["table"] = "table"
    id: str
    label: str | None = None
    rows: str
    columns: list[ExtensionDisplayColumnSemantics] = Field(min_length=1)


class ExtensionMatrixDisplaySemantics(BaseModel):
    """One matrix-style result view compiled into a generic table block."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["matrix"] = "matrix"
    id: str
    label: str | None = None
    rows: str
    cols: str
    cell: str


class ExtensionDisplaySemantics(BaseModel):
    """Normalized student-facing display layer for a declarative extension."""

    model_config = ConfigDict(extra="forbid")

    summary: list[ExtensionSummaryDisplaySemantics] = Field(default_factory=list)
    tables: list[ExtensionTableDisplaySemantics] = Field(default_factory=list)
    matrices: list[ExtensionMatrixDisplaySemantics] = Field(default_factory=list)


class ExtensionBundleSemantics(BaseModel):
    """Typed semantics payload for declarative extension runtimes."""

    model_config = ConfigDict(extra="forbid")

    supported: bool = True
    mode: Literal["declarative_bundle"] = "declarative_bundle"
    alias: str
    dsl_format: str
    wizard_mode: Literal["linear"] = "linear"
    stage_ids: list[str] = Field(default_factory=list)
    symbols: list[ExtensionSymbolSemantics] = Field(default_factory=list)
    inputs: list[ExtensionInputStepSemantics] = Field(default_factory=list)
    display: ExtensionDisplaySemantics = Field(default_factory=ExtensionDisplaySemantics)
