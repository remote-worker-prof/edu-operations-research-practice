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


def test_thread_transport_rejects_legacy_bare_commands_in_primary_shell() -> None:
    """`/app` thread transport should reject bare command syntax and point users to slash/guided."""
    client = TestClient(create_app())
    thread_id = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "study_planner"},
    ).json()["thread"]["thread_id"]

    response = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert response.status_code == 200
    payload = response.json()
    assistant_message = payload["turn"]["assistant_message"]
    assert "Команда без `/` (`start`) недоступна в новом чате `/app`." in assistant_message
    assert "/legacy" in assistant_message
    assert payload["interaction"]["last_intent"]["source"] == "legacy_bare"
    assert payload["interaction"]["current_stage"] == "courses"
    assert payload["interaction"]["draft"] == {}


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


def test_thread_turn_explain_model_and_extension_are_grounded_in_real_artifacts() -> None:
    """Explain-mode should read actual bundle artifacts or virtual canonical artifacts."""
    client = TestClient(create_app())

    study_thread = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "study_planner"},
    ).json()["thread"]["thread_id"]
    default_or_thread = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "default_or"},
    ).json()["thread"]["thread_id"]

    study_model = client.post(
        f"/api/chat/threads/{study_thread}/turn",
        json={"model_alias": "openai_default", "message": "/explain model"},
    )
    assert study_model.status_code == 200
    assert "set COURSES;" in study_model.json()["turn"]["assistant_message"]

    study_extension = client.post(
        f"/api/chat/threads/{study_thread}/turn",
        json={"model_alias": "openai_default", "message": "/explain extension"},
    )
    assert study_extension.status_code == 200
    assert "format: student_math_v2" in study_extension.json()["turn"]["assistant_message"]

    default_or_model = client.post(
        f"/api/chat/threads/{default_or_thread}/turn",
        json={"model_alias": "openai_default", "message": "/explain model"},
    )
    assert default_or_model.status_code == 200
    assert "четырёхэтапный OR-конвейер" in default_or_model.json()["turn"]["assistant_message"]


def test_guided_mode_keeps_open_ended_patch_in_confirmation_flow() -> None:
    """Guided mode should require explicit confirmation before applying NL draft patches."""
    client = TestClient(create_app())

    thread_id = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "study_planner"},
    ).json()["thread"]["thread_id"]

    proposed = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={
            "model_alias": "openai_default",
            "message": 'courses course_names ["Math","Physics"], required_hours [12,18]',
        },
    )
    assert proposed.status_code == 200
    proposed_payload = proposed.json()
    assert "напишите `да`" in proposed_payload["turn"]["assistant_message"]
    assert len(proposed_payload["interaction"]["pending_proposals"]) == 2
    assert proposed_payload["interaction"]["current_stage"] == "courses"

    confirmed = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={"model_alias": "openai_default", "message": "да"},
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["interaction"]["pending_proposals"] == []
    assert confirmed_payload["interaction"]["draft"]["courses"]["course_names"] == [
        "Math",
        "Physics",
    ]
    assert confirmed_payload["interaction"]["current_stage"] == "time_budget"


def test_power_mode_auto_applies_grounded_default_or_patch_without_special_product_path() -> None:
    """Migrated default_or should auto-apply grounded NL updates in power mode."""
    client = TestClient(create_app())

    thread_id = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "default_or"},
    ).json()["thread"]["thread_id"]

    mode_response = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={"model_alias": "openai_default", "message": "/mode power"},
    )
    assert mode_response.status_code == 200
    assert mode_response.json()["interaction"]["interaction_mode"] == "power"

    patched = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={
            "model_alias": "openai_default",
            "message": (
                'production products ["A","B"], profits [40,30], '
                'resource_matrix [[2,1],[1,1.5]], resource_limits [240,180], '
                'demand_upper_bounds [70,80], pallet_factors [1.0,0.8]'
            ),
        },
    )
    assert patched.status_code == 200
    patched_payload = patched.json()
    assert patched_payload["interaction"]["interaction_mode"] == "power"
    assert patched_payload["interaction"]["pending_proposals"] == []
    assert patched_payload["interaction"]["draft"]["production"]["products"] == ["A", "B"]
    assert patched_payload["interaction"]["draft"]["production"]["profits"] == [40, 30]
    assert "Изменения применены." in patched_payload["turn"]["assistant_message"]


def test_transportation_accepts_matrix_patch_from_open_ended_message() -> None:
    """Matrix-aware declarative bundles should ground 2-D NL updates in the typed schema."""
    client = TestClient(create_app())

    thread_id = client.post(
        "/api/chat/threads",
        json={"model_alias": "openai_default", "extension_alias": "transportation"},
    ).json()["thread"]["thread_id"]

    setup_messages = [
        '/payload origins {"origin_names":["North","South"],"supply":[20,15]}',
        '/payload destinations {"destination_names":["East","West"],"demand":[10,25]}',
        "/mode power",
    ]
    for message in setup_messages:
        response = client.post(
            f"/api/chat/threads/{thread_id}/turn",
            json={"model_alias": "openai_default", "message": message},
        )
        assert response.status_code == 200

    patched = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={
            "model_alias": "openai_default",
            "message": "costs cost_matrix [[4,6],[5,4]]",
        },
    )
    assert patched.status_code == 200
    patched_payload = patched.json()
    assert patched_payload["interaction"]["interaction_mode"] == "power"
    assert len(patched_payload["interaction"]["pending_proposals"]) == 1
    assert "напишите `да`" in patched_payload["turn"]["assistant_message"]

    confirmed = client.post(
        f"/api/chat/threads/{thread_id}/turn",
        json={"model_alias": "openai_default", "message": "да"},
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["interaction"]["pending_proposals"] == []
    assert confirmed_payload["interaction"]["draft"]["costs"]["cost_matrix"] == [
        [4, 6],
        [5, 4],
    ]
    assert "Изменения применены." in confirmed_payload["turn"]["assistant_message"]
