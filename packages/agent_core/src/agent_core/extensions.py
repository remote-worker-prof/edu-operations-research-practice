"""Helpers for startup-time extension discovery in the current process."""

from __future__ import annotations

from extension_api import ExtensionRegistry


def load_extension_registry() -> ExtensionRegistry:
    """Discover installable extensions visible in the current Python environment."""
    return ExtensionRegistry.discover()
