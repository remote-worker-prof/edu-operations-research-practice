"""Unit tests for manifest-driven extension switching and the sample runtime."""

from __future__ import annotations

from agent_core.default_or_extension import DefaultORExtensionProvider
from agent_core.extension_commands import build_stage_alias_map, parse_extension_command
from agent_core.extension_flow import (
    manifest_for_alias,
    reset_session_for_extension,
    session_is_empty,
)
from agent_core.models import AgentSession
from extension_api import DiscoveredExtension, ExtensionRegistry
from sample_study_planner_extension import StudyPlannerExtensionProvider


def _registry_with_default_and_sample() -> ExtensionRegistry:
    """Creates a deterministic registry with built-in default_or and sample provider."""
    default_provider = DefaultORExtensionProvider()
    default_manifest = default_provider.get_manifest()
    sample_provider = StudyPlannerExtensionProvider()
    sample_manifest = sample_provider.get_manifest()
    return ExtensionRegistry(
        [
            DiscoveredExtension(
                alias=default_manifest.alias,
                manifest=default_manifest,
                provider=default_provider,
                entry_point_name=default_manifest.alias,
                module=default_provider.__class__.__module__,
                source=f"builtin:{default_manifest.alias}",
            ),
            DiscoveredExtension(
                alias=sample_manifest.alias,
                manifest=sample_manifest,
                provider=sample_provider,
                entry_point_name=sample_manifest.alias,
                module=sample_provider.__class__.__module__,
                source=f"test:{sample_manifest.alias}",
            ),
        ]
    )


def test_compose_extension_registry_includes_built_in_default_or() -> None:
    """Проверяет, что композиция registry всегда добавляет built-in `default_or`."""
    registry = _registry_with_default_and_sample()

    assert registry.aliases() == ["default_or", "study_planner"]
    assert manifest_for_alias(registry, "study_planner").title == "Study Planner"


def test_sample_manifest_stage_aliases_are_resolved_by_generic_command_parser() -> None:
    """Проверяет manifest-driven stage alias resolution для sample extension."""
    manifest = StudyPlannerExtensionProvider().get_manifest()
    alias_map = build_stage_alias_map(manifest)

    assert alias_map["courses"] == "courses"
    assert alias_map["курсы"] == "courses"
    assert alias_map["budget"] == "time_budget"
    assert alias_map["приоритеты"] == "priorities"

    result = parse_extension_command(
        message='json budget {"weekly_hours":12,"weeks":4}',
        current_stage=None,
        manifest=manifest,
    )
    assert result.action == "stage_json"
    assert result.stage == "time_budget"


def test_sample_runtime_validates_lengths_and_builds_result_sections() -> None:
    """Проверяет валидацию и deterministic run sample study-planner extension."""
    runtime = StudyPlannerExtensionProvider().create_runtime()
    invalid_errors = runtime.validate_draft(
        {
            "courses": {"names": ["Math", "ML"], "hours_required": [30]},
            "time_budget": {"weekly_hours": 12, "weeks": 4},
            "priorities": {"weights": [0.6, 0.4]},
        }
    )
    assert invalid_errors["courses"]

    valid_draft = {
        "courses": {"names": ["Math", "ML", "DB"], "hours_required": [30, 24, 18]},
        "time_budget": {"weekly_hours": 12, "weeks": 4},
        "priorities": {"weights": [0.5, 0.3, 0.2]},
    }
    assert runtime.validate_draft(valid_draft) == {
        "courses": [],
        "time_budget": [],
        "priorities": [],
    }

    runtime_input = runtime.build_runtime_input(valid_draft)
    result = runtime.run(runtime_input)
    sections = runtime.build_result_sections(result)

    assert result["total_available_hours"] == 48.0
    assert result["fully_covered_courses"] == 0
    assert len(result["course_plan"]) == 3
    assert sections[0].title == "Итог плана"
    assert sections[2].title == "Рекомендации по курсам"
    assert sections[2].blocks[0].rows[0][0] == "Math"


def test_session_is_empty_after_reset_and_switch_ready_state() -> None:
    """Проверяет политику: пустая сессия может быть переключена на другой extension."""
    session = AgentSession()
    assert session_is_empty(session)

    session.scenario_draft.production = {"products": ["A"]}
    assert not session_is_empty(session)

    manifest = StudyPlannerExtensionProvider().get_manifest()
    reset_session_for_extension(session, alias="study_planner", manifest=manifest)

    assert session.extension_alias == "study_planner"
    assert session_is_empty(session)
    assert session.collection_state.current_stage == "courses"
