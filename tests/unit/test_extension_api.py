"""Unit-тесты foundation-слоя extension SDK и discovery registry."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from extension_api import (
    DuplicateExtensionAliasError,
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionResultSection,
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

    assert app.state.extension_registry is registry
    assert app.state.service.extension_registry is registry
