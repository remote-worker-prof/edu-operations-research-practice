"""Unified semantics-first conversation pipeline for the primary React chat."""

from __future__ import annotations

from dataclasses import dataclass, field

from extension_api import ExtensionRegistry

from agent_core.conversation_context import ConversationContext
from agent_core.conversation_handlers import ConversationIntentHandlerRegistry
from agent_core.extension_commands import parse_extension_command
from agent_core.extension_flow import handle_extension_turn
from agent_core.models import AgentSession, ChatMessage
from agent_core.patch_policy import PatchApplicationPolicy
from agent_core.semantic_command_interpreter import SemanticCommandInterpreter
from agent_core.semantic_nl_engine import SemanticIntentEngine


def _append_message(session: AgentSession, role: str, content: str) -> None:
    """Append one chat message to the session transcript."""
    session.messages.append(ChatMessage(role=role, content=content))


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
    """Template-method orchestration for one user turn in the new chat."""

    command_interpreter: SemanticCommandInterpreter = field(
        default_factory=SemanticCommandInterpreter
    )
    nl_engine: SemanticIntentEngine = field(default_factory=SemanticIntentEngine)
    patch_policy: PatchApplicationPolicy = field(default_factory=PatchApplicationPolicy)
    legacy_adapter: LegacyBareCommandAdapter = field(default_factory=LegacyBareCommandAdapter)
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

        if resolution.intent.kind == "unknown":
            adapted = self.legacy_adapter.maybe_handle(
                session=context.session,
                user_message=user_message,
                registry=registry,
            )
            if adapted is not None:
                adapted_session, assistant_message = adapted
                adapted_session.last_intent_resolution = resolution.model_copy(
                    update={"source": "legacy_bare", "grounded": True, "confidence": 1.0}
                )
                return adapted_session, assistant_message

        assistant_message = self.handler_registry.handle(
            context=context,
            resolution=resolution,
            patch_policy=self.patch_policy,
        )
        _append_message(context.session, "user", user_message.strip())
        _append_message(context.session, "assistant", assistant_message)
        return context.session, assistant_message
