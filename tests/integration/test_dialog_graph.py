"""Интеграционные тесты ветвления DialogGraph.

Цель: зафиксировать поведение графа при неполных данных и при корректном входе.
"""

from agent_core.models import ChatTurnRequest


def test_dialog_graph_missing_fields(agent_service) -> None:
    """Проверяет ветку `ask_missing`, когда параметров недостаточно.

    Риск:
    - граф может ошибочно запускать OR-пайплайн без полного набора параметров.
    """
    # Arrange / Act
    turn = agent_service.handle_turn(ChatTurnRequest(model_alias="local_default", message="start"))

    # Assert
    assert "production" in turn.assistant_message.lower()
    assert turn.session.or_result is None


def test_dialog_graph_happy_path(agent_service) -> None:
    """Проверяет ветку полного успешного расчёта.

    Риск:
    - нарушение порядка узлов графа и потеря финального `execution_trace`.
    """
    # Arrange / Act
    preset_turn = agent_service.handle_turn(
        ChatTurnRequest(model_alias="local_default", message="load preset demo")
    )
    turn = agent_service.handle_turn(
        ChatTurnRequest(
            session_id=preset_turn.session.session_id,
            model_alias="local_default",
            message="run",
        )
    )

    # Assert
    assert turn.session.or_result is not None
    assert turn.session.or_result.execution_trace[-1] == "build_routes"
