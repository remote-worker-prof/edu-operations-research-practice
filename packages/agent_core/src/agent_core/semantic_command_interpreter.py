"""Typed slash-command interpretation over canonical extension semantics."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionManifest,
    IntentResolution,
    PatchProposal,
    SemanticIntent,
)

from agent_core.semantic_schema import (
    resolve_field_path,
    resolve_stage_id,
    stage_alias_items_by_specificity,
)
from agent_core.slash_commands import SlashCommand, parse_slash_command

SlashHandler = Callable[
    [SlashCommand, str, ExtensionManifest, ExtensionBundleSemantics | None],
    IntentResolution,
]


def _parse_scalar(value_text: str) -> Any:
    value_text = value_text.strip()
    if not value_text:
        return value_text
    try:
        return json.loads(value_text)
    except json.JSONDecodeError:
        pass
    normalized = value_text.lower()
    if normalized in {"true", "false"}:
        return normalized == "true"
    if re.fullmatch(r"-?\d+", value_text):
        return int(value_text)
    if re.fullmatch(r"-?\d+\.\d+", value_text):
        return float(value_text)
    return value_text


@dataclass(frozen=True)
class CommandSpec:
    """Declarative registration entry for one slash command handler."""

    name: str
    handler: SlashHandler


@dataclass(frozen=True)
class SemanticCommandInterpreter:
    """Strategy that turns slash commands into typed semantic intents."""

    def interpret(
        self,
        *,
        message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution | None:
        command = parse_slash_command(message)
        if command is None:
            return None
        spec = self._spec_map().get(command.name)
        if spec is None:
            return self._unknown_resolution(raw_message=message)
        return spec.handler(command, message, manifest, semantics)

    def _spec_map(self) -> dict[str, CommandSpec]:
        return {
            spec.name: spec
            for spec in (
                CommandSpec("invalid", self._handle_invalid),
                CommandSpec("new", self._handle_new),
                CommandSpec("use", self._handle_use),
                CommandSpec("show", self._handle_show),
                CommandSpec("solve", self._handle_solve),
                CommandSpec("run", self._handle_solve),
                CommandSpec("validate", self._handle_validate),
                CommandSpec("reset", self._handle_reset),
                CommandSpec("help", self._handle_help),
                CommandSpec("explain", self._handle_explain),
                CommandSpec("semantics", self._handle_semantics),
                CommandSpec("mode", self._handle_mode),
                CommandSpec("step", self._handle_step),
                CommandSpec("payload", self._handle_payload),
                CommandSpec("set", self._handle_set),
                CommandSpec("next", self._handle_next),
            )
        }

    def _unknown_resolution(self, *, raw_message: str) -> IntentResolution:
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="unknown", raw_message=raw_message),
            confidence=0.0,
            grounded=False,
        )

    def _patch_error(
        self,
        *,
        raw_message: str,
        clarification: str,
    ) -> IntentResolution:
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
            confidence=0.0,
            grounded=False,
            clarifications=[clarification],
        )

    def _handle_invalid(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="unknown", raw_message=raw_message),
            confidence=0.0,
            grounded=False,
            clarifications=[
                "Команда не распознана. Используйте /help, чтобы увидеть доступные варианты."
            ],
        )

    def _handle_new(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="new_thread",
                raw_message=raw_message,
                extension_alias=command.arg,
            ),
            confidence=1.0,
            grounded=True,
        )

    def _handle_use(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="use_extension",
                raw_message=raw_message,
                extension_alias=command.arg,
            ),
            confidence=1.0,
            grounded=bool(command.arg),
            clarifications=[] if command.arg else ["Формат команды: /use <extension>."],
        )

    def _handle_show(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="show",
                raw_message=raw_message,
                target=(command.arg or "steps"),
            ),
            confidence=1.0,
            grounded=True,
        )

    def _handle_solve(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="solve", raw_message=raw_message),
            confidence=1.0,
            grounded=True,
        )

    def _handle_validate(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="validate", raw_message=raw_message),
            confidence=1.0,
            grounded=True,
        )

    def _handle_reset(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="reset", raw_message=raw_message),
            confidence=1.0,
            grounded=True,
        )

    def _handle_help(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="help", raw_message=raw_message),
            confidence=1.0,
            grounded=True,
        )

    def _handle_explain(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del manifest, semantics
        target = (command.arg or "result").strip().lower()
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="explain", raw_message=raw_message, target=target),
            confidence=1.0,
            grounded=True,
        )

    def _handle_semantics(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="explain",
                raw_message=raw_message,
                target="semantics_snapshot",
            ),
            confidence=1.0,
            grounded=True,
        )

    def _handle_mode(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del manifest, semantics
        normalized = (command.arg or "").strip().lower()
        if normalized not in {"guided", "power"}:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="mode", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=["Формат команды: /mode guided|power."],
            )
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="mode",
                raw_message=raw_message,
                interaction_mode=normalized,
            ),
            confidence=1.0,
            grounded=True,
        )

    def _handle_step(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        if not command.arg:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="step", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=["Формат команды: /step <stage>."],
            )
        stage_id = resolve_stage_id(
            raw=command.arg,
            manifest=manifest,
            semantics=semantics,
        )
        if stage_id is None:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="step", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=[f"Неизвестный stage `{command.arg}`."],
            )
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="step", raw_message=raw_message, stage_id=stage_id),
            confidence=1.0,
            grounded=True,
        )

    def _handle_payload(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        resolved = self._resolve_payload_target_and_json(
            command=command,
            manifest=manifest,
            semantics=semantics,
        )
        if resolved is None:
            return self._patch_error(
                raw_message=raw_message,
                clarification="Формат команды: /payload <stage> <json>.",
            )
        stage_id, payload_text = resolved
        if stage_id is None:
            return self._patch_error(
                raw_message=raw_message,
                clarification=f"Неизвестный stage `{command.arg}`.",
            )
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            return self._patch_error(
                raw_message=raw_message,
                clarification=f"Некорректный JSON в /payload: {exc}",
            )
        if not isinstance(payload, dict):
            return self._patch_error(
                raw_message=raw_message,
                clarification="Команда /payload ожидает JSON-объект.",
            )
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(
                kind="patch_draft",
                raw_message=raw_message,
                stage_id=stage_id,
            ),
            proposals=[
                PatchProposal(
                    stage_id=stage_id,
                    payload=payload,
                    confidence=1.0,
                    source="slash",
                )
            ],
            confidence=1.0,
            grounded=True,
            requires_confirmation=False,
        )

    def _resolve_payload_target_and_json(
        self,
        *,
        command: SlashCommand,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> tuple[str | None, str] | None:
        if not command.arg or not command.payload:
            return None
        raw_body = f"{command.arg} {command.payload}".strip()
        lowered = raw_body.lower()
        for alias, stage_id in stage_alias_items_by_specificity(
            manifest=manifest,
            semantics=semantics,
        ):
            if lowered == alias:
                continue
            if not lowered.startswith(alias):
                continue
            if len(lowered) > len(alias) and not lowered[len(alias)].isspace():
                continue
            remainder = raw_body[len(alias) :].lstrip()
            if remainder:
                return stage_id, remainder
        return resolve_stage_id(
            raw=command.arg,
            manifest=manifest,
            semantics=semantics,
        ), command.payload

    def _handle_set(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        if not command.payload:
            return self._patch_error(
                raw_message=raw_message,
                clarification="Формат команды: /set <stage>.<field> <value>.",
            )

        stripped = command.payload.strip()
        lowered = stripped.lower()
        for alias, stage_id in stage_alias_items_by_specificity(
            manifest=manifest,
            semantics=semantics,
        ):
            prefix = f"{alias}."
            if not lowered.startswith(prefix):
                continue
            remainder = stripped[len(alias) + 1 :]
            if " " not in remainder:
                break
            raw_path, value_text = remainder.split(" ", maxsplit=1)
            field_path = resolve_field_path(
                raw=raw_path,
                stage_id=stage_id,
                manifest=manifest,
                semantics=semantics,
            )
            if field_path is None:
                return self._patch_error(
                    raw_message=raw_message,
                    clarification=f"Неизвестное поле `{raw_path}` для stage `{stage_id}`.",
                )
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(
                    kind="patch_draft",
                    raw_message=raw_message,
                    stage_id=stage_id,
                ),
                proposals=[
                    PatchProposal(
                        stage_id=stage_id,
                        path=field_path,
                        value=_parse_scalar(value_text),
                        confidence=1.0,
                        source="slash",
                    )
                ],
                confidence=1.0,
                grounded=True,
                requires_confirmation=False,
            )

        return self._patch_error(
            raw_message=raw_message,
            clarification="Формат команды: /set <stage>.<field> <value>.",
        )

    def _handle_next(
        self,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        del command, manifest, semantics
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="step", raw_message=raw_message, target="next"),
            confidence=1.0,
            grounded=True,
        )
