"""Pydantic-контракты для диалогового агента и web/API интерфейсов.

Назначение модуля:
- хранить типизированные модели состояния сессии и payload API;
- централизовать валидацию пользовательских данных.

Роль в архитектуре:
- это граница контрактов между `webapp`, `agent_core` и `or_core`.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from or_core.models import ORResult
from pydantic import BaseModel, Field

from agent_core.config import DEFAULT_MODEL_ALIAS


class ChatMessage(BaseModel):
    """Одна реплика в истории диалога.

    Что делает:
    - фиксирует роль автора (`user`/`assistant`/`system`) и текст сообщения.

    Зачем:
    - история сообщений используется и для UI, и для контекстной логики агента.
    """

    role: Literal["user", "assistant", "system"]
    content: str


class ScenarioParamState(BaseModel):
    """Текущее состояние коэффициентов сценария в сессии.

    Что делает:
    - хранит уже извлечённые значения множителей спроса и ресурсов.

    Зачем:
    - позволяет диалогу работать итеративно: часть параметров может прийти в разных сообщениях.
    """

    demand_multiplier: float | None = Field(default=None, gt=0, le=2)
    resource_multiplier: float | None = Field(default=None, gt=0, le=2)

    def missing_fields(self) -> list[str]:
        """Возвращает список параметров, которых ещё не хватает для расчёта.

        Что делает:
        - проверяет, заданы ли оба коэффициента;
        - собирает отсутствующие поля в список.

        Зачем:
        - `DialogGraph` использует этот список для построения уточняющего вопроса пользователю.
        """
        missing: list[str] = []
        if self.demand_multiplier is None:
            missing.append("demand_multiplier")
        if self.resource_multiplier is None:
            missing.append("resource_multiplier")
        return missing


class AgentSession(BaseModel):
    """Полное состояние пользовательской сессии диалога.

    Что делает:
    - объединяет историю сообщений, входные параметры, OR-результат и диагностику.

    Зачем:
    - это главный state-объект, который хранилище и граф передают между шагами обработки.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    scenario_params: ScenarioParamState = Field(default_factory=ScenarioParamState)
    missing_fields: list[str] = Field(default_factory=list)
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


class ExtractionResult(BaseModel):
    """Результат извлечения параметров из пользовательского текста.

    Может содержать как успешные значения коэффициентов, так и предупреждения/ошибки.
    """

    demand_multiplier: float | None = Field(default=None, gt=0, le=2)
    resource_multiplier: float | None = Field(default=None, gt=0, le=2)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
