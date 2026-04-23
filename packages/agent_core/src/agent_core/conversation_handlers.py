"""Registry-driven intent handlers for the semantics-first chat orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from extension_api import IntentResolution, PatchProposal

from agent_core.conversation_context import ConversationContext
from agent_core.extension_flow import (
    _handle_edit_stage,
    _handle_next,
    _handle_reset,
    _handle_run,
    _handle_set_field,
    _handle_stage_json,
    _invalidate_extension_result,
    manifest_for_alias,
    session_is_empty,
    sync_default_or_legacy_from_generic_state,
)
from agent_core.interaction_state import (
    render_help_text,
    render_result_overview,
    render_steps_overview,
    render_validation_overview,
)
from agent_core.models import CommandResult, InputPatch
from agent_core.patch_policy import PatchApplicationPolicy
from agent_core.semantic_schema import resolve_artifact


def render_proposals(proposals: list[PatchProposal]) -> str:
    """Render pending patch proposals as a stable human-readable list."""
    lines = ["Предлагаю обновить данные так:"]
    for proposal in proposals:
        if proposal.payload is not None:
            lines.append(
                f"- `{proposal.stage_id}` целиком: "
                f"{json.dumps(proposal.payload, ensure_ascii=False)}"
            )
        elif proposal.path is not None:
            lines.append(f"- `{proposal.stage_id}.{proposal.path}` = {proposal.value!r}")
    return "\n".join(lines)


def render_clarifications(clarifications: list[str]) -> str:
    """Render schema-driven clarifications collected during command/NL interpretation."""
    if not clarifications:
        return "Не удалось понять сообщение в терминах текущего extension."
    lines = ["Нужна небольшая конкретизация:"]
    lines.extend(f"- {item}" for item in clarifications)
    return "\n".join(lines)


def _apply_proposals(
    *,
    context: ConversationContext,
    proposals: list[PatchProposal],
) -> str:
    for proposal in proposals:
        if proposal.payload is not None:
            _handle_stage_json(
                session=context.session,
                result=CommandResult(
                    action="stage_json",
                    stage=proposal.stage_id,
                    patch=InputPatch(stage=proposal.stage_id, payload=proposal.payload),
                ),
                manifest=context.manifest,
                runtime=context.runtime,
                provider=context.provider,
            )
        elif proposal.path is not None:
            _handle_set_field(
                session=context.session,
                result=CommandResult(
                    action="set_field",
                    stage=proposal.stage_id,
                    patch=InputPatch(
                        stage=proposal.stage_id,
                        path=proposal.path,
                        value=proposal.value,
                    ),
                ),
                manifest=context.manifest,
                runtime=context.runtime,
                provider=context.provider,
            )

    _invalidate_extension_result(context.session)
    sync_default_or_legacy_from_generic_state(context.session)
    context.refresh_runtime_state()

    lines = ["Изменения применены.", render_proposals(proposals)]
    if context.session.pending_question:
        lines.extend(["", context.session.pending_question])
    return "\n".join(lines)


def _render_explain_response(
    *,
    context: ConversationContext,
    target: str,
) -> str:
    normalized = target.strip().lower()
    if normalized == "result":
        return render_result_overview(context.session)
    if normalized.startswith("step"):
        _, _, maybe_stage = normalized.partition(" ")
        stage_id = maybe_stage or context.session.collection_state.current_stage or ""
        if not stage_id:
            return "Сейчас не выбран активный step для объяснения."
        if context.semantics is None or not context.semantics.stages:
            return (
                f"Extension `{context.session.extension_alias}` "
                "пока не публикует typed step semantics."
            )
        for item in context.semantics.stages:
            if item.stage_id != stage_id:
                continue
            lines = [f"Шаг `{item.stage_id}` — {item.label}."]
            if item.expectation_hint:
                lines.append(item.expectation_hint)
            if item.fields:
                lines.append("Поля этого шага:")
                lines.extend(f"- {field.field_path}: {field.label}" for field in item.fields)
            return "\n".join(lines)
        return f"Не удалось найти step `{stage_id}` в typed semantics."

    artifact = resolve_artifact(semantics=context.semantics, target=normalized)
    if artifact is None:
        return "Для этого extension пока нет объяснения по запрошенному артефакту."
    parts = [artifact.label]
    if artifact.summary:
        parts.append(artifact.summary)
    if artifact.content:
        parts.extend(["", artifact.content])
    elif artifact.path:
        parts.extend(["", artifact.path])
    return "\n".join(parts)


class ConversationIntentHandler(Protocol):
    """Internal command object protocol for one family of semantic intents."""

    supported_kinds: frozenset[str]

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        """Handle one intent family and return the assistant message."""


@dataclass(frozen=True)
class SessionLifecycleHandler:
    """Handle session-scoped lifecycle operations such as new/use/reset/mode."""

    supported_kinds: frozenset[str] = frozenset(
        {"mode", "new_thread", "reset", "use_extension"}
    )

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        del patch_policy
        intent = resolution.intent
        if intent.kind == "mode":
            if intent.interaction_mode not in {"guided", "power"}:
                return "Формат команды: /mode guided|power."
            context.session.interaction_mode = intent.interaction_mode
            context.session.nl_apply_policy = (
                "confirm"
                if context.session.interaction_mode == "guided"
                else "auto_if_confident"
            )
            context.invalidate_interaction()
            return (
                f"Режим взаимодействия переключён на "
                f"`{context.session.interaction_mode}`."
            )

        if intent.kind == "new_thread":
            target_alias = intent.extension_alias or context.session.extension_alias
            try:
                manifest_for_alias(context.registry, target_alias)
            except Exception:
                return f"Extension `{target_alias}` не найдено."
            context.reset_for_extension(target_alias)
            sync_default_or_legacy_from_generic_state(context.session)
            return (
                f"Начат новый чистый сценарий для `{target_alias}`. "
                f"{context.session.pending_question or ''}"
            ).strip()

        if intent.kind == "use_extension":
            if not intent.extension_alias:
                return "Формат команды: /use <extension>."
            if intent.extension_alias == context.session.extension_alias:
                return f"Уже выбран extension `{intent.extension_alias}`."
            try:
                manifest_for_alias(context.registry, intent.extension_alias)
            except Exception:
                return f"Extension `{intent.extension_alias}` не найдено."
            if not session_is_empty(context.session):
                return (
                    "Нельзя сменить extension в непустом треде. "
                    "Используйте /new <extension> для нового чистого сценария."
                )
            context.reset_for_extension(intent.extension_alias)
            sync_default_or_legacy_from_generic_state(context.session)
            return f"Выбран extension `{intent.extension_alias}`."

        outcome = _handle_reset(
            session=context.session,
            result=CommandResult(action="reset"),
            manifest=context.manifest,
            runtime=context.runtime,
            provider=context.provider,
        )
        sync_default_or_legacy_from_generic_state(context.session)
        context.refresh_runtime_state()
        context.session.pending_patch_proposals = []
        return outcome.assistant_message or "Черновик сброшен."


@dataclass(frozen=True)
class ReadOnlyHandler:
    """Handle read-only and explain intents without mutating the draft."""

    supported_kinds: frozenset[str] = frozenset({"explain", "help", "show", "validate"})

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        del patch_policy
        intent = resolution.intent
        interaction = context.interaction_state()
        if intent.kind == "show":
            target = intent.target or "steps"
            if target == "steps":
                return render_steps_overview(interaction)
            if target == "draft":
                lines = [
                    "Текущий draft:",
                    json.dumps(interaction.draft, ensure_ascii=False, indent=2),
                ]
                if interaction.current_stage and interaction.expected_payload is not None:
                    lines.append("")
                    lines.append(f"Ожидаемая форма для `{interaction.current_stage}`:")
                    lines.append(
                        json.dumps(
                            interaction.expected_payload,
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                return "\n".join(lines)
            if target == "result":
                return render_result_overview(context.session)
            return "Команда /show поддерживает только steps, draft или result."

        if intent.kind == "help":
            return render_help_text(interaction)
        if intent.kind == "validate":
            return render_validation_overview(interaction)
        return _render_explain_response(
            context=context,
            target=intent.target or "result",
        )


@dataclass(frozen=True)
class StepNavigationHandler:
    """Handle explicit movement between current and next wizard steps."""

    supported_kinds: frozenset[str] = frozenset({"step"})

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        del patch_policy
        intent = resolution.intent
        if intent.target == "next":
            outcome = _handle_next(
                session=context.session,
                result=CommandResult(action="next"),
                manifest=context.manifest,
                runtime=context.runtime,
                provider=context.provider,
            )
            context.refresh_runtime_state()
            return (
                outcome.assistant_message
                or context.session.pending_question
                or "Перешли к следующему stage."
            )
        if not intent.stage_id:
            return "Формат команды: /step <stage>."
        outcome = _handle_edit_stage(
            session=context.session,
            result=CommandResult(action="edit_stage", stage=intent.stage_id),
            manifest=context.manifest,
            runtime=context.runtime,
            provider=context.provider,
        )
        context.refresh_runtime_state()
        return outcome.assistant_message or context.session.pending_question or "Stage переключён."


@dataclass(frozen=True)
class DraftMutationHandler:
    """Handle patch proposals, confirm/reject flow, and direct draft mutations."""

    supported_kinds: frozenset[str] = frozenset({"confirm", "patch_draft", "reject"})

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        intent = resolution.intent
        if intent.kind == "confirm":
            if not context.session.pending_patch_proposals:
                return "Сейчас нет ожидающих подтверждения изменений."
            applied = _apply_proposals(
                context=context,
                proposals=list(context.session.pending_patch_proposals),
            )
            context.session.pending_patch_proposals = []
            context.invalidate_interaction()
            return applied

        if intent.kind == "reject":
            if not context.session.pending_patch_proposals:
                return "Сейчас нет предложенных изменений для отмены."
            context.session.pending_patch_proposals = []
            context.invalidate_interaction()
            return "Предложенные изменения отброшены."

        if not resolution.proposals:
            return render_clarifications(resolution.clarifications)

        context.session.pending_patch_proposals = list(resolution.proposals)
        requires_confirmation = patch_policy.requires_confirmation(
            session=context.session,
            resolution=resolution,
        )
        context.session.last_intent_resolution = resolution.model_copy(
            update={"requires_confirmation": requires_confirmation}
        )
        context.invalidate_interaction()
        if requires_confirmation:
            return (
                render_proposals(resolution.proposals)
                + "\n\nЕсли всё верно, напишите `да`. Если нет — `нет`."
            )

        message = _apply_proposals(context=context, proposals=resolution.proposals)
        context.session.pending_patch_proposals = []
        context.invalidate_interaction()
        return message


@dataclass(frozen=True)
class ExecutionHandler:
    """Handle execution intents that run the underlying solver/runtime."""

    supported_kinds: frozenset[str] = frozenset({"solve"})

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        del resolution, patch_policy
        outcome = _handle_run(
            session=context.session,
            result=CommandResult(action="run"),
            manifest=context.manifest,
            runtime=context.runtime,
            provider=context.provider,
        )
        context.refresh_runtime_state()
        return outcome.assistant_message or "Расчёт выполнен."


class ConversationIntentHandlerRegistry:
    """Registry that dispatches typed intents to focused command objects."""

    def __init__(
        self,
        handlers: tuple[ConversationIntentHandler, ...] | None = None,
    ) -> None:
        configured = handlers or (
            SessionLifecycleHandler(),
            ReadOnlyHandler(),
            StepNavigationHandler(),
            DraftMutationHandler(),
            ExecutionHandler(),
        )
        self._by_kind: dict[str, ConversationIntentHandler] = {}
        for handler in configured:
            for kind in handler.supported_kinds:
                self._by_kind[kind] = handler

    def handle(
        self,
        *,
        context: ConversationContext,
        resolution: IntentResolution,
        patch_policy: PatchApplicationPolicy,
    ) -> str:
        handler = self._by_kind.get(resolution.intent.kind)
        if handler is None:
            return render_clarifications(resolution.clarifications)
        return handler.handle(
            context=context,
            resolution=resolution,
            patch_policy=patch_policy,
        )
