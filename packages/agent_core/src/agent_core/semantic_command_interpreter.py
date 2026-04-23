"""Typed slash-command interpretation over canonical extension semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionManifest,
    IntentResolution,
    PatchProposal,
    SemanticIntent,
)

from agent_core.semantic_schema import resolve_field_path, resolve_stage_id, stage_alias_map
from agent_core.slash_commands import SlashCommand, parse_slash_command


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


def _stage_alias_items_by_specificity(
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> list[tuple[str, str]]:
    alias_map = stage_alias_map(manifest=manifest, semantics=semantics)
    return sorted(alias_map.items(), key=lambda item: (-len(item[0]), item[0]))


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
        return self._resolve_command(
            command=command,
            raw_message=message,
            manifest=manifest,
            semantics=semantics,
        )

    def _resolve_command(
        self,
        *,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        if command.name == "invalid":
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="unknown", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=[
                    "Команда не распознана. Используйте /help, чтобы увидеть доступные варианты."
                ],
            )

        if command.name == "new":
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

        if command.name == "use":
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

        if command.name == "show":
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

        if command.name in {"solve", "run"}:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="solve", raw_message=raw_message),
                confidence=1.0,
                grounded=True,
            )

        if command.name == "validate":
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="validate", raw_message=raw_message),
                confidence=1.0,
                grounded=True,
            )

        if command.name == "reset":
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="reset", raw_message=raw_message),
                confidence=1.0,
                grounded=True,
            )

        if command.name == "help":
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="help", raw_message=raw_message),
                confidence=1.0,
                grounded=True,
            )

        if command.name == "explain":
            target = (command.arg or "result").strip().lower()
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="explain", raw_message=raw_message, target=target),
                confidence=1.0,
                grounded=True,
            )

        if command.name == "semantics":
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

        if command.name == "mode":
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

        if command.name == "step":
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

        if command.name == "payload":
            return self._resolve_payload(
                command=command,
                raw_message=raw_message,
                manifest=manifest,
                semantics=semantics,
            )

        if command.name == "set":
            return self._resolve_set(
                command=command,
                raw_message=raw_message,
                manifest=manifest,
                semantics=semantics,
            )

        if command.name == "next":
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="step", raw_message=raw_message, target="next"),
                confidence=1.0,
                grounded=True,
            )

        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="unknown", raw_message=raw_message),
            confidence=0.0,
            grounded=False,
        )

    def _resolve_payload(
        self,
        *,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        if not command.arg or not command.payload:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=["Формат команды: /payload <stage> <json>."],
            )
        stage_id = resolve_stage_id(raw=command.arg, manifest=manifest, semantics=semantics)
        if stage_id is None:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=[f"Неизвестный stage `{command.arg}`."],
            )
        try:
            payload = json.loads(command.payload)
        except json.JSONDecodeError as exc:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=[f"Некорректный JSON в /payload: {exc}"],
            )
        if not isinstance(payload, dict):
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=["Команда /payload ожидает JSON-объект."],
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

    def _resolve_set(
        self,
        *,
        command: SlashCommand,
        raw_message: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        if not command.payload:
            return IntentResolution(
                source="slash",
                intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                confidence=0.0,
                grounded=False,
                clarifications=["Формат команды: /set <stage>.<field> <value>."],
            )
        stripped = command.payload.strip()
        for alias, stage_id in _stage_alias_items_by_specificity(manifest, semantics):
            prefix = f"{alias}."
            normalized = stripped.lower()
            if not normalized.startswith(prefix):
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
                return IntentResolution(
                    source="slash",
                    intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
                    confidence=0.0,
                    grounded=False,
                    clarifications=[f"Неизвестное поле `{raw_path}` для stage `{stage_id}`."],
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
        return IntentResolution(
            source="slash",
            intent=SemanticIntent(kind="patch_draft", raw_message=raw_message),
            confidence=0.0,
            grounded=False,
            clarifications=["Формат команды: /set <stage>.<field> <value>."],
        )
