"""Policies for confirming or auto-applying grounded NL patch proposals."""

from __future__ import annotations

from dataclasses import dataclass

from extension_api import IntentResolution

from agent_core.models import AgentSession


@dataclass(frozen=True)
class PatchApplicationPolicy:
    """Decide whether candidate draft mutations require explicit confirmation."""

    auto_apply_threshold: float = 0.85

    def requires_confirmation(
        self,
        *,
        session: AgentSession,
        resolution: IntentResolution,
    ) -> bool:
        if not resolution.proposals:
            return False
        if resolution.source == "slash":
            return False
        if session.interaction_mode == "guided":
            return True
        if not resolution.grounded:
            return True
        if resolution.clarifications:
            return True
        return resolution.confidence < self.auto_apply_threshold
