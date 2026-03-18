"""Manifest-driven deterministic command parser for installable extensions."""

from __future__ import annotations

import json
import re
from typing import Any

from extension_api import ExtensionManifest

from agent_core.models import CommandResult, InputPatch


def build_stage_alias_map(manifest: ExtensionManifest) -> dict[str, str]:
    """Builds a lowercase alias -> stage_id mapping from an extension manifest."""
    alias_map: dict[str, str] = {}
    stage_map = manifest.stage_map()
    for stage in manifest.stage_graph:
        alias_map[stage.stage_id.lower()] = stage.stage_id
        alias_map[stage.label.strip().lower()] = stage.stage_id
        for alias in stage.aliases:
            alias_map[alias.strip().lower()] = stage.stage_id
    for stage_id, aliases in manifest.stage_aliases.items():
        if stage_id not in stage_map:
            continue
        for alias in aliases:
            alias_map[alias.strip().lower()] = stage_id
    return alias_map


def _resolve_stage(raw: str, alias_map: dict[str, str]) -> str | None:
    """Resolves one stage alias to a canonical stage_id."""
    return alias_map.get(raw.strip().lower())


def _stage_alias_items_by_specificity(alias_map: dict[str, str]) -> list[tuple[str, str]]:
    """Returns stage aliases sorted so multi-word/long aliases win first."""
    return sorted(alias_map.items(), key=lambda item: (-len(item[0]), item[0]))


def _resolve_json_stage_and_payload(
    command_body: str,
    alias_map: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Splits `json <stage> { ... }` into a canonical stage_id and JSON payload text."""
    json_start = command_body.find("{")
    if json_start < 0:
        return None, None, None

    stage_raw = command_body[:json_start].strip()
    payload_text = command_body[json_start:].strip()
    if not stage_raw or not payload_text:
        return None, None, None
    return _resolve_stage(stage_raw, alias_map), stage_raw, payload_text


def _resolve_set_stage_path_and_value(
    command_body: str,
    alias_map: dict[str, str],
) -> tuple[str | None, str | None, str | None, bool]:
    """Splits `set <stage>.<field_path> <value>` with longest stage-alias matching."""
    stripped = command_body.strip()
    normalized = stripped.lower()

    for alias, stage_id in _stage_alias_items_by_specificity(alias_map):
        prefix = f"{alias}."
        if not normalized.startswith(prefix):
            continue
        remainder = stripped[len(alias) + 1 :]
        if not remainder or " " not in remainder:
            return None, None, None, False
        path, value_text = remainder.split(" ", maxsplit=1)
        path = path.strip()
        value_text = value_text.strip()
        if not path or not value_text:
            return None, None, None, False
        return stage_id, path, value_text, False

    return None, None, None, "." in stripped and " " in stripped


def _parse_scalar(value_text: str) -> Any:
    """Parses a scalar, JSON array/object, or leaves the raw string as fallback."""
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


def parse_extension_command(
    *,
    message: str,
    current_stage: str | None,
    manifest: ExtensionManifest,
) -> CommandResult:
    """Parses a deterministic extension command against manifest-driven stage aliases."""
    text = message.strip()
    if not text:
        return CommandResult(action="invalid", errors=["Пустая команда"])

    alias_map = build_stage_alias_map(manifest)
    lower = text.lower()
    if lower in {"start", "старт"}:
        return CommandResult(action="start")
    if lower in {"reset", "сброс"}:
        return CommandResult(action="reset")
    if lower in {"help", "помощь"}:
        return CommandResult(action="help")
    if lower in {"show input", "show", "показать ввод", "показать"}:
        return CommandResult(action="show_input")
    if lower in {"next", "далее"}:
        return CommandResult(action="next")
    if lower in {"run", "запуск"}:
        return CommandResult(action="run")
    if manifest.default_preset and lower in {
        "load preset demo",
        "preset demo",
        "load demo",
        "загрузить демо",
    }:
        return CommandResult(action="load_preset", preset_ref=manifest.default_preset)

    if lower.startswith("edit "):
        maybe_stage = _resolve_stage(text.split(" ", maxsplit=1)[1], alias_map)
        if maybe_stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для edit"])
        return CommandResult(action="edit_stage", stage=maybe_stage)

    if lower.startswith("json "):
        stage, _, payload_text = _resolve_json_stage_and_payload(
            text[len("json ") :],
            alias_map,
        )
        if payload_text is None:
            return CommandResult(action="invalid", errors=["Формат: json <stage> { ... }"])
        if stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для json"])
        try:
            payload = json.loads(payload_text)
            if not isinstance(payload, dict):
                return CommandResult(action="invalid", errors=["JSON stage должен быть объектом"])
        except json.JSONDecodeError as exc:
            return CommandResult(action="invalid", errors=[f"Некорректный JSON: {exc}"])
        return CommandResult(
            action="stage_json",
            stage=stage,
            patch=InputPatch(stage=stage, payload=payload),
        )

    if lower.startswith("set "):
        stage, path, value_text, unknown_stage = _resolve_set_stage_path_and_value(
            text[len("set ") :],
            alias_map,
        )
        if stage is None or path is None or value_text is None:
            if unknown_stage:
                return CommandResult(action="invalid", errors=["Неизвестный stage для set"])
            return CommandResult(
                action="invalid",
                errors=["Формат: set <stage>.<field_path> <value>"],
            )
        value = _parse_scalar(value_text)
        return CommandResult(
            action="set_field",
            stage=stage,
            patch=InputPatch(stage=stage, path=path, value=value),
        )

    if text.startswith("{") and text.endswith("}"):
        if current_stage is None:
            return CommandResult(
                action="invalid",
                errors=["Уточните stage: используйте json <stage> { ... }"],
            )
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return CommandResult(action="invalid", errors=["JSON stage должен быть объектом"])
        except json.JSONDecodeError as exc:
            return CommandResult(action="invalid", errors=[f"Некорректный JSON: {exc}"])
        return CommandResult(
            action="stage_json",
            stage=current_stage,
            patch=InputPatch(stage=current_stage, payload=payload),
        )

    return CommandResult(
        action="invalid",
        errors=[
            "Не распознана команда. Используйте: start, next, show input, "
            "set <stage>.<field> <value>, json <stage> {..}, run."
        ],
    )
