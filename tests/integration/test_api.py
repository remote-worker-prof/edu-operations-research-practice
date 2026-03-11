import re

from fastapi.testclient import TestClient
from webapp.main import app

client = TestClient(app)


def test_api_chat_turn_success(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is not None


def test_api_provider_unavailable_warning(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["warnings"]


def test_htmx_turn_full_cycle(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    page = client.get("/")
    assert page.status_code == 200

    match = re.search(r'name="session_id" value="([^"]+)"', page.text)
    assert match is not None
    session_id = match.group(1)

    partial = client.post(
        "/chat/turn",
        data={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
        },
    )
    assert partial.status_code == 200
    assert "Суммарная длина" in partial.text
