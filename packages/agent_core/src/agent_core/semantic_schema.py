"""Shared schema-driven helpers for slash parsing, NL extraction, and explain mode."""

from __future__ import annotations

from collections import defaultdict

from extension_api import (
    ExtensionArtifactSemantics,
    ExtensionBundleSemantics,
    ExtensionFieldSemantics,
    ExtensionManifest,
    ExtensionRuntime,
    ExtensionStageSemantics,
)


def runtime_bundle_semantics(runtime: ExtensionRuntime) -> ExtensionBundleSemantics | None:
    """Load typed runtime semantics defensively from an extension runtime."""
    try:
        raw = runtime.build_nl_semantics()
    except Exception:  # pragma: no cover - defensive adapter seam
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ExtensionBundleSemantics.model_validate(raw)
    except Exception:
        return None


def stage_catalog(
    *,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> list[ExtensionStageSemantics]:
    """Return the canonical stage catalog for parser/NL/explain use."""
    if semantics is not None and semantics.stages:
        return list(semantics.stages)

    field_alias_by_stage: dict[str, dict[str, list[str]]] = defaultdict(dict)
    if semantics is not None:
        for stage in semantics.stages:
            for field in stage.fields:
                field_alias_by_stage[stage.stage_id][field.field_path] = list(field.aliases)

    catalog: list[ExtensionStageSemantics] = []
    for stage in manifest.stage_graph:
        fields: list[ExtensionFieldSemantics] = []
        stage_field_aliases = field_alias_by_stage.get(stage.stage_id, {})
        for field in stage.field_specs:
            fields.append(
                ExtensionFieldSemantics(
                    stage_id=stage.stage_id,
                    field_path=field.field_path,
                    label=field.label,
                    aliases=stage_field_aliases.get(field.field_path, list(field.aliases)),
                    value_type=field.value_type or "json",
                    help=field.description,
                    example=field.examples[0] if field.examples else None,
                )
            )
        catalog.append(
            ExtensionStageSemantics(
                stage_id=stage.stage_id,
                label=stage.label,
                aliases=list(stage.aliases) + list(manifest.stage_aliases.get(stage.stage_id, [])),
                examples=list(stage.examples),
                fields=fields,
            )
        )
    return catalog


def stage_map(
    *,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> dict[str, ExtensionStageSemantics]:
    """Return a canonical stage lookup by stage id."""
    return {
        stage.stage_id: stage
        for stage in stage_catalog(manifest=manifest, semantics=semantics)
    }


def stage_alias_map(
    *,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> dict[str, str]:
    """Build case-insensitive alias -> stage_id mapping from the canonical catalog."""
    mapping: dict[str, str] = {}
    for stage in stage_catalog(manifest=manifest, semantics=semantics):
        mapping[stage.stage_id.lower()] = stage.stage_id
        mapping[stage.label.strip().lower()] = stage.stage_id
        for alias in stage.aliases:
            mapping[alias.strip().lower()] = stage.stage_id
    return mapping


def field_catalog(
    *,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
    stage_id: str,
) -> list[ExtensionFieldSemantics]:
    """Return the canonical field catalog for one stage."""
    fallback_stage = ExtensionStageSemantics(stage_id=stage_id, label=stage_id)
    return stage_map(manifest=manifest, semantics=semantics).get(stage_id, fallback_stage).fields


def field_alias_map(
    *,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
    stage_id: str,
) -> dict[str, str]:
    """Build case-insensitive field alias -> canonical field path mapping."""
    mapping: dict[str, str] = {}
    for field in field_catalog(manifest=manifest, semantics=semantics, stage_id=stage_id):
        mapping[field.field_path.strip().lower()] = field.field_path
        mapping[field.label.strip().lower()] = field.field_path
        for alias in field.aliases:
            mapping[alias.strip().lower()] = field.field_path
    try:
        manifest_aliases = manifest.field_alias_map(stage_id)
    except Exception:
        manifest_aliases = {}
    for alias, field_path in manifest_aliases.items():
        mapping[alias.strip().lower()] = field_path
    return mapping


def resolve_stage_id(
    *,
    raw: str,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> str | None:
    """Resolve a user-facing stage reference into a canonical stage id."""
    return stage_alias_map(manifest=manifest, semantics=semantics).get(raw.strip().lower())


def resolve_field_path(
    *,
    raw: str,
    stage_id: str,
    manifest: ExtensionManifest,
    semantics: ExtensionBundleSemantics | None,
) -> str | None:
    """Resolve a user-facing field reference into a canonical field path."""
    return field_alias_map(
        manifest=manifest,
        semantics=semantics,
        stage_id=stage_id,
    ).get(raw.strip().lower())


def artifact_catalog(
    semantics: ExtensionBundleSemantics | None,
) -> list[ExtensionArtifactSemantics]:
    """Return the extension artifact catalog for explain/read-only UI."""
    if semantics is None:
        return []
    return list(semantics.artifacts)


def resolve_artifact(
    *,
    semantics: ExtensionBundleSemantics | None,
    target: str,
) -> ExtensionArtifactSemantics | None:
    """Resolve one explain target such as `model` or `extension` to an artifact."""
    normalized = target.strip().lower()
    for artifact in artifact_catalog(semantics):
        if artifact.id.lower() == normalized or artifact.kind.lower() == normalized:
            return artifact
    return None
