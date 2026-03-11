"""In-memory session storage for v1 demo."""

from __future__ import annotations

from threading import Lock

from agent_core.models import AgentSession


class InMemorySessionStore:
    """Simple thread-safe in-memory store keyed by session_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._lock = Lock()

    def create(self) -> AgentSession:
        session = AgentSession()
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AgentSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.model_copy(deep=True) if session else None

    def get_or_create(self, session_id: str | None) -> AgentSession:
        if session_id:
            existing = self.get(session_id)
            if existing:
                return existing
        return self.create()

    def save(self, session: AgentSession) -> AgentSession:
        with self._lock:
            self._sessions[session.session_id] = session.model_copy(deep=True)
        return session
