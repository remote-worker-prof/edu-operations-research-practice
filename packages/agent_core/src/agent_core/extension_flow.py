"""Minimal manifest-driven deterministic flow for non-default extensions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionManifest,
    ExtensionMatrixInputSemantics,
    ExtensionRegistry,
    ExtensionRuntime,
    ExtensionTableInputSemantics,
    PresetLoaderExtensionProvider,
)
from or_core.models import ORResult, ScenarioDraft
from pydantic import BaseModel

from agent_core.default_or_extension import (
    DEFAULT_OR_EXTENSION_ALIAS,
    default_or_extension_draft_from_scenario_draft,
    default_or_scenario_draft_from_extension_draft,
)
from agent_core.extension_commands import parse_extension_command
from agent_core.models import AgentSession, ChatMessage, CommandResult, StageStatusSnapshot


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


def build_stage_statuses_for_manifest(
    *,
    manifest: ExtensionManifest,
    session: AgentSession,
) -> list[StageStatusSnapshot]:
    """Builds a normalized stage-status snapshot for one manifest-driven session."""
    stage_map = manifest.stage_map()
    missing = set(session.missing_fields)
    current = session.collection_state.current_stage
    statuses: list[StageStatusSnapshot] = []
    for stage_id in stage_order_for_manifest(manifest):
        stage = stage_map[stage_id]
        errors = list(session.validation_errors_by_stage.get(stage_id, []))
        statuses.append(
            StageStatusSnapshot(
                stage_id=stage_id,
                label=stage.label,
                depends_on=list(stage.depends_on),
                ready=stage_id not in missing and not errors,
                current=stage_id == current,
                missing=stage_id in missing,
                errors=errors,
            )
        )
    return statuses


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
    session.extension_stage_statuses = build_stage_statuses_for_manifest(
        manifest=manifest,
        session=session,
    )


def _append_message(session: AgentSession, role: str, content: str) -> None:
    """Appends one chat message to the generic extension session."""
    session.messages.append(ChatMessage(role=role, content=content))


def _extension_semantics(runtime: ExtensionRuntime) -> ExtensionBundleSemantics | None:
    """Returns typed declarative semantics when an extension runtime exposes them."""
    try:
        raw = runtime.build_nl_semantics()
    except Exception:  # pragma: no cover - defensive adapter seam
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ExtensionBundleSemantics.model_validate(raw)
    except Exception:
        return None


def _semantics_step(
    runtime: ExtensionRuntime | None,
    stage_id: str,
) -> Any | None:
    if runtime is None:
        return None
    semantics = _extension_semantics(runtime)
    if semantics is None:
        return None
    return next((step for step in semantics.inputs if step.step_id == stage_id), None)


def _stage_payload_skeleton(step: Any) -> dict[str, Any]:
    if step.shape is None:
        payload: dict[str, Any] = {}
        for field in step.scalars:
            payload[field.field_path] = 0 if field.value_type == "number" else ""
        for field in step.vectors:
            payload[field.field_path] = [0, 0, 0] if field.value_type == "number" else ["", "", ""]
        return payload
    if isinstance(step.shape, ExtensionTableInputSemantics):
        payload = {step.shape.key.field_path: ["элемент_1", "элемент_2"]}
        for column in step.shape.columns:
            payload[column.field_path] = [0, 0] if column.value_type == "number" else ["", ""]
        return payload
    if isinstance(step.shape, ExtensionMatrixInputSemantics):
        payload = {}
        for field in step.shape.fields:
            payload[field.field_path] = [[0, 0], [0, 0]]
        return payload
    return {}


def _stage_expectation_hint(runtime: ExtensionRuntime | None, stage_id: str) -> str:
    step = _semantics_step(runtime, stage_id)
    if step is None:
        return ""
    if step.shape is None:
        field_labels = [field.label for field in [*step.scalars, *step.vectors]]
        return "Ожидаемые поля: " + ", ".join(field_labels) + "."
    if isinstance(step.shape, ExtensionTableInputSemantics):
        column_labels = ", ".join(column.label for column in step.shape.columns)
        return (
            f"Ожидается таблица по множеству `{step.shape.set_name}`: "
            f"ключ `{step.shape.key.label}` и колонки {column_labels}."
        )
    if isinstance(step.shape, ExtensionMatrixInputSemantics):
        field_labels = ", ".join(field.label for field in step.shape.fields)
        return (
            f"Ожидается матрица для `{field_labels}` по множествам "
            f"`{step.shape.row_set}` x `{step.shape.col_set}`. "
            f"Строки идут в порядке `{step.shape.row_set}`, "
            f"столбцы — в порядке `{step.shape.col_set}`."
        )
    return ""


def _stage_prompt(
    manifest: ExtensionManifest,
    stage_id: str,
    runtime: ExtensionRuntime | None = None,
) -> str:
    """Builds a beginner-friendly prompt for one manifest stage."""
    stage = manifest.stage_map()[stage_id]
    step = _semantics_step(runtime, stage_id)
    example = None
    if step is not None and step.example_command is not None:
        example = step.example_command
    elif step is not None:
        example = f"json {stage_id} {json.dumps(_stage_payload_skeleton(step), ensure_ascii=False)}"
    elif stage.examples:
        example = stage.examples[0]
    else:
        example = f"json {stage_id} {{...}}"
    hint = _stage_expectation_hint(runtime, stage_id)
    if hint:
        return f"Заполните stage {stage.label}. {hint} Пример: {example}"
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
    if is_default_or_extension(session.extension_alias):
        session.or_result = None


def sync_default_or_legacy_from_generic_state(session: AgentSession) -> None:
    """Synchronizes legacy default_or slots from the generic extension state."""
    if not is_default_or_extension(session.extension_alias):
        return
    session.scenario_draft = default_or_scenario_draft_from_extension_draft(
        session.extension_draft
    )
    if session.extension_result is None:
        session.or_result = None


def _serialize_extension_result_value(
    value: Any,
    *,
    warnings: list[str],
    path: str = "result",
) -> Any:
    """Converts extension results into JSON-safe values for session/API transport."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        return _serialize_extension_result_value(
            value.model_dump(mode="json"),
            warnings=warnings,
            path=path,
        )
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize_extension_result_value(
            asdict(value),
            warnings=warnings,
            path=path,
        )
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_extension_result_value(
                item,
                warnings=warnings,
                path=f"{path}.{key}",
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _serialize_extension_result_value(
                item,
                warnings=warnings,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]

    warnings.append(
        f"Extension result at `{path}` of type `{type(value).__name__}` "
        "is not JSON-serializable; stored repr fallback instead."
    )
    return {"repr": repr(value)}


def _serialize_extension_result(value: Any) -> tuple[Any, str | None]:
    """Serializes one runtime result and returns an optional warning message."""
    warnings: list[str] = []
    serialized = _serialize_extension_result_value(value, warnings=warnings)
    warning = warnings[0] if warnings else None
    return serialized, warning


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
    session.extension_stage_statuses = build_stage_statuses_for_manifest(
        manifest=manifest,
        session=session,
    )


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


def _pending_question(
    session: AgentSession,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime | None = None,
) -> str:
    """Returns the next deterministic prompt for the current extension."""
    if session.collection_state.ready_to_run:
        return "Входы валидны. Для запуска расчёта отправьте `run`."
    next_stage = _next_missing_stage(session, manifest)
    if next_stage is None:
        return "Исправьте ошибки во вводе и повторите `run`."
    return _stage_prompt(manifest, next_stage, runtime)


def _handle_start(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    session.extension_draft = {}
    first_stage = stage_order_for_manifest(manifest)[0]
    session.collection_state.current_stage = _next_missing_stage(session, manifest) or first_stage
    session.collection_state.mode = "wizard"
    session.validation_errors_by_stage = {}
    session.missing_fields = stage_order_for_manifest(manifest)
    return GenericCollectOutcome(
        assistant_message=_stage_prompt(
            manifest,
            session.collection_state.current_stage or "",
            runtime,
        ),
        draft_changed=True,
    )


def _handle_reset(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    reset_session_for_extension(session, alias=session.extension_alias, manifest=manifest)
    return GenericCollectOutcome(
        assistant_message=(
            "Черновик extension сброшен. "
            + _stage_prompt(manifest, session.collection_state.current_stage or "", runtime)
        ),
        draft_changed=True,
    )


def _handle_edit_stage(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del provider
    if result.stage is None:
        return GenericCollectOutcome(assistant_message="Ошибка ввода: не указан stage для edit.")
    session.collection_state.current_stage = result.stage
    session.collection_state.mode = "wizard"
    return GenericCollectOutcome(assistant_message=_stage_prompt(manifest, result.stage, runtime))


def _handle_stage_json(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del manifest, runtime, provider
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
    provider: object,
) -> GenericCollectOutcome:
    del manifest, runtime, provider
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
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    rendered = json.dumps(session.extension_draft, ensure_ascii=False, indent=2)
    target_stage = _next_missing_stage(session, manifest) or session.collection_state.current_stage
    if target_stage is None:
        return GenericCollectOutcome(assistant_message=f"Текущий draft:\n{rendered}")
    step = _semantics_step(runtime, target_stage)
    example = None
    if step is not None:
        example = step.example_command or (
            f"json {target_stage} {json.dumps(_stage_payload_skeleton(step), ensure_ascii=False)}"
        )
    hint = _stage_expectation_hint(runtime, target_stage)
    lines = [f"Текущий draft:\n{rendered}", f"Следующий stage: {target_stage}."]
    if hint:
        lines.append(hint)
    if example is not None:
        lines.append(f"Пример команды: {example}")
    return GenericCollectOutcome(assistant_message="\n".join(lines))


def _handle_next(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    next_stage = _next_missing_stage(session, manifest)
    session.collection_state.mode = "wizard"
    if next_stage is None:
        return GenericCollectOutcome(
            assistant_message="Все stages заполнены. Выполните `run` для запуска расчёта."
        )
    session.collection_state.current_stage = next_stage
    return GenericCollectOutcome(assistant_message=_stage_prompt(manifest, next_stage, runtime))


def _handle_run(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
    if not session.collection_state.ready_to_run:
        next_stage = _next_missing_stage(session, manifest)
        if next_stage is None:
            return GenericCollectOutcome(
                assistant_message="Входы ещё невалидны. Проверьте ошибки stage в левой панели."
            )
        return GenericCollectOutcome(
            assistant_message="Нельзя запустить extension: не все входы готовы. "
            + _stage_prompt(manifest, next_stage, runtime)
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

    serialized_result, serialization_warning = _serialize_extension_result(raw_result)
    session.extension_result = serialized_result
    session.extension_result_sections = runtime.build_result_sections(raw_result)
    session.explanation = runtime.fallback_explain(raw_result)
    if is_default_or_extension(session.extension_alias) and isinstance(raw_result, ORResult):
        session.or_result = raw_result
    if serialization_warning and serialization_warning not in session.warnings:
        session.warnings.append(serialization_warning)
    return GenericCollectOutcome(
        assistant_message=session.explanation or "Расчёт extension завершён."
    )


def _handle_help(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del result, provider
    stages = ", ".join(stage_order_for_manifest(manifest))
    current_stage = session.collection_state.current_stage or manifest.topological_stage_ids()[0]
    example = _stage_prompt(manifest, current_stage, runtime)
    return GenericCollectOutcome(
        assistant_message=(
            "Команды: start, show input, next, run, "
            "edit <stage>, json <stage> {..}, set <stage>.<field> <value>, reset. "
            f"Доступные stages: {stages}. {example}"
        )
    )


def _handle_invalid(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del session, manifest, runtime, provider
    issues = "; ".join(result.errors) if result.errors else "не распознана команда"
    return GenericCollectOutcome(assistant_message=f"Ошибка ввода: {issues}")


def _handle_load_preset(
    *,
    session: AgentSession,
    result: CommandResult,
    manifest: ExtensionManifest,
    runtime: ExtensionRuntime,
    provider: object,
) -> GenericCollectOutcome:
    del runtime
    if result.preset_ref is None:
        return GenericCollectOutcome(
            assistant_message="Ошибка preset: не указана ссылка на built-in preset."
        )
    if not isinstance(provider, PresetLoaderExtensionProvider):
        return GenericCollectOutcome(
            assistant_message=(
                f"Extension `{manifest.alias}` не поддерживает загрузку preset "
                f"`{result.preset_ref}`."
            )
        )

    try:
        raw_preset = provider.load_preset(result.preset_ref)
    except Exception as exc:
        return GenericCollectOutcome(
            assistant_message=(
                f"Не удалось загрузить preset `{result.preset_ref}` "
                f"для extension `{manifest.alias}`: {exc}"
            )
        )

    if not isinstance(raw_preset, dict):
        return GenericCollectOutcome(
            assistant_message=(
                f"Preset `{result.preset_ref}` для extension `{manifest.alias}` "
                "должен возвращать объект вида {stage_id: { ... }}."
            )
        )

    stage_map = manifest.stage_map()
    normalized_preset: dict[str, dict[str, Any]] = {}
    for stage_id, payload in raw_preset.items():
        if stage_id not in stage_map:
            return GenericCollectOutcome(
                assistant_message=(
                    f"Preset `{result.preset_ref}` для extension `{manifest.alias}` "
                    f"содержит неизвестный stage `{stage_id}`."
                )
            )
        if not isinstance(payload, dict):
            return GenericCollectOutcome(
                assistant_message=(
                    f"Preset `{result.preset_ref}` для extension `{manifest.alias}` "
                    f"должен возвращать объект stage `{stage_id}`."
                )
            )
        normalized_preset[stage_id] = dict(payload)

    session.extension_draft = normalized_preset
    session.collection_state.current_stage = None
    session.collection_state.mode = "json"
    return GenericCollectOutcome(
        assistant_message=(
            f"Built-in preset `{result.preset_ref}` загружен для extension `{manifest.alias}`."
        ),
        draft_changed=True,
    )


def sync_default_or_compatibility_state(
    *,
    session: AgentSession,
    registry: ExtensionRegistry,
) -> None:
    """Synchronizes generic extension mirrors for the legacy default OR session."""
    if not is_default_or_extension(session.extension_alias):
        return

    discovered = registry.require(DEFAULT_OR_EXTENSION_ALIAS)
    manifest = discovered.manifest
    runtime = discovered.create_runtime()

    session.extension_draft = default_or_extension_draft_from_scenario_draft(session.scenario_draft)

    if session.or_result is None:
        session.extension_result = None
        session.extension_result_sections = []
    else:
        serialized_result, serialization_warning = _serialize_extension_result(session.or_result)
        session.extension_result = serialized_result
        session.extension_result_sections = runtime.build_result_sections(session.or_result)
        if serialization_warning and serialization_warning not in session.warnings:
            session.warnings.append(serialization_warning)

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
    session.extension_stage_statuses = build_stage_statuses_for_manifest(
        manifest=manifest,
        session=session,
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
    """Processes one deterministic extension turn through the generic extension runtime."""
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
    outcome = handler(
        session=session,
        result=result,
        manifest=manifest,
        runtime=runtime,
        provider=discovered.provider,
    )

    if outcome.draft_changed:
        _invalidate_extension_result(session)
        sync_default_or_legacy_from_generic_state(session)

    _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
    _sync_phase_and_summary(session, manifest)
    session.pending_question = _pending_question(session, manifest, runtime)

    assistant_message = outcome.assistant_message or session.pending_question
    _append_message(session, "assistant", assistant_message)
    return session, assistant_message


def is_default_or_extension(alias: str) -> bool:
    """Returns whether one alias should still route through the legacy dialog graph."""
    return alias == DEFAULT_OR_EXTENSION_ALIAS
