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

from agent_core.default_or_contract import DEFAULT_OR_STAGE_ORDER, DefaultORStageName
from agent_core.explainer import explain_result_for_student
from agent_core.input_parser import parse_user_command
from agent_core.llm import LLMClient
from agent_core.models import (
    AgentSession,
    CandidatePatch,
    ChatMessage,
    CommandResult,
    NLParseResult,
)
from agent_core.nl_parser import parse_nl_turn, teaching_hints_for_patches

STAGE_LABELS: dict[DefaultORStageName, str] = {
    "production": "Production",
    "shipment": "Shipment",
    "assignment": "Assignment",
    "routing": "Routing",
}

_STAGE_DRAFT_FIELDS: dict[DefaultORStageName, str] = {
    "production": "production",
    "shipment": "shipment",
    "assignment": "assignment",
    "routing": "routing",
}

_STAGE_EXAMPLES: dict[DefaultORStageName, str] = {
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

_MAX_CONFIRMED_PATCHES = 64


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


def _next_missing_stage(session: AgentSession) -> DefaultORStageName | None:
    """Возвращает первый незаполненный stage в порядке legacy OR-stage order."""
    for stage in DEFAULT_OR_STAGE_ORDER:
        if stage in session.missing_fields:
            return stage
    return None


def _stage_prompt(stage: DefaultORStageName) -> str:
    """Формирует подсказку с примером JSON для выбранного stage."""
    return f"Заполните stage {STAGE_LABELS[stage]}. Пример: json {stage} {_STAGE_EXAMPLES[stage]}"


def _apply_stage_payload(session: AgentSession, stage: DefaultORStageName, payload: dict) -> None:
    """Записывает payload в нужный раздел draft по имени stage."""
    setattr(session.scenario_draft, _STAGE_DRAFT_FIELDS[stage], payload)


def _stage_payload_ref(session: AgentSession, stage: DefaultORStageName) -> dict:
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
    session.missing_fields = [stage for stage in DEFAULT_OR_STAGE_ORDER if stage_errors[stage]]
    session.collection_state.ready_to_run = not session.missing_fields
    if session.collection_state.current_stage is None or (
        session.collection_state.current_stage not in session.missing_fields
    ):
        session.collection_state.current_stage = _next_missing_stage(session)


def _sync_phase_and_summary(session: AgentSession) -> None:
    """Синхронизирует фазу диалога и учебный pre-run summary."""
    if session.confirmation_state.pending_patches:
        session.collection_state.phase = "awaiting_confirmation"
    elif session.collection_state.ready_to_run:
        session.collection_state.phase = "ready_to_run"
    else:
        session.collection_state.phase = "drafting"

    if session.collection_state.ready_to_run and not session.confirmation_state.pending_patches:
        session.pre_run_summary = (
            "Перед запуском готовы все 4 этапа: Production -> Shipment -> Assignment -> Routing. "
            "После `run` вы получите численное решение и объяснение."
        )
    else:
        session.pre_run_summary = None


def _pending_question(session: AgentSession) -> str:
    """Возвращает следующий системный вопрос пользователю по текущему состоянию."""
    if session.confirmation_state.pending_patches:
        return "Подтвердите извлечённые параметры ответом `да` или `нет`."
    if session.nl_uncertainties:
        return session.nl_uncertainties[0]
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
    session.pre_run_summary = None


def _clear_nl_context(session: AgentSession) -> None:
    """Очищает transient-состояние NL-интерпретации."""
    session.nl_uncertainties = []
    session.nl_confidence = None
    session.teaching_hints = []
    session.pending_question = None


def _candidate_patch_key(patch: CandidatePatch) -> tuple[str, str, str]:
    """Строит hashable-ключ patch-а для dedup/retention логики."""
    try:
        normalized_value = json.dumps(patch.value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        normalized_value = repr(patch.value)
    return patch.stage, patch.field_path, normalized_value


def _deduplicate_candidate_patches(patches: list[CandidatePatch]) -> list[CandidatePatch]:
    """Убирает дубликаты patch-ей, сохраняя последнее значение каждого поля."""
    ordered: dict[tuple[str, str, str], CandidatePatch] = {}
    for patch in patches:
        key = _candidate_patch_key(patch)
        if key in ordered:
            del ordered[key]
        ordered[key] = patch
    return list(ordered.values())


def _store_confirmed_patches(
    session: AgentSession,
    patches: list[CandidatePatch],
) -> None:
    """Сохраняет подтверждённые patches с dedup и ограничением длины истории."""
    merged = list(session.confirmation_state.confirmed_patches)
    existing_index = {_candidate_patch_key(item): idx for idx, item in enumerate(merged)}
    for patch in patches:
        key = _candidate_patch_key(patch)
        if key in existing_index:
            del merged[existing_index[key]]
            existing_index = {_candidate_patch_key(item): idx for idx, item in enumerate(merged)}
        merged.append(patch)
        existing_index[key] = len(merged) - 1
    session.confirmation_state.confirmed_patches = merged[-_MAX_CONFIRMED_PATCHES:]


def _clear_pending_confirmation(session: AgentSession) -> None:
    """Сбрасывает неподтверждённые candidate patches."""
    session.confirmation_state.pending_patches = []


def _format_candidate_patches(patches: list[CandidatePatch]) -> str:
    """Формирует человекочитаемое представление candidate patches."""
    rows = [f"- {patch.stage}.{patch.field_path} = {patch.value!r}" for patch in patches]
    return "\n".join(rows)


def _apply_candidate_patch(session: AgentSession, patch: CandidatePatch) -> None:
    """Применяет один подтверждённый patch к scenario draft."""
    payload = dict(_stage_payload_ref(session, patch.stage))
    _set_nested(payload, patch.field_path, patch.value)
    _apply_stage_payload(session, patch.stage, payload)
    session.collection_state.current_stage = patch.stage


def _handle_nl_turn(
    *,
    session: AgentSession,
    nl_result: NLParseResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    """Обрабатывает NL-результат до fallback в command parser."""
    if nl_result.intent == "confirm":
        pending = session.confirmation_state.pending_patches
        if not pending:
            return CollectOutcome(
                assistant_message=(
                    "Сейчас нет параметров на подтверждение. Введите данные для этапа."
                )
            )
        confirmed_now = _deduplicate_candidate_patches(pending)
        for patch in confirmed_now:
            _apply_candidate_patch(session, patch)
        _store_confirmed_patches(session, confirmed_now)
        _clear_pending_confirmation(session)
        _clear_nl_context(session)
        session.collection_state.mode = "nl"
        return CollectOutcome(
            assistant_message=(
                "Параметры подтверждены и применены.\n"
                "Кратко:\n"
                f"{_format_candidate_patches(confirmed_now)}"
            ),
            draft_changed=True,
        )

    if nl_result.intent == "reject":
        _clear_pending_confirmation(session)
        _clear_nl_context(session)
        session.collection_state.mode = "nl"
        return CollectOutcome(
            assistant_message=(
                "Принято, не применяю candidate patches. "
                "Уточните один параметр в формате: `stage поле значение`."
            )
        )

    if nl_result.intent == "run":
        command_result = CommandResult(action="run")
        return _dispatch_collect_action(session=session, result=command_result, deps=deps)

    if nl_result.intent == "help":
        session.collection_state.mode = "nl"
        return CollectOutcome(
            assistant_message=(
                "Пишите свободно, например: "
                '`производство прибыль [40,30], продукты ["A","B"]`. '
                "Я покажу, что понял, и попрошу подтверждение `да/нет`."
            )
        )

    if nl_result.intent != "patch":
        return CollectOutcome()

    session.collection_state.mode = "nl"
    session.nl_confidence = nl_result.confidence
    session.nl_uncertainties = nl_result.uncertainties
    session.teaching_hints = teaching_hints_for_patches(nl_result.candidate_patches)

    if nl_result.uncertainties:
        return CollectOutcome(
            assistant_message=(
                f"{nl_result.uncertainties[0]}\n"
                "Если удобнее, используйте безопасный fallback: `json <stage> {...}` "
                "или `set <stage>.<field> <value>`."
            )
        )

    if not nl_result.candidate_patches:
        return CollectOutcome(
            assistant_message=(
                "Пока не удалось извлечь поля из сообщения. "
                "Добавьте stage и значения параметров в одном сообщении."
            )
        )

    session.confirmation_state.pending_patches = nl_result.candidate_patches
    return CollectOutcome(
        assistant_message=(
            f"Я извлёк параметры (confidence={nl_result.confidence:.2f}):\n"
            f"{_format_candidate_patches(nl_result.candidate_patches)}\n"
            "Подтвердите `да` или отклоните `нет`."
        )
    )


def _handle_start(
    *,
    session: AgentSession,
    result: CommandResult,
    deps: DialogGraphDeps,
) -> CollectOutcome:
    del result, deps
    session.scenario_draft = session.scenario_draft.__class__()
    session.collection_state.current_stage = "production"
    session.collection_state.mode = "wizard"
    _clear_pending_confirmation(session)
    _clear_nl_context(session)
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
    session.collection_state.mode = "wizard"
    _clear_pending_confirmation(session)
    _clear_nl_context(session)
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
    session.collection_state.mode = "wizard"
    _clear_pending_confirmation(session)
    _clear_nl_context(session)
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
    session.collection_state.mode = "wizard"
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
    session.collection_state.mode = "json"
    _clear_pending_confirmation(session)
    _clear_nl_context(session)
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
    session.collection_state.mode = "wizard"
    _clear_pending_confirmation(session)
    _clear_nl_context(session)
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
    session.collection_state.mode = "wizard"
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
    if session.confirmation_state.pending_patches:
        return CollectOutcome(
            assistant_message=(
                "Нельзя запускать расчёт с неподтверждёнными NL-параметрами. "
                "Ответьте `да` или `нет`."
            )
        )
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
    nl_result = parse_nl_turn(
        message=text,
        current_stage=session.collection_state.current_stage,
        llm_client=deps.llm_client,
        model_alias=session.model_alias,
    )
    if nl_result.intent != "none":
        outcome = _handle_nl_turn(session=session, nl_result=nl_result, deps=deps)
    else:
        result = parse_user_command(
            message=text, current_stage=session.collection_state.current_stage
        )
        outcome = _dispatch_collect_action(session=session, result=result, deps=deps)

    if outcome.draft_changed:
        _invalidate_cached_result(session)

    _recompute_collection_state(session=session, assembler=deps.scenario_assembler)
    _sync_phase_and_summary(session)
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
    session.collection_state.phase = "running"
    try:
        runtime_input = deps.scenario_assembler.build_from_draft(session.scenario_draft)
        session.or_result = deps.or_pipeline.run(runtime_input)
        session.errors = []
        _clear_pending_confirmation(session)
        _clear_nl_context(session)
        session.pending_question = None
        session.collection_state.ready_to_run = True
        _sync_phase_and_summary(session)
    except (ScenarioValidationError, ORPipelineError) as exc:
        session.errors = [str(exc)]
        session.or_result = None
        session.collection_state.phase = "drafting"
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
