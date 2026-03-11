"""Оркестрация диалога: сбор OR-входов, запуск OR-подграфа, объяснение."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from typing import Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from or_core.exceptions import ORPipelineError, ScenarioValidationError
from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioAssembler, ScenarioPresetLoader

from agent_core.explainer import explain_result_for_student
from agent_core.input_parser import parse_user_command
from agent_core.llm import LLMClient
from agent_core.models import STAGE_ORDER, AgentSession, ChatMessage, CommandResult, StageName

STAGE_LABELS: dict[StageName, str] = {
    "production": "Production",
    "shipment": "Shipment",
    "assignment": "Assignment",
    "routing": "Routing",
}

_STAGE_DRAFT_FIELDS: dict[StageName, str] = {
    "production": "production",
    "shipment": "shipment",
    "assignment": "assignment",
    "routing": "routing",
}

_STAGE_EXAMPLES: dict[StageName, str] = {
    "production": (
        '{"products":["A","B"],"profits":[40,30],'
        '"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],'
        '"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}'
    ),
    "shipment": (
        '{"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],'
        '"clients":["C1","C2","C3"],"client_demand":[42,38,40],'
        '"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}'
    ),
    "assignment": '{"resources":["truck_1","truck_2"],"cost_matrix":[[8,6,7],[5,8,6]]}',
    "routing": (
        '{"distance_matrix":[[0,10,12],[10,0,6],[12,6,0]],'
        '"depot_index":0,"client_nodes":[1,2],'
        '"vehicle_capacities":[55,45]}'
    ),
}


class DialogGraphState(TypedDict, total=False):
    """Состояние узлов диалогового графа."""

    session: AgentSession
    user_message: str
    assistant_message: str
    should_run: bool


@dataclass(frozen=True)
class DialogGraphDeps:
    """Явный контейнер зависимостей для узлов графа."""

    scenario_assembler: ScenarioAssembler
    preset_loader: ScenarioPresetLoader
    or_pipeline: ORPipeline
    llm_client: LLMClient


@dataclass(frozen=True)
class CollectOutcome:
    """Результат обработки одной команды интерактивного ввода."""

    assistant_message: str = ""
    draft_changed: bool = False
    should_run: bool = False


def _append_message(
    session: AgentSession,
    role: Literal["user", "assistant"],
    content: str,
) -> None:
    """Добавляет реплику в историю сообщений сессии."""
    session.messages.append(ChatMessage(role=role, content=content))


def _add_user_message_node(state: DialogGraphState) -> DialogGraphState:
    """Сохраняет входящее сообщение пользователя и очищает runtime-ошибки."""
    session = state["session"].model_copy(deep=True)
    text = state["user_message"].strip()
    _append_message(session, "user", text)
    session.errors = []
    return {"session": session}


def _next_missing_stage(session: AgentSession) -> StageName | None:
    """Возвращает первый незаполненный stage в порядке `STAGE_ORDER`."""
    for stage in STAGE_ORDER:
        if stage in session.missing_fields:
            return stage
    return None


def _stage_prompt(stage: StageName) -> str:
    """Формирует подсказку с примером JSON для выбранного stage."""
    return f"Заполните stage {STAGE_LABELS[stage]}. Пример: json {stage} {_STAGE_EXAMPLES[stage]}"


def _apply_stage_payload(session: AgentSession, stage: StageName, payload: dict) -> None:
    """Записывает payload в нужный раздел draft по имени stage."""
    setattr(session.scenario_draft, _STAGE_DRAFT_FIELDS[stage], payload)


def _stage_payload_ref(session: AgentSession, stage: StageName) -> dict:
    """Возвращает текущий payload выбранного stage из draft."""
    return getattr(session.scenario_draft, _STAGE_DRAFT_FIELDS[stage])


def _set_nested(payload: dict, path: str, value) -> None:
    """Обновляет вложенное поле словаря по dotted-path."""
    parts = [part for part in path.split(".") if part]
    if not parts:
        return
    cursor = payload
    for key in parts[:-1]:
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[parts[-1]] = value


def _recompute_collection_state(
    *,
    session: AgentSession,
    assembler: ScenarioAssembler,
) -> None:
    """Пересчитывает ошибки/готовность stage после изменения draft."""
    stage_errors = assembler.stage_errors(session.scenario_draft)
    session.validation_errors_by_stage = stage_errors
    session.missing_fields = [stage for stage in STAGE_ORDER if stage_errors[stage]]
    session.collection_state.ready_to_run = not session.missing_fields
    if session.collection_state.current_stage is None or (
        session.collection_state.current_stage not in session.missing_fields
    ):
        session.collection_state.current_stage = _next_missing_stage(session)


def _pending_question(session: AgentSession) -> str:
    """Возвращает следующий системный вопрос пользователю по текущему состоянию."""
    if session.collection_state.ready_to_run:
        return "Входы валидны. Для запуска расчёта отправьте `run`."
    stage = _next_missing_stage(session)
    if stage is None:
        return "Исправьте ошибки в текущем вводе и повторите `run`."
    return _stage_prompt(stage)


def _invalidate_cached_result(session: AgentSession) -> None:
    """Сбрасывает кэш результата при изменении входов."""
    session.or_result = None
    session.explanation = None


def _handle_start(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result, deps
    session.scenario_draft = session.scenario_draft.__class__()
    session.collection_state.current_stage = "production"
    return CollectOutcome(assistant_message=_stage_prompt("production"), draft_changed=True)


def _handle_reset(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result, deps
    session.scenario_draft = session.scenario_draft.__class__()
    session.collection_state.current_stage = "production"
    session.scenario_draft.preset_ref = None
    return CollectOutcome(
        assistant_message="Черновик сброшен. " + _stage_prompt("production"),
        draft_changed=True,
    )


def _handle_load_preset(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    if result.preset_ref != "demo":
        return CollectOutcome(assistant_message="Ошибка ввода: неизвестный preset.")
    session.scenario_draft = deps.preset_loader.load_demo_draft()
    return CollectOutcome(
        assistant_message=(
            "Загружен demo preset. Проверьте ввод командой `show input` и запустите `run`."
        ),
        draft_changed=True,
    )


def _handle_edit_stage(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del deps
    if result.stage is None:
        return CollectOutcome(assistant_message="Ошибка ввода: не указан stage для edit.")
    session.collection_state.current_stage = result.stage
    return CollectOutcome(assistant_message=_stage_prompt(result.stage))


def _handle_stage_json(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del deps
    if result.patch is None:
        return CollectOutcome(assistant_message="Ошибка ввода: не удалось распознать JSON patch.")
    if result.patch.payload is None:
        return CollectOutcome(assistant_message="Ошибка ввода: JSON patch должен быть объектом.")
    _apply_stage_payload(session, result.patch.stage, result.patch.payload)
    session.collection_state.current_stage = result.patch.stage
    return CollectOutcome(
        assistant_message=f"Stage {STAGE_LABELS[result.patch.stage]} обновлён JSON-объектом.",
        draft_changed=True,
    )


def _handle_set_field(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del deps
    if result.patch is None:
        return CollectOutcome(assistant_message="Ошибка ввода: отсутствует patch для set.")
    if result.patch.path is None:
        return CollectOutcome(assistant_message="Ошибка ввода: отсутствует путь поля для set.")
    payload = dict(_stage_payload_ref(session, result.patch.stage))
    _set_nested(payload, result.patch.path, result.patch.value)
    _apply_stage_payload(session, result.patch.stage, payload)
    session.collection_state.current_stage = result.patch.stage
    return CollectOutcome(
        assistant_message=(
            f"Поле {result.patch.stage}.{result.patch.path} обновлено. "
            f"Текущее значение: {result.patch.value!r}"
        ),
        draft_changed=True,
    )


def _handle_show_input(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result, deps
    rendered = json.dumps(
        session.scenario_draft.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    return CollectOutcome(assistant_message=f"Текущий draft:\n{rendered}")


def _handle_next(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result, deps
    next_stage = _next_missing_stage(session)
    if next_stage is None:
        return CollectOutcome(
            assistant_message="Все stage заполнены. Выполните `run` для запуска OR-пайплайна."
        )
    session.collection_state.current_stage = next_stage
    return CollectOutcome(assistant_message=_stage_prompt(next_stage))


def _handle_run(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result
    _recompute_collection_state(session=session, assembler=deps.scenario_assembler)
    if session.collection_state.ready_to_run:
        return CollectOutcome(should_run=True)
    next_stage = _next_missing_stage(session)
    if next_stage is None:
        return CollectOutcome(
            assistant_message="Входы ещё невалидны. Проверьте ошибки stage в левой панели."
        )
    return CollectOutcome(
        assistant_message="Нельзя запустить OR: не все входы готовы. " + _stage_prompt(next_stage)
    )


def _handle_help(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del session, result, deps
    return CollectOutcome(
        assistant_message=(
            "Команды: start, show input, next, run, load preset demo, "
            "edit <stage>, json <stage> {..}, set <stage>.<field> <value>, reset."
        )
    )


def _handle_invalid(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del session, deps
    issues = "; ".join(result.errors) if result.errors else "не распознана команда"
    return CollectOutcome(assistant_message=f"Ошибка ввода: {issues}")


CollectHandler = Callable[..., CollectOutcome]

_COLLECT_HANDLERS: dict[str, CollectHandler] = {
    "start": _handle_start,
    "reset": _handle_reset,
    "load_preset": _handle_load_preset,
    "edit_stage": _handle_edit_stage,
    "stage_json": _handle_stage_json,
    "set_field": _handle_set_field,
    "show_input": _handle_show_input,
    "next": _handle_next,
    "run": _handle_run,
    "help": _handle_help,
    "invalid": _handle_invalid,
}


def _dispatch_collect_action(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    """Маршрутизирует command action в конкретный обработчик."""
    handler = _COLLECT_HANDLERS.get(result.action, _handle_invalid)
    return handler(session=session, result=result, deps=deps)


def _collect_inputs_node(
    state: DialogGraphState,
    *,
    deps: DialogGraphDeps,
) -> DialogGraphState:
    """Разбирает реплику, обновляет draft и формирует следующий вопрос."""
    session = state["session"].model_copy(deep=True)
    text = state["user_message"]
    result = parse_user_command(message=text, current_stage=session.collection_state.current_stage)

    outcome = _dispatch_collect_action(session=session, result=result, deps=deps)

    if outcome.draft_changed:
        _invalidate_cached_result(session)

    _recompute_collection_state(session=session, assembler=deps.scenario_assembler)
    session.pending_question = _pending_question(session)

    assistant_message = outcome.assistant_message
    should_run = outcome.should_run
    if assistant_message and not should_run:
        _append_message(session, "assistant", assistant_message)
    elif not should_run and not assistant_message:
        assistant_message = session.pending_question
        _append_message(session, "assistant", assistant_message)

    return {
        "session": session,
        "assistant_message": assistant_message,
        "should_run": should_run,
    }


def _route_after_collect(state: DialogGraphState) -> str:
    """Маршрутизирует поток после интерактивного сбора входов."""
    if state.get("should_run"):
        return "run"
    return "respond"


def _run_or_subgraph_node(
    state: DialogGraphState,
    *,
    deps: DialogGraphDeps,
) -> DialogGraphState:
    """Запускает OR-пайплайн, только если draft полностью валиден и подтверждён."""
    session = state["session"].model_copy(deep=True)
    try:
        runtime_input = deps.scenario_assembler.build_from_draft(session.scenario_draft)
        session.or_result = deps.or_pipeline.run(runtime_input)
        session.errors = []
        session.collection_state.ready_to_run = True
    except (ScenarioValidationError, ORPipelineError) as exc:
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
        session.errors = ["Не удалось сформировать OR-результат"]
        return {"session": session}

    explanation, warnings = explain_result_for_student(
        result=session.or_result,
        model_alias=session.model_alias,
        llm_client=deps.llm_client,
    )
    session.warnings = [*session.warnings, *[w for w in warnings if w not in session.warnings]]
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


def _respond_collection_node(state: DialogGraphState) -> DialogGraphState:
    """Завершающий узел для ветки сбора входов без запуска OR."""
    return {"session": state["session"], "assistant_message": state.get("assistant_message", "")}


def build_dialog_graph(
    *,
    scenario_assembler: ScenarioAssembler,
    preset_loader: ScenarioPresetLoader,
    or_pipeline: ORPipeline,
    llm_client: LLMClient,
):
    """Собирает исполняемый LangGraph для одного хода диалога."""
    deps = DialogGraphDeps(
        scenario_assembler=scenario_assembler,
        preset_loader=preset_loader,
        or_pipeline=or_pipeline,
        llm_client=llm_client,
    )

    builder = StateGraph(DialogGraphState)
    builder.add_node("add_user_message", _add_user_message_node)
    builder.add_node("collect_inputs", partial(_collect_inputs_node, deps=deps))
    builder.add_node("run_or_subgraph", partial(_run_or_subgraph_node, deps=deps))
    builder.add_node("explain", partial(_explain_node, deps=deps))
    builder.add_node("respond_error", _respond_error_node)
    builder.add_node("respond_collection", _respond_collection_node)

    builder.add_edge(START, "add_user_message")
    builder.add_edge("add_user_message", "collect_inputs")
    builder.add_conditional_edges(
        "collect_inputs",
        _route_after_collect,
        {
            "run": "run_or_subgraph",
            "respond": "respond_collection",
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
    builder.add_edge("respond_collection", END)
    builder.add_edge("explain", END)
    builder.add_edge("respond_error", END)
    return builder.compile()
