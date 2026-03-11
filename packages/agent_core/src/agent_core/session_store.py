"""Потокобезопасное in-memory хранилище сессий для демо-версии.

Модуль intentionally простой: без БД и внешней персистентности, чтобы студентам
было легче понять базовый жизненный цикл state-объекта.
"""

from __future__ import annotations

from threading import Lock

from agent_core.models import AgentSession


class InMemorySessionStore:
    """Простое потокобезопасное хранилище `session_id -> AgentSession`."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._lock = Lock()

    def create(self) -> AgentSession:
        """Создаёт новую сессию и сразу сохраняет её в словаре."""
        session = AgentSession()
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AgentSession | None:
        """Возвращает глубокую копию сессии по id или `None`."""
        with self._lock:
            session = self._sessions.get(session_id)
            return session.model_copy(deep=True) if session else None

    def get_or_create(self, session_id: str | None) -> AgentSession:
        """Возвращает существующую сессию или создаёт новую, если id отсутствует/не найден."""
        if session_id:
            existing = self.get(session_id)
            if existing:
                return existing
        return self.create()

    def save(self, session: AgentSession) -> AgentSession:
        """Сохраняет (копию) сессии и возвращает исходный объект."""
        with self._lock:
            self._sessions[session.session_id] = session.model_copy(deep=True)
        return session
