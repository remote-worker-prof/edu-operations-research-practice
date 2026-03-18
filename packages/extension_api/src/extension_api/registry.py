"""Discovery and registry primitives for installable extension packages."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from importlib.metadata import EntryPoint
from typing import Iterable, Protocol, runtime_checkable

from .constants import EXTENSION_ENTRY_POINT_GROUP
from .models import ExtensionManifest, ExtensionResultSection


class ExtensionDiscoveryError(RuntimeError):
    """Base runtime error for extension discovery failures."""


class InvalidExtensionProviderError(ExtensionDiscoveryError):
    """Raised when an entry point does not expose a valid provider contract."""


class DuplicateExtensionAliasError(ExtensionDiscoveryError):
    """Raised when two discovered providers declare the same manifest alias."""


class ExtensionNotFoundError(KeyError):
    """Raised when the registry cannot resolve a requested extension alias."""


@runtime_checkable
class ExtensionRuntime(Protocol):
    """Runtime contract that student-authored extensions must implement."""

    manifest: ExtensionManifest

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        """Return validation errors grouped by stage ID."""

    def build_runtime_input(self, draft: dict[str, object]) -> object:
        """Build the deterministic runtime input from the generic draft."""

    def run(self, runtime_input: object) -> object:
        """Execute the extension-specific deterministic pipeline."""

    def fallback_explain(self, result: object) -> str:
        """Produce deterministic explanation text when no LLM is available."""

    def build_llm_explain_prompt(self, result: object) -> str:
        """Build the extension-specific prompt for an explanation model."""

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        """Return generic data-driven UI sections for the result view."""

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        """Return extension-specific hints for the current draft."""

    def build_nl_semantics(self) -> dict[str, object]:
        """Return extension-owned metadata for NL extraction/parsing."""


@runtime_checkable
class ExtensionProvider(Protocol):
    """Entry-point provider contract loaded from installable extension packages."""

    def get_manifest(self) -> ExtensionManifest:
        """Return the stable extension manifest."""

    def create_runtime(self) -> ExtensionRuntime:
        """Create a fresh runtime instance for one application process."""


@dataclass(frozen=True, slots=True)
class DiscoveredExtension:
    """One extension discovered from the Python environment."""

    alias: str
    manifest: ExtensionManifest
    provider: ExtensionProvider
    entry_point_name: str
    module: str
    source: str

    def create_runtime(self) -> ExtensionRuntime:
        """Construct a runtime from the underlying provider."""
        return self.provider.create_runtime()


def _looks_like_provider(candidate: object) -> bool:
    """Use duck typing so entry points may expose instance, class, or factory."""
    return callable(getattr(candidate, "get_manifest", None)) and callable(
        getattr(candidate, "create_runtime", None)
    )


def _coerce_provider(loaded: object, *, entry_point_name: str) -> ExtensionProvider:
    """Normalize entry-point targets into a concrete provider instance."""
    candidate = loaded
    if isinstance(candidate, type):
        candidate = candidate()
    elif callable(candidate) and not _looks_like_provider(candidate):
        candidate = candidate()

    if not _looks_like_provider(candidate):
        raise InvalidExtensionProviderError(
            f"entry point {entry_point_name!r} must expose an ExtensionProvider, "
            "a provider class, or a zero-argument provider factory"
        )
    return candidate  # type: ignore[return-value]


class ExtensionRegistry:
    """In-memory registry of discovered installable extensions."""

    def __init__(self, discovered: Iterable[DiscoveredExtension] | None = None) -> None:
        self._by_alias: dict[str, DiscoveredExtension] = {}
        for extension in discovered or ():
            if extension.alias in self._by_alias:
                existing = self._by_alias[extension.alias]
                raise DuplicateExtensionAliasError(
                    f"duplicate extension alias {extension.alias!r}: "
                    f"{existing.source} vs {extension.source}"
                )
            self._by_alias[extension.alias] = extension

    def __contains__(self, alias: object) -> bool:
        """Allow quick `alias in registry` checks."""
        return isinstance(alias, str) and alias in self._by_alias

    def __len__(self) -> int:
        """Return the number of discovered extensions."""
        return len(self._by_alias)

    def aliases(self) -> list[str]:
        """Return sorted public aliases for UI/API consumption."""
        return sorted(self._by_alias)

    def all(self) -> list[DiscoveredExtension]:
        """Return all discovered extensions in stable alias order."""
        return [self._by_alias[alias] for alias in self.aliases()]

    def get(self, alias: str) -> DiscoveredExtension | None:
        """Return a discovered extension or `None` if absent."""
        return self._by_alias.get(alias)

    def require(self, alias: str) -> DiscoveredExtension:
        """Return a discovered extension or raise a dedicated lookup error."""
        extension = self.get(alias)
        if extension is None:
            raise ExtensionNotFoundError(alias)
        return extension

    @classmethod
    def discover(
        cls,
        *,
        group: str = EXTENSION_ENTRY_POINT_GROUP,
        entry_points: Iterable[EntryPoint] | None = None,
    ) -> "ExtensionRegistry":
        """Discover providers from the current Python environment."""
        discovered: list[DiscoveredExtension] = []
        alias_sources: dict[str, str] = {}
        resolved_entry_points = (
            tuple(metadata.entry_points(group=group))
            if entry_points is None
            else tuple(entry_points)
        )

        for entry_point in resolved_entry_points:
            provider = _coerce_provider(entry_point.load(), entry_point_name=entry_point.name)
            manifest = provider.get_manifest()
            source = f"{entry_point.group}:{entry_point.name}"
            if manifest.alias in alias_sources:
                raise DuplicateExtensionAliasError(
                    f"duplicate extension alias {manifest.alias!r}: "
                    f"{alias_sources[manifest.alias]} vs {source}"
                )
            alias_sources[manifest.alias] = source
            discovered.append(
                DiscoveredExtension(
                    alias=manifest.alias,
                    manifest=manifest,
                    provider=provider,
                    entry_point_name=entry_point.name,
                    module=entry_point.module,
                    source=source,
                )
            )

        return cls(discovered)
