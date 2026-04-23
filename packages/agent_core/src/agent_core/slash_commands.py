"""Canonical slash-command parsing for the new semantics-driven chat shell."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    """Normalized slash command with canonical name and raw arguments."""

    name: str
    arg: str | None = None
    payload: str | None = None


def parse_slash_command(message: str) -> SlashCommand | None:
    """Parses one `/command ...` string into a normalized internal representation."""
    text = message.strip()
    if not text.startswith("/"):
        return None

    body = text[1:].strip()
    if not body:
        return SlashCommand(name="help")

    parts = body.split(maxsplit=1)
    name = parts[0].lower()
    remainder = parts[1].strip() if len(parts) > 1 else ""

    if name in {
        "new",
        "use",
        "next",
        "solve",
        "explain",
        "help",
        "reset",
        "validate",
        "run",
        "semantics",
        "mode",
    }:
        return SlashCommand(name=name, arg=remainder or None)

    if name == "show":
        return SlashCommand(name="show", arg=(remainder or "steps").lower())

    if name == "step":
        return SlashCommand(name="step", arg=remainder or None)

    if name == "payload":
        if not remainder:
            return SlashCommand(name="payload")
        stage_and_payload = remainder.split(maxsplit=1)
        stage = stage_and_payload[0]
        payload = stage_and_payload[1].strip() if len(stage_and_payload) > 1 else None
        return SlashCommand(name="payload", arg=stage, payload=payload)

    if name == "set":
        return SlashCommand(name="set", payload=remainder or None)

    return SlashCommand(name="invalid", payload=text)


def validate_payload_json(command: SlashCommand) -> str | None:
    """Returns a user-facing error when `/payload` carries malformed JSON."""
    if command.name != "payload":
        return None
    if not command.arg or not command.payload:
        return "Формат команды: /payload <stage> <json>."
    try:
        parsed = json.loads(command.payload)
    except json.JSONDecodeError as exc:
        return f"Некорректный JSON в /payload: {exc}"
    if not isinstance(parsed, dict):
        return "Команда /payload ожидает JSON-объект."
    return None
