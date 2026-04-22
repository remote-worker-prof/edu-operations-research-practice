"""Helpers for loading external Lark grammar files shipped with agent_core."""

from __future__ import annotations

from importlib.resources import files


def load_grammar_text(filename: str) -> str:
    """Return the text of one bundled .lark grammar file."""
    return files("agent_core.grammars").joinpath(filename).read_text(encoding="utf-8")
