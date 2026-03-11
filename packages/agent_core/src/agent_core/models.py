"""Typed contracts for dialog state and service interfaces."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from or_core.models import ORResult
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ScenarioParamState(BaseModel):
    demand_multiplier: float | None = Field(default=None, gt=0, le=2)
    resource_multiplier: float | None = Field(default=None, gt=0, le=2)

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if self.demand_multiplier is None:
            missing.append("demand_multiplier")
        if self.resource_multiplier is None:
            missing.append("resource_multiplier")
        return missing


class AgentSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    scenario_params: ScenarioParamState = Field(default_factory=ScenarioParamState)
    missing_fields: list[str] = Field(default_factory=list)
    or_result: ORResult | None = None
    explanation: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_alias: str = "openai_default"


class ChatTurnRequest(BaseModel):
    session_id: str | None = None
    model_alias: str = "openai_default"
    message: str = Field(..., min_length=1)


class TurnResult(BaseModel):
    session: AgentSession
    assistant_message: str


class LLMResponse(BaseModel):
    content: str
    model_alias: str
    model_name: str
    used_fallback: bool = False


class ExtractionResult(BaseModel):
    demand_multiplier: float | None = Field(default=None, gt=0, le=2)
    resource_multiplier: float | None = Field(default=None, gt=0, le=2)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
