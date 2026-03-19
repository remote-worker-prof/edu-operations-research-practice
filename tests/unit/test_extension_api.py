"""Unit-тесты foundation-слоя extension SDK и discovery registry."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from agent_core.default_or_extension import DEFAULT_OR_EXTENSION_ALIAS
from extension_api import (
    DuplicateExtensionAliasError,
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionResultSection,
    FieldSpec,
    InvalidExtensionProviderError,
    StageSpec,
)
from webapp.main import create_app


@dataclass(frozen=True)
class _FakeEntryPoint:
    """Минимальный stand-in для `importlib.metadata.EntryPoint` в unit-тестах."""

    name: str
    provider: object
    group: str = "edu_or_agent.extensions"
    module: str = "tests.unit.fake_extension_provider"

    def load(self) -> object:
        return self.provider


class _FakeRuntime:
    """Минимальный runtime для discovery/registry тестов."""

    manifest: ExtensionManifest

    def __init__(self, manifest: ExtensionManifest) -> None:
        self.manifest = manifest

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        return {}

    def build_runtime_input(self, draft: dict[str, object]) -> object:
        return draft

    def run(self, runtime_input: object) -> object:
        return runtime_input

    def fallback_explain(self, result: object) -> str:
        return "fallback"

    def build_llm_explain_prompt(self, result: object) -> str:
        return "prompt"

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        return []

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        return []

    def build_nl_semantics(self) -> dict[str, object]:
        return {}


class FakeProvider:
    """Поставщик extension manifest/runtime для discovery тестов."""

    def get_manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            alias="study_planner",
            title="Study Planner",
            description="Deterministic study-planner demo extension",
            version="0.1.0",
            stage_graph=[
                StageSpec(stage_id="courses", label="Courses"),
                StageSpec(stage_id="time_budget", label="Time Budget"),
                StageSpec(stage_id="priorities", label="Priorities", depends_on=["courses"]),
            ],
        )

    def create_runtime(self) -> _FakeRuntime:
        return _FakeRuntime(self.get_manifest())


class DuplicateAliasProvider:
    """Второй provider с тем же alias, чтобы проверить защиту registry."""

    def get_manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            alias="study_planner",
            title="Study Planner Duplicate",
            description="Conflicting alias provider",
            version="0.1.0",
            stage_graph=[StageSpec(stage_id="courses", label="Courses")],
        )

    def create_runtime(self) -> _FakeRuntime:
        return _FakeRuntime(self.get_manifest())


class PresetAwareFakeProvider:
    """Provider that honestly supports manifest.default_preset."""

    def get_manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            alias="preset_demo",
            title="Preset Demo",
            description="Provider with one built-in preset",
            version="0.1.0",
            default_preset="demo",
            stage_graph=[
                StageSpec(stage_id="courses", label="Courses"),
                StageSpec(stage_id="time_budget", label="Time Budget"),
            ],
        )

    def create_runtime(self) -> _FakeRuntime:
        return _FakeRuntime(self.get_manifest())

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, object]]:
        if preset_ref != "demo":
            raise ValueError(f"Unsupported preset: {preset_ref}")
        return {
            "courses": {"names": ["Math"], "hours_required": [12]},
            "time_budget": {"weekly_hours": 6, "weeks": 2},
        }


class InvalidPresetProvider:
    """Provider that lies in the manifest by declaring a preset without a loader."""

    def get_manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            alias="invalid_preset_demo",
            title="Invalid Preset Demo",
            description="Broken provider for strict contract tests",
            version="0.1.0",
            default_preset="demo",
            stage_graph=[StageSpec(stage_id="courses", label="Courses")],
        )

    def create_runtime(self) -> _FakeRuntime:
        return _FakeRuntime(self.get_manifest())


def test_extension_manifest_validates_stage_dag_and_topological_order() -> None:
    """Проверяет, что manifest поддерживает DAG-валидацию и стабильный topo-order."""
    manifest = ExtensionManifest(
        alias="planner_demo",
        title="Planner Demo",
        description="Demo extension",
        version="0.1.0",
        stage_graph=[
            StageSpec(stage_id="courses", label="Courses"),
            StageSpec(stage_id="time_budget", label="Time Budget"),
            StageSpec(stage_id="priorities", label="Priorities", depends_on=["courses"]),
            StageSpec(
                stage_id="plan",
                label="Plan",
                depends_on=["courses", "time_budget", "priorities"],
            ),
        ],
    )

    assert manifest.topological_stage_ids() == [
        "courses",
        "time_budget",
        "priorities",
        "plan",
    ]


def test_extension_manifest_rejects_cycles() -> None:
    """Проверяет ранний отказ на циклических stage dependencies."""
    with pytest.raises(ValueError, match="acyclic"):
        ExtensionManifest(
            alias="cyclic_demo",
            title="Cyclic Demo",
            description="Invalid extension",
            version="0.1.0",
            stage_graph=[
                StageSpec(stage_id="a", label="A", depends_on=["b"]),
                StageSpec(stage_id="b", label="B", depends_on=["a"]),
            ],
        )


def test_extension_registry_discovers_provider_from_entry_points() -> None:
    """Проверяет discovery по entry points без привязки к конкретному runtime пакету."""
    registry = ExtensionRegistry.discover(
        entry_points=[
            _FakeEntryPoint(
                name="study_planner",
                provider=FakeProvider,
            )
        ]
    )

    discovered = registry.require("study_planner")
    assert registry.aliases() == ["study_planner"]
    assert discovered.manifest.title == "Study Planner"
    assert discovered.source == "edu_or_agent.extensions:study_planner"


def test_extension_registry_rejects_duplicate_manifest_aliases() -> None:
    """Проверяет защиту от конфликтующих alias между extension-пакетами."""
    with pytest.raises(DuplicateExtensionAliasError, match="study_planner"):
        ExtensionRegistry.discover(
            entry_points=[
                _FakeEntryPoint(
                    name="study_planner_a",
                    provider=FakeProvider,
                ),
                _FakeEntryPoint(
                    name="study_planner_b",
                    provider=DuplicateAliasProvider,
                ),
            ]
        )


def test_extension_registry_rejects_provider_that_declares_default_preset_without_loader() -> None:
    """Проверяет strict-mode отказ на manifest/provider preset drift."""
    with pytest.raises(InvalidExtensionProviderError, match="default_preset"):
        ExtensionRegistry.discover(
            entry_points=[
                _FakeEntryPoint(
                    name="invalid_preset_demo",
                    provider=InvalidPresetProvider,
                )
            ]
        )


def test_extension_registry_exposes_builtin_preset_loader_when_provider_supports_it() -> None:
    """Проверяет, что honest preset-capable provider discover'ится без деградации."""
    registry = ExtensionRegistry.discover(
        entry_points=[
            _FakeEntryPoint(
                name="preset_demo",
                provider=PresetAwareFakeProvider,
            )
        ]
    )

    discovered = registry.require("preset_demo")
    preset = discovered.load_preset("demo")

    assert preset["courses"]["names"] == ["Math"]
    assert preset["time_budget"]["weeks"] == 2


def test_extension_manifest_rejects_colliding_field_aliases() -> None:
    """Проверяет ранний отказ, если alias конфликтует с другим canonical path."""
    with pytest.raises(ValueError, match="conflicts with canonical field path"):
        ExtensionManifest(
            alias="collision_demo",
            title="Collision Demo",
            description="Invalid field alias mapping",
            version="0.1.0",
            stage_graph=[
                StageSpec(
                    stage_id="time_budget",
                    label="Time Budget",
                    field_specs=[
                        FieldSpec(
                            field_path="weekly_hours",
                            label="Weekly hours",
                            aliases=["weeks"],
                        ),
                        FieldSpec(field_path="weeks", label="Weeks"),
                    ],
                )
            ],
        )


def test_extension_manifest_rejects_ambiguous_manifest_level_field_alias_target() -> None:
    """Проверяет отказ на ambiguous manifest.field_aliases key без stage prefix."""
    with pytest.raises(ValueError, match="ambiguous across stages"):
        ExtensionManifest(
            alias="ambiguous_alias_demo",
            title="Ambiguous Alias Demo",
            description="Invalid manifest-level field alias target",
            version="0.1.0",
            stage_graph=[
                StageSpec(
                    stage_id="shipment",
                    label="Shipment",
                    field_specs=[FieldSpec(field_path="cost_matrix", label="Cost matrix")],
                ),
                StageSpec(
                    stage_id="assignment",
                    label="Assignment",
                    field_specs=[FieldSpec(field_path="cost_matrix", label="Cost matrix")],
                ),
            ],
            field_aliases={"cost_matrix": ["matrix"]},
        )


def test_create_app_attaches_extension_registry_to_app_state() -> None:
    """Проверяет, что webapp хранит startup-discovered registry в `app.state`."""
    registry = ExtensionRegistry.discover(
        entry_points=[
            _FakeEntryPoint(
                name="study_planner",
                provider=FakeProvider,
            )
        ]
    )

    app = create_app(extension_registry=registry)

    assert app.state.extension_registry is app.state.service.extension_registry
    assert app.state.extension_registry.require(DEFAULT_OR_EXTENSION_ALIAS).manifest.title == (
        "Default OR Pipeline"
    )
    assert app.state.extension_registry.require("study_planner").manifest.title == "Study Planner"
