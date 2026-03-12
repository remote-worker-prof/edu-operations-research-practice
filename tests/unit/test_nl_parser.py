"""Unit-тесты NL-парсера для гибридного dialog-режима."""

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
