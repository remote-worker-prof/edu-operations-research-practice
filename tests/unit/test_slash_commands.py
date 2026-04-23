"""Unit tests for the new slash-command layer and interaction-state seam."""

from __future__ import annotations

from agent_core.models import ChatTurnRequest
from agent_core.service import AgentService
from agent_core.slash_commands import (
    parse_slash_command,
    validate_payload_json,
)


def test_parse_slash_command_supports_payload_and_show_default() -> None:
    """`/payload` and bare `/show` should normalize into stable internal forms."""
    payload = parse_slash_command('/payload costs {"cost_matrix":[[4, 6], [5, 4]]}')
    show = parse_slash_command("/show")

    assert payload is not None
    assert payload.name == "payload"
    assert payload.arg == "costs"
    assert payload.payload == '{"cost_matrix":[[4, 6], [5, 4]]}'
    assert show is not None
    assert show.name == "show"
    assert show.arg == "steps"


def test_validate_payload_json_rejects_non_object() -> None:
    """`/payload` must reject arrays and other non-object JSON values early."""
    command = parse_slash_command("/payload priorities [1,2,3]")
    assert command is not None

    error = validate_payload_json(command)

    assert error == "Команда /payload ожидает JSON-объект."


def test_parse_slash_command_returns_none_for_bare_command_syntax() -> None:
    """Legacy bare commands should not be parsed as slash commands in the primary shell."""
    assert parse_slash_command("start") is None
    assert parse_slash_command("run") is None
    assert parse_slash_command('json priorities {"priority":[5,4]}') is None


def test_agent_service_rejects_bare_command_in_slash_turn_path() -> None:
    """Primary slash/thread path should reject bare command syntax with deterministic guidance."""
    service = AgentService()
    session = service.create_session(model_alias="openai_default")

    result = service.handle_slash_turn(
        ChatTurnRequest(
            session_id=session.session_id,
            model_alias="openai_default",
            message="start",
        )
    )

    assert "Команда без `/` (`start`) недоступна в новом чате `/app`." in result.assistant_message
    assert "/help" in result.assistant_message
    assert result.session.last_intent_resolution is not None
    assert result.session.last_intent_resolution.source == "legacy_bare"
    assert result.session.extension_draft == {}


def test_agent_service_handles_new_extension_thread_reset_via_slash_new() -> None:
    """`/new <extension>` should reset the current thread and start the new extension."""
    service = AgentService()
    session = service.create_session(model_alias="openai_default")

    result = service.handle_slash_turn(
        ChatTurnRequest(
            session_id=session.session_id,
            model_alias="openai_default",
            message="/new study_planner",
        )
    )

    assert result.session.extension_alias == "study_planner"
    assert result.session.messages[-2].content == "/new study_planner"
    assert "Заполните stage" in result.assistant_message
