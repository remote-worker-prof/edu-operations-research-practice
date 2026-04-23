"""Unified semantics-first conversation pipeline for the primary React chat."""

from __future__ import annotations

from dataclasses import dataclass, field

from extension_api import ExtensionRegistry, IntentResolution, SemanticIntent

from agent_core.conversation_context import ConversationContext
from agent_core.conversation_handlers import ConversationIntentHandlerRegistry
from agent_core.extension_commands import parse_extension_command
from agent_core.models import AgentSession, ChatMessage
from agent_core.patch_policy import PatchApplicationPolicy
from agent_core.semantic_command_interpreter import SemanticCommandInterpreter
from agent_core.semantic_nl_engine import SemanticIntentEngine


def _append_message(session: AgentSession, role: str, content: str) -> None:
    """Append one chat message to the session transcript."""
    session.messages.append(ChatMessage(role=role, content=content))


@dataclass
class LegacyBareCommandGuard:
    """Detect deprecated bare commands so `/app` can reject them deterministically."""

    def maybe_detect(
        self,
        *,
        session: AgentSession,
        user_message: str,
        registry: ExtensionRegistry,
    ) -> str | None:
        text = user_message.strip()
        if not text or text.startswith("/"):
            return None
        discovered = registry.require(session.extension_alias)
        result = parse_extension_command(
            message=text,
            current_stage=session.collection_state.current_stage,
            manifest=discovered.manifest,
        )
        if result.action == "invalid":
            return None
        return result.action


def _legacy_command_rejected_message(action: str) -> str:
    """Render one stable rejection message for bare commands in the new chat shell."""
    return (
        f"Команда без `/` (`{action}`) недоступна в новом чате `/app`.\n"
        "Используйте guided UI или slash-команды: `/help`, `/payload`, `/set`, `/solve`.\n"
        "Legacy bare-режим доступен только на `/legacy`."
    )


@dataclass
class ConversationOrchestrator:
    """Template-method orchestration for one user turn in the new chat."""

    command_interpreter: SemanticCommandInterpreter = field(
        default_factory=SemanticCommandInterpreter
    )
    nl_engine: SemanticIntentEngine = field(default_factory=SemanticIntentEngine)
    patch_policy: PatchApplicationPolicy = field(default_factory=PatchApplicationPolicy)
    legacy_guard: LegacyBareCommandGuard = field(default_factory=LegacyBareCommandGuard)
    handler_registry: ConversationIntentHandlerRegistry = field(
        default_factory=ConversationIntentHandlerRegistry
    )

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
        context = ConversationContext.build(session=session, registry=registry)
        context.refresh_runtime_state()
        legacy_action = self.legacy_guard.maybe_detect(
            session=context.session,
            user_message=user_message,
            registry=registry,
        )
        if legacy_action is not None:
            assistant_message = _legacy_command_rejected_message(legacy_action)
            context.session.last_intent_resolution = IntentResolution(
                source="legacy_bare",
                intent=SemanticIntent(kind="unknown", raw_message=user_message),
                confidence=1.0,
                grounded=False,
                clarifications=[assistant_message],
            )
            _append_message(context.session, "user", user_message.strip())
            _append_message(context.session, "assistant", assistant_message)
            return context.session, assistant_message

        resolution = self.command_interpreter.interpret(
            message=user_message,
            manifest=context.manifest,
            semantics=context.semantics,
        )
        if resolution is None:
            resolution = self.nl_engine.interpret(
                message=user_message,
                current_stage=context.session.collection_state.current_stage,
                manifest=context.manifest,
                semantics=context.semantics,
                model_alias=model_alias,
            )

        context.session.last_intent_resolution = resolution
        context.session.nl_apply_policy = (
            "confirm"
            if context.session.interaction_mode == "guided"
            else "auto_if_confident"
        )

        assistant_message = self.handler_registry.handle(
            context=context,
            resolution=resolution,
            patch_policy=self.patch_policy,
        )
        _append_message(context.session, "user", user_message.strip())
        _append_message(context.session, "assistant", assistant_message)
        return context.session, assistant_message
