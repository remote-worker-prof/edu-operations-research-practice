"""Unit-тесты NL-парсера для гибридного dialog-режима."""

from agent_core.models import LLMResponse
from agent_core.nl_parser import parse_nl_turn


def test_parse_nl_turn_extracts_stage_patches() -> None:
    """Проверяет извлечение candidate patches из свободной реплики."""
    result = parse_nl_turn(
        message='production profits [40,30], products ["A","B"]',
        current_stage=None,
    )
    assert result.intent == "patch"
    assert result.candidate_patches
    assert result.uncertainties == []
    assert {patch.field_path for patch in result.candidate_patches} == {"profits", "products"}


def test_parse_nl_turn_detects_ambiguous_stage() -> None:
    """Проверяет detection неоднозначности, когда в сообщении несколько stages."""
    result = parse_nl_turn(
        message="production shipment cost_matrix [[1,2],[2,1]]",
        current_stage=None,
    )
    assert result.intent == "patch"
    assert result.candidate_patches == []
    assert result.uncertainties


def test_parse_nl_turn_handles_confirmation_intent() -> None:
    """Проверяет специальные NL-интенции подтверждения."""
    result = parse_nl_turn(message="да", current_stage="production")
    assert result.intent == "confirm"
    assert result.confidence == 1.0


def test_parse_nl_turn_leaves_help_command_for_deterministic_parser() -> None:
    """Проверяет, что `help` идёт в command parser, а не в NL-help ветку."""
    result = parse_nl_turn(message="help", current_stage="production")
    assert result.intent == "none"


def test_parse_nl_turn_leaves_russian_show_alias_for_deterministic_parser() -> None:
    """Проверяет, что `показать` не перехватывается NL-слоем."""
    result = parse_nl_turn(message="показать", current_stage="production")
    assert result.intent == "none"


def test_parse_nl_turn_leaves_raw_json_shortcut_for_command_parser() -> None:
    """Проверяет, что raw JSON shortcut не перехватывается NL-слоем."""
    result = parse_nl_turn(
        message='{"warehouses":["W1","W2"],"clients":["C1","C2"]}',
        current_stage="shipment",
    )
    assert result.intent == "none"


def test_parse_nl_turn_prefers_patch_over_run_when_fields_present() -> None:
    """Проверяет policy precedence: extraction выше run при наличии полей."""
    result = parse_nl_turn(
        message='запусти production profits [40,30], products ["A","B"]',
        current_stage=None,
    )
    assert result.intent == "patch"
    assert {patch.field_path for patch in result.candidate_patches} == {"profits", "products"}


class _FakeLLMClient:
    """Минимальный test-double для LLM fallback без сетевых вызовов."""

    def available_aliases(self) -> list[str]:
        return ["openai_default"]

    def complete(
        self,
        *,
        messages,
        model_alias: str,
        task_mode: str,
        temperature: float = 0,
    ) -> LLMResponse:
        del messages, task_mode, temperature
        return LLMResponse(
            content=(
                '{"stage":"shipment","patches":[{"field_path":"clients","value":["C1","C2"]}],'
                '"uncertainties":[]}'
            ),
            model_alias=model_alias,
            model_name="fake-model",
        )


def test_parse_nl_turn_uses_llm_fallback_for_stage_detection() -> None:
    """Проверяет LLM-assisted fallback, когда детерминированно stage не найден."""
    result = parse_nl_turn(
        message="Нужно отгрузить на клиентов C1 и C2, обнови список",
        current_stage=None,
        llm_client=_FakeLLMClient(),
        model_alias="openai_default",
    )
    assert result.intent == "patch"
    assert result.candidate_patches
    assert result.candidate_patches[0].stage == "shipment"
    assert result.candidate_patches[0].field_path == "clients"
