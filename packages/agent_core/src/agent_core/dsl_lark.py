"""Lark-core для детерминированного разбора surface-форм команд DSL.

Модуль отвечает только за формальный разбор "формы" команды:
- edit/json/set с сохранением хвоста аргументов как текста;
- raw JSON shortcut;
- fallback в текстовую команду, если форма не распознана.

Семантика stage/field и валидация payload остаются в существующих
manifest-driven/default парсерах, чтобы сохранить обратную совместимость.
"""

from __future__ import annotations

from dataclasses import dataclass

from lark import Lark, Token, Tree, UnexpectedInput

_GRAMMAR = r"""
start: edit_command
     | json_command
     | set_command
     | raw_json_command
     | text_command

edit_command: EDIT WS TAIL
json_command: JSON WS TAIL
set_command: SET WS TAIL
raw_json_command: JSON_OBJECT
text_command: TAIL

EDIT.20: /(?i:edit)\b/
JSON.20: /(?i:json)\b/
SET.20: /(?i:set)\b/
JSON_OBJECT.10: /\{[\s\S]*\}/
TAIL.1: /[\s\S]+/
WS: /[ \t]+/
"""

_PARSER = Lark(_GRAMMAR, start="start", parser="lalr", maybe_placeholders=False)


@dataclass(frozen=True)
class TextCommandNode:
    """Fallback-узел для строк, не попавших в формальные правила grammar-core."""

    raw_text: str


@dataclass(frozen=True)
class EditCommandNode:
    """AST-узел для `edit <stage>` с непреобразованным `stage` аргументом."""

    argument: str


@dataclass(frozen=True)
class JsonCommandNode:
    """AST-узел для `json <stage> { ... }` с непреобразованным хвостом."""

    argument: str


@dataclass(frozen=True)
class SetCommandNode:
    """AST-узел для `set <stage>.<field> <value>` с непреобразованным хвостом."""

    argument: str


@dataclass(frozen=True)
class RawJsonCommandNode:
    """AST-узел для raw JSON shortcut (`{ ... }`) без префикса команды."""

    payload_text: str


DSLCommandNode = (
    TextCommandNode | EditCommandNode | JsonCommandNode | SetCommandNode | RawJsonCommandNode
)


def _last_token_text(tree: Tree[Token]) -> str:
    """Возвращает текст последнего токена из узла grammar-tree."""
    token = tree.children[-1]
    if not isinstance(token, Token):  # pragma: no cover - defensive guard
        return str(token)
    return str(token)


def parse_command_surface(message: str) -> DSLCommandNode:
    """Парсит форму DSL-команды и возвращает минимальный AST-узел.

    Важно: функция не валидирует stage/field/JSON-семантику.
    Она только классифицирует тип surface-команды и сохраняет хвост аргументов.
    """
    text = message.strip()
    if not text:
        return TextCommandNode(raw_text=text)

    try:
        parsed = _PARSER.parse(text)
    except UnexpectedInput:
        return TextCommandNode(raw_text=text)

    node = parsed.children[0] if parsed.data == "start" else parsed
    if not isinstance(node, Tree):  # pragma: no cover - defensive guard
        return TextCommandNode(raw_text=text)

    if node.data == "edit_command":
        return EditCommandNode(argument=_last_token_text(node).strip())
    if node.data == "json_command":
        return JsonCommandNode(argument=_last_token_text(node).strip())
    if node.data == "set_command":
        return SetCommandNode(argument=_last_token_text(node).strip())
    if node.data == "raw_json_command":
        return RawJsonCommandNode(payload_text=_last_token_text(node).strip())
    return TextCommandNode(raw_text=text)
