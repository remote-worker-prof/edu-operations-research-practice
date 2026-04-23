"""Declarative extension bundles backed by YAML + ORX LP models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from extension_api import (
    ExtensionArtifactSemantics,
    ExtensionBundleSemantics,
    ExtensionDisplayColumnSemantics,
    ExtensionDisplaySemantics,
    ExtensionFieldSemantics,
    ExtensionInputStepSemantics,
    ExtensionManifest,
    ExtensionMatrixDisplaySemantics,
    ExtensionMatrixFieldSemantics,
    ExtensionMatrixInputSemantics,
    ExtensionResultSection,
    ExtensionScalarInputSemantics,
    ExtensionStageSemantics,
    ExtensionSummaryDisplaySemantics,
    ExtensionSymbolSemantics,
    ExtensionTableColumnSemantics,
    ExtensionTableDisplaySemantics,
    ExtensionTableInputSemantics,
    ExtensionTableKeySemantics,
    ExtensionVectorInputSemantics,
    FieldSpec,
    JsonBlock,
    KVBlock,
    KVItem,
    ListBlock,
    StageSpec,
    SummaryBlock,
    TableBlock,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_core.declarative_orx import (
    BoundModelInput,
    CompiledModel,
    compile_orx_model,
    parse_orx_model,
    solve_compiled_model,
)
from agent_core.declarative_orx_v2 import parse_orx_expr_v2, parse_orx_model_v2
from agent_core.orx_metamodel import (
    BinaryExpr,
    Expr,
    IndexedExpr,
    IteratorBinding,
    ModelProgram,
    NameExpr,
    NumberExpr,
    ParamDecl,
    ReportFieldDecl,
    ScalarReportDecl,
    SumExpr,
    TableReportDecl,
    UnaryExpr,
)


class DeclarativeBundleError(ValueError):
    """Raised when a declarative extension bundle is malformed."""


class _ExtensionMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    title: str
    description: str
    version: str = "0.1.0"
    default_preset: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    stage_aliases: dict[str, list[str]] = Field(default_factory=dict)
    ui_metadata: dict[str, Any] = Field(default_factory=dict)


class _StageFieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    label: str
    description: str | None = None
    required: bool = True
    value_type: str | None = None
    aliases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class _StageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    label: str
    depends_on: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    fields: list[_StageFieldConfig] = Field(default_factory=list)


class _SetBindingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(alias="from")
    default: list[str] | None = None


class _ParamBindingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(alias="from")
    index_set: str | None = None
    index_sets: tuple[str, ...] | None = None
    default: Any = None

    @model_validator(mode="after")
    def validate_index_sets(self) -> "_ParamBindingConfig":
        if self.index_set is not None:
            expected = (self.index_set,)
            if self.index_sets is None:
                self.index_sets = expected
            elif self.index_sets != expected:
                raise ValueError("index_set and index_sets must describe the same 1-D binding")
        return self

    @property
    def declared_index_sets(self) -> tuple[str, ...]:
        if self.index_sets is not None:
            return tuple(self.index_sets)
        if self.index_set is not None:
            return (self.index_set,)
        return ()


class _BindingsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sets: dict[str, _SetBindingConfig] = Field(default_factory=dict)
    params: dict[str, _ParamBindingConfig] = Field(default_factory=dict)


class _KVItemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    report: str


class _SummaryBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["summary"] = "summary"
    title: str | None = None
    text: str


class _KVBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["kv"] = "kv"
    title: str | None = None
    items: list[_KVItemConfig]


class _TableColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    field: str


class _TableBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["table"] = "table"
    title: str | None = None
    report: str
    columns: list[_TableColumnConfig]


class _MatrixBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["matrix"] = "matrix"
    title: str | None = None
    report: str
    row_label: str = "Строка"
    row_field: str
    col_field: str
    value_field: str


class _ListBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["list"] = "list"
    title: str | None = None
    report: str


class _JsonBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["json"] = "json"
    title: str | None = None
    report: str


_ResultBlockConfig = Annotated[
    _SummaryBlockConfig
    | _KVBlockConfig
    | _TableBlockConfig
    | _MatrixBlockConfig
    | _ListBlockConfig
    | _JsonBlockConfig,
    Field(discriminator="type"),
]


class _ResultSectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    blocks: list[_ResultBlockConfig]


class _ResultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[_ResultSectionConfig]


class _TextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallback_explain_template: str | None = None
    llm_explain_prompt_template: str | None = None


class DeclarativeBundleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["expert_v1"] = "expert_v1"
    extension: _ExtensionMetaConfig
    stages: list[_StageConfig]
    bindings: _BindingsConfig
    results: _ResultsConfig
    presets: dict[str, str] = Field(default_factory=dict)
    text: _TextConfig = Field(default_factory=_TextConfig)

    @model_validator(mode="after")
    def validate_default_preset(self) -> "DeclarativeBundleConfig":
        default_preset = self.extension.default_preset
        if default_preset is not None and default_preset not in self.presets:
            raise ValueError(f"extension.default_preset `{default_preset}` must exist in presets")
        return self


class _StudentExtensionMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    title: str
    description: str
    version: str = "0.1.0"
    default_preset: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class _StudentFieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    help: str | None = None
    type: Literal["number", "string", "list[number]", "list[string]"]
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: str | int | float | bool | list[str] | list[float] | None = None
    bind: str | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentTableKeyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    help: str | None = None
    example: str | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentTableColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    help: str | None = None
    type: Literal["number", "string"]
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: str | int | float | bool | None = None
    bind: str | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentTableConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    set: str
    key: _StudentTableKeyConfig
    columns: list[_StudentTableColumnConfig] = Field(min_length=1)


class _StudentStepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    fields: list[_StudentFieldConfig] = Field(default_factory=list)
    table: _StudentTableConfig | None = None

    @model_validator(mode="after")
    def validate_step_shape(self) -> "_StudentStepConfig":
        has_fields = bool(self.fields)
        has_table = self.table is not None
        if has_fields == has_table:
            raise ValueError("wizard step must declare either `fields` or `table`, but not both")
        return self


class _StudentResultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show: list[str] = Field(min_length=1)


class StudentBundleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["student_v1"] = "student_v1"
    extension: _StudentExtensionMetaConfig
    wizard: list[_StudentStepConfig] = Field(min_length=1)
    results: _StudentResultsConfig
    presets: dict[str, str] = Field(default_factory=dict)
    text: _TextConfig = Field(default_factory=_TextConfig)

    @model_validator(mode="after")
    def validate_default_preset(self) -> "StudentBundleConfig":
        default_preset = self.extension.default_preset
        if default_preset is not None and default_preset not in self.presets:
            raise ValueError(f"extension.default_preset `{default_preset}` must exist in presets")
        return self


class _StudentMathExtensionMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    title: str
    description: str
    version: str = "0.1.0"
    default_preset: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    stage_aliases: dict[str, list[str]] = Field(default_factory=dict)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)


class _StudentMathScalarInputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    param: str
    field: str | None = None
    label: str
    help: str | None = None
    type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: str | int | float | bool | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentMathVectorInputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    param: str
    over: str
    field: str | None = None
    label: str
    help: str | None = None
    type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: list[str] | list[float] | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentMathTableKeyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    label: str
    help: str | None = None
    example: str | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentMathTableColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    param: str
    field: str | None = None
    label: str
    help: str | None = None
    type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: str | int | float | bool | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentMathTableInputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: str
    key: _StudentMathTableKeyConfig
    columns: list[_StudentMathTableColumnConfig] = Field(min_length=1)


class _StudentMathMatrixFieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    param: str
    field: str | None = None
    label: str
    help: str | None = None
    type: Literal["number", "string"] = "number"
    required: bool = True
    min: float | None = None
    max: float | None = None
    example: list[list[float]] | list[list[str]] | None = None
    aliases: list[str] = Field(default_factory=list)


class _StudentMathMatrixInputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows_set: str
    cols_set: str
    fields: list[_StudentMathMatrixFieldConfig] = Field(min_length=1)


class _StudentMathInputStepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    params: list[_StudentMathScalarInputConfig] = Field(default_factory=list)
    vectors: list[_StudentMathVectorInputConfig] = Field(default_factory=list)
    table: _StudentMathTableInputConfig | None = None
    matrix: _StudentMathMatrixInputConfig | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "_StudentMathInputStepConfig":
        variants = (
            int(bool(self.params or self.vectors))
            + int(self.table is not None)
            + int(self.matrix is not None)
        )
        if variants != 1:
            raise ValueError(
                "inputs step must declare either (`params`/`vectors`), one `table`, or one `matrix`"
            )
        return self


class _StudentMathSummaryDisplayItemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    expr: str
    label: str | None = None


class _StudentMathTableDisplayColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    expr: str
    label: str | None = None


class _StudentMathTableDisplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rows: str
    label: str | None = None
    columns: list[_StudentMathTableDisplayColumnConfig] = Field(min_length=1)


class _StudentMathMatrixDisplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rows: str
    cols: str
    cell: str
    label: str | None = None


class _StudentMathDisplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: list[_StudentMathSummaryDisplayItemConfig] = Field(default_factory=list)
    tables: list[_StudentMathTableDisplayConfig] = Field(default_factory=list)
    matrices: list[_StudentMathMatrixDisplayConfig] = Field(default_factory=list)


class StudentMathBundleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["student_math_v2"] = "student_math_v2"
    extension: _StudentMathExtensionMetaConfig
    inputs: list[_StudentMathInputStepConfig] = Field(min_length=1)
    display: _StudentMathDisplayConfig = Field(default_factory=_StudentMathDisplayConfig)
    presets: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_default_preset(self) -> "StudentMathBundleConfig":
        default_preset = self.extension.default_preset
        if default_preset is not None and default_preset not in self.presets:
            raise ValueError(f"extension.default_preset `{default_preset}` must exist in presets")
        return self


@dataclass(frozen=True, slots=True)
class DeclarativeBundle:
    root_path: Path
    config: DeclarativeBundleConfig
    manifest: ExtensionManifest
    model: CompiledModel
    semantics: ExtensionBundleSemantics | None = None


class DeclarativeExtensionProvider:
    """Adapter that exposes a declarative bundle through the existing provider contract."""

    def __init__(self, bundle: DeclarativeBundle) -> None:
        self._bundle = bundle

    def get_manifest(self) -> ExtensionManifest:
        return self._bundle.manifest

    def create_runtime(self) -> "DeclarativeExtensionRuntime":
        return DeclarativeExtensionRuntime(self._bundle)

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, Any]]:
        try:
            relative_path = self._bundle.config.presets[preset_ref]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported preset `{preset_ref}` for declarative extension "
                f"`{self._bundle.manifest.alias}`"
            ) from exc
        preset_path = self._bundle.root_path / relative_path
        payload = _load_yaml_file(preset_path)
        if not isinstance(payload, dict):
            raise DeclarativeBundleError(
                f"Preset `{preset_ref}` in `{preset_path}` must be a stage payload mapping"
            )
        normalized: dict[str, dict[str, Any]] = {}
        for stage_id, stage_payload in payload.items():
            if not isinstance(stage_id, str) or not isinstance(stage_payload, dict):
                raise DeclarativeBundleError(
                    f"Preset `{preset_ref}` contains invalid stage payload `{stage_id!r}`"
                )
            normalized[stage_id] = dict(stage_payload)
        return normalized


class DeclarativeExtensionRuntime:
    """Generic runtime for YAML + ORX extension bundles."""

    def __init__(self, bundle: DeclarativeBundle) -> None:
        self._bundle = bundle
        self.manifest = bundle.manifest

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        errors = {stage.stage_id: [] for stage in self._bundle.config.stages}
        for stage in self._bundle.config.stages:
            payload = draft.get(stage.stage_id)
            stage_payload = payload if isinstance(payload, dict) else {}
            for field in stage.fields:
                if field.field_path not in stage_payload:
                    if field.required:
                        errors[stage.stage_id].append(
                            f"Поле {stage.stage_id}.{field.field_path} обязательно."
                        )
                    continue
                errors[stage.stage_id].extend(
                    _validate_field_value(
                        stage_id=stage.stage_id,
                        field=field,
                        value=stage_payload[field.field_path],
                        schema=stage.input_schema.get(field.field_path),
                    )
                )
        _, binding_errors = self._resolve_bound_input(draft, collect_errors=True)
        for stage_id, stage_errors in binding_errors.items():
            errors[stage_id].extend(stage_errors)
        return errors

    def build_runtime_input(self, draft: dict[str, object]) -> BoundModelInput:
        bound_input, errors = self._resolve_bound_input(draft, collect_errors=False)
        if errors:
            joined = "; ".join(
                f"{stage_id}: {', '.join(messages)}"
                for stage_id, messages in errors.items()
                if messages
            )
            raise DeclarativeBundleError(f"Draft is not valid for declarative extension: {joined}")
        assert bound_input is not None
        return bound_input

    def run(self, runtime_input: object) -> dict[str, Any]:
        if not isinstance(runtime_input, BoundModelInput):
            raise TypeError("DeclarativeExtensionRuntime expects BoundModelInput runtime_input")
        result = solve_compiled_model(self._bundle.model, runtime_input)
        return result.result_payload

    def fallback_explain(self, result: object) -> str:
        template = self._bundle.config.text.fallback_explain_template
        if template:
            return template.format(**_template_context(result))
        if isinstance(result, dict) and "objective_value" in result:
            return (
                "Декларативная LP-модель успешно решена. "
                f"Значение целевой функции: {result['objective_value']}."
            )
        return "Декларативная LP-модель успешно решена."

    def build_llm_explain_prompt(self, result: object) -> str:
        template = self._bundle.config.text.llm_explain_prompt_template
        if template:
            return template.format(**_template_context(result))
        return (
            f"Explain the result of declarative extension `{self._bundle.manifest.alias}` "
            f"for students. Result: {result!r}"
        )

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        if not isinstance(result, dict):
            return []
        sections: list[ExtensionResultSection] = []
        for section in self._bundle.config.results.sections:
            blocks: list[Any] = []
            for block in section.blocks:
                if isinstance(block, _SummaryBlockConfig):
                    blocks.append(SummaryBlock(title=block.title, text=block.text))
                elif isinstance(block, _KVBlockConfig):
                    items = [
                        KVItem(key=item.key, value=result.get(item.report)) for item in block.items
                    ]
                    blocks.append(KVBlock(title=block.title, items=items))
                elif isinstance(block, _TableBlockConfig):
                    rows_payload = result.get(block.report, [])
                    rows = [
                        [row.get(column.field) for column in block.columns]
                        for row in rows_payload
                        if isinstance(row, dict)
                    ]
                    blocks.append(
                        TableBlock(
                            title=block.title,
                            columns=[column.label for column in block.columns],
                            rows=rows,
                        )
                    )
                elif isinstance(block, _MatrixBlockConfig):
                    rows_payload = result.get(block.report, [])
                    columns, rows = _pivot_matrix_rows(
                        rows_payload=rows_payload,
                        row_label=block.row_label,
                        row_field=block.row_field,
                        col_field=block.col_field,
                        value_field=block.value_field,
                    )
                    blocks.append(
                        TableBlock(
                            title=block.title,
                            columns=columns,
                            rows=rows,
                        )
                    )
                elif isinstance(block, _ListBlockConfig):
                    items = result.get(block.report, [])
                    blocks.append(
                        ListBlock(
                            title=block.title,
                            items=[str(item) for item in items] if isinstance(items, list) else [],
                        )
                    )
                elif isinstance(block, _JsonBlockConfig):
                    blocks.append(JsonBlock(title=block.title, value=result.get(block.report)))
                else:  # pragma: no cover - exhaustive union guard
                    raise DeclarativeBundleError(f"Unsupported declarative result block: {block!r}")
            sections.append(
                ExtensionResultSection(
                    section_id=section.section_id,
                    title=section.title,
                    blocks=blocks,
                )
            )
        return sections

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        del draft
        return []

    def build_nl_semantics(self) -> dict[str, object]:
        if self._bundle.semantics is not None:
            semantics = self._bundle.semantics
        else:
            semantics = _build_bundle_semantics_from_compiled_config(
                config=self._bundle.config,
                model=self._bundle.model,
            )
        if not semantics.artifacts:
            semantics = semantics.model_copy(
                update={"artifacts": _build_bundle_artifacts(self._bundle.root_path, semantics)}
            )
        return semantics.model_dump(mode="json")

    def _resolve_bound_input(
        self,
        draft: dict[str, object],
        *,
        collect_errors: bool,
    ) -> tuple[BoundModelInput | None, dict[str, list[str]]]:
        errors = {stage.stage_id: [] for stage in self._bundle.config.stages}
        set_values: dict[str, tuple[str, ...]] = {}
        params: dict[str, float | dict[str, float] | dict[tuple[str, ...], float]] = {}

        for set_name, binding in self._bundle.config.bindings.sets.items():
            stage_id, field_path = _split_source_path(binding.source)
            value, has_value = _extract_draft_value(
                draft=draft,
                stage_id=stage_id,
                field_path=field_path,
            )
            if not has_value:
                value = binding.default
            if value is None:
                errors[stage_id].append(
                    f"Не заполнена binding source `{binding.source}` для set `{set_name}`."
                )
                continue
            normalized = _coerce_string_list(value)
            if normalized is None:
                errors[stage_id].append(
                    f"Поле {binding.source} должно быть непустым списком строк "
                    f"для set `{set_name}`."
                )
                continue
            if len(set(normalized)) != len(normalized):
                errors[stage_id].append(
                    f"Поле {binding.source} содержит дубли, "
                    f"а set `{set_name}` требует уникальные ключи."
                )
                continue
            set_values[set_name] = tuple(normalized)

        for declaration in self._bundle.model.required_input_params:
            binding = self._bundle.config.bindings.params.get(declaration.name)
            if binding is None:
                continue
            stage_id, field_path = _split_source_path(binding.source)
            value, has_value = _extract_draft_value(
                draft=draft,
                stage_id=stage_id,
                field_path=field_path,
            )
            if not has_value:
                value = binding.default
            if value is None:
                errors[stage_id].append(
                    f"Не заполнена binding source `{binding.source}` "
                    f"для param `{declaration.name}`."
                )
                continue
            if not declaration.index_sets:
                if not isinstance(value, (int, float)):
                    errors[stage_id].append(
                        f"Поле {binding.source} должно быть числом для param `{declaration.name}`."
                    )
                    continue
                params[declaration.name] = float(value)
                continue

            declared_index_sets = binding.declared_index_sets or declaration.index_sets
            if declared_index_sets != declaration.index_sets:
                errors[stage_id].append(
                    f"Binding `{declaration.name}` должен ссылаться на множества "
                    f"`{declaration.index_sets}`, а не `{declared_index_sets}`."
                )
                continue

            if len(declaration.index_sets) == 1:
                normalized_list = _coerce_number_list(value)
                if normalized_list is None:
                    errors[stage_id].append(
                        f"Поле {binding.source} должно быть непустым списком чисел "
                        f"для param `{declaration.name}`."
                    )
                    continue
                index_set = declaration.index_sets[0]
                keys = set_values.get(index_set)
                if keys is None:
                    errors[stage_id].append(
                        f"Сначала должен быть разрешён set `{index_set}` "
                        f"для param `{declaration.name}`."
                    )
                    continue
                if len(normalized_list) != len(keys):
                    errors[stage_id].append(
                        f"Длина {binding.source} должна совпадать с размером set `{index_set}`."
                    )
                    continue
                params[declaration.name] = {
                    key: float(item) for key, item in zip(keys, normalized_list, strict=True)
                }
                continue

            if len(declaration.index_sets) == 2:
                normalized_matrix = _coerce_number_matrix(value)
                if normalized_matrix is None:
                    errors[stage_id].append(
                        f"Поле {binding.source} должно быть прямоугольной матрицей чисел "
                        f"для param `{declaration.name}`."
                    )
                    continue
                row_set, col_set = declaration.index_sets
                row_keys = set_values.get(row_set)
                if row_keys is None:
                    errors[stage_id].append(
                        f"Сначала должен быть разрешён set `{row_set}` "
                        f"для матрицы `{declaration.name}`."
                    )
                    continue
                col_keys = set_values.get(col_set)
                if col_keys is None:
                    errors[stage_id].append(
                        f"Сначала должен быть разрешён set `{col_set}` "
                        f"для матрицы `{declaration.name}`."
                    )
                    continue
                if len(normalized_matrix) != len(row_keys):
                    errors[stage_id].append(
                        f"Число строк в {binding.source} должно совпадать с размером set "
                        f"`{row_set}`."
                    )
                    continue
                if any(len(row) != len(col_keys) for row in normalized_matrix):
                    errors[stage_id].append(
                        f"Каждая строка {binding.source} должна содержать ровно "
                        f"{len(col_keys)} значений по set `{col_set}`."
                    )
                    continue
                params[declaration.name] = {
                    (row_key, col_key): float(normalized_matrix[row_index][col_index])
                    for row_index, row_key in enumerate(row_keys)
                    for col_index, col_key in enumerate(col_keys)
                }
                continue

            errors[stage_id].append(
                f"Param `{declaration.name}` имеет арность {len(declaration.index_sets)}, "
                "а student_math_v2 сейчас поддерживает только scalar, vector и matrix (2-D) ввод."
            )

        populated_errors = {stage_id: messages for stage_id, messages in errors.items() if messages}
        if populated_errors:
            return None, errors if collect_errors else populated_errors
        return BoundModelInput(sets=set_values, params=params), {}


def _load_bundle_config(
    *, raw_config: dict[str, object], model: CompiledModel, config_path: Path
) -> DeclarativeBundleConfig:
    raw_format = raw_config.get("format", "expert_v1")
    if raw_format == "expert_v1":
        try:
            return DeclarativeBundleConfig.model_validate(raw_config)
        except Exception as exc:  # pragma: no cover - pydantic keeps detailed context already
            raise DeclarativeBundleError(
                f"Invalid declarative config `{config_path}`: {exc}"
            ) from exc
    if raw_format == "student_v1":
        try:
            student_config = StudentBundleConfig.model_validate(raw_config)
        except Exception as exc:  # pragma: no cover - pydantic keeps detailed context already
            raise DeclarativeBundleError(
                f"Invalid student declarative config `{config_path}`: {exc}"
            ) from exc
        return _compile_student_bundle_config(student_config, model=model)
    raise DeclarativeBundleError(
        f"Unsupported declarative format `{raw_format}` in `{config_path}`. "
        "Используйте `student_math_v2`, `student_v1` или `expert_v1`."
    )


def _load_bundle_artifacts(
    *,
    raw_config: dict[str, object],
    model_source: str,
    config_path: Path,
) -> tuple[DeclarativeBundleConfig, CompiledModel, ExtensionBundleSemantics | None]:
    raw_format = raw_config.get("format", "expert_v1")
    if raw_format == "student_math_v2":
        try:
            student_math_config = StudentMathBundleConfig.model_validate(raw_config)
        except Exception as exc:  # pragma: no cover - pydantic keeps detailed context already
            raise DeclarativeBundleError(
                f"Invalid student_math_v2 declarative config `{config_path}`: {exc}"
            ) from exc
        base_model = compile_orx_model(parse_orx_model_v2(model_source))
        return _compile_student_math_bundle_config(student_math_config, model=base_model)

    base_model = compile_orx_model(parse_orx_model(model_source))
    return (
        _load_bundle_config(
            raw_config=raw_config,
            model=base_model,
            config_path=config_path,
        ),
        base_model,
        None,
    )


def _compile_student_bundle_config(
    config: StudentBundleConfig, *, model: CompiledModel
) -> DeclarativeBundleConfig:
    stages: list[_StageConfig] = []
    set_bindings: dict[str, _SetBindingConfig] = {}
    param_bindings: dict[str, _ParamBindingConfig] = {}
    step_ids: list[str] = []
    for index, step in enumerate(config.wizard):
        depends_on = [config.wizard[index - 1].id] if index > 0 else []
        step_ids.append(step.id)
        if step.table is not None:
            stage_config, stage_set_bindings, stage_param_bindings = _compile_student_table_step(
                step=step, model=model, depends_on=depends_on
            )
        else:
            stage_config, stage_set_bindings, stage_param_bindings = _compile_student_field_step(
                step=step, model=model, depends_on=depends_on
            )
        stages.append(stage_config)
        for set_name, binding in stage_set_bindings.items():
            existing = set_bindings.get(set_name)
            if existing is not None and existing != binding:
                raise DeclarativeBundleError(
                    f"student_v1 пытается по-разному заполнить множество `{set_name}`"
                )
            set_bindings[set_name] = binding
        for param_name, binding in stage_param_bindings.items():
            existing = param_bindings.get(param_name)
            if existing is not None and existing != binding:
                raise DeclarativeBundleError(
                    f"student_v1 пытается по-разному заполнить параметр `{param_name}`"
                )
            param_bindings[param_name] = binding

    extension_examples = _student_manifest_examples(config)
    extension_labels = dict(config.extension.labels)
    ui_metadata = {
        "kind": config.extension.alias,
        "dsl_format": "student_v1",
        "wizard_mode": "linear",
        "wizard_steps": step_ids,
    }
    return DeclarativeBundleConfig(
        format="expert_v1",
        extension=_ExtensionMetaConfig(
            alias=config.extension.alias,
            title=config.extension.title,
            description=config.extension.description,
            version=config.extension.version,
            default_preset=config.extension.default_preset,
            labels=extension_labels,
            examples=extension_examples,
            ui_metadata=ui_metadata,
        ),
        stages=stages,
        bindings=_BindingsConfig(sets=set_bindings, params=param_bindings),
        results=_compile_student_results(config.results, model=model, labels=extension_labels),
        presets=config.presets,
        text=config.text,
    )


def _compile_student_field_step(
    *,
    step: _StudentStepConfig,
    model: CompiledModel,
    depends_on: list[str],
) -> tuple[_StageConfig, dict[str, _SetBindingConfig], dict[str, _ParamBindingConfig]]:
    input_schema: dict[str, Any] = {}
    fields: list[_StageFieldConfig] = []
    param_bindings: dict[str, _ParamBindingConfig] = {}
    for field in step.fields:
        target = field.bind or field.id
        declaration = _student_param_target(
            name=target,
            model=model,
            context=f"{step.id}.{field.id}",
        )
        input_schema[field.id] = _student_field_schema(field)
        fields.append(
            _StageFieldConfig(
                field_path=field.id,
                label=field.label,
                description=field.help,
                required=field.required,
                value_type=field.type,
                aliases=_student_field_aliases(field.id, explicit_aliases=field.aliases),
                examples=_student_examples(field.example),
            )
        )
        binding = _ParamBindingConfig(
            **{
                "from": f"{step.id}.{field.id}",
                **(
                    {"index_set": declaration.index_set}
                    if declaration.index_set is not None
                    else {}
                ),
            }
        )
        existing = param_bindings.get(declaration.name)
        if existing is not None and existing != binding:
            raise DeclarativeBundleError(
                f"Поле `{step.id}.{field.id}` конфликтует с другой привязкой параметра "
                f"`{declaration.name}`."
            )
        param_bindings[declaration.name] = binding

    return (
        _StageConfig(
            stage_id=step.id,
            label=step.label,
            depends_on=depends_on,
            aliases=_student_stage_aliases(step.id, step.label, explicit_aliases=step.aliases),
            examples=_student_stage_examples(step),
            input_schema=input_schema,
            fields=fields,
        ),
        {},
        param_bindings,
    )


def _compile_student_table_step(
    *,
    step: _StudentStepConfig,
    model: CompiledModel,
    depends_on: list[str],
) -> tuple[_StageConfig, dict[str, _SetBindingConfig], dict[str, _ParamBindingConfig]]:
    table = step.table
    assert table is not None
    if table.set not in model.set_names:
        raise DeclarativeBundleError(
            f"Таблица `{step.id}.{table.id}` ссылается на неизвестное множество `{table.set}`."
        )

    input_schema: dict[str, Any] = {
        table.key.id: {
            "min_items": 1,
            "unique": True,
        }
    }
    fields: list[_StageFieldConfig] = [
        _StageFieldConfig(
            field_path=table.key.id,
            label=table.key.label,
            description=table.key.help,
            required=True,
            value_type="list[string]",
            aliases=_student_field_aliases(table.key.id, explicit_aliases=table.key.aliases),
            examples=_student_examples(
                [table.key.example] if table.key.example is not None else None
            ),
        )
    ]
    param_bindings: dict[str, _ParamBindingConfig] = {}
    for column in table.columns:
        declaration = _student_param_target(
            name=column.bind or column.id,
            model=model,
            context=f"{step.id}.{column.id}",
        )
        if declaration.index_set is None:
            raise DeclarativeBundleError(
                f"Колонка `{step.id}.{column.id}` должна быть связана с векторным param, "
                f"а `{declaration.name}` является scalar param."
            )
        if declaration.index_set != table.set:
            raise DeclarativeBundleError(
                f"Колонка `{step.id}.{column.id}` должна ссылаться на set `{table.set}`, "
                f"а param `{declaration.name}` ожидает `{declaration.index_set}`."
            )
        input_schema[column.id] = _student_table_column_schema(column)
        fields.append(
            _StageFieldConfig(
                field_path=column.id,
                label=column.label,
                description=column.help,
                required=column.required,
                value_type=f"list[{column.type}]",
                aliases=_student_field_aliases(column.id, explicit_aliases=column.aliases),
                examples=_student_examples(
                    [column.example] if column.example is not None else None
                ),
            )
        )
        param_bindings[declaration.name] = _ParamBindingConfig(
            **{
                "from": f"{step.id}.{column.id}",
                "index_set": table.set,
            }
        )

    return (
        _StageConfig(
            stage_id=step.id,
            label=step.label,
            depends_on=depends_on,
            aliases=_student_stage_aliases(step.id, step.label, explicit_aliases=step.aliases),
            examples=_student_stage_examples(step),
            input_schema=input_schema,
            fields=fields,
        ),
        {table.set: _SetBindingConfig(**{"from": f"{step.id}.{table.key.id}"})},
        param_bindings,
    )


def _compile_student_results(
    config: _StudentResultsConfig,
    *,
    model: CompiledModel,
    labels: dict[str, str],
) -> _ResultsConfig:
    scalar_reports = {report.name for report in model.scalar_reports}
    table_reports = {report.name: report for report in model.table_reports}
    sections: list[_ResultSectionConfig] = []
    seen: set[str] = set()
    for report_name in config.show:
        if report_name in seen:
            raise DeclarativeBundleError(
                f"results.show содержит дублирующийся report `{report_name}`"
            )
        seen.add(report_name)
        title = labels.get(report_name, _humanize_identifier(report_name))
        section_id = f"student-report-{report_name}"
        if report_name in scalar_reports:
            sections.append(
                _ResultSectionConfig(
                    section_id=section_id,
                    title=title,
                    blocks=[
                        _KVBlockConfig(
                            title=None,
                            items=[_KVItemConfig(key=title, report=report_name)],
                        )
                    ],
                )
            )
            continue
        report = table_reports.get(report_name)
        if report is None:
            raise DeclarativeBundleError(
                f"results.show ссылается на неизвестный report `{report_name}`."
            )
        sections.append(
            _ResultSectionConfig(
                section_id=section_id,
                title=title,
                blocks=[
                    _TableBlockConfig(
                        title=None,
                        report=report_name,
                        columns=[
                            _TableColumnConfig(
                                label=labels.get(
                                    f"{report_name}.{field.name}",
                                    _humanize_identifier(field.name),
                                ),
                                field=field.name,
                            )
                            for field in report.fields
                        ],
                    )
                ],
            )
        )
    return _ResultsConfig(sections=sections)


def _compile_student_math_bundle_config(
    config: StudentMathBundleConfig,
    *,
    model: CompiledModel,
) -> tuple[DeclarativeBundleConfig, CompiledModel, ExtensionBundleSemantics]:
    semantics = _build_student_math_bundle_semantics(config=config, model=model)
    stages: list[_StageConfig] = []
    set_bindings: dict[str, _SetBindingConfig] = {}
    param_bindings: dict[str, _ParamBindingConfig] = {}
    step_ids: list[str] = []
    for index, step in enumerate(semantics.inputs):
        depends_on = [semantics.inputs[index - 1].step_id] if index > 0 else []
        step_ids.append(step.step_id)
        if step.shape is None:
            stage_config, stage_set_bindings, stage_param_bindings = (
                _compile_student_math_param_step(
                    step=step,
                    depends_on=depends_on,
                )
            )
        elif isinstance(step.shape, ExtensionTableInputSemantics):
            stage_config, stage_set_bindings, stage_param_bindings = (
                _compile_student_math_table_step(
                    step=step,
                    depends_on=depends_on,
                )
            )
        else:
            stage_config, stage_set_bindings, stage_param_bindings = (
                _compile_student_math_matrix_step(
                    step=step,
                    depends_on=depends_on,
                )
            )
        stages.append(stage_config)
        for set_name, binding in stage_set_bindings.items():
            existing = set_bindings.get(set_name)
            if existing is not None and existing != binding:
                raise DeclarativeBundleError(
                    f"student_math_v2 пытается по-разному заполнить множество `{set_name}`"
                )
            set_bindings[set_name] = binding
        for param_name, binding in stage_param_bindings.items():
            existing = param_bindings.get(param_name)
            if existing is not None and existing != binding:
                raise DeclarativeBundleError(
                    f"student_math_v2 пытается по-разному заполнить параметр `{param_name}`"
                )
            param_bindings[param_name] = binding

    extension_examples = _student_math_manifest_examples(semantics)
    extension_labels = dict(config.extension.labels)
    _merge_student_math_display_labels(semantics.display, labels=extension_labels)
    synthetic_scalar_reports, synthetic_table_reports = _compile_student_math_display_reports(
        semantics.display
    )
    synthesized_model = compile_orx_model(
        ModelProgram(
            sets=model.sets,
            params=model.params,
            vars=model.vars,
            objective=model.objective,
            constraints=model.constraints,
            scalar_reports=synthetic_scalar_reports,
            table_reports=synthetic_table_reports,
        )
    )
    ui_metadata = {
        "kind": config.extension.alias,
        "dsl_format": "student_math_v2",
        "wizard_mode": "linear",
        "wizard_steps": step_ids,
        "math_notation": "ampl_like_lp",
    }
    compiled_config = DeclarativeBundleConfig(
        format="expert_v1",
        extension=_ExtensionMetaConfig(
            alias=config.extension.alias,
            title=config.extension.title,
            description=config.extension.description,
            version=config.extension.version,
            default_preset=config.extension.default_preset,
            labels=extension_labels,
            examples=extension_examples,
            field_aliases=config.extension.field_aliases,
            stage_aliases=config.extension.stage_aliases,
            ui_metadata=ui_metadata,
        ),
        stages=stages,
        bindings=_BindingsConfig(sets=set_bindings, params=param_bindings),
        results=_compile_student_math_results(
            display=semantics.display,
            labels=extension_labels,
        ),
        presets=config.presets,
        text=_TextConfig(),
    )
    return compiled_config, synthesized_model, semantics


def _build_student_math_bundle_semantics(
    *,
    config: StudentMathBundleConfig,
    model: CompiledModel,
) -> ExtensionBundleSemantics:
    inputs = [_build_student_math_step_semantics(step=step, model=model) for step in config.inputs]
    display = _build_student_math_display_semantics(
        config=config.display,
        model=model,
    )
    stages = [
        _build_stage_semantics_from_step(
            step=step_semantics,
            expectation_hint=_student_math_expectation_hint(step),
        )
        for step, step_semantics in zip(config.inputs, inputs, strict=False)
    ]
    return ExtensionBundleSemantics(
        alias=config.extension.alias,
        dsl_format="student_math_v2",
        stage_ids=[step.step_id for step in inputs],
        symbols=_build_student_math_symbol_catalog(model),
        inputs=inputs,
        display=display,
        stages=stages,
    )


def _build_student_math_symbol_catalog(model: CompiledModel) -> list[ExtensionSymbolSemantics]:
    symbols: list[ExtensionSymbolSemantics] = []
    for declaration in model.sets:
        symbols.append(ExtensionSymbolSemantics(name=declaration.name, kind="set"))
    for declaration in model.params:
        symbols.append(
            ExtensionSymbolSemantics(
                name=declaration.name,
                kind="param",
                dimensions=len(declaration.index_sets),
                index_sets=list(declaration.index_sets),
                required_input=declaration.expr is None,
                derived=declaration.expr is not None,
            )
        )
    for declaration in model.vars:
        symbols.append(
            ExtensionSymbolSemantics(
                name=declaration.name,
                kind="var",
                dimensions=len(declaration.index_sets),
                index_sets=list(declaration.index_sets),
            )
        )
    symbols.append(
        ExtensionSymbolSemantics(
            name=model.objective.name,
            kind="objective",
        )
    )
    return symbols


def _build_student_math_step_semantics(
    *,
    step: _StudentMathInputStepConfig,
    model: CompiledModel,
) -> ExtensionInputStepSemantics:
    if step.table is not None:
        semantics = _build_student_math_table_step_semantics(step=step, model=model)
    elif step.matrix is not None:
        semantics = _build_student_math_matrix_step_semantics(step=step, model=model)
    else:
        semantics = _build_student_math_param_step_semantics(step=step, model=model)
    return semantics.model_copy(
        update={"example_command": _student_math_step_example_command(semantics)}
    )


def _build_student_math_param_step_semantics(
    *,
    step: _StudentMathInputStepConfig,
    model: CompiledModel,
) -> ExtensionInputStepSemantics:
    scalars: list[ExtensionScalarInputSemantics] = []
    vectors: list[ExtensionVectorInputSemantics] = []

    for field in step.params:
        declaration = _student_param_target(
            name=field.param,
            model=model,
            context=f"{step.id}.{field.param}",
        )
        if declaration.index_sets:
            raise DeclarativeBundleError(
                f"`{step.id}.{field.param}` должен ссылаться на scalar param, "
                f"а `{declaration.name}` индексируется по {declaration.index_sets}."
            )
        field_path = field.field or field.param
        scalars.append(
            ExtensionScalarInputSemantics(
                param=declaration.name,
                field_path=field_path,
                label=field.label,
                help=field.help,
                value_type=field.type,
                required=field.required,
                min=field.min,
                max=field.max,
                aliases=_student_field_aliases(field_path, explicit_aliases=field.aliases),
                example=field.example,
            )
        )

    for field in step.vectors:
        declaration = _student_param_target(
            name=field.param,
            model=model,
            context=f"{step.id}.{field.param}",
        )
        if declaration.index_set is None:
            raise DeclarativeBundleError(
                f"`{step.id}.{field.param}` должен ссылаться на 1-D param, "
                f"а `{declaration.name}` имеет арность {len(declaration.index_sets)}."
            )
        if declaration.index_set != field.over:
            raise DeclarativeBundleError(
                f"`{step.id}.{field.param}` должен быть связан с set `{declaration.index_set}`, "
                f"а в inputs указан `{field.over}`."
            )
        field_path = field.field or field.param
        vectors.append(
            ExtensionVectorInputSemantics(
                param=declaration.name,
                over=declaration.index_set,
                field_path=field_path,
                label=field.label,
                help=field.help,
                value_type=field.type,
                required=field.required,
                min=field.min,
                max=field.max,
                aliases=_student_field_aliases(field_path, explicit_aliases=field.aliases),
                example=field.example,
            )
        )

    return ExtensionInputStepSemantics(
        step_id=step.id,
        label=step.label,
        aliases=_student_stage_aliases(step.id, step.label, explicit_aliases=step.aliases),
        scalars=scalars,
        vectors=vectors,
    )


def _build_student_math_table_step_semantics(
    *,
    step: _StudentMathInputStepConfig,
    model: CompiledModel,
) -> ExtensionInputStepSemantics:
    table = step.table
    assert table is not None
    if table.set not in model.set_names:
        raise DeclarativeBundleError(
            f"inputs.table для шага `{step.id}` ссылается на неизвестное множество `{table.set}`."
        )
    key_field_path = table.key.field or table.set.lower()
    key = ExtensionTableKeySemantics(
        set_name=table.set,
        field_path=key_field_path,
        label=table.key.label,
        help=table.key.help,
        aliases=_student_field_aliases(key_field_path, explicit_aliases=table.key.aliases),
        example=table.key.example,
    )
    columns: list[ExtensionTableColumnSemantics] = []
    for column in table.columns:
        declaration = _student_param_target(
            name=column.param,
            model=model,
            context=f"{step.id}.{column.param}",
        )
        if declaration.index_set != table.set:
            raise DeclarativeBundleError(
                f"Колонка `{step.id}.{column.param}` должна ссылаться на set `{table.set}`, "
                f"а param `{declaration.name}` ожидает `{declaration.index_set}`."
            )
        field_path = column.field or column.param
        columns.append(
            ExtensionTableColumnSemantics(
                param=declaration.name,
                set_name=table.set,
                field_path=field_path,
                label=column.label,
                help=column.help,
                value_type=column.type,
                required=column.required,
                min=column.min,
                max=column.max,
                aliases=_student_field_aliases(field_path, explicit_aliases=column.aliases),
                example=column.example,
            )
        )

    return ExtensionInputStepSemantics(
        step_id=step.id,
        label=step.label,
        aliases=_student_stage_aliases(step.id, step.label, explicit_aliases=step.aliases),
        shape=ExtensionTableInputSemantics(
            set_name=table.set,
            key=key,
            columns=columns,
        ),
    )


def _build_student_math_matrix_step_semantics(
    *,
    step: _StudentMathInputStepConfig,
    model: CompiledModel,
) -> ExtensionInputStepSemantics:
    matrix = step.matrix
    assert matrix is not None
    if matrix.rows_set not in model.set_names:
        raise DeclarativeBundleError(
            f"inputs.matrix для шага `{step.id}` ссылается на неизвестное множество "
            f"`{matrix.rows_set}`."
        )
    if matrix.cols_set not in model.set_names:
        raise DeclarativeBundleError(
            f"inputs.matrix для шага `{step.id}` ссылается на неизвестное множество "
            f"`{matrix.cols_set}`."
        )
    fields: list[ExtensionMatrixFieldSemantics] = []
    for field in matrix.fields:
        declaration = _student_param_target(
            name=field.param,
            model=model,
            context=f"{step.id}.{field.param}",
        )
        expected_sets = (matrix.rows_set, matrix.cols_set)
        if declaration.index_sets != expected_sets:
            raise DeclarativeBundleError(
                f"`{step.id}.{field.param}` должен ссылаться на 2-D param по "
                f"`{expected_sets}`, а `{declaration.name}` ожидает {declaration.index_sets}."
            )
        field_path = field.field or field.param
        fields.append(
            ExtensionMatrixFieldSemantics(
                param=declaration.name,
                row_set=matrix.rows_set,
                col_set=matrix.cols_set,
                field_path=field_path,
                label=field.label,
                help=field.help,
                value_type=field.type,
                required=field.required,
                min=field.min,
                max=field.max,
                aliases=_student_field_aliases(field_path, explicit_aliases=field.aliases),
                example=field.example,
            )
        )

    return ExtensionInputStepSemantics(
        step_id=step.id,
        label=step.label,
        aliases=_student_stage_aliases(step.id, step.label, explicit_aliases=step.aliases),
        shape=ExtensionMatrixInputSemantics(
            row_set=matrix.rows_set,
            col_set=matrix.cols_set,
            fields=fields,
        ),
    )


def _build_student_math_display_semantics(
    *,
    config: _StudentMathDisplayConfig,
    model: CompiledModel,
) -> ExtensionDisplaySemantics:
    summary = [
        ExtensionSummaryDisplaySemantics(id=item.id, label=item.label, expr=item.expr)
        for item in config.summary
    ]
    tables = [
        ExtensionTableDisplaySemantics(
            id=table.id,
            label=table.label,
            rows=table.rows,
            columns=[
                ExtensionDisplayColumnSemantics(
                    id=column.id,
                    label=column.label,
                    expr=column.expr,
                )
                for column in table.columns
            ],
        )
        for table in config.tables
    ]
    matrices = [
        ExtensionMatrixDisplaySemantics(
            id=matrix.id,
            label=matrix.label,
            rows=matrix.rows,
            cols=matrix.cols,
            cell=matrix.cell,
        )
        for matrix in config.matrices
    ]
    if summary or tables or matrices:
        return ExtensionDisplaySemantics(
            summary=summary,
            tables=tables,
            matrices=matrices,
        )
    return _compile_student_math_auto_display(model=model)


def _compile_student_math_param_step(
    *,
    step: ExtensionInputStepSemantics,
    depends_on: list[str],
) -> tuple[_StageConfig, dict[str, _SetBindingConfig], dict[str, _ParamBindingConfig]]:
    input_schema: dict[str, Any] = {}
    fields: list[_StageFieldConfig] = []
    param_bindings: dict[str, _ParamBindingConfig] = {}

    for field in step.scalars:
        input_schema[field.field_path] = _student_math_scalar_schema(field)
        fields.append(
            _StageFieldConfig(
                field_path=field.field_path,
                label=field.label,
                description=field.help,
                required=field.required,
                value_type=field.value_type,
                aliases=field.aliases,
                examples=_student_examples(field.example),
            )
        )
        param_bindings[field.param] = _ParamBindingConfig(
            **{"from": f"{step.step_id}.{field.field_path}"}
        )

    for field in step.vectors:
        input_schema[field.field_path] = _student_math_vector_schema(field)
        fields.append(
            _StageFieldConfig(
                field_path=field.field_path,
                label=field.label,
                description=field.help,
                required=field.required,
                value_type=f"list[{field.value_type}]",
                aliases=field.aliases,
                examples=_student_examples(field.example),
            )
        )
        param_bindings[field.param] = _ParamBindingConfig(
            **{
                "from": f"{step.step_id}.{field.field_path}",
                "index_set": field.over,
            }
        )

    return (
        _StageConfig(
            stage_id=step.step_id,
            label=step.label,
            depends_on=depends_on,
            aliases=step.aliases,
            examples=_student_math_stage_examples(step),
            input_schema=input_schema,
            fields=fields,
        ),
        {},
        param_bindings,
    )


def _compile_student_math_table_step(
    *,
    step: ExtensionInputStepSemantics,
    depends_on: list[str],
) -> tuple[_StageConfig, dict[str, _SetBindingConfig], dict[str, _ParamBindingConfig]]:
    assert isinstance(step.shape, ExtensionTableInputSemantics)
    table = step.shape
    input_schema: dict[str, Any] = {
        table.key.field_path: {
            "min_items": 1,
            "unique": True,
        }
    }
    fields: list[_StageFieldConfig] = [
        _StageFieldConfig(
            field_path=table.key.field_path,
            label=table.key.label,
            description=table.key.help,
            required=True,
            value_type="list[string]",
            aliases=table.key.aliases,
            examples=_student_examples(
                [table.key.example] if table.key.example is not None else None
            ),
        )
    ]
    param_bindings: dict[str, _ParamBindingConfig] = {}
    for column in table.columns:
        input_schema[column.field_path] = _student_math_table_column_schema(column)
        fields.append(
            _StageFieldConfig(
                field_path=column.field_path,
                label=column.label,
                description=column.help,
                required=column.required,
                value_type=f"list[{column.value_type}]",
                aliases=column.aliases,
                examples=_student_examples(
                    [column.example] if column.example is not None else None
                ),
            )
        )
        param_bindings[column.param] = _ParamBindingConfig(
            **{
                "from": f"{step.step_id}.{column.field_path}",
                "index_set": table.set_name,
            }
        )

    return (
        _StageConfig(
            stage_id=step.step_id,
            label=step.label,
            depends_on=depends_on,
            aliases=step.aliases,
            examples=_student_math_stage_examples(step),
            input_schema=input_schema,
            fields=fields,
        ),
        {table.set_name: _SetBindingConfig(**{"from": f"{step.step_id}.{table.key.field_path}"})},
        param_bindings,
    )


def _compile_student_math_matrix_step(
    *,
    step: ExtensionInputStepSemantics,
    depends_on: list[str],
) -> tuple[_StageConfig, dict[str, _SetBindingConfig], dict[str, _ParamBindingConfig]]:
    assert isinstance(step.shape, ExtensionMatrixInputSemantics)
    matrix = step.shape
    input_schema: dict[str, Any] = {}
    fields: list[_StageFieldConfig] = []
    param_bindings: dict[str, _ParamBindingConfig] = {}
    for field in matrix.fields:
        input_schema[field.field_path] = _student_math_matrix_schema(field)
        fields.append(
            _StageFieldConfig(
                field_path=field.field_path,
                label=field.label,
                description=field.help,
                required=field.required,
                value_type=f"matrix[{field.value_type}]",
                aliases=field.aliases,
                examples=_student_examples(field.example),
            )
        )
        param_bindings[field.param] = _ParamBindingConfig(
            **{
                "from": f"{step.step_id}.{field.field_path}",
                "index_sets": (matrix.row_set, matrix.col_set),
            }
        )
    return (
        _StageConfig(
            stage_id=step.step_id,
            label=step.label,
            depends_on=depends_on,
            aliases=step.aliases,
            examples=_student_math_stage_examples(step),
            input_schema=input_schema,
            fields=fields,
        ),
        {},
        param_bindings,
    )


def _compile_student_math_display_reports(
    display: ExtensionDisplaySemantics,
) -> tuple[tuple[ScalarReportDecl, ...], tuple[TableReportDecl, ...]]:
    scalar_reports: list[ScalarReportDecl] = []
    table_reports: list[TableReportDecl] = []
    seen_names: set[str] = set()

    for item in display.summary:
        if item.id in seen_names:
            raise DeclarativeBundleError(
                f"display.summary содержит повторяющийся report `{item.id}`"
            )
        seen_names.add(item.id)
        scalar_reports.append(ScalarReportDecl(name=item.id, expr=parse_orx_expr_v2(item.expr)))

    for table in display.tables:
        if table.id in seen_names:
            raise DeclarativeBundleError(
                f"display.tables содержит повторяющийся report `{table.id}`"
            )
        seen_names.add(table.id)
        row_binding = _parse_iterator_clause(
            table.rows,
            context="display.tables.rows",
        )
        fields = tuple(
            ReportFieldDecl(name=column.id, expr=parse_orx_expr_v2(column.expr))
            for column in table.columns
        )
        table_reports.append(
            TableReportDecl(name=table.id, iterators=(row_binding,), fields=fields)
        )

    for matrix in display.matrices:
        if matrix.id in seen_names:
            raise DeclarativeBundleError(
                f"display.matrices содержит повторяющийся report `{matrix.id}`"
            )
        seen_names.add(matrix.id)
        row_binding = _parse_iterator_clause(
            matrix.rows,
            context="display.matrices.rows",
        )
        col_binding = _parse_iterator_clause(
            matrix.cols,
            context="display.matrices.cols",
        )
        if row_binding.name == col_binding.name:
            raise DeclarativeBundleError(
                "display.matrices требует разные iterator names для rows и cols."
            )
        table_reports.append(
            TableReportDecl(
                name=matrix.id,
                iterators=(row_binding, col_binding),
                fields=(
                    ReportFieldDecl(name="row_key", expr=parse_orx_expr_v2(row_binding.name)),
                    ReportFieldDecl(name="col_key", expr=parse_orx_expr_v2(col_binding.name)),
                    ReportFieldDecl(name="value", expr=parse_orx_expr_v2(matrix.cell)),
                ),
            )
        )

    return tuple(scalar_reports), tuple(table_reports)


def _compile_student_math_auto_display(
    *,
    model: CompiledModel,
) -> ExtensionDisplaySemantics:
    summary = [
        ExtensionSummaryDisplaySemantics(
            id="objective_value",
            label="Значение целевой функции",
            expr=_render_orx_expr(model.objective.expr),
        )
    ]
    tables: list[ExtensionTableDisplaySemantics] = []
    matrices: list[ExtensionMatrixDisplaySemantics] = []

    for declaration in model.vars:
        if not declaration.index_sets:
            continue
        report_name = f"{declaration.name}_plan"
        if len(declaration.index_sets) == 1:
            iterator_name = declaration.index_names[0]
            tables.append(
                ExtensionTableDisplaySemantics(
                    id=report_name,
                    label=_humanize_identifier(report_name),
                    rows=f"{iterator_name} in {declaration.index_sets[0]}",
                    columns=[
                        ExtensionDisplayColumnSemantics(
                            id="item",
                            label="Элемент",
                            expr=iterator_name,
                        ),
                        ExtensionDisplayColumnSemantics(
                            id="value",
                            label=_humanize_identifier(declaration.name),
                            expr=f"{declaration.name}[{iterator_name}]",
                        ),
                    ],
                )
            )
            continue
        if len(declaration.index_sets) == 2:
            row_name, col_name = declaration.index_names
            row_set, col_set = declaration.index_sets
            matrices.append(
                ExtensionMatrixDisplaySemantics(
                    id=report_name,
                    label=_humanize_identifier(report_name),
                    rows=f"{row_name} in {row_set}",
                    cols=f"{col_name} in {col_set}",
                    cell=f"{declaration.name}[{row_name}, {col_name}]",
                )
            )
    return ExtensionDisplaySemantics(
        summary=summary,
        tables=tables,
        matrices=matrices,
    )


def _compile_student_math_results(
    *,
    display: ExtensionDisplaySemantics,
    labels: dict[str, str],
) -> _ResultsConfig:
    sections: list[_ResultSectionConfig] = []
    for report in display.summary:
        title = report.label or labels.get(report.id, _humanize_identifier(report.id))
        sections.append(
            _ResultSectionConfig(
                section_id=f"student-math-summary-{report.id}",
                title=title,
                blocks=[
                    _KVBlockConfig(
                        title=None,
                        items=[_KVItemConfig(key=title, report=report.id)],
                    )
                ],
            )
        )
    for report in display.tables:
        title = report.label or labels.get(report.id, _humanize_identifier(report.id))
        sections.append(
            _ResultSectionConfig(
                section_id=f"student-math-table-{report.id}",
                title=title,
                blocks=[
                    _TableBlockConfig(
                        title=None,
                        report=report.id,
                        columns=[
                            _TableColumnConfig(
                                label=labels.get(
                                    f"{report.id}.{field.id}",
                                    field.label or _humanize_identifier(field.id),
                                ),
                                field=field.id,
                            )
                            for field in report.columns
                        ],
                    )
                ],
            )
        )
    for report in display.matrices:
        title = report.label or labels.get(report.id, _humanize_identifier(report.id))
        row_binding = _parse_iterator_clause(
            report.rows,
            context="display.matrices.rows",
        )
        sections.append(
            _ResultSectionConfig(
                section_id=f"student-math-matrix-{report.id}",
                title=title,
                blocks=[
                    _MatrixBlockConfig(
                        title=None,
                        report=report.id,
                        row_label=labels.get(
                            f"{report.id}.row",
                            _humanize_identifier(row_binding.set_name.lower()),
                        ),
                        row_field="row_key",
                        col_field="col_key",
                        value_field="value",
                    )
                ],
            )
        )
    return _ResultsConfig(sections=sections)


def _merge_student_math_display_labels(
    display: ExtensionDisplaySemantics,
    *,
    labels: dict[str, str],
) -> None:
    for item in display.summary:
        if item.label is not None:
            labels[item.id] = item.label
    for table in display.tables:
        if table.label is not None:
            labels[table.id] = table.label
        for column in table.columns:
            if column.label is not None:
                labels[f"{table.id}.{column.id}"] = column.label
    for matrix in display.matrices:
        if matrix.label is not None:
            labels[matrix.id] = matrix.label


def _parse_iterator_clause(raw: str, *, context: str) -> IteratorBinding:
    parts = raw.strip().split()
    if len(parts) != 3 or parts[1] != "in":
        raise DeclarativeBundleError(f"{context} должно иметь вид `i in ITEMS`.")
    return IteratorBinding(name=parts[0], set_name=parts[2])


def _student_math_scalar_schema(
    field: ExtensionScalarInputSemantics,
) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    if field.value_type == "number":
        schema.setdefault("numeric", True)
        if field.min is not None:
            schema["minimum"] = field.min
        if field.max is not None:
            schema["maximum"] = field.max
    return schema


def _student_math_vector_schema(
    field: ExtensionVectorInputSemantics,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"min_items": 1}
    if field.value_type == "number":
        schema["numeric_items"] = True
        if field.min is not None:
            schema["item_minimum"] = field.min
        if field.max is not None:
            schema["item_maximum"] = field.max
    return schema


def _student_math_table_column_schema(
    column: ExtensionTableColumnSemantics,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"min_items": 1}
    if column.value_type == "number":
        schema["numeric_items"] = True
        if column.min is not None:
            schema["item_minimum"] = column.min
        if column.max is not None:
            schema["item_maximum"] = column.max
    return schema


def _student_math_matrix_schema(
    field: ExtensionMatrixFieldSemantics,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "matrix": True,
        "rows_set": field.row_set,
        "cols_set": field.col_set,
    }
    if field.value_type == "number":
        schema["numeric_items"] = True
        if field.min is not None:
            schema["item_minimum"] = field.min
        if field.max is not None:
            schema["item_maximum"] = field.max
    return schema


def _student_math_stage_examples(step: ExtensionInputStepSemantics) -> list[str]:
    if step.example_command is None:
        return []
    return [step.example_command]


def _student_math_manifest_examples(semantics: ExtensionBundleSemantics) -> list[str]:
    examples = ["start"]
    for step in semantics.inputs:
        examples.extend(_student_math_stage_examples(step))
    examples.append("run")
    return examples


def _student_math_step_example_command(
    step: ExtensionInputStepSemantics,
) -> str | None:
    payload: dict[str, Any] = {}
    if step.shape is None:
        for field in [*step.scalars, *step.vectors]:
            if field.example is None:
                return None
            payload[field.field_path] = field.example
    elif isinstance(step.shape, ExtensionTableInputSemantics):
        if step.shape.key.example is None:
            return None
        payload[step.shape.key.field_path] = [step.shape.key.example]
        for column in step.shape.columns:
            if column.example is None:
                return None
            payload[column.field_path] = [column.example]
    else:
        assert isinstance(step.shape, ExtensionMatrixInputSemantics)
        for field in step.shape.fields:
            if field.example is None:
                return None
            payload[field.field_path] = field.example
    return f"json {step.step_id} {json.dumps(payload, ensure_ascii=False)}"


def _render_orx_expr(expr: Expr) -> str:
    if isinstance(expr, NumberExpr):
        return str(int(expr.value)) if float(expr.value).is_integer() else str(expr.value)
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, IndexedExpr):
        return f"{expr.name}[{', '.join(expr.index_names)}]"
    if isinstance(expr, UnaryExpr):
        return f"-{_render_orx_expr(expr.operand)}"
    if isinstance(expr, SumExpr):
        iterator_text = ", ".join(
            f"{iterator.name} in {iterator.set_name}" for iterator in expr.iterators
        )
        return f"sum{{{iterator_text}}} {_render_orx_expr(expr.body)}"
    if isinstance(expr, BinaryExpr):
        left = _render_orx_expr(expr.left)
        right = _render_orx_expr(expr.right)
        return f"{left} {expr.op} {right}"
    raise DeclarativeBundleError(f"Unsupported ORX expression node for rendering: {expr!r}")


def _build_bundle_semantics_from_compiled_config(
    *,
    config: DeclarativeBundleConfig,
    model: CompiledModel,
) -> ExtensionBundleSemantics:
    binding_by_source = {
        binding.source: (param_name, binding)
        for param_name, binding in config.bindings.params.items()
    }
    inputs: list[ExtensionInputStepSemantics] = []
    for stage in config.stages:
        scalars: list[ExtensionScalarInputSemantics] = []
        vectors: list[ExtensionVectorInputSemantics] = []
        for field in stage.fields:
            binding_entry = binding_by_source.get(f"{stage.stage_id}.{field.field_path}")
            if binding_entry is None:
                continue
            param_name, binding = binding_entry
            declared_sets = binding.declared_index_sets
            example = None
            if field.examples:
                try:
                    example = json.loads(field.examples[0])
                except json.JSONDecodeError:
                    example = field.examples[0]
            numeric = bool(stage.input_schema.get(field.field_path, {}).get("numeric"))
            numeric_items = bool(stage.input_schema.get(field.field_path, {}).get("numeric_items"))
            minimum = stage.input_schema.get(field.field_path, {}).get("minimum")
            maximum = stage.input_schema.get(field.field_path, {}).get("maximum")
            item_minimum = stage.input_schema.get(field.field_path, {}).get("item_minimum")
            item_maximum = stage.input_schema.get(field.field_path, {}).get("item_maximum")
            if not declared_sets:
                scalars.append(
                    ExtensionScalarInputSemantics(
                        param=param_name,
                        field_path=field.field_path,
                        label=field.label,
                        help=field.description,
                        value_type="number" if numeric else "string",
                        required=field.required,
                        min=float(minimum) if isinstance(minimum, (int, float)) else None,
                        max=float(maximum) if isinstance(maximum, (int, float)) else None,
                        aliases=list(field.aliases),
                        example=example,
                    )
                )
            elif len(declared_sets) == 1:
                vectors.append(
                    ExtensionVectorInputSemantics(
                        param=param_name,
                        over=declared_sets[0],
                        field_path=field.field_path,
                        label=field.label,
                        help=field.description,
                        value_type="number" if numeric_items else "string",
                        required=field.required,
                        min=float(item_minimum) if isinstance(item_minimum, (int, float)) else None,
                        max=float(item_maximum) if isinstance(item_maximum, (int, float)) else None,
                        aliases=list(field.aliases),
                        example=example,
                    )
                )

        inputs.append(
            ExtensionInputStepSemantics(
                step_id=stage.stage_id,
                label=stage.label,
                aliases=list(stage.aliases),
                scalars=scalars,
                vectors=vectors,
                example_command=stage.examples[0] if stage.examples else None,
            )
        )

    stages = [
        ExtensionStageSemantics(
            stage_id=stage.stage_id,
            label=stage.label,
            aliases=list(stage.aliases),
            examples=list(stage.examples),
            fields=[
                ExtensionFieldSemantics(
                    stage_id=stage.stage_id,
                    field_path=field.field_path,
                    label=field.label,
                    aliases=list(field.aliases),
                    value_type=field.value_type or "json",
                    help=field.description,
                    example=field.examples[0] if field.examples else None,
                )
                for field in stage.field_specs
            ],
        )
        for stage in config.stages
    ]
    return ExtensionBundleSemantics(
        alias=config.extension.alias,
        dsl_format=str(config.extension.ui_metadata.get("dsl_format", config.format)),
        stage_ids=[stage.stage_id for stage in config.stages],
        symbols=_build_student_math_symbol_catalog(model),
        inputs=inputs,
        display=ExtensionDisplaySemantics(),
        stages=stages,
    )


def _student_math_expectation_hint(step: _StudentMathInputStepConfig) -> str | None:
    if step.table is not None:
        column_labels = ", ".join(column.label for column in step.table.columns)
        return (
            f"Ожидается таблица: ключ `{step.table.key.label}`"
            + (f" и колонки {column_labels}." if column_labels else ".")
        )
    if step.matrix is not None:
        field_labels = ", ".join(field.label for field in step.matrix.fields)
        return (
            f"Ожидается матрица `{field_labels}` по множествам "
            f"`{step.matrix.rows_set}` x `{step.matrix.cols_set}`."
        )
    field_labels = ", ".join(
        field.label for field in [*step.params, *step.vectors]
    )
    if not field_labels:
        return None
    return f"Ожидаемые поля: {field_labels}."


def _build_stage_semantics_from_step(
    *,
    step: ExtensionInputStepSemantics,
    expectation_hint: str | None,
) -> ExtensionStageSemantics:
    fields: list[ExtensionFieldSemantics] = []
    for field in step.scalars:
        fields.append(
            ExtensionFieldSemantics(
                stage_id=step.step_id,
                field_path=field.field_path,
                label=field.label,
                aliases=list(field.aliases),
                value_type=field.value_type,
                help=field.help,
                example=field.example,
            )
        )
    for field in step.vectors:
        fields.append(
            ExtensionFieldSemantics(
                stage_id=step.step_id,
                field_path=field.field_path,
                label=field.label,
                aliases=list(field.aliases),
                value_type=field.value_type,
                help=field.help,
                example=field.example,
            )
        )
    if isinstance(step.shape, ExtensionTableInputSemantics):
        fields.append(
            ExtensionFieldSemantics(
                stage_id=step.step_id,
                field_path=step.shape.key.field_path,
                label=step.shape.key.label,
                aliases=list(step.shape.key.aliases),
                value_type="string",
                help=step.shape.key.help,
                example=step.shape.key.example,
            )
        )
        for column in step.shape.columns:
            fields.append(
                ExtensionFieldSemantics(
                    stage_id=step.step_id,
                    field_path=column.field_path,
                    label=column.label,
                    aliases=list(column.aliases),
                    value_type=column.value_type,
                    help=column.help,
                    example=column.example,
                )
            )
    if isinstance(step.shape, ExtensionMatrixInputSemantics):
        for field in step.shape.fields:
            fields.append(
                ExtensionFieldSemantics(
                    stage_id=step.step_id,
                    field_path=field.field_path,
                    label=field.label,
                    aliases=list(field.aliases),
                    value_type=field.value_type,
                    help=field.help,
                    example=field.example,
                )
            )
    return ExtensionStageSemantics(
        stage_id=step.step_id,
        label=step.label,
        aliases=list(step.aliases),
        examples=[step.example_command] if step.example_command else [],
        expectation_hint=expectation_hint,
        fields=fields,
    )


def _build_bundle_artifacts(
    root_path: Path,
    semantics: ExtensionBundleSemantics,
) -> list[ExtensionArtifactSemantics]:
    artifacts: list[ExtensionArtifactSemantics] = []
    for filename, artifact_id, kind, label, language in (
        ("model.orx", "model", "model", "Математическая модель", "orx"),
        ("extension.yaml", "extension", "extension", "Структура extension", "yaml"),
    ):
        candidate = root_path / filename
        if not candidate.exists():
            continue
        artifacts.append(
            ExtensionArtifactSemantics(
                id=artifact_id,
                kind=kind,
                label=label,
                language=language,
                path=str(candidate),
                content=candidate.read_text(encoding="utf-8"),
                summary=f"Read-only artifact `{filename}` для extension `{semantics.alias}`.",
            )
        )
    artifacts.append(
        ExtensionArtifactSemantics(
            id="semantics_snapshot",
            kind="semantics_snapshot",
            label="Typed semantics snapshot",
            language="json",
            content=json.dumps(semantics.model_dump(mode="json"), ensure_ascii=False, indent=2),
            summary="Сериализованный typed semantics snapshot текущего extension.",
        )
    )
    return artifacts


def _pivot_matrix_rows(
    *,
    rows_payload: object,
    row_label: str,
    row_field: str,
    col_field: str,
    value_field: str,
) -> tuple[list[str], list[list[Any]]]:
    if not isinstance(rows_payload, list):
        return [row_label], []

    row_order: list[str] = []
    col_order: list[str] = []
    row_values: dict[str, dict[str, Any]] = {}
    for raw_row in rows_payload:
        if not isinstance(raw_row, dict):
            continue
        row_key = raw_row.get(row_field)
        col_key = raw_row.get(col_field)
        if row_key is None or col_key is None:
            continue
        row_token = str(row_key)
        col_token = str(col_key)
        if row_token not in row_values:
            row_values[row_token] = {}
            row_order.append(row_token)
        if col_token not in col_order:
            col_order.append(col_token)
        row_values[row_token][col_token] = raw_row.get(value_field)

    columns = [row_label, *col_order]
    rows = [
        [row_key, *(row_values.get(row_key, {}).get(col_key) for col_key in col_order)]
        for row_key in row_order
    ]
    return columns, rows


def _coerce_number_matrix(value: object) -> list[list[float]] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[list[float]] = []
    expected_len: int | None = None
    for row in value:
        if not isinstance(row, list) or not row:
            return None
        normalized_row: list[float] = []
        for item in row:
            if not isinstance(item, (int, float)):
                return None
            normalized_row.append(float(item))
        if expected_len is None:
            expected_len = len(normalized_row)
        elif expected_len != len(normalized_row):
            return None
        normalized.append(normalized_row)
    return normalized


def _student_param_target(*, name: str, model: CompiledModel, context: str) -> ParamDecl:
    declaration = next((param for param in model.params if param.name == name), None)
    if declaration is None:
        raise DeclarativeBundleError(
            f"Не удалось автоматически привязать `{context}` к param `{name}`. "
            "Проверьте имя поля или добавьте `bind`."
        )
    if declaration.expr is not None:
        raise DeclarativeBundleError(
            f"`{context}` нельзя привязать к derived param `{name}`. "
            "Derived param нужно вычислять внутри model.orx."
        )
    return declaration


def _student_field_schema(field: _StudentFieldConfig) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    if field.type in {"number", "list[number]"}:
        if field.min is not None:
            schema["minimum" if field.type == "number" else "item_minimum"] = field.min
        if field.max is not None:
            schema["maximum" if field.type == "number" else "item_maximum"] = field.max
    if field.type.startswith("list["):
        schema["min_items"] = 1
        if field.type == "list[string]":
            schema["unique"] = field.id.endswith("_names") or field.id in {"names", "course_names"}
    return schema


def _student_table_column_schema(column: _StudentTableColumnConfig) -> dict[str, Any]:
    schema: dict[str, Any] = {"min_items": 1}
    if column.type == "number":
        if column.min is not None:
            schema["item_minimum"] = column.min
        if column.max is not None:
            schema["item_maximum"] = column.max
    return schema


def _student_stage_examples(step: _StudentStepConfig) -> list[str]:
    payload: dict[str, Any] = {}
    if step.table is not None:
        table = step.table
        if table.key.example is None:
            return []
        payload[table.key.id] = [table.key.example]
        for column in table.columns:
            if column.example is None:
                return []
            payload[column.id] = [column.example]
    else:
        for field in step.fields:
            if field.example is None:
                return []
            payload[field.id] = field.example
    return [f"json {step.id} {json.dumps(payload, ensure_ascii=False)}"]


def _student_manifest_examples(config: StudentBundleConfig) -> list[str]:
    examples = ["start"]
    if config.extension.default_preset is not None:
        examples.append(f"load preset {config.extension.default_preset}")
    for step in config.wizard:
        examples.extend(_student_stage_examples(step))
    examples.append("run")
    return examples


def _student_stage_aliases(
    stage_id: str, label: str, *, explicit_aliases: list[str] | None = None
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for raw in (
        stage_id,
        stage_id.replace("_", " "),
        *stage_id.split("_"),
        label,
        *label.split(),
        *(explicit_aliases or []),
    ):
        candidate = raw.strip().lower()
        if not candidate or candidate in seen:
            continue
        if candidate == stage_id.lower() or candidate == label.strip().lower():
            continue
        aliases.append(candidate)
        seen.add(candidate)
    return aliases


def _student_field_aliases(
    field_id: str, *, explicit_aliases: list[str] | None = None
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    tokens = [token for token in field_id.split("_") if token]
    spaced = " ".join(tokens)
    if spaced and spaced != field_id:
        aliases.append(spaced)
        seen.add(spaced)
    if len(tokens) == 2:
        reversed_snake = f"{tokens[1]}_{tokens[0]}"
        if reversed_snake != field_id:
            aliases.append(reversed_snake)
            seen.add(reversed_snake)
    for alias in explicit_aliases or []:
        normalized = alias.strip()
        if not normalized or normalized == field_id or normalized in seen:
            continue
        aliases.append(normalized)
        seen.add(normalized)
    return aliases


def _student_examples(example: object) -> list[str]:
    if example is None:
        return []
    rendered = json.dumps(example, ensure_ascii=False)
    return [rendered]


def _humanize_identifier(value: str) -> str:
    text = value.replace("_", " ").strip()
    if not text:
        return value
    return text[0].upper() + text[1:]


@lru_cache(maxsize=256)
def load_declarative_bundle(
    bundle_root: Path,
    *,
    config_filename: str = "extension.yaml",
    model_filename: str = "model.orx",
) -> DeclarativeBundle:
    """Load, validate, and compile one declarative extension bundle."""
    resolved_root = bundle_root.resolve()
    config_path = resolved_root / config_filename
    model_path = resolved_root / model_filename
    raw_config = _load_yaml_file(config_path)
    if not isinstance(raw_config, dict):
        raise DeclarativeBundleError(f"Declarative config `{config_path}` must be a YAML mapping")
    model_source = model_path.read_text(encoding="utf-8")
    config, model, semantics = _load_bundle_artifacts(
        raw_config=raw_config,
        model_source=model_source,
        config_path=config_path,
    )
    manifest = _compile_manifest(config)
    _validate_bundle_semantics(root=resolved_root, config=config, manifest=manifest, model=model)
    return DeclarativeBundle(
        root_path=resolved_root,
        config=config,
        manifest=manifest,
        model=model,
        semantics=semantics,
    )


def load_declarative_provider(
    bundle_root: Path,
    *,
    config_filename: str = "extension.yaml",
    model_filename: str = "model.orx",
) -> DeclarativeExtensionProvider:
    """Load one declarative extension bundle and wrap it as a provider."""
    return DeclarativeExtensionProvider(
        load_declarative_bundle(
            bundle_root,
            config_filename=config_filename,
            model_filename=model_filename,
        )
    )


def discover_declarative_bundle_roots(root: Path) -> list[Path]:
    """Return all declarative extension directories under one root."""
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        candidate.parent for candidate in root.glob("*/extension.yaml") if candidate.is_file()
    )


def _load_yaml_file(path: Path) -> object:
    if not path.exists():
        raise DeclarativeBundleError(f"Required declarative file is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _compile_manifest(config: DeclarativeBundleConfig) -> ExtensionManifest:
    return ExtensionManifest(
        alias=config.extension.alias,
        title=config.extension.title,
        description=config.extension.description,
        version=config.extension.version,
        default_preset=config.extension.default_preset,
        labels=config.extension.labels,
        examples=config.extension.examples,
        field_aliases=config.extension.field_aliases,
        stage_aliases=config.extension.stage_aliases,
        ui_metadata=config.extension.ui_metadata,
        stage_graph=[
            StageSpec(
                stage_id=stage.stage_id,
                label=stage.label,
                depends_on=stage.depends_on,
                examples=stage.examples,
                aliases=stage.aliases,
                input_schema=stage.input_schema,
                field_specs=[
                    FieldSpec(
                        field_path=field.field_path,
                        label=field.label,
                        description=field.description,
                        required=field.required,
                        value_type=field.value_type,
                        aliases=field.aliases,
                        examples=field.examples,
                    )
                    for field in stage.fields
                ],
            )
            for stage in config.stages
        ],
    )


def _validate_bundle_semantics(
    *,
    root: Path,
    config: DeclarativeBundleConfig,
    manifest: ExtensionManifest,
    model: CompiledModel,
) -> None:
    manifest_stage_map = manifest.stage_map()
    field_lookup = {
        stage_id: {field.field_path for field in stage.field_specs}
        for stage_id, stage in manifest_stage_map.items()
    }

    for set_name, binding in config.bindings.sets.items():
        if set_name not in model.set_names:
            raise DeclarativeBundleError(f"Binding declares unknown model set `{set_name}`")
        stage_id, field_path = _split_source_path(binding.source)
        _assert_manifest_field_exists(
            stage_id=stage_id,
            field_path=field_path,
            field_lookup=field_lookup,
        )

    for param_name, binding in config.bindings.params.items():
        declaration = next((param for param in model.params if param.name == param_name), None)
        if declaration is None:
            raise DeclarativeBundleError(f"Binding declares unknown model param `{param_name}`")
        if declaration.expr is not None:
            raise DeclarativeBundleError(
                f"Binding for derived param `{param_name}` is not allowed; derive it in model.orx"
            )
        stage_id, field_path = _split_source_path(binding.source)
        _assert_manifest_field_exists(
            stage_id=stage_id,
            field_path=field_path,
            field_lookup=field_lookup,
        )
        declared_index_sets = binding.declared_index_sets
        if declared_index_sets and declared_index_sets != declaration.index_sets:
            raise DeclarativeBundleError(
                f"Param binding `{param_name}` must reference sets `{declaration.index_sets}`, "
                f"а указано `{declared_index_sets}`."
            )

    for declaration in model.sets:
        if declaration.name not in config.bindings.sets:
            raise DeclarativeBundleError(
                f"Declarative bundle is missing a set binding for `{declaration.name}`"
            )

    for declaration in model.required_input_params:
        if declaration.name not in config.bindings.params:
            raise DeclarativeBundleError(
                f"Declarative bundle is missing a param binding for `{declaration.name}`"
            )

    scalar_reports = {report.name for report in model.scalar_reports}
    table_reports = {
        report.name: {report_field.name for report_field in report.fields}
        for report in model.table_reports
    }
    for section in config.results.sections:
        for block in section.blocks:
            if isinstance(block, _SummaryBlockConfig):
                continue
            if isinstance(block, _KVBlockConfig):
                for item in block.items:
                    if item.report not in scalar_reports:
                        raise DeclarativeBundleError(
                            f"KV block `{section.section_id}` references "
                            f"unknown scalar report `{item.report}`"
                        )
                continue
            if isinstance(block, _TableBlockConfig):
                available_fields = table_reports.get(block.report)
                if available_fields is None:
                    raise DeclarativeBundleError(
                        f"Table block `{section.section_id}` references "
                        f"unknown table report `{block.report}`"
                    )
                for column in block.columns:
                    if column.field not in available_fields:
                        raise DeclarativeBundleError(
                            f"Table block `{section.section_id}` references unknown field "
                            f"`{column.field}` in table report `{block.report}`"
                        )
                continue
            if isinstance(block, _MatrixBlockConfig):
                available_fields = table_reports.get(block.report)
                if available_fields is None:
                    raise DeclarativeBundleError(
                        f"Matrix block `{section.section_id}` references "
                        f"unknown table report `{block.report}`"
                    )
                for field_name in (block.row_field, block.col_field, block.value_field):
                    if field_name not in available_fields:
                        raise DeclarativeBundleError(
                            f"Matrix block `{section.section_id}` references unknown field "
                            f"`{field_name}` in table report `{block.report}`"
                        )
                continue
            if isinstance(block, (_ListBlockConfig, _JsonBlockConfig)):
                if block.report not in scalar_reports and block.report not in table_reports:
                    raise DeclarativeBundleError(
                        f"Result block `{section.section_id}` references "
                        f"unknown report `{block.report}`"
                    )
    for preset_ref, relative_path in config.presets.items():
        preset_path = root / relative_path
        if not preset_path.exists():
            raise DeclarativeBundleError(
                f"Preset `{preset_ref}` points to missing file `{preset_path}`"
            )


def _assert_manifest_field_exists(
    *, stage_id: str, field_path: str, field_lookup: dict[str, set[str]]
) -> None:
    if stage_id not in field_lookup:
        raise DeclarativeBundleError(f"Binding references unknown stage `{stage_id}`")
    if field_path not in field_lookup[stage_id]:
        raise DeclarativeBundleError(f"Binding references unknown field `{stage_id}.{field_path}`")


def _split_source_path(source: str) -> tuple[str, str]:
    if "." not in source:
        raise DeclarativeBundleError(
            f"Binding source `{source}` must use <stage_id>.<field_path> syntax"
        )
    stage_id, field_path = source.split(".", maxsplit=1)
    if not stage_id or not field_path:
        raise DeclarativeBundleError(
            f"Binding source `{source}` must use <stage_id>.<field_path> syntax"
        )
    return stage_id, field_path


def _extract_draft_value(
    *, draft: dict[str, object], stage_id: str, field_path: str
) -> tuple[object | None, bool]:
    payload = draft.get(stage_id)
    if not isinstance(payload, dict):
        return None, False
    if field_path not in payload:
        return None, False
    return payload[field_path], True


def _coerce_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        normalized.append(item.strip())
    return normalized


def _coerce_number_list(value: object) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)):
            return None
        normalized.append(float(item))
    return normalized


def _validate_field_value(
    *,
    stage_id: str,
    field: _StageFieldConfig,
    value: object,
    schema: object,
) -> list[str]:
    errors: list[str] = []
    rules = schema if isinstance(schema, dict) else {}
    value_type = field.value_type
    if value_type == "matrix[number]":
        matrix = _coerce_number_matrix(value)
        if matrix is None:
            return [
                f"Поле {field.field_path} должно быть прямоугольной матрицей чисел "
                "в виде вложенных списков."
            ]
        item_minimum = rules.get("item_minimum")
        if isinstance(item_minimum, (int, float)) and any(
            item < float(item_minimum) for row in matrix for item in row
        ):
            errors.append(f"Все значения матрицы {field.field_path} должны быть >= {item_minimum}.")
        item_maximum = rules.get("item_maximum")
        if isinstance(item_maximum, (int, float)) and any(
            item > float(item_maximum) for row in matrix for item in row
        ):
            errors.append(f"Все значения матрицы {field.field_path} должны быть <= {item_maximum}.")
        return errors
    if value_type == "number":
        if not isinstance(value, (int, float)):
            return [f"Поле {field.field_path} должно быть числом."]
        minimum = rules.get("minimum")
        if isinstance(minimum, (int, float)) and float(value) < float(minimum):
            errors.append(f"Поле {field.field_path} должно быть >= {minimum}.")
        maximum = rules.get("maximum")
        if isinstance(maximum, (int, float)) and float(value) > float(maximum):
            errors.append(f"Поле {field.field_path} должно быть <= {maximum}.")
        return errors
    if value_type == "string":
        if not isinstance(value, str) or not value.strip():
            return [f"Поле {field.field_path} должно быть непустой строкой."]
        return errors
    if value_type == "list[number]":
        values = _coerce_number_list(value)
        if values is None:
            return [f"Поле {field.field_path} должно быть непустым списком чисел."]
        min_items = rules.get("min_items")
        if isinstance(min_items, int) and len(values) < min_items:
            errors.append(
                f"Поле {field.field_path} должно содержать минимум {min_items} элементов."
            )
        item_minimum = rules.get("item_minimum")
        if isinstance(item_minimum, (int, float)) and any(
            item < float(item_minimum) for item in values
        ):
            errors.append(f"Все значения {field.field_path} должны быть >= {item_minimum}.")
        item_maximum = rules.get("item_maximum")
        if isinstance(item_maximum, (int, float)) and any(
            item > float(item_maximum) for item in values
        ):
            errors.append(f"Все значения {field.field_path} должны быть <= {item_maximum}.")
        return errors
    if value_type == "list[string]":
        values = _coerce_string_list(value)
        if values is None:
            return [f"Поле {field.field_path} должно быть непустым списком строк."]
        min_items = rules.get("min_items")
        if isinstance(min_items, int) and len(values) < min_items:
            errors.append(
                f"Поле {field.field_path} должно содержать минимум {min_items} элементов."
            )
        unique = rules.get("unique")
        if unique and len(set(values)) != len(values):
            errors.append(f"Поле {field.field_path} не должно содержать дубли.")
        return errors
    return errors


def _template_context(result: object) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {"result": result}
