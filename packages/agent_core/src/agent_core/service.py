"""High-level application service for dialog turns."""

from __future__ import annotations

from pathlib import Path

from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioBuilder

from agent_core.config import default_scenario_path
from agent_core.dialog_graph import build_dialog_graph
from agent_core.llm import LLMClient
from agent_core.models import AgentSession, ChatTurnRequest, TurnResult
from agent_core.session_store import InMemorySessionStore


class AgentService:
    """Facade used by web/API routes."""

    def __init__(
        self,
        *,
        scenario_path: Path | None = None,
        session_store: InMemorySessionStore | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._store = session_store or InMemorySessionStore()
        self._llm_client = llm_client or LLMClient()
        self._scenario_builder = ScenarioBuilder(scenario_path or default_scenario_path())
        self._or_pipeline = ORPipeline()
        self._dialog_graph = build_dialog_graph(
            scenario_builder=self._scenario_builder,
            or_pipeline=self._or_pipeline,
            llm_client=self._llm_client,
        )

    @property
    def store(self) -> InMemorySessionStore:
        return self._store

    def create_session(self, model_alias: str = "openai_default") -> AgentSession:
        session = self._store.create()
        session.model_alias = model_alias
        self._store.save(session)
        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        return self._store.get(session_id)

    def handle_turn(self, request: ChatTurnRequest) -> TurnResult:
        session = self._store.get_or_create(request.session_id)
        session.model_alias = request.model_alias

        output_state = self._dialog_graph.invoke(
            {
                "session": session,
                "user_message": request.message,
            }
        )
        updated_session = output_state["session"]
        self._store.save(updated_session)

        return TurnResult(
            session=updated_session,
            assistant_message=output_state.get("assistant_message", ""),
        )
