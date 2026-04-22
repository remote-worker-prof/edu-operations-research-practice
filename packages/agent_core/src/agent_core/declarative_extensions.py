"""Declarative extension bundles backed by YAML + ORX LP models."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from extension_api import (
    ExtensionManifest,
    ExtensionResultSection,
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
    default: Any = None


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
    _SummaryBlockConfig | _KVBlockConfig | _TableBlockConfig | _ListBlockConfig | _JsonBlockConfig,
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
            raise ValueError(
                f"extension.default_preset `{default_preset}` must exist in presets"
            )
        return self


@dataclass(frozen=True, slots=True)
class DeclarativeBundle:
    root_path: Path
    config: DeclarativeBundleConfig
    manifest: ExtensionManifest
    model: CompiledModel


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
                        KVItem(key=item.key, value=result.get(item.report))
                        for item in block.items
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
        return {
            "supported": True,
            "mode": "declarative_bundle",
            "alias": self._bundle.manifest.alias,
            "stages": [stage.stage_id for stage in self._bundle.config.stages],
        }

    def _resolve_bound_input(
        self,
        draft: dict[str, object],
        *,
        collect_errors: bool,
    ) -> tuple[BoundModelInput | None, dict[str, list[str]]]:
        errors = {stage.stage_id: [] for stage in self._bundle.config.stages}
        set_values: dict[str, tuple[str, ...]] = {}
        params: dict[str, float | dict[str, float]] = {}

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
                    f"Не заполнена binding source `{binding.source}` "
                    f"для set `{set_name}`."
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
            if declaration.index_set is None:
                if not isinstance(value, (int, float)):
                    errors[stage_id].append(
                        f"Поле {binding.source} должно быть числом для param `{declaration.name}`."
                    )
                    continue
                params[declaration.name] = float(value)
                continue

            normalized_list = _coerce_number_list(value)
            if normalized_list is None:
                errors[stage_id].append(
                    f"Поле {binding.source} должно быть непустым списком чисел "
                    f"для param `{declaration.name}`."
                )
                continue
            index_set = binding.index_set or declaration.index_set
            if index_set != declaration.index_set:
                errors[stage_id].append(
                    f"Binding `{declaration.name}` должен ссылаться на set "
                    f"`{declaration.index_set}`, "
                    f"а не `{index_set}`."
                )
                continue
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
                key: float(item)
                for key, item in zip(keys, normalized_list, strict=True)
            }

        populated_errors = {stage_id: messages for stage_id, messages in errors.items() if messages}
        if populated_errors:
            return None, errors if collect_errors else populated_errors
        return BoundModelInput(sets=set_values, params=params), {}


@lru_cache(maxsize=128)
def load_declarative_bundle(bundle_root: Path) -> DeclarativeBundle:
    """Load, validate, and compile one declarative extension bundle."""
    resolved_root = bundle_root.resolve()
    config_path = resolved_root / "extension.yaml"
    model_path = resolved_root / "model.orx"
    raw_config = _load_yaml_file(config_path)
    if not isinstance(raw_config, dict):
        raise DeclarativeBundleError(f"Declarative config `{config_path}` must be a YAML mapping")
    try:
        config = DeclarativeBundleConfig.model_validate(raw_config)
    except Exception as exc:  # pragma: no cover - pydantic keeps detailed context already
        raise DeclarativeBundleError(f"Invalid declarative config `{config_path}`: {exc}") from exc
    manifest = _compile_manifest(config)
    model_source = model_path.read_text(encoding="utf-8")
    model = compile_orx_model(parse_orx_model(model_source))
    _validate_bundle_semantics(root=resolved_root, config=config, manifest=manifest, model=model)
    return DeclarativeBundle(root_path=resolved_root, config=config, manifest=manifest, model=model)


def load_declarative_provider(bundle_root: Path) -> DeclarativeExtensionProvider:
    """Load one declarative extension bundle and wrap it as a provider."""
    return DeclarativeExtensionProvider(load_declarative_bundle(bundle_root))


def discover_declarative_bundle_roots(root: Path) -> list[Path]:
    """Return all declarative extension directories under one root."""
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        candidate.parent
        for candidate in root.glob("*/extension.yaml")
        if candidate.is_file()
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
        if declaration.index_set is not None:
            expected_set = binding.index_set or declaration.index_set
            if expected_set != declaration.index_set:
                raise DeclarativeBundleError(
                    f"Param binding `{param_name}` must reference set `{declaration.index_set}`"
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
        raise DeclarativeBundleError(
            f"Binding references unknown field `{stage_id}.{field_path}`"
        )


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
    del stage_id
    errors: list[str] = []
    rules = schema if isinstance(schema, dict) else {}
    value_type = field.value_type
    if value_type == "number":
        if not isinstance(value, (int, float)):
            return [f"Поле {field.field_path} должно быть числом."]
        minimum = rules.get("minimum")
        if isinstance(minimum, (int, float)) and float(value) < float(minimum):
            errors.append(f"Поле {field.field_path} должно быть >= {minimum}.")
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
                f"Поле {field.field_path} должно содержать минимум "
                f"{min_items} элементов."
            )
        item_minimum = rules.get("item_minimum")
        if isinstance(item_minimum, (int, float)) and any(
            item < float(item_minimum) for item in values
        ):
            errors.append(
                f"Все значения {field.field_path} должны быть >= {item_minimum}."
            )
        return errors
    if value_type == "list[string]":
        values = _coerce_string_list(value)
        if values is None:
            return [f"Поле {field.field_path} должно быть непустым списком строк."]
        min_items = rules.get("min_items")
        if isinstance(min_items, int) and len(values) < min_items:
            errors.append(
                f"Поле {field.field_path} должно содержать минимум "
                f"{min_items} элементов."
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
