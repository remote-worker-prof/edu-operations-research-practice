"""Unified semantics-first conversation pipeline for the primary React chat."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionRegistry,
    IntentResolution,
    PatchProposal,
)

from agent_core.extension_commands import parse_extension_command
from agent_core.extension_flow import (
    _handle_edit_stage,
    _handle_next,
    _handle_reset,
    _handle_run,
    _handle_set_field,
    _handle_stage_json,
    _invalidate_extension_result,
    _pending_question,
    _recompute_extension_state,
    _sync_phase_and_summary,
    handle_extension_turn,
    manifest_for_alias,
    reset_session_for_extension,
    session_is_empty,
    sync_default_or_legacy_from_generic_state,
)
from agent_core.interaction_state import (
    build_interaction_state,
    render_help_text,
    render_result_overview,
    render_steps_overview,
    render_validation_overview,
)
from agent_core.models import AgentSession, ChatMessage, CommandResult, InputPatch
from agent_core.patch_policy import PatchApplicationPolicy
from agent_core.semantic_command_interpreter import SemanticCommandInterpreter
from agent_core.semantic_nl_engine import SemanticIntentEngine
from agent_core.semantic_schema import resolve_artifact, runtime_bundle_semantics


def _append_message(session: AgentSession, role: str, content: str) -> None:
    session.messages.append(ChatMessage(role=role, content=content))


def _render_proposals(proposals: list[PatchProposal]) -> str:
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


def _render_clarifications(clarifications: list[str]) -> str:
    if not clarifications:
        return "Не удалось понять сообщение в терминах текущего extension."
    lines = ["Нужна небольшая конкретизация:"]
    lines.extend(f"- {item}" for item in clarifications)
    return "\n".join(lines)


@dataclass
class LegacyBareCommandAdapter:
    """Compatibility adapter for deprecated bare commands in the new shell."""

    def maybe_handle(
        self,
        *,
        session: AgentSession,
        user_message: str,
        registry: ExtensionRegistry,
    ) -> tuple[AgentSession, str] | None:
        discovered = registry.require(session.extension_alias)
        result = parse_extension_command(
            message=user_message,
            current_stage=session.collection_state.current_stage,
            manifest=discovered.manifest,
        )
        if result.action == "invalid":
            return None
        return handle_extension_turn(
            session=session,
            user_message=user_message,
            registry=registry,
        )


@dataclass
class ConversationOrchestrator:
    """Template-method style orchestration for one user turn in the new chat."""

    command_interpreter: SemanticCommandInterpreter = field(
        default_factory=SemanticCommandInterpreter
    )
    nl_engine: SemanticIntentEngine = field(default_factory=SemanticIntentEngine)
    patch_policy: PatchApplicationPolicy = field(default_factory=PatchApplicationPolicy)
    legacy_adapter: LegacyBareCommandAdapter = field(default_factory=LegacyBareCommandAdapter)

    def handle(
        self,
        *,
        session: AgentSession,
        user_message: str,
        registry: ExtensionRegistry,
        model_alias: str | None,
    ) -> tuple[AgentSession, str]:
        session = session.model_copy(deep=True)
        session.errors = []

        discovered = registry.require(session.extension_alias)
        manifest = discovered.manifest
        runtime = discovered.create_runtime()
        semantics = runtime_bundle_semantics(runtime)

        self._refresh_runtime_state(
            session=session,
            manifest=manifest,
            runtime=runtime,
        )

        resolution = self.command_interpreter.interpret(
            message=user_message,
            manifest=manifest,
            semantics=semantics,
        )
        if resolution is None:
            resolution = self.nl_engine.interpret(
                message=user_message,
                current_stage=session.collection_state.current_stage,
                manifest=manifest,
                semantics=semantics,
                model_alias=model_alias,
            )

        session.last_intent_resolution = resolution
        session.nl_apply_policy = (
            "confirm" if session.interaction_mode == "guided" else "auto_if_confident"
        )

        if resolution.intent.kind == "unknown":
            adapted = self.legacy_adapter.maybe_handle(
                session=session,
                user_message=user_message,
                registry=registry,
            )
            if adapted is not None:
                adapted_session, assistant_message = adapted
                adapted_session.last_intent_resolution = resolution.model_copy(
                    update={"source": "legacy_bare", "grounded": True, "confidence": 1.0}
                )
                return adapted_session, assistant_message

        assistant_message = self._apply_resolution(
            session=session,
            registry=registry,
            resolution=resolution,
            semantics=semantics,
        )
        _append_message(session, "user", user_message.strip())
        _append_message(session, "assistant", assistant_message)
        return session, assistant_message

    def _refresh_runtime_state(
        self,
        *,
        session: AgentSession,
        manifest,
        runtime,
    ) -> None:
        _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
        _sync_phase_and_summary(session, manifest)
        session.pending_question = _pending_question(session, manifest, runtime)

    def _apply_resolution(
        self,
        *,
        session: AgentSession,
        registry: ExtensionRegistry,
        resolution: IntentResolution,
        semantics: ExtensionBundleSemantics | None,
    ) -> str:
        discovered = registry.require(session.extension_alias)
        manifest = discovered.manifest
        runtime = discovered.create_runtime()
        intent = resolution.intent

        if intent.kind == "new_thread":
            target_alias = intent.extension_alias or session.extension_alias
            try:
                target_manifest = manifest_for_alias(registry, target_alias)
            except Exception:
                return f"Extension `{target_alias}` не найдено."
            reset_session_for_extension(session, alias=target_alias, manifest=target_manifest)
            self._refresh_runtime_state(
                session=session,
                manifest=target_manifest,
                runtime=registry.require(target_alias).create_runtime(),
            )
            sync_default_or_legacy_from_generic_state(session)
            return (
                f"Начат новый чистый сценарий для `{target_alias}`. "
                f"{session.pending_question or ''}".strip()
            )

        if intent.kind == "use_extension":
            if not intent.extension_alias:
                return "Формат команды: /use <extension>."
            if intent.extension_alias == session.extension_alias:
                return f"Уже выбран extension `{intent.extension_alias}`."
            try:
                target_manifest = manifest_for_alias(registry, intent.extension_alias)
            except Exception:
                return f"Extension `{intent.extension_alias}` не найдено."
            if not session_is_empty(session):
                return (
                    "Нельзя сменить extension в непустом треде. "
                    "Используйте /new <extension> для нового чистого сценария."
                )
            reset_session_for_extension(
                session,
                alias=intent.extension_alias,
                manifest=target_manifest,
            )
            self._refresh_runtime_state(
                session=session,
                manifest=target_manifest,
                runtime=registry.require(intent.extension_alias).create_runtime(),
            )
            sync_default_or_legacy_from_generic_state(session)
            return f"Выбран extension `{intent.extension_alias}`."

        if intent.kind == "show":
            interaction = build_interaction_state(session=session, registry=registry)
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
                return render_result_overview(session)
            return "Команда /show поддерживает только steps, draft или result."

        if intent.kind == "help":
            interaction = build_interaction_state(session=session, registry=registry)
            return render_help_text(interaction)

        if intent.kind == "validate":
            interaction = build_interaction_state(session=session, registry=registry)
            return render_validation_overview(interaction)

        if intent.kind == "mode":
            if intent.interaction_mode not in {"guided", "power"}:
                return "Формат команды: /mode guided|power."
            session.interaction_mode = intent.interaction_mode
            session.nl_apply_policy = (
                "confirm" if session.interaction_mode == "guided" else "auto_if_confident"
            )
            return f"Режим взаимодействия переключён на `{session.interaction_mode}`."

        if intent.kind == "step":
            if intent.target == "next":
                outcome = _handle_next(
                    session=session,
                    result=CommandResult(action="next"),
                    manifest=manifest,
                    runtime=runtime,
                    provider=discovered.provider,
                )
                self._refresh_runtime_state(session=session, manifest=manifest, runtime=runtime)
                return (
                    outcome.assistant_message
                    or session.pending_question
                    or "Перешли к следующему stage."
                )
            if not intent.stage_id:
                return "Формат команды: /step <stage>."
            outcome = _handle_edit_stage(
                session=session,
                result=CommandResult(action="edit_stage", stage=intent.stage_id),
                manifest=manifest,
                runtime=runtime,
                provider=discovered.provider,
            )
            self._refresh_runtime_state(session=session, manifest=manifest, runtime=runtime)
            return outcome.assistant_message or session.pending_question or "Stage переключён."

        if intent.kind == "reset":
            outcome = _handle_reset(
                session=session,
                result=CommandResult(action="reset"),
                manifest=manifest,
                runtime=runtime,
                provider=discovered.provider,
            )
            sync_default_or_legacy_from_generic_state(session)
            self._refresh_runtime_state(session=session, manifest=manifest, runtime=runtime)
            session.pending_patch_proposals = []
            return outcome.assistant_message or "Черновик сброшен."

        if intent.kind == "solve":
            outcome = _handle_run(
                session=session,
                result=CommandResult(action="run"),
                manifest=manifest,
                runtime=runtime,
                provider=discovered.provider,
            )
            self._refresh_runtime_state(session=session, manifest=manifest, runtime=runtime)
            return outcome.assistant_message or "Расчёт выполнен."

        if intent.kind == "explain":
            return self._render_explain_response(
                session=session,
                semantics=semantics,
                target=intent.target or "result",
            )

        if intent.kind == "confirm":
            if not session.pending_patch_proposals:
                return "Сейчас нет ожидающих подтверждения изменений."
            applied = self._apply_proposals(
                session=session,
                manifest=manifest,
                runtime=runtime,
                provider=discovered.provider,
                proposals=list(session.pending_patch_proposals),
            )
            session.pending_patch_proposals = []
            return applied

        if intent.kind == "reject":
            if not session.pending_patch_proposals:
                return "Сейчас нет предложенных изменений для отмены."
            session.pending_patch_proposals = []
            return "Предложенные изменения отброшены."

        if intent.kind == "patch_draft":
            if not resolution.proposals:
                return _render_clarifications(resolution.clarifications)
            session.pending_patch_proposals = list(resolution.proposals)
            requires_confirmation = self.patch_policy.requires_confirmation(
                session=session,
                resolution=resolution,
            )
            session.last_intent_resolution = resolution.model_copy(
                update={"requires_confirmation": requires_confirmation}
            )
            if requires_confirmation:
                return (
                    _render_proposals(resolution.proposals)
                    + "\n\nЕсли всё верно, напишите `да`. Если нет — `нет`."
                )
            message = self._apply_proposals(
                session=session,
                manifest=manifest,
                runtime=runtime,
                provider=discovered.provider,
                proposals=resolution.proposals,
            )
            session.pending_patch_proposals = []
            return message

        return _render_clarifications(resolution.clarifications)

    def _apply_proposals(
        self,
        *,
        session: AgentSession,
        manifest,
        runtime,
        provider,
        proposals: list[PatchProposal],
    ) -> str:
        for proposal in proposals:
            if proposal.payload is not None:
                _handle_stage_json(
                    session=session,
                    result=CommandResult(
                        action="stage_json",
                        stage=proposal.stage_id,
                        patch=InputPatch(stage=proposal.stage_id, payload=proposal.payload),
                    ),
                    manifest=manifest,
                    runtime=runtime,
                    provider=provider,
                )
            elif proposal.path is not None:
                _handle_set_field(
                    session=session,
                    result=CommandResult(
                        action="set_field",
                        stage=proposal.stage_id,
                        patch=InputPatch(
                            stage=proposal.stage_id,
                            path=proposal.path,
                            value=proposal.value,
                        ),
                    ),
                    manifest=manifest,
                    runtime=runtime,
                    provider=provider,
                )

        _invalidate_extension_result(session)
        sync_default_or_legacy_from_generic_state(session)
        self._refresh_runtime_state(session=session, manifest=manifest, runtime=runtime)

        lines = ["Изменения применены.", _render_proposals(proposals)]
        if session.pending_question:
            lines.extend(["", session.pending_question])
        return "\n".join(lines)

    def _render_explain_response(
        self,
        *,
        session: AgentSession,
        semantics: ExtensionBundleSemantics | None,
        target: str,
    ) -> str:
        normalized = target.strip().lower()
        if normalized == "result":
            return render_result_overview(session)
        if normalized.startswith("step"):
            _, _, maybe_stage = normalized.partition(" ")
            stage_id = maybe_stage or session.collection_state.current_stage or ""
            if not stage_id:
                return "Сейчас не выбран активный step для объяснения."
            if semantics is None or not semantics.stages:
                return (
                    f"Extension `{session.extension_alias}` пока не публикует typed step semantics."
                )
            for item in semantics.stages:
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

        artifact = resolve_artifact(semantics=semantics, target=normalized)
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
