"""Helpers for startup-time extension discovery in the current process."""

from __future__ import annotations

from extension_api import DiscoveredExtension, ExtensionRegistry

from agent_core.default_or_extension import DefaultORExtensionProvider


def _builtin_extensions() -> list[DiscoveredExtension]:
    """Returns built-in compatibility providers that always exist inside the app."""
    provider = DefaultORExtensionProvider()
    manifest = provider.get_manifest()
    return [
        DiscoveredExtension(
            alias=manifest.alias,
            manifest=manifest,
            provider=provider,
            entry_point_name=manifest.alias,
            module=provider.__class__.__module__,
            source=f"builtin:{manifest.alias}",
        )
    ]


def compose_extension_registry(
    discovered: ExtensionRegistry | None = None,
) -> ExtensionRegistry:
    """Merges built-in providers with an optional externally supplied registry."""
    external = discovered or ExtensionRegistry()
    return ExtensionRegistry([*_builtin_extensions(), *external.all()])


def load_extension_registry() -> ExtensionRegistry:
    """Discover installable extensions visible in the current Python environment."""
    discovered = ExtensionRegistry.discover()
    return compose_extension_registry(discovered)
