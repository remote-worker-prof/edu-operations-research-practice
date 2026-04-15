"""Детерминированный парсер команд чата для интерактивного сбора OR-входов."""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.default_or_contract import DefaultORStageName
from agent_core.dsl_lark import (
    EditCommandNode,
    JsonCommandNode,
    RawJsonCommandNode,
    SetCommandNode,
    parse_command_surface,
)
from agent_core.models import CommandResult, InputPatch

_STAGE_ALIASES: dict[str, DefaultORStageName] = {
    "production": "production",
    "prod": "production",
    "производство": "production",
    "shipment": "shipment",
    "ship": "shipment",
    "отгрузка": "shipment",
    "assignment": "assignment",
    "assign": "assignment",
    "назначение": "assignment",
    "routing": "routing",
    "route": "routing",
    "маршрутизация": "routing",
}


def _resolve_stage(raw: str) -> DefaultORStageName | None:
    """Резолвит алиас stage (ru/en) в каноническое имя stage."""
    return _STAGE_ALIASES.get(raw.strip().lower())


def _parse_scalar(value_text: str) -> Any:
    """Пытается распарсить значение как JSON scalar/array/object, иначе строка."""
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


def parse_user_command(
    *,
    message: str,
    current_stage: DefaultORStageName | None,
) -> CommandResult:
    """Преобразует реплику пользователя в структурированную команду.

    Парсер намеренно детерминированный: для критичных входных параметров OR
    нельзя полагаться только на LLM-интерпретацию текста.
    """
    text = message.strip()
    if not text:
        return CommandResult(action="invalid", errors=["Пустая команда"])

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
    if lower in {"load preset demo", "preset demo", "load demo", "загрузить демо"}:
        return CommandResult(action="load_preset", preset_ref="demo")

    parsed_surface = parse_command_surface(text)
    if isinstance(parsed_surface, EditCommandNode):
        maybe_stage = _resolve_stage(parsed_surface.argument)
        if maybe_stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для edit"])
        return CommandResult(action="edit_stage", stage=maybe_stage)

    if isinstance(parsed_surface, JsonCommandNode):
        parts = parsed_surface.argument.split(" ", maxsplit=1)
        if len(parts) < 2:
            return CommandResult(
                action="invalid",
                errors=["Формат: json <stage> { ... }"],
            )
        stage = _resolve_stage(parts[0])
        if stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для json"])
        try:
            payload = json.loads(parts[1])
            if not isinstance(payload, dict):
                return CommandResult(action="invalid", errors=["JSON stage должен быть объектом"])
        except json.JSONDecodeError as exc:
            return CommandResult(action="invalid", errors=[f"Некорректный JSON: {exc}"])
        return CommandResult(
            action="stage_json",
            stage=stage,
            patch=InputPatch(stage=stage, payload=payload),
        )

    if isinstance(parsed_surface, SetCommandNode):
        # Формат: set <stage>.<path> <value>
        parts = parsed_surface.argument.split(" ", maxsplit=1)
        if len(parts) < 2 or "." not in parts[0]:
            return CommandResult(
                action="invalid",
                errors=["Формат: set <stage>.<field_path> <value>"],
            )
        target = parts[0]
        value = _parse_scalar(parts[1])
        stage_raw, path = target.split(".", maxsplit=1)
        stage = _resolve_stage(stage_raw)
        if stage is None:
            return CommandResult(action="invalid", errors=["Неизвестный stage для set"])
        return CommandResult(
            action="set_field",
            stage=stage,
            patch=InputPatch(stage=stage, path=path, value=value),
        )

    # Shortcut: если пользователь отправил JSON-объект без команды, применяем
    # его к текущему stage wizard-режима.
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
            "set <stage>.<field> <value>, json <stage> {..}, load preset demo, run."
        ],
    )
