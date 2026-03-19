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

from extension_api import ExtensionResultSection
from or_core.models import ORResult, ScenarioDraft
from pydantic import BaseModel, Field, computed_field

from agent_core.config import DEFAULT_MODEL_ALIAS
from agent_core.default_or_extension import DEFAULT_OR_EXTENSION_ALIAS


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

    mode: Literal["wizard", "json", "nl"] = "wizard"
    phase: Literal["drafting", "awaiting_confirmation", "ready_to_run", "running"] = "drafting"
    current_stage: str | None = None
    ready_to_run: bool = False


class InputPatch(BaseModel):
    """Частичное обновление draft, извлечённое из команды пользователя."""

    stage: str
    payload: dict[str, Any] | None = None
    path: str | None = None
    value: Any = None


class CandidatePatch(BaseModel):
    """Кандидат на обновление draft, извлечённый из естественного языка."""

    stage: str
    field_path: str
    value: Any
    source_text: str


class ConfirmationState(BaseModel):
    """Состояние подтверждения извлечённых NL-патчей."""

    pending_patches: list[CandidatePatch] = Field(default_factory=list)
    confirmed_patches: list[CandidatePatch] = Field(default_factory=list)


class TeachingHint(BaseModel):
    """Учебная подсказка по конкретному параметру OR-модели."""

    field: str
    meaning: str
    units: str
    example: str


class NLParseResult(BaseModel):
    """Результат интерпретации свободной реплики в структурированный intent."""

    intent: Literal["none", "patch", "confirm", "reject", "run", "help"]
    candidate_patches: list[CandidatePatch] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    source_text: str = ""


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
    stage: str | None = None
    preset_ref: str | None = None
    errors: list[str] = Field(default_factory=list)


class StageStatusSnapshot(BaseModel):
    """Normalized stage readiness snapshot for manifest-driven and legacy flows."""

    stage_id: str
    label: str
    depends_on: list[str] = Field(default_factory=list)
    ready: bool = False
    current: bool = False
    missing: bool = False
    errors: list[str] = Field(default_factory=list)


class ExtensionStateSnapshot(BaseModel):
    """Generic extension-aware draft/result slot for session and turn contracts."""

    alias: str
    draft: dict[str, dict[str, Any]] = Field(default_factory=dict)
    result: Any | None = None
    result_sections: list[ExtensionResultSection] = Field(default_factory=list)
    stage_statuses: list[StageStatusSnapshot] = Field(default_factory=list)


class AgentSession(BaseModel):
    """Полное состояние пользовательской сессии диалога.

    Что делает:
    - объединяет историю сообщений, входные параметры, OR-результат и диагностику.

    Зачем:
    - это главный state-объект, который хранилище и граф передают между шагами обработки.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    extension_alias: str = DEFAULT_OR_EXTENSION_ALIAS
    extension_draft: dict[str, dict[str, Any]] = Field(default_factory=dict)
    extension_result: Any | None = None
    extension_result_sections: list[ExtensionResultSection] = Field(default_factory=list)
    extension_stage_statuses: list[StageStatusSnapshot] = Field(default_factory=list)
    scenario_draft: ScenarioDraft = Field(default_factory=ScenarioDraft)
    collection_state: CollectionState = Field(default_factory=CollectionState)
    confirmation_state: ConfirmationState = Field(default_factory=ConfirmationState)
    missing_fields: list[str] = Field(default_factory=list)
    validation_errors_by_stage: dict[str, list[str]] = Field(default_factory=dict)
    teaching_hints: list[TeachingHint] = Field(default_factory=list)
    nl_uncertainties: list[str] = Field(default_factory=list)
    nl_confidence: float | None = None
    pre_run_summary: str | None = None
    pending_question: str | None = None
    or_result: ORResult | None = None
    explanation: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_alias: str = DEFAULT_MODEL_ALIAS

    @computed_field(return_type=ExtensionStateSnapshot)
    @property
    def extension_state(self) -> ExtensionStateSnapshot:
        """Returns a generic snapshot for extension-aware clients and transports."""
        return ExtensionStateSnapshot(
            alias=self.extension_alias,
            draft=self.extension_draft,
            result=self.extension_result,
            result_sections=self.extension_result_sections,
            stage_statuses=self.extension_stage_statuses,
        )


class ChatTurnRequest(BaseModel):
    """Входной payload одного хода диалога (HTML и JSON endpoints)."""

    session_id: str | None = None
    model_alias: str = DEFAULT_MODEL_ALIAS
    extension_alias: str | None = None
    message: str = Field(..., min_length=1)


class TurnResult(BaseModel):
    """Результат обработки одного хода диалога.

    Содержит обновлённую сессию и финальный текст ответа ассистента за этот ход.
    """

    session: AgentSession
    assistant_message: str

    @computed_field(return_type=ExtensionStateSnapshot)
    @property
    def extension_state(self) -> ExtensionStateSnapshot:
        """Mirrors the generic extension snapshot at the turn envelope level."""
        return self.session.extension_state


class LLMResponse(BaseModel):
    """Нормализованный ответ LLM-клиента для внутренних вызовов agent_core."""

    content: str
    model_alias: str
    model_name: str
    used_fallback: bool = False
