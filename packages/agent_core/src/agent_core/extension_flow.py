"""Minimal manifest-driven deterministic flow for non-default extensions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from extension_api import ExtensionManifest, ExtensionRegistry, ExtensionRuntime
from or_core.models import ScenarioDraft

from agent_core.default_or_extension import DEFAULT_OR_EXTENSION_ALIAS
from agent_core.extension_commands import parse_extension_command
from agent_core.models import AgentSession, ChatMessage, CommandResult


@dataclass(frozen=True)
class GenericCollectOutcome:
    """Result of one deterministic extension command step."""

    assistant_message: str = ""
    draft_changed: bool = False
    should_run: bool = False


def manifest_for_alias(registry: ExtensionRegistry, alias: str) -> ExtensionManifest:
    """Returns the manifest for a concrete extension alias."""
    return registry.require(alias).manifest


def stage_order_for_manifest(manifest: ExtensionManifest) -> list[str]:
    """Returns the stable topological stage order for one manifest."""
    return manifest.topological_stage_ids()


def stage_label_map_for_manifest(manifest: ExtensionManifest) -> dict[str, str]:
    """Returns numbered human-readable labels for the current manifest."""
    return {
        stage_id: f"{index + 1}) {manifest.stage_map()[stage_id].label}"
        for index, stage_id in enumerate(stage_order_for_manifest(manifest))
    }


def session_is_empty(session: AgentSession) -> bool:
    """Checks whether the session contains no user-provided draft/result state."""
    scenario_has_inputs = any(
        bool(getattr(session.scenario_draft, stage_name))
        for stage_name in ("production", "shipment", "assignment", "routing")
    )
    extension_has_inputs = any(bool(payload) for payload in session.extension_draft.values())
    return not any(
        [
            scenario_has_inputs,
            session.scenario_draft.preset_ref,
            session.or_result is not None,
            extension_has_inputs,
            session.extension_result is not None,
            bool(session.extension_result_sections),
            bool(session.confirmation_state.pending_patches),
            bool(session.confirmation_state.confirmed_patches),
        ]
    )


def reset_session_for_extension(
    session: AgentSession,
    *,
    alias: str,
    manifest: ExtensionManifest,
) -> None:
    """Clears runtime state and initializes the session for one concrete extension."""
    session.extension_alias = alias
    session.extension_draft = {}
    session.extension_result = None
    session.extension_result_sections = []
    session.scenario_draft = ScenarioDraft()
    session.or_result = None
    session.explanation = None
    session.errors = []
    session.warnings = []
    session.nl_uncertainties = []
    session.nl_confidence = None
    session.teaching_hints = []
    session.pre_run_summary = None
    session.pending_question = None
    session.validation_errors_by_stage = {}
    session.confirmation_state.pending_patches = []
    session.confirmation_state.confirmed_patches = []
    session.collection_state.mode = "wizard"
    session.collection_state.phase = "drafting"
    session.collection_state.ready_to_run = False
    order = stage_order_for_manifest(manifest)
    session.collection_state.current_stage = order[0] if order else None
    session.missing_fields = order


def _append_message(session: AgentSession, role: str, content: str) -> None:
    """Appends one chat message to the generic extension session."""
    session.messages.append(ChatMessage(role=role, content=content))


def _stage_prompt(manifest: ExtensionManifest, stage_id: str) -> str:
    """Builds a beginner-friendly prompt for one manifest stage."""
    stage = manifest.stage_map()[stage_id]
    example = stage.examples[0] if stage.examples else f"json {stage_id} {{...}}"
    return f"Заполните stage {stage.label}. Пример: {example}"


def _next_missing_stage(session: AgentSession, manifest: ExtensionManifest) -> str | None:
    """Returns the first not-ready stage in topological order."""
    for stage_id in stage_order_for_manifest(manifest):
        if stage_id in session.missing_fields:
            return stage_id
    return None


def _set_nested(payload: dict, path: str, value) -> None:
    """Updates one nested dictionary field by dotted path."""
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


def _invalidate_extension_result(session: AgentSession) -> None:
    """Drops cached generic extension results after draft changes."""
    session.extension_result = None
    session.extension_result_sections = []
    session.explanation = None
    session.pre_run_summary = None


def _recompute_extension_state(
    *,
    session: AgentSession,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> None:
    """Recomputes validation, missing stages, and current stage from the generic draft."""
    stage_ids = stage_order_for_manifest(manifest)
    raw_errors = runtime.validate_draft(session.extension_draft)
    normalized_errors = {stage_id: list(raw_errors.get(stage_id, [])) for stage_id in stage_ids}
    session.validation_errors_by_stage = normalized_errors
    session.missing_fields = [stage_id for stage_id in stage_ids if normalized_errors[stage_id]]
    session.collection_state.ready_to_run = not session.missing_fields
    current_stage = session.collection_state.current_stage
    if (
        current_stage is None
        or current_stage not in stage_ids
        or current_stage not in session.missing_fields
    ):
        session.collection_state.current_stage = _next_missing_stage(session, manifest)


def _sync_phase_and_summary(session: AgentSession, manifest: ExtensionManifest) -> None:
    """Synchronizes generic phase and pre-run summary for manifest-driven flows."""
    if session.collection_state.ready_to_run:
        session.collection_state.phase = "ready_to_run"
        stage_chain = " -> ".join(stage.label for stage in manifest.stage_graph)
        session.pre_run_summary = (
            f"Готовы все этапы extension `{session.extension_alias}`: {stage_chain}. "
            "Отправьте `run`, чтобы получить детерминированный результат."
        )
    else:
        session.collection_state.phase = "drafting"
        session.pre_run_summary = None


def _pending_question(session: AgentSession, manifest: ExtensionManifest) -> str:
    """Returns the next deterministic prompt for the current extension."""
    if session.collection_state.ready_to_run:
        return "Входы валидны. Для запуска расчёта отправьте `run`."
    next_stage = _next_missing_stage(session, manifest)
    if next_stage is None:
        return "Исправьте ошибки во вводе и повторите `run`."
    return _stage_prompt(manifest, next_stage)


def _handle_start(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del result, runtime
    session.extension_draft = {}
    first_stage = stage_order_for_manifest(manifest)[0]
    session.collection_state.current_stage = _next_missing_stage(session, manifest) or first_stage
    session.collection_state.mode = "wizard"
    session.validation_errors_by_stage = {}
    session.missing_fields = stage_order_for_manifest(manifest)
    return GenericCollectOutcome(
        assistant_message=_stage_prompt(manifest, session.collection_state.current_stage or ""),
        draft_changed=True,
    )


def _handle_reset(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del result, runtime
    reset_session_for_extension(session, alias=session.extension_alias, manifest=manifest)
    return GenericCollectOutcome(
        assistant_message=(
            "Черновик extension сброшен. "
            + _stage_prompt(manifest, session.collection_state.current_stage or "")
        ),
        draft_changed=True,
    )


def _handle_edit_stage(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del runtime
    if result.stage is None:
        return GenericCollectOutcome(assistant_message="Ошибка ввода: не указан stage для edit.")
    session.collection_state.current_stage = result.stage
    session.collection_state.mode = "wizard"
    return GenericCollectOutcome(assistant_message=_stage_prompt(manifest, result.stage))


def _handle_stage_json(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del manifest, runtime
    if result.patch is None or result.patch.payload is None:
        return GenericCollectOutcome(
            assistant_message="Ошибка ввода: JSON patch должен быть объектом."
        )
    session.extension_draft[result.patch.stage] = dict(result.patch.payload)
    session.collection_state.current_stage = result.patch.stage
    session.collection_state.mode = "json"
    return GenericCollectOutcome(
        assistant_message=f"Stage {result.patch.stage} обновлён JSON-объектом.",
        draft_changed=True,
    )


def _handle_set_field(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del manifest, runtime
    if result.patch is None or result.patch.path is None:
        return GenericCollectOutcome(
            assistant_message="Ошибка ввода: отсутствует путь поля для set."
        )
    payload = dict(session.extension_draft.get(result.patch.stage, {}))
    _set_nested(payload, result.patch.path, result.patch.value)
    session.extension_draft[result.patch.stage] = payload
    session.collection_state.current_stage = result.patch.stage
    session.collection_state.mode = "wizard"
    return GenericCollectOutcome(
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
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del result, manifest, runtime
    rendered = json.dumps(session.extension_draft, ensure_ascii=False, indent=2)
    return GenericCollectOutcome(assistant_message=f"Текущий draft:\n{rendered}")


def _handle_next(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del result, runtime
    next_stage = _next_missing_stage(session, manifest)
    session.collection_state.mode = "wizard"
    if next_stage is None:
        return GenericCollectOutcome(
            assistant_message="Все stages заполнены. Выполните `run` для запуска расчёта."
        )
    session.collection_state.current_stage = next_stage
    return GenericCollectOutcome(assistant_message=_stage_prompt(manifest, next_stage))


def _handle_run(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del result
    _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
    if not session.collection_state.ready_to_run:
        next_stage = _next_missing_stage(session, manifest)
        if next_stage is None:
            return GenericCollectOutcome(
                assistant_message="Входы ещё невалидны. Проверьте ошибки stage в левой панели."
            )
        return GenericCollectOutcome(
            assistant_message="Нельзя запустить extension: не все входы готовы. "
            + _stage_prompt(manifest, next_stage)
        )

    try:
        runtime_input = runtime.build_runtime_input(session.extension_draft)
        raw_result = runtime.run(runtime_input)
    except Exception as exc:  # pragma: no cover - defensive runtime safeguard
        session.errors = [f"Ошибка выполнения extension `{session.extension_alias}`: {exc}"]
        return GenericCollectOutcome(
            assistant_message=(
                f"Ошибка выполнения extension `{session.extension_alias}`. "
                "Проверьте входы и повторите попытку."
            )
        )

    if isinstance(raw_result, dict):
        session.extension_result = raw_result
    else:
        session.extension_result = {"repr": repr(raw_result)}
    session.extension_result_sections = runtime.build_result_sections(raw_result)
    session.explanation = runtime.fallback_explain(raw_result)
    return GenericCollectOutcome(
        assistant_message=session.explanation or "Расчёт extension завершён."
    )


def _handle_help(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del session, result, runtime
    stages = ", ".join(stage_order_for_manifest(manifest))
    return GenericCollectOutcome(
        assistant_message=(
            "Команды: start, show input, next, run, "
            "edit <stage>, json <stage> {..}, set <stage>.<field> <value>, reset. "
            f"Доступные stages: {stages}."
        )
    )


def _handle_invalid(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del session, manifest, runtime
    issues = "; ".join(result.errors) if result.errors else "не распознана команда"
    return GenericCollectOutcome(assistant_message=f"Ошибка ввода: {issues}")


def _handle_load_preset(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
) -> GenericCollectOutcome:
    del session, result, runtime
    return GenericCollectOutcome(
        assistant_message=(
            f"Extension `{manifest.alias}` не предоставляет built-in preset. "
            "Введите данные по stage-ам вручную."
        )
    )


_HANDLERS: dict[str, Callable[..., GenericCollectOutcome]] = {
    "start": _handle_start,
    "reset": _handle_reset,
    "edit_stage": _handle_edit_stage,
    "stage_json": _handle_stage_json,
    "set_field": _handle_set_field,
    "show_input": _handle_show_input,
    "next": _handle_next,
    "run": _handle_run,
    "help": _handle_help,
    "load_preset": _handle_load_preset,
    "invalid": _handle_invalid,
}


def handle_extension_turn(
    *,
    session: AgentSession,
    user_message: str,
    registry: ExtensionRegistry,
) -> tuple[AgentSession, str]:
    """Processes one deterministic extension turn for a non-default extension."""
    session = session.model_copy(deep=True)
    session.errors = []
    discovered = registry.require(session.extension_alias)
    manifest = discovered.manifest
    runtime = discovered.create_runtime()

    text = user_message.strip()
    _append_message(session, "user", text)

    result = parse_extension_command(
        message=text,
        current_stage=session.collection_state.current_stage,
        manifest=manifest,
    )
    handler = _HANDLERS.get(result.action, _handle_invalid)
    outcome = handler(session=session, result=result, manifest=manifest, runtime=runtime)

    if outcome.draft_changed:
        _invalidate_extension_result(session)

    _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
    _sync_phase_and_summary(session, manifest)
    session.pending_question = _pending_question(session, manifest)

    assistant_message = outcome.assistant_message or session.pending_question
    _append_message(session, "assistant", assistant_message)
    return session, assistant_message


def is_default_or_extension(alias: str) -> bool:
    """Returns whether one alias should still route through the legacy dialog graph."""
    return alias == DEFAULT_OR_EXTENSION_ALIAS
