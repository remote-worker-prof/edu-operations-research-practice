"""Unit tests for the semantics-driven conversation core."""

from __future__ import annotations

from agent_core.extensions import tolerant_discovery_report
from agent_core.models import AgentSession
from agent_core.patch_policy import PatchApplicationPolicy
from agent_core.semantic_command_interpreter import SemanticCommandInterpreter
from agent_core.semantic_nl_engine import SemanticIntentEngine
from agent_core.semantic_schema import runtime_bundle_semantics
from extension_api import IntentResolution, PatchProposal, SemanticIntent


def _bundle(alias: str):
    registry = tolerant_discovery_report().registry
    discovered = registry.require(alias)
    runtime = discovered.create_runtime()
    semantics = runtime_bundle_semantics(runtime)
    return discovered.manifest, semantics


def test_semantic_command_interpreter_uses_bundle_aliases_as_single_source_of_truth() -> None:
    """Slash parsing should resolve stage and field aliases from typed semantics."""
    manifest, semantics = _bundle("study_planner")

    resolution = SemanticCommandInterpreter().interpret(
        message="/set budget.hours_per_week 12",
        manifest=manifest,
        semantics=semantics,
    )

    assert resolution is not None
    assert resolution.intent.kind == "patch_draft"
    assert resolution.grounded is True
    assert len(resolution.proposals) == 1
    proposal = resolution.proposals[0]
    assert proposal.stage_id == "time_budget"
    assert proposal.path == "weekly_hours"
    assert proposal.value == 12


def test_semantic_command_interpreter_handles_mode_and_explain_commands() -> None:
    """Primary slash contract should expose power/guided mode and DSL explanations."""
    manifest, semantics = _bundle("transportation")
    interpreter = SemanticCommandInterpreter()

    mode_resolution = interpreter.interpret(
        message="/mode power",
        manifest=manifest,
        semantics=semantics,
    )
    explain_resolution = interpreter.interpret(
        message="/explain extension",
        manifest=manifest,
        semantics=semantics,
    )

    assert mode_resolution is not None
    assert mode_resolution.intent.kind == "mode"
    assert mode_resolution.intent.interaction_mode == "power"
    assert explain_resolution is not None
    assert explain_resolution.intent.kind == "explain"
    assert explain_resolution.intent.target == "extension"


def test_semantic_nl_engine_extracts_grounded_study_planner_patch_proposals() -> None:
    """Open-ended NL should stay grounded in the active extension semantics."""
    manifest, semantics = _bundle("study_planner")

    resolution = SemanticIntentEngine().interpret(
        message='budget hours_per_week 12, study_weeks 4',
        current_stage="courses",
        manifest=manifest,
        semantics=semantics,
        model_alias=None,
    )

    assert resolution.intent.kind == "patch_draft"
    assert resolution.grounded is True
    assert resolution.clarifications == []
    assert {(item.stage_id, item.path) for item in resolution.proposals} == {
        ("time_budget", "weekly_hours"),
        ("time_budget", "weeks"),
    }


def test_semantic_nl_engine_extracts_default_or_patch_proposals_without_hardcoded_product_path(
) -> None:
    """Migrated default_or should use the same semantics-first NL layer as declarative bundles."""
    manifest, semantics = _bundle("default_or")

    resolution = SemanticIntentEngine().interpret(
        message='production profits [40,30], products ["A","B"]',
        current_stage=None,
        manifest=manifest,
        semantics=semantics,
        model_alias=None,
    )

    assert resolution.intent.kind == "patch_draft"
    assert resolution.grounded is True
    assert {(item.stage_id, item.path) for item in resolution.proposals} == {
        ("production", "profits"),
        ("production", "products"),
    }


def test_patch_policy_keeps_guided_mode_safe_and_power_mode_grounded() -> None:
    """Guided mode confirms; power mode auto-applies only well-grounded patches."""
    policy = PatchApplicationPolicy()
    guided_session = AgentSession(interaction_mode="guided")
    power_session = AgentSession(interaction_mode="power")
    safe_resolution = IntentResolution(
        source="semantic_nl",
        intent=SemanticIntent(kind="patch_draft", raw_message="test"),
        confidence=0.0,
        grounded=False,
    )
    grounded_resolution = IntentResolution(
        source="semantic_nl",
        intent=SemanticIntent(kind="patch_draft", raw_message="test"),
        proposals=[
            PatchProposal(
                stage_id="courses",
                path="required_hours",
                value=[12, 18],
                confidence=0.92,
                source="semantic_nl",
            )
        ],
        confidence=0.92,
        grounded=True,
        clarifications=[],
    )
    uncertain_resolution = grounded_resolution.model_copy(
        update={"confidence": 0.6}
    )

    assert policy.requires_confirmation(
        session=guided_session,
        resolution=grounded_resolution,
    )
    assert not policy.requires_confirmation(
        session=power_session,
        resolution=grounded_resolution,
    )
    assert policy.requires_confirmation(
        session=power_session,
        resolution=uncertain_resolution,
    )
    assert not policy.requires_confirmation(
        session=power_session,
        resolution=safe_resolution,
    )
