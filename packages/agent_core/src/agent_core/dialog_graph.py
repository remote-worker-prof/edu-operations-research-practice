"""Оркестрация диалога на LangGraph: сбор параметров, OR-расчёт, объяснение."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from or_core.exceptions import ORPipelineError
from or_core.models import ScenarioParams
from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioBuilder
from pydantic import ValidationError

from agent_core.explainer import explain_result_for_student
from agent_core.extractor import extract_user_intent_and_params
from agent_core.llm import LLMClient
from agent_core.models import AgentSession, ChatMessage, ScenarioParamState


class DialogGraphState(TypedDict, total=False):
    """Состояние узлов диалогового графа.

    Поля:
    - `session`: текущее состояние пользовательской сессии;
    - `user_message`: входная реплика текущего шага;
    - `assistant_message`: финальный ответ ассистента в этом шаге.
    """

    session: AgentSession
    user_message: str
    assistant_message: str


@dataclass(frozen=True)
class DialogGraphDeps:
    """Явный контейнер зависимостей для узлов графа.

    Зачем:
    - узлы остаются чистыми и тестопригодными;
    - зависимости передаются явно, а не через глобальные переменные.
    """

    scenario_builder: ScenarioBuilder
    or_pipeline: ORPipeline
    llm_client: LLMClient


def _append_message(
    session: AgentSession,
    role: Literal["user", "assistant"],
    content: str,
) -> None:
    """Добавляет реплику в историю сообщений сессии."""
    session.messages.append(ChatMessage(role=role, content=content))


def _merge_unique(values: list[str], additions: list[str]) -> list[str]:
    """Объединяет два списка без дубликатов, сохраняя исходный порядок."""
    merged = list(values)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def _add_user_message_node(state: DialogGraphState) -> DialogGraphState:
    """Сохраняет входящее сообщение пользователя и очищает устаревшие ошибки."""
    session = state["session"].model_copy(deep=True)
    text = state["user_message"].strip()
    _append_message(session, "user", text)
    session.errors = []
    return {"session": session}


def _extract_params_node(
    state: DialogGraphState,
    *,
    deps: DialogGraphDeps,
) -> DialogGraphState:
    """Извлекает параметры из текста и объединяет результат с состоянием сессии."""
    session = state["session"].model_copy(deep=True)
    text = state["user_message"]

    extraction = extract_user_intent_and_params(
        message=text,
        model_alias=session.model_alias,
        llm_client=deps.llm_client,
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


def _route_after_extraction(state: DialogGraphState) -> str:
    """Выбирает следующую ветку после extraction: ask/run/error."""
    session = state["session"]
    if session.errors:
        return "error"
    if session.missing_fields:
        return "ask"
    return "run"


def _ask_missing_node(state: DialogGraphState) -> DialogGraphState:
    """Формирует уточняющий вопрос, если не хватает параметров сценария."""
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


def _run_or_subgraph_node(
    state: DialogGraphState,
    *,
    deps: DialogGraphDeps,
) -> DialogGraphState:
    """Запускает детерминированный OR-пайплайн при полноте входных параметров."""
    session = state["session"].model_copy(deep=True)

    try:
        runtime_params = ScenarioParams(
            demand_multiplier=session.scenario_params.demand_multiplier,
            resource_multiplier=session.scenario_params.resource_multiplier,
        )
        runtime_input = deps.scenario_builder.build(runtime_params)
        session.or_result = deps.or_pipeline.run(runtime_input)
        session.errors = []
        session.missing_fields = []
    except (ValidationError, ORPipelineError) as exc:
        session.errors = [str(exc)]
        session.or_result = None

    return {"session": session}


def _route_after_or(state: DialogGraphState) -> str:
    """Маршрутизирует шаг после OR-пайплайна: explain или error."""
    return "error" if state["session"].errors else "explain"


def _explain_node(
    state: DialogGraphState,
    *,
    deps: DialogGraphDeps,
) -> DialogGraphState:
    """Генерирует учебное объяснение рассчитанного OR-результата."""
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
        llm_client=deps.llm_client,
    )
    session.warnings = _merge_unique(session.warnings, warnings)
    session.explanation = explanation
    _append_message(session, "assistant", explanation)
    return {"session": session, "assistant_message": explanation}


def _respond_error_node(state: DialogGraphState) -> DialogGraphState:
    """Преобразует технические ошибки в понятный ответ ассистента."""
    session = state["session"].model_copy(deep=True)
    issues = "; ".join(session.errors)
    message = f"Не удалось выполнить шаг: {issues}. Проверьте параметры и попробуйте снова."
    _append_message(session, "assistant", message)
    return {"session": session, "assistant_message": message}


def build_dialog_graph(
    *,
    scenario_builder: ScenarioBuilder,
    or_pipeline: ORPipeline,
    llm_client: LLMClient,
):
    """Собирает исполняемый LangGraph для одного хода диалога.

    Что делает:
    - создаёт state-граф с узлами extraction, валидации, OR-расчёта и объяснения;
    - настраивает условные рёбра для веток `ask/run/error`.

    Зачем:
    - формализует бизнес-flow в виде детерминированного графа, который удобно тестировать.

    Входы:
    - `scenario_builder`: фабрика runtime-входа OR-пайплайна;
    - `or_pipeline`: фасад детерминированных OR-расчётов;
    - `llm_client`: клиент LLM для extraction и explanation.

    Выходы:
    - скомпилированный граф (`CompiledStateGraph`) с методом `.invoke(...)`.

    Ошибки:
    - узлы не бросают инфраструктурные ошибки наружу в штатном flow;
    - ошибки расчёта переводятся в `session.errors` и ветку `respond_error`.

    Пример:
    - используется в `AgentService.__init__`, затем вызывается через
      `self._dialog_graph.invoke(...)`.
    """
    deps = DialogGraphDeps(
        scenario_builder=scenario_builder,
        or_pipeline=or_pipeline,
        llm_client=llm_client,
    )

    builder = StateGraph(DialogGraphState)
    builder.add_node("add_user_message", _add_user_message_node)
    builder.add_node("extract_params", partial(_extract_params_node, deps=deps))
    builder.add_node("ask_missing", _ask_missing_node)
    builder.add_node("run_or_subgraph", partial(_run_or_subgraph_node, deps=deps))
    builder.add_node("explain", partial(_explain_node, deps=deps))
    builder.add_node("respond_error", _respond_error_node)

    builder.add_edge(START, "add_user_message")
    builder.add_edge("add_user_message", "extract_params")

    builder.add_conditional_edges(
        "extract_params",
        _route_after_extraction,
        {
            "ask": "ask_missing",
            "run": "run_or_subgraph",
            "error": "respond_error",
        },
    )

    builder.add_conditional_edges(
        "run_or_subgraph",
        _route_after_or,
        {
            "explain": "explain",
            "error": "respond_error",
        },
    )

    builder.add_edge("ask_missing", END)
    builder.add_edge("explain", END)
    builder.add_edge("respond_error", END)

    return builder.compile()
