"""Typed public models for extension manifests and result presentation."""

from __future__ import annotations

import re
from collections import deque
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


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
