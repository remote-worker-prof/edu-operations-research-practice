"""Unit-тесты детерминированного парсера команд интерактивного ввода."""

from agent_core.input_parser import parse_user_command


def test_parser_recognizes_stage_json_command() -> None:
    """Проверяет JSON shortcut для stage-команды."""
    result = parse_user_command(
        message='json production {"products":["A"],"profits":[1],"resource_matrix":[[1]],'
        '"resource_limits":[10],"demand_upper_bounds":[10],"pallet_factors":[1]}',
        current_stage=None,
    )
    assert result.action == "stage_json"
    assert result.patch is not None
    assert result.patch.stage == "production"
    assert result.patch.payload is not None
    assert result.patch.payload["products"] == ["A"]


def test_parser_recognizes_set_command_with_nested_path() -> None:
    """Проверяет patch-команду set с вложенным path."""
    result = parse_user_command(
        message="set routing.depot_index 0",
        current_stage="routing",
    )
    assert result.action == "set_field"
    assert result.patch is not None
    assert result.patch.stage == "routing"
    assert result.patch.path == "depot_index"
    assert result.patch.value == 0


def test_parser_rejects_unknown_command() -> None:
    """Проверяет человеко-понятную ошибку на нераспознанную команду."""
    result = parse_user_command(message="абракадабра", current_stage=None)
    assert result.action == "invalid"
    assert result.errors
