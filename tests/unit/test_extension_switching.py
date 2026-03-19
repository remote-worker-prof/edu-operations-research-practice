"""Unit tests for manifest-driven extension switching and the sample runtime."""

from __future__ import annotations

from agent_core.default_or_extension import DefaultORExtensionProvider
from agent_core.extension_commands import (
    build_field_alias_map,
    build_stage_alias_map,
    parse_extension_command,
)
from agent_core.extension_flow import (
    manifest_for_alias,
    reset_session_for_extension,
    session_is_empty,
    sync_default_or_compatibility_state,
)
from agent_core.models import AgentSession, TurnResult
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
    assert alias_map["time budget"] == "time_budget"
    assert alias_map["приоритеты"] == "priorities"

    result = parse_extension_command(
        message='json budget {"weekly_hours":12,"weeks":4}',
        current_stage=None,
        manifest=manifest,
    )
    assert result.action == "stage_json"
    assert result.stage == "time_budget"


def test_generic_parser_supports_multiword_stage_labels_in_edit_json_and_set() -> None:
    """Проверяет longest-match resolution для multi-word stage labels/aliases."""
    manifest = StudyPlannerExtensionProvider().get_manifest()

    edit_ru = parse_extension_command(
        message="edit бюджет времени",
        current_stage=None,
        manifest=manifest,
    )
    assert edit_ru.action == "edit_stage"
    assert edit_ru.stage == "time_budget"

    json_ru = parse_extension_command(
        message='json бюджет времени {"weekly_hours":12,"weeks":4}',
        current_stage=None,
        manifest=manifest,
    )
    assert json_ru.action == "stage_json"
    assert json_ru.stage == "time_budget"
    assert json_ru.patch is not None
    assert json_ru.patch.payload == {"weekly_hours": 12, "weeks": 4}

    set_ru = parse_extension_command(
        message="set бюджет времени.weekly_hours 12",
        current_stage=None,
        manifest=manifest,
    )
    assert set_ru.action == "set_field"
    assert set_ru.stage == "time_budget"
    assert set_ru.patch is not None
    assert set_ru.patch.path == "weekly_hours"
    assert set_ru.patch.value == 12

    json_en = parse_extension_command(
        message='json time budget {"weekly_hours":10,"weeks":3}',
        current_stage=None,
        manifest=manifest,
    )
    assert json_en.action == "stage_json"
    assert json_en.stage == "time_budget"

    set_en = parse_extension_command(
        message="set time budget.weeks 5",
        current_stage=None,
        manifest=manifest,
    )
    assert set_en.action == "set_field"
    assert set_en.stage == "time_budget"
    assert set_en.patch is not None
    assert set_en.patch.path == "weeks"
    assert set_en.patch.value == 5


def test_sample_manifest_field_aliases_are_canonicalized_in_set_json_and_raw_json() -> None:
    """Проверяет canonicalization alias paths для sample extension."""
    manifest = StudyPlannerExtensionProvider().get_manifest()
    field_aliases = build_field_alias_map(manifest, "time_budget")

    assert field_aliases["hours_per_week"] == "weekly_hours"
    assert field_aliases["study_weeks"] == "weeks"

    set_alias = parse_extension_command(
        message="set time budget.hours_per_week 12",
        current_stage=None,
        manifest=manifest,
    )
    assert set_alias.action == "set_field"
    assert set_alias.patch is not None
    assert set_alias.patch.path == "weekly_hours"
    assert set_alias.patch.value == 12

    json_alias = parse_extension_command(
        message=('json courses {"course_names":["Math","ML"],"hours_needed":[30,24]}'),
        current_stage=None,
        manifest=manifest,
    )
    assert json_alias.action == "stage_json"
    assert json_alias.patch is not None
    assert json_alias.patch.payload == {
        "names": ["Math", "ML"],
        "hours_required": [30, 24],
    }

    raw_json_alias = parse_extension_command(
        message='{"hours_per_week":12,"study_weeks":4}',
        current_stage="time_budget",
        manifest=manifest,
    )
    assert raw_json_alias.action == "stage_json"
    assert raw_json_alias.patch is not None
    assert raw_json_alias.patch.payload == {
        "weekly_hours": 12,
        "weeks": 4,
    }


def test_parser_rejects_conflicting_alias_and_canonical_values_in_same_json_payload() -> None:
    """Проверяет явный отказ на конфликт alias/canonical key в одном payload."""
    manifest = StudyPlannerExtensionProvider().get_manifest()

    result = parse_extension_command(
        message='json time budget {"weekly_hours":12,"hours_per_week":10,"weeks":4}',
        current_stage=None,
        manifest=manifest,
    )

    assert result.action == "invalid"
    assert result.errors
    assert "Конфликт alias-ключей" in result.errors[0]


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


def test_sample_extension_provider_exposes_working_builtin_demo_preset() -> None:
    """Проверяет, что sample extension действительно умеет load preset demo."""
    provider = StudyPlannerExtensionProvider()
    preset = provider.load_preset("demo")
    runtime = provider.create_runtime()

    assert runtime.validate_draft(preset) == {
        "courses": [],
        "time_budget": [],
        "priorities": [],
    }
    assert preset["courses"]["names"] == ["Math", "ML", "Databases"]
    assert preset["time_budget"]["weeks"] == 4


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


def test_agent_session_and_turn_result_expose_generic_extension_state_snapshot() -> None:
    """Проверяет generic extension snapshot в session и turn transport models."""
    session = AgentSession(
        extension_alias="study_planner",
        extension_draft={"courses": {"names": ["Math"], "hours_required": [30]}},
        extension_result={"total_available_hours": 48.0},
        extension_stage_statuses=[
            {
                "stage_id": "courses",
                "label": "Курсы",
                "ready": True,
                "current": True,
            }
        ],
    )

    assert session.extension_state.alias == "study_planner"
    assert session.extension_state.draft["courses"]["names"] == ["Math"]
    assert session.extension_state.result == {"total_available_hours": 48.0}
    assert session.extension_state.stage_statuses[0].stage_id == "courses"
    assert session.extension_state.stage_statuses[0].current is True

    turn = TurnResult(session=session, assistant_message="ok")

    assert turn.extension_state.alias == "study_planner"
    assert turn.extension_state.draft == session.extension_draft
    assert turn.model_dump(mode="json")["extension_state"]["alias"] == "study_planner"


def test_sync_default_or_compatibility_state_populates_generic_mirrors() -> None:
    """Проверяет, что legacy default_or session получает честный generic snapshot."""
    registry = _registry_with_default_and_sample()
    session = AgentSession()
    session.scenario_draft.production = {"products": ["A"]}

    sync_default_or_compatibility_state(session=session, registry=registry)

    assert session.extension_alias == "default_or"
    assert session.extension_state.draft["production"] == {"products": ["A"]}
    assert [item.stage_id for item in session.extension_state.stage_statuses] == [
        "production",
        "shipment",
        "assignment",
        "routing",
    ]
    assert session.extension_state.stage_statuses[0].current is True
    assert session.extension_state.stage_statuses[0].ready is False
