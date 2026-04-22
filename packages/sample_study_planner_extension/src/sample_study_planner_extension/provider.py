"""Compatibility adapter for the declarative study_planner bundle."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_core.declarative_extensions import load_declarative_provider
from extension_api import ExtensionManifest


@lru_cache(maxsize=1)
def _provider():
    bundle_root = Path(__file__).resolve().parents[4] / "extensions" / "study_planner"
    return load_declarative_provider(bundle_root)


class StudyPlannerExtensionProvider:
    """Legacy import path that now delegates to the declarative bundle runtime."""

    def get_manifest(self) -> ExtensionManifest:
        return _provider().get_manifest()

    def create_runtime(self):
        return _provider().create_runtime()

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, Any]]:
        return _provider().load_preset(preset_ref)
