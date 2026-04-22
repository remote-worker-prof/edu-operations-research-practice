"""CopilotKit/AG-UI adapter over the existing backend-owned AgentService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ag_ui.core import (
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder
from copilotkit import Agent

from agent_core.config import DEFAULT_MODEL_ALIAS
from agent_core.models import ChatTurnRequest
from agent_core.service import AgentService


def _message_content(message: dict[str, Any]) -> str:
    """Extracts plain text from CopilotKit/AG-UI message payloads."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


class SemanticsChatAgent(Agent):
    """AG-UI agent that delegates execution to the existing deterministic backend."""

    def __init__(self, *, service: AgentService) -> None:
        super().__init__(
            name="edu_or_chat",
            description="Guided educational OR chat over typed extension semantics.",
        )
        self._service = service
        self._encoder = EventEncoder()

    async def get_state(
        self,
        *,
        thread_id: str,
    ) -> dict[str, Any]:
        """Returns backend-owned thread state for CopilotKit state hydration."""
        session = self._service.get_session(thread_id)
        if session is None:
            return {
                "threadId": thread_id,
                "threadExists": False,
                "state": {},
                "messages": [],
            }

        interaction = self._service.build_interaction_state(thread_id)
        return {
            "threadId": thread_id,
            "threadExists": True,
            "state": {
                "interaction": (
                    interaction.model_dump(mode="json")
                    if interaction is not None
                    else None
                ),
                "session": session.model_dump(mode="json"),
            },
            "messages": [
                {
                    "id": f"{thread_id}:{index}",
                    "createdAt": session.updated_at.isoformat(),
                    "role": message.role,
                    "content": message.content,
                }
                for index, message in enumerate(session.messages)
            ],
        }

    def execute(
        self,
        *,
        state: dict,
        config: dict | None = None,
        messages: list[dict[str, Any]],
        thread_id: str,
        actions: list[dict[str, Any]] | None = None,
        meta_events: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Streams AG-UI events while delegating one turn to `AgentService`."""
        del actions, meta_events, kwargs
        latest_user_message = next(
            (
                _message_content(message)
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        ).strip()
        if not latest_user_message:
            latest_user_message = "/help"

        model_alias = DEFAULT_MODEL_ALIAS
        if isinstance(config, dict):
            model_alias = str(config.get("model_alias") or model_alias)
        if isinstance(state, dict):
            interaction_state = state.get("interaction", {})
            if isinstance(interaction_state, dict):
                model_alias = str(interaction_state.get("model_alias") or model_alias)

        turn = self._service.handle_slash_turn(
            ChatTurnRequest(
                session_id=thread_id,
                model_alias=model_alias,
                message=latest_user_message,
            )
        )
        interaction = self._service.build_interaction_state(turn.session.session_id)

        run_id = str(uuid4())
        message_id = str(uuid4())
        snapshot = {
            "interaction": interaction.model_dump(mode="json") if interaction is not None else None,
            "session": turn.session.model_dump(mode="json"),
        }
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        yield self._encoder.encode(
            RunStartedEvent(
                threadId=turn.session.session_id,
                runId=run_id,
                timestamp=timestamp_ms,
            )
        )
        yield self._encoder.encode(
            TextMessageStartEvent(
                messageId=message_id,
                role="assistant",
                timestamp=timestamp_ms,
            )
        )
        yield self._encoder.encode(
            TextMessageContentEvent(
                messageId=message_id,
                delta=turn.assistant_message,
                timestamp=timestamp_ms,
            )
        )
        yield self._encoder.encode(
            TextMessageEndEvent(
                messageId=message_id,
                timestamp=timestamp_ms,
            )
        )
        yield self._encoder.encode(
            StateSnapshotEvent(
                snapshot=snapshot,
                timestamp=timestamp_ms,
            )
        )
        yield self._encoder.encode(
            RunFinishedEvent(
                threadId=turn.session.session_id,
                runId=run_id,
                result={
                    "assistantMessage": turn.assistant_message,
                    "interaction": snapshot["interaction"],
                },
                timestamp=timestamp_ms,
            )
        )
