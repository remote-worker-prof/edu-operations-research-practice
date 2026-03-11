"""Pydantic-контракты для диалогового агента и web/API интерфейсов.

Назначение модуля:
- хранить типизированные модели состояния сессии и payload API;
- централизовать валидацию пользовательских данных.

Роль в архитектуре:
- это граница контрактов между `webapp`, `agent_core` и `or_core`.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from or_core.models import ORResult, ScenarioDraft
from pydantic import BaseModel, Field

from agent_core.config import DEFAULT_MODEL_ALIAS

STAGE_ORDER = ["production", "shipment", "assignment", "routing"]
StageName = Literal["production", "shipment", "assignment", "routing"]


class ChatMessage(BaseModel):
    """Одна реплика в истории диалога.

    Что делает:
    - фиксирует роль автора (`user`/`assistant`/`system`) и текст сообщения.

    Зачем:
    - история сообщений используется и для UI, и для контекстной логики агента.
    """

    role: Literal["user", "assistant", "system"]
    content: str


class CollectionState(BaseModel):
    """Текущее состояние интерактивного сбора входов OR-подграфа."""

    mode: Literal["wizard", "json"] = "wizard"
    current_stage: StageName | None = "production"
    ready_to_run: bool = False


class InputPatch(BaseModel):
    """Частичное обновление draft, извлечённое из команды пользователя."""

    stage: StageName
    payload: dict[str, Any] | None = None
    path: str | None = None
    value: Any = None


class CommandResult(BaseModel):
    """Результат детерминированного разбора пользовательской реплики."""

    action: Literal[
        "start",
        "next",
        "show_input",
        "run",
        "reset",
        "load_preset",
        "edit_stage",
        "stage_json",
        "set_field",
        "help",
        "invalid",
    ]
    message: str | None = None
    patch: InputPatch | None = None
    stage: StageName | None = None
    preset_ref: Literal["demo"] | None = None
    errors: list[str] = Field(default_factory=list)


class AgentSession(BaseModel):
    """Полное состояние пользовательской сессии диалога.

    Что делает:
    - объединяет историю сообщений, входные параметры, OR-результат и диагностику.

    Зачем:
    - это главный state-объект, который хранилище и граф передают между шагами обработки.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    scenario_draft: ScenarioDraft = Field(default_factory=ScenarioDraft)
    collection_state: CollectionState = Field(default_factory=CollectionState)
    missing_fields: list[StageName] = Field(default_factory=list)
    validation_errors_by_stage: dict[str, list[str]] = Field(default_factory=dict)
    pending_question: str | None = None
    or_result: ORResult | None = None
    explanation: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_alias: str = DEFAULT_MODEL_ALIAS


class ChatTurnRequest(BaseModel):
    """Входной payload одного хода диалога (HTML и JSON endpoints)."""

    session_id: str | None = None
    model_alias: str = DEFAULT_MODEL_ALIAS
    message: str = Field(..., min_length=1)


class TurnResult(BaseModel):
    """Результат обработки одного хода диалога.

    Содержит обновлённую сессию и финальный текст ответа ассистента за этот ход.
    """

    session: AgentSession
    assistant_message: str


class LLMResponse(BaseModel):
    """Нормализованный ответ LLM-клиента для внутренних вызовов agent_core."""

    content: str
    model_alias: str
    model_name: str
    used_fallback: bool = False
