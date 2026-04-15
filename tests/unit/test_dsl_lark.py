"""Unit-тесты для Lark grammar-core и минимального AST команд DSL."""

from agent_core.dsl_lark import (
    EditCommandNode,
    JsonCommandNode,
    RawJsonCommandNode,
    SetCommandNode,
    TextCommandNode,
    parse_command_surface,
)


def test_lark_core_parses_edit_surface() -> None:
    """Проверяет, что grammar-core выделяет форму `edit <stage>`."""
    node = parse_command_surface("edit бюджет времени")
    assert isinstance(node, EditCommandNode)
    assert node.argument == "бюджет времени"


def test_lark_core_parses_json_surface() -> None:
    """Проверяет, что grammar-core выделяет форму `json <stage> { ... }`."""
    node = parse_command_surface('json time budget {"weekly_hours":12,"weeks":4}')
    assert isinstance(node, JsonCommandNode)
    assert node.argument == 'time budget {"weekly_hours":12,"weeks":4}'


def test_lark_core_parses_set_surface() -> None:
    """Проверяет, что grammar-core выделяет форму `set <stage>.<field> <value>`."""
    node = parse_command_surface("set time budget.weeks 5")
    assert isinstance(node, SetCommandNode)
    assert node.argument == "time budget.weeks 5"


def test_lark_core_parses_raw_json_shortcut() -> None:
    """Проверяет поддержку raw JSON shortcut как отдельного AST-узла."""
    node = parse_command_surface('{"hours_per_week":12,"study_weeks":4}')
    assert isinstance(node, RawJsonCommandNode)
    assert node.payload_text == '{"hours_per_week":12,"study_weeks":4}'


def test_lark_core_falls_back_to_text_for_non_structural_command() -> None:
    """Проверяет fallback-ветку grammar-core для неструктурных команд."""
    node = parse_command_surface("start")
    assert isinstance(node, TextCommandNode)
    assert node.raw_text == "start"
