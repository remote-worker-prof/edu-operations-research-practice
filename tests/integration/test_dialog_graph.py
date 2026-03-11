from agent_core.models import ChatTurnRequest


def test_dialog_graph_missing_fields(agent_service) -> None:
    turn = agent_service.handle_turn(ChatTurnRequest(model_alias="local_default", message="Привет"))

    assert "укажите параметры" in turn.assistant_message.lower()
    assert turn.session.or_result is None


def test_dialog_graph_happy_path(agent_service) -> None:
    turn = agent_service.handle_turn(
        ChatTurnRequest(model_alias="local_default", message="спрос 1.0 ресурс 1.0")
    )

    assert turn.session.or_result is not None
    assert turn.session.or_result.execution_trace[-1] == "finalize_report"
