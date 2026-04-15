"""Manifest-driven deterministic command parser for installable extensions."""

from __future__ import annotations

import json
import re
from typing import Any

from extension_api import ExtensionManifest

from agent_core.dsl_lark import (
    EditCommandNode,
    JsonCommandNode,
    RawJsonCommandNode,
    SetCommandNode,
    parse_command_surface,
)
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


def build_field_alias_map(manifest: ExtensionManifest, stage_id: str) -> dict[str, str]:
    """Builds a normalized alias -> canonical field path map for one stage."""
    return manifest.field_alias_map(stage_id)


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


def _set_nested(payload: dict[str, Any], path: str, value: Any) -> None:
    """Set one dotted path in a nested dictionary payload."""
    cursor = payload
    parts = [part for part in path.split(".") if part]
    if not parts:
        return
    for key in parts[:-1]:
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[parts[-1]] = value


def _flatten_payload(payload: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested stage payload into dotted field paths."""
    flattened: dict[str, Any] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten_payload(value, prefix=path))
        else:
            flattened[path] = value
    return flattened


def _canonical_field_path(
    *,
    manifest: ExtensionManifest,
    stage_id: str,
    raw_path: str,
) -> str:
    """Return canonical field path for one stage-local path or alias."""
    normalized = raw_path.strip().lower()
    canonical_paths = manifest.canonical_field_paths(stage_id)
    if normalized in canonical_paths:
        return canonical_paths[normalized]
    return build_field_alias_map(manifest, stage_id).get(normalized, raw_path.strip())


def _canonicalize_stage_payload(
    *,
    manifest: ExtensionManifest,
    stage_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Rewrite alias keys in one stage JSON payload to canonical field paths."""
    flattened = _flatten_payload(payload)
    canonicalized_flat: dict[str, Any] = {}
    for raw_path, value in flattened.items():
        canonical_path = _canonical_field_path(
            manifest=manifest,
            stage_id=stage_id,
            raw_path=raw_path,
        )
        if canonical_path in canonicalized_flat and canonicalized_flat[canonical_path] != value:
            raise ValueError(
                f"Конфликт alias-ключей для поля `{stage_id}.{canonical_path}`: "
                "получены разные значения."
            )
        canonicalized_flat[canonical_path] = value

    normalized_payload: dict[str, Any] = {}
    for canonical_path, value in canonicalized_flat.items():
        _set_nested(normalized_payload, canonical_path, value)
    return normalized_payload


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

    parsed_surface = parse_command_surface(text)
    if isinstance(parsed_surface, EditCommandNode):
        maybe_stage = _resolve_stage(parsed_surface.argument, alias_map)
        if maybe_stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для edit"])
        return CommandResult(action="edit_stage", stage=maybe_stage)

    if isinstance(parsed_surface, JsonCommandNode):
        stage, _, payload_text = _resolve_json_stage_and_payload(
            parsed_surface.argument,
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
            payload = _canonicalize_stage_payload(
                manifest=manifest,
                stage_id=stage,
                payload=payload,
            )
        except ValueError as exc:
            return CommandResult(action="invalid", errors=[str(exc)])
        except json.JSONDecodeError as exc:
            return CommandResult(action="invalid", errors=[f"Некорректный JSON: {exc}"])
        return CommandResult(
            action="stage_json",
            stage=stage,
            patch=InputPatch(stage=stage, payload=payload),
        )

    if isinstance(parsed_surface, SetCommandNode):
        stage, path, value_text, unknown_stage = _resolve_set_stage_path_and_value(
            parsed_surface.argument,
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
        path = _canonical_field_path(manifest=manifest, stage_id=stage, raw_path=path)
        return CommandResult(
            action="set_field",
            stage=stage,
            patch=InputPatch(stage=stage, path=path, value=value),
        )

    if isinstance(parsed_surface, RawJsonCommandNode):
        if current_stage is None:
            return CommandResult(
                action="invalid",
                errors=["Уточните stage: используйте json <stage> { ... }"],
            )
        try:
            payload = json.loads(parsed_surface.payload_text)
            if not isinstance(payload, dict):
                return CommandResult(action="invalid", errors=["JSON stage должен быть объектом"])
            payload = _canonicalize_stage_payload(
                manifest=manifest,
                stage_id=current_stage,
                payload=payload,
            )
        except ValueError as exc:
            return CommandResult(action="invalid", errors=[str(exc)])
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
