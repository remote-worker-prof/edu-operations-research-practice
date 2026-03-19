"""Shared contract fragments for the legacy default OR workflow."""

from __future__ import annotations

from typing import Literal, TypeAlias

DefaultORStageName: TypeAlias = Literal[
    "production",
    "shipment",
    "assignment",
    "routing",
]

DEFAULT_OR_STAGE_ORDER: list[DefaultORStageName] = [
    "production",
    "shipment",
    "assignment",
    "routing",
]
