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
        parts = text.split(" ", maxsplit=2)
        if len(parts) < 3:
            return CommandResult(action="invalid", errors=["Формат: json <stage> { ... }"])
        stage = _resolve_stage(parts[1], alias_map)
        if stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для json"])
        try:
            payload = json.loads(parts[2])
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
        parts = text.split(" ", maxsplit=2)
        if len(parts) < 3 or "." not in parts[1]:
            return CommandResult(
                action="invalid",
                errors=["Формат: set <stage>.<field_path> <value>"],
            )
        target = parts[1]
        value = _parse_scalar(parts[2])
        stage_raw, path = target.split(".", maxsplit=1)
        stage = _resolve_stage(stage_raw, alias_map)
        if stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для set"])
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
