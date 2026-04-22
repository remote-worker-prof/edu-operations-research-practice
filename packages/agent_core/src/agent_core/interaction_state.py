"""Dynamic interaction-state helpers for semantics-driven chat surfaces."""

from __future__ import annotations

import json

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionDisplaySemantics,
    ExtensionInputStepSemantics,
    ExtensionInteractionState,
    ExtensionManifest,
    ExtensionOption,
    ExtensionRegistry,
    ExtensionStageInteraction,
    SlashCommandSpec,
)

from agent_core.extension_flow import (
    _extension_semantics,
    _semantics_step,
    _stage_expectation_hint,
    _stage_payload_skeleton,
    manifest_for_alias,
    stage_order_for_manifest,
)
from agent_core.models import AgentSession


def canonical_slash_commands() -> list[SlashCommandSpec]:
    """Returns the canonical slash-command contract for the new chat shell."""
    return [
        SlashCommandSpec(
            name="/new",
            usage="/new [extension]",
            summary="Начать новый чистый сценарий в текущем треде.",
            category="user",
            example="/new study_planner",
        ),
        SlashCommandSpec(
            name="/use",
            usage="/use <extension>",
            summary="Выбрать extension для текущего треда.",
            category="user",
            example="/use transportation",
        ),
        SlashCommandSpec(
            name="/next",
            usage="/next",
            summary="Перейти к следующему незаполненному шагу.",
            category="user",
        ),
        SlashCommandSpec(
            name="/show",
            usage="/show [steps|draft|result]",
            summary="Показать этапы, текущий черновик или результат.",
            category="user",
            example="/show draft",
        ),
        SlashCommandSpec(
            name="/solve",
            usage="/solve",
            summary="Запустить расчёт по текущему черновику.",
            category="user",
        ),
        SlashCommandSpec(
            name="/explain",
            usage="/explain",
            summary="Показать текстовое объяснение текущего результата.",
            category="user",
        ),
        SlashCommandSpec(
            name="/help",
            usage="/help",
            summary="Показать доступные команды и подсказки по текущему шагу.",
            category="user",
        ),
        SlashCommandSpec(
            name="/reset",
            usage="/reset",
            summary="Сбросить текущий черновик extension.",
            category="user",
        ),
        SlashCommandSpec(
            name="/step",
            usage="/step <stage>",
            summary="Перейти к конкретному stage вручную.",
            category="power",
            example="/step priorities",
        ),
        SlashCommandSpec(
            name="/payload",
            usage="/payload <stage> <json>",
            summary="Передать структурированный JSON-пейлоад для stage.",
            category="power",
            example='/payload priorities {"priority":[5,4,3]}',
        ),
        SlashCommandSpec(
            name="/set",
            usage="/set <path> <value>",
            summary="Изменить отдельное поле точечно.",
            category="power",
            example="/set priorities.priority[0] 5",
        ),
        SlashCommandSpec(
            name="/validate",
            usage="/validate",
            summary="Проверить черновик без запуска решателя.",
            category="power",
        ),
        SlashCommandSpec(
            name="/semantics",
            usage="/semantics",
            summary="Показать typed semantics текущего extension.",
            category="power",
        ),
        SlashCommandSpec(
            name="/run",
            usage="/run",
            summary="Технический синоним команды /solve.",
            category="power",
        ),
    ]


def _step_example_command(
    *,
    step: ExtensionInputStepSemantics | None,
    stage_id: str,
) -> str | None:
    if step is None:
        return None
    payload = _stage_payload_skeleton(step)
    return f"/payload {stage_id} {json.dumps(payload, ensure_ascii=False)}"


def _draft_summary(
    *,
    session: AgentSession,
    manifest: ExtensionManifest,
) -> str:
    ready_count = sum(1 for row in session.extension_stage_statuses if row.ready)
    total_count = len(stage_order_for_manifest(manifest))
    if session.collection_state.ready_to_run and session.pre_run_summary:
        return session.pre_run_summary
    return (
        f"Extension `{session.extension_alias}`: готово этапов {ready_count} из {total_count}. "
        f"Текущий stage: {session.collection_state.current_stage or 'не выбран'}."
    )


def build_interaction_state(
    *,
    session: AgentSession,
    registry: ExtensionRegistry,
) -> ExtensionInteractionState:
    """Builds typed dynamic interaction state for one backend-owned thread."""
    manifest = manifest_for_alias(registry, session.extension_alias)
    discovered = registry.require(session.extension_alias)
    runtime = discovered.create_runtime()
    semantics = _extension_semantics(runtime)
    current_stage = session.collection_state.current_stage
    current_step = _semantics_step(runtime, current_stage) if current_stage else None

    statuses: list[ExtensionStageInteraction] = []
    for row in session.extension_stage_statuses:
        step = _semantics_step(runtime, row.stage_id)
        statuses.append(
            ExtensionStageInteraction(
                stage_id=row.stage_id,
                label=row.label,
                depends_on=list(row.depends_on),
                ready=row.ready,
                current=row.current,
                missing=row.missing,
                errors=list(row.errors),
                expectation_hint=_stage_expectation_hint(runtime, row.stage_id) or None,
                example_command=_step_example_command(step=step, stage_id=row.stage_id),
            )
        )

    available_extensions = [
        ExtensionOption(
            alias=item.alias,
            title=item.manifest.title,
            description=item.manifest.description,
        )
        for item in registry.all()
    ]
    expected_payload = _stage_payload_skeleton(current_step) if current_step is not None else None
    display: ExtensionDisplaySemantics | None = semantics.display if semantics is not None else None

    return ExtensionInteractionState(
        thread_id=session.session_id,
        thread_exists=True,
        active_extension=session.extension_alias,
        available_extensions=available_extensions,
        current_stage=current_stage,
        pending_question=session.pending_question,
        draft_summary=_draft_summary(session=session, manifest=manifest),
        expected_payload=expected_payload,
        draft=session.extension_draft,
        stage_statuses=statuses,
        current_step=current_step,
        display=display,
        result_sections=list(session.extension_result_sections),
        commands=canonical_slash_commands(),
        semantics=semantics,
    )


def render_steps_overview(state: ExtensionInteractionState) -> str:
    """Renders a compact beginner-friendly stage overview."""
    lines = ["Этапы текущего extension:"]
    for row in state.stage_statuses:
        marker = "->" if row.current else "  "
        status = "готово" if row.ready else "нужно заполнить"
        lines.append(f"{marker} {row.stage_id}: {row.label} — {status}")
        if row.errors:
            lines.extend(f"   ошибка: {error}" for error in row.errors)
    if state.pending_question:
        lines.append("")
        lines.append(state.pending_question)
    return "\n".join(lines)


def render_result_overview(session: AgentSession) -> str:
    """Renders one text response for `/show result` and `/explain`."""
    if session.extension_result_sections:
        section_titles = ", ".join(section.title for section in session.extension_result_sections)
        if session.explanation:
            return f"{session.explanation}\n\nРазделы результата: {section_titles}."
        return f"Результат готов. Разделы: {section_titles}."
    if session.explanation:
        return session.explanation
    return "Результат пока отсутствует. Сначала заполните входы и выполните /solve."


def render_semantics_json(semantics: ExtensionBundleSemantics | None) -> str:
    """Renders static bundle semantics as pretty JSON for power users."""
    if semantics is None:
        return "Текущее extension не публикует typed semantics."
    return json.dumps(semantics.model_dump(mode="json"), ensure_ascii=False, indent=2)


def render_validation_overview(state: ExtensionInteractionState) -> str:
    """Renders one short validation summary without running the solver."""
    broken = [row for row in state.stage_statuses if row.errors]
    if not broken:
        return "Черновик валиден. Можно запускать расчёт командой /solve."

    lines = ["Найдены ошибки во вводе:"]
    for row in broken:
        for error in row.errors:
            lines.append(f"- {row.label}: {error}")
    if state.pending_question:
        lines.append("")
        lines.append(state.pending_question)
    return "\n".join(lines)


def render_help_text(state: ExtensionInteractionState) -> str:
    """Renders slash-command help tailored to the current interaction state."""
    lines = ["Основные команды нового чата:"]
    for command in state.commands:
        lines.append(f"- {command.usage}: {command.summary}")
    if state.current_stage and state.expected_payload is not None:
        payload = json.dumps(state.expected_payload, ensure_ascii=False)
        lines.append("")
        lines.append(
            f"Для текущего stage `{state.current_stage}` можно отправить, например: "
            f"/payload {state.current_stage} {payload}"
        )
    return "\n".join(lines)
