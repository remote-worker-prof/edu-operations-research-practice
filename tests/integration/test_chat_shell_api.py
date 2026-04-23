"""Integration tests for the new thread API and CopilotKit/AG-UI transport."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from webapp.main import create_app


def _decode_sse_events(body: str) -> list[dict[str, object]]:
    """Extracts AG-UI SSE payloads from one streaming response body."""
    events: list[dict[str, object]] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def _fake_chat_web_export(tmp_path: Path) -> Path:
    """Creates a minimal static export directory for `/app/*` integration checks."""
    export_dir = tmp_path / "chat_web_export"
    export_dir.mkdir()
    (export_dir / "index.html").write_text(
        (
            "<!doctype html><html><body>"
            "<div data-testid='react-chat-shell'>chat shell</div>"
            "</body></html>"
        ),
        encoding="utf-8",
    )
    return export_dir


def test_root_redirects_to_app_and_legacy_ui_remains_available(tmp_path: Path) -> None:
    """Product root should point to the React shell, while `/legacy` still serves HTMX."""
    client = TestClient(create_app(chat_web_export_dir=_fake_chat_web_export(tmp_path)))

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/app/"

    app_shell = client.get("/app/")
    assert app_shell.status_code == 200
    assert "react-chat-shell" in app_shell.text

    legacy = client.get("/legacy")
    assert legacy.status_code == 200
    assert 'id="workspace"' in legacy.text


def test_app_route_shows_clear_fallback_when_static_export_is_missing(tmp_path: Path) -> None:
    """Local backend should explain how to build the React shell if `/app/` assets are absent."""
    client = TestClient(create_app(chat_web_export_dir=tmp_path / "missing-export"))

    response = client.get("/app/")
    assert response.status_code == 503
    assert "make chat-web-build" in response.text
    assert "/legacy" in response.text


def test_copilotkit_runtime_info_matches_js_runtime_shape() -> None:
    """React CopilotKit runtime discovery should receive a dict-based agent catalog."""
    client = TestClient(create_app())

    response = client.get("/api/copilotkit/info")
    assert response.status_code == 200

    payload = response.json()
    assert payload["mode"] == "sse"
    assert payload["audioFileTranscriptionEnabled"] is False
    assert payload["agents"]["edu_or_chat"]["description"]
    assert payload["agents"]["edu_or_chat"]["capabilities"] == {}


def test_thread_endpoints_create_turn_and_expose_interaction_state() -> None:
    """The new React shell should get thread CRUD and typed interaction state from FastAPI."""
    client = TestClient(create_app())

    create_response = client.post(
        "/api/chat/threads",
        json={
            "model_alias": "openai_default",
            "extension_alias": "study_planner",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    thread_id = created["thread"]["thread_id"]
    assert created["interaction"]["active_extension"] == "study_planner"
    assert created["interaction"]["current_stage"] == "courses"

    turn_response = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={
            "model_alias": "openai_default",
            "message": (
                '/payload courses {"course_names":["Math","Physics"],"required_hours":[12,18]}'
            ),
        },
    )
    assert turn_response.status_code == 200
    turn_payload = turn_response.json()
    assert turn_payload["interaction"]["current_stage"] == "time_budget"
    assert turn_payload["interaction"]["draft"]["courses"]["course_names"] == ["Math", "Physics"]

    interaction_response = client.get(f"/api/chat/threads/{thread_id}/interaction")
    assert interaction_response.status_code == 200
    interaction = interaction_response.json()
    assert interaction["expected_payload"] == {"weekly_hours": 0, "weeks": 0}

    list_response = client.get("/api/chat/threads")
    assert list_response.status_code == 200
    listed_threads = list_response.json()
    assert any(item["thread_id"] == thread_id for item in listed_threads)


def test_thread_turn_supports_matrix_payloads_and_validation_hints() -> None:
    """Matrix-based declarative bundles should work through the new thread transport."""
    client = TestClient(create_app())

    create_response = client.post(
        "/api/chat/threads",
        json={
            "model_alias": "openai_default",
            "extension_alias": "transportation",
        },
    )
    thread_id = create_response.json()["thread"]["thread_id"]

    commands = [
        '/payload origins {"origin_names":["North","South"],"supply":[20,15]}',
        '/payload destinations {"destination_names":["A","B"],"demand":[10,25]}',
        '/payload costs {"cost_matrix":[[4,6],[5,4]]}',
        "/solve",
    ]
    last_turn = None
    for message in commands:
        response = client.post(
            f"/api/chat/threads/{thread_id}/turn",
            json={"model_alias": "openai_default", "message": message},
        )
        assert response.status_code == 200
        last_turn = response.json()

    assert last_turn is not None
    assert last_turn["interaction"]["active_extension"] == "transportation"
    result_sections = last_turn["turn"]["session"]["extension_result_sections"]
    assert result_sections[0]["blocks"][0]["type"] in {"kv", "summary"}
    assert any(
        block["type"] == "table" for section in result_sections for block in section["blocks"]
    )


def test_copilotkit_agui_endpoint_streams_agent_events() -> None:
    """CopilotKit endpoint should stream AG-UI events over the backend-owned thread state."""
    client = TestClient(create_app())

    thread_response = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "study_planner"},
    )
    thread_id = thread_response.json()["thread"]["thread_id"]

    response = client.post(
        "/api/copilotkit/agent/edu_or_chat",
        json={
            "threadId": thread_id,
            "state": {},
            "messages": [
                {
                    "id": "msg-1",
                    "createdAt": "2026-04-22T00:00:00Z",
                    "role": "user",
                    "content": "/help",
                }
            ],
            "actions": [],
            "nodeName": "root",
        },
    )

    assert response.status_code == 200
    events = _decode_sse_events(response.text)
    event_types = [event["type"] for event in events]
    assert event_types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_CONTENT" in event_types
    assert "STATE_SNAPSHOT" in event_types
    assert event_types[-1] == "RUN_FINISHED"

    snapshot = next(event["snapshot"] for event in events if event["type"] == "STATE_SNAPSHOT")
    assert snapshot["interaction"]["active_extension"] == "study_planner"


def test_default_or_uses_same_thread_transport_in_plain_chat_mode() -> None:
    """Legacy default_or should still work through the new thread transport."""
    client = TestClient(create_app())

    create_response = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "default_or"},
    )
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread"]["thread_id"]

    turn_response = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={
            "model_alias": "openai_default",
            "message": "Покажи, какие этапы сейчас доступны в стандартном OR-конвейере.",
        },
    )
    assert turn_response.status_code == 200
    payload = turn_response.json()
    assert payload["interaction"]["active_extension"] == "default_or"
    assistant_message = payload["turn"]["assistant_message"].lower()
    assert "production" in assistant_message
    assert "shipment" in assistant_message
    assert "assignment" in assistant_message
    assert "routing" in assistant_message
    assert payload["turn"]["session"]["messages"][-1]["role"] == "assistant"
