"""Helpers for startup-time extension discovery in the current process."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import metadata
from importlib.metadata import EntryPoint
from typing import Iterable

from extension_api import (
    EXTENSION_ENTRY_POINT_GROUP,
    DiscoveredExtension,
    ExtensionDiscoveryError,
    ExtensionRegistry,
)

from agent_core.default_or_extension import DefaultORExtensionProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExtensionRegistryLoadReport:
    """Startup-time discovery result with one usable registry and quarantine warnings."""

    registry: ExtensionRegistry
    warnings: list[str] = field(default_factory=list)


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


def tolerant_discovery_report(
    *,
    group: str = EXTENSION_ENTRY_POINT_GROUP,
    entry_points: Iterable[EntryPoint] | None = None,
) -> ExtensionRegistryLoadReport:
    """Discovers external extensions one-by-one and quarantines broken providers."""
    external_extensions: list[DiscoveredExtension] = []
    warnings: list[str] = []
    alias_sources = {item.alias: item.source for item in _builtin_extensions()}
    resolved_entry_points = (
        tuple(metadata.entry_points(group=group)) if entry_points is None else tuple(entry_points)
    )

    for entry_point in resolved_entry_points:
        source = f"{entry_point.group}:{entry_point.name}"
        try:
            discovered_registry = ExtensionRegistry.discover(
                group=group,
                entry_points=[entry_point],
            )
        except ExtensionDiscoveryError as exc:
            message = f"Quarantined extension `{source}` during startup discovery: {exc}"
            logger.warning(message)
            warnings.append(message)
            continue

        discovered = discovered_registry.all()[0]
        if discovered.alias in alias_sources:
            message = (
                f"Quarantined extension `{source}` during startup discovery: duplicate alias "
                f"`{discovered.alias}` conflicts with {alias_sources[discovered.alias]}."
            )
            logger.warning(message)
            warnings.append(message)
            continue

        alias_sources[discovered.alias] = discovered.source
        external_extensions.append(discovered)

    return ExtensionRegistryLoadReport(
        registry=compose_extension_registry(ExtensionRegistry(external_extensions)),
        warnings=warnings,
    )


def load_extension_registry() -> ExtensionRegistry:
    """Discover installable extensions visible in the current Python environment."""
    return tolerant_discovery_report().registry
