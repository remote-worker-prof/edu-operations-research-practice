"""Public SDK for installable educational agent extensions."""

from .constants import EXTENSION_ENTRY_POINT_GROUP
from .models import (
    ExtensionManifest,
    ExtensionResultBlock,
    ExtensionResultSection,
    FieldSpec,
    JsonBlock,
    KVBlock,
    KVItem,
    ListBlock,
    StageSpec,
    SummaryBlock,
    TableBlock,
)
from .registry import (
    DiscoveredExtension,
    DuplicateExtensionAliasError,
    ExtensionDiscoveryError,
    ExtensionNotFoundError,
    ExtensionProvider,
    ExtensionRegistry,
    ExtensionRuntime,
    InvalidExtensionProviderError,
)

__all__ = [
    "DiscoveredExtension",
    "DuplicateExtensionAliasError",
    "EXTENSION_ENTRY_POINT_GROUP",
    "ExtensionDiscoveryError",
    "ExtensionManifest",
    "ExtensionNotFoundError",
    "ExtensionProvider",
    "ExtensionRegistry",
    "ExtensionResultBlock",
    "ExtensionResultSection",
    "ExtensionRuntime",
    "FieldSpec",
    "InvalidExtensionProviderError",
    "JsonBlock",
    "KVBlock",
    "KVItem",
    "ListBlock",
    "StageSpec",
    "SummaryBlock",
    "TableBlock",
]
