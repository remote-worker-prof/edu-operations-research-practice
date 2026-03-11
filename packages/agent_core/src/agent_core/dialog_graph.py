"""LangGraph dialog orchestration."""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from or_core.exceptions import ORPipelineError
from or_core.models import ScenarioParams
from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioBuilder
from pydantic import ValidationError

from agent_core.explainer import explain_result_for_student
from agent_core.extractor import extract_user_intent_and_params
from agent_core.models import AgentSession, ChatMessage, ScenarioParamState


class DialogGraphState(TypedDict, total=False):
    session: AgentSession
    user_message: str
    assistant_message: str


def _append_message(
    session: AgentSession,
    role: Literal["user", "assistant"],
    content: str,
) -> None:
    session.messages.append(ChatMessage(role=role, content=content))


def _merge_unique(values: list[str], additions: list[str]) -> list[str]:
    merged = list(values)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def build_dialog_graph(
    *,
    scenario_builder: ScenarioBuilder,
    or_pipeline: ORPipeline,
    llm_client,
):
    """Build dialog graph that collects params, runs OR pipeline, and explains result."""

    def add_user_message(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)
        text = state["user_message"].strip()
        _append_message(session, "user", text)
        session.errors = []
        return {"session": session}

    def extract_params(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)
        text = state["user_message"]

        extraction = extract_user_intent_and_params(
            message=text,
            model_alias=session.model_alias,
            llm_client=llm_client,
        )

        session.warnings = _merge_unique(session.warnings, extraction.warnings)
        session.errors = _merge_unique(session.errors, extraction.errors)

        next_demand = (
            extraction.demand_multiplier
            if extraction.demand_multiplier is not None
            else session.scenario_params.demand_multiplier
        )
        next_resource = (
            extraction.resource_multiplier
            if extraction.resource_multiplier is not None
            else session.scenario_params.resource_multiplier
        )

        try:
            session.scenario_params = ScenarioParamState(
                demand_multiplier=next_demand,
                resource_multiplier=next_resource,
            )
        except ValidationError:
            session.errors = _merge_unique(
                session.errors,
                ["Параметры должны быть числами в диапазоне (0, 2]"],
            )

        session.missing_fields = session.scenario_params.missing_fields()
        return {"session": session}

    def route_after_extraction(state: DialogGraphState) -> str:
        session = state["session"]
        if session.errors:
            return "error"
        if session.missing_fields:
            return "ask"
        return "run"

    def ask_missing(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)
        labels = {
            "demand_multiplier": "коэффициент спроса",
            "resource_multiplier": "коэффициент ресурсов",
        }
        requested = [labels[field] for field in session.missing_fields]
        message = (
            "Чтобы запустить расчёт, укажите параметры: "
            + ", ".join(requested)
            + ". Пример: 'спрос 1.0, ресурс 1.0'."
        )
        _append_message(session, "assistant", message)
        return {"session": session, "assistant_message": message}

    def run_or_subgraph(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)

        try:
            runtime_params = ScenarioParams(
                demand_multiplier=session.scenario_params.demand_multiplier,
                resource_multiplier=session.scenario_params.resource_multiplier,
            )
            runtime_input = scenario_builder.build(runtime_params)
            session.or_result = or_pipeline.run(runtime_input)
            session.errors = []
            session.missing_fields = []
        except (ValidationError, ORPipelineError) as exc:
            session.errors = [str(exc)]
            session.or_result = None

        return {"session": session}

    def route_after_or(state: DialogGraphState) -> str:
        return "error" if state["session"].errors else "explain"

    def explain(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)
        if session.or_result is None:
            session.errors = _merge_unique(
                session.errors,
                ["Не удалось сформировать OR-результат"],
            )
            return {"session": session}

        explanation, warnings = explain_result_for_student(
            result=session.or_result,
            model_alias=session.model_alias,
            llm_client=llm_client,
        )
        session.warnings = _merge_unique(session.warnings, warnings)
        session.explanation = explanation
        _append_message(session, "assistant", explanation)
        return {"session": session, "assistant_message": explanation}

    def respond_error(state: DialogGraphState) -> DialogGraphState:
        session = state["session"].model_copy(deep=True)
        issues = "; ".join(session.errors)
        message = (
            "Не удалось выполнить шаг: "
            f"{issues}. Проверьте параметры и попробуйте снова."
        )
        _append_message(session, "assistant", message)
        return {"session": session, "assistant_message": message}

    builder = StateGraph(DialogGraphState)
    builder.add_node("add_user_message", add_user_message)
    builder.add_node("extract_params", extract_params)
    builder.add_node("ask_missing", ask_missing)
    builder.add_node("run_or_subgraph", run_or_subgraph)
    builder.add_node("explain", explain)
    builder.add_node("respond_error", respond_error)

    builder.add_edge(START, "add_user_message")
    builder.add_edge("add_user_message", "extract_params")

    builder.add_conditional_edges(
        "extract_params",
        route_after_extraction,
        {
            "ask": "ask_missing",
            "run": "run_or_subgraph",
            "error": "respond_error",
        },
    )

    builder.add_conditional_edges(
        "run_or_subgraph",
        route_after_or,
        {
            "explain": "explain",
            "error": "respond_error",
        },
    )

    builder.add_edge("ask_missing", END)
    builder.add_edge("explain", END)
    builder.add_edge("respond_error", END)

    return builder.compile()
