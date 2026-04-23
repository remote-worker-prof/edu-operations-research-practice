"""Shared runtime context for one semantics-driven chat turn."""

from __future__ import annotations

from dataclasses import dataclass, field

from extension_api import (
    DiscoveredExtension,
    ExtensionBundleSemantics,
    ExtensionInteractionState,
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionRuntime,
)

from agent_core.extension_flow import (
    _pending_question,
    _recompute_extension_state,
    _sync_phase_and_summary,
    reset_session_for_extension,
)
from agent_core.interaction_state import build_interaction_state
from agent_core.models import AgentSession
from agent_core.semantic_schema import runtime_bundle_semantics


@dataclass
class ConversationContext:
    """Bundles all runtime objects that should be reused during one chat turn."""

    session: AgentSession
    registry: ExtensionRegistry
    discovered: DiscoveredExtension
    manifest: ExtensionManifest
    runtime: ExtensionRuntime
    semantics: ExtensionBundleSemantics | None
    _interaction: ExtensionInteractionState | None = field(
        default=None,
        init=False,
        repr=False,
    )

    @classmethod
    def build(
        cls,
        *,
        session: AgentSession,
        registry: ExtensionRegistry,
    ) -> ConversationContext:
        """Build a context for the session's currently selected extension."""
        discovered = registry.require(session.extension_alias)
        runtime = discovered.create_runtime()
        return cls(
            session=session,
            registry=registry,
            discovered=discovered,
            manifest=discovered.manifest,
            runtime=runtime,
            semantics=runtime_bundle_semantics(runtime),
        )

    @property
    def provider(self):
        """Expose the active provider without reloading it from the registry."""
        return self.discovered.provider

    def invalidate_interaction(self) -> None:
        """Drop the cached interaction snapshot after any state mutation."""
        self._interaction = None

    def refresh_runtime_state(self) -> None:
        """Recompute derived state for the active extension and clear interaction cache."""
        _recompute_extension_state(
            session=self.session,
            manifest=self.manifest,
            runtime=self.runtime,
        )
        _sync_phase_and_summary(self.session, self.manifest)
        self.session.pending_question = _pending_question(
            self.session,
            self.manifest,
            self.runtime,
        )
        self.invalidate_interaction()

    def interaction_state(self) -> ExtensionInteractionState:
        """Return one cached interaction snapshot for the current turn."""
        if self._interaction is None:
            self._interaction = build_interaction_state(
                session=self.session,
                registry=self.registry,
            )
        return self._interaction

    def reset_for_extension(self, alias: str) -> None:
        """Switch the session to a clean draft for another extension and reload runtime."""
        target = self.registry.require(alias)
        reset_session_for_extension(
            self.session,
            alias=alias,
            manifest=target.manifest,
        )
        self.discovered = target
        self.manifest = target.manifest
        self.runtime = target.create_runtime()
        self.semantics = runtime_bundle_semantics(self.runtime)
        self.refresh_runtime_state()
