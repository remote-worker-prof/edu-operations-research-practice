"""Focused adapters that isolate legacy `default_or` compatibility concerns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping

from extension_api import (
    ExtensionArtifactSemantics,
    ExtensionBundleSemantics,
    ExtensionFieldSemantics,
    ExtensionManifest,
    ExtensionRuntime,
    ExtensionStageSemantics,
)
from or_core.models import ScenarioDraft

from agent_core.default_or_contract import DEFAULT_OR_STAGE_ORDER

if TYPE_CHECKING:
    from agent_core.models import AgentSession, StageStatusSnapshot


@dataclass(frozen=True)
class DefaultOrSemanticsAdapter:
    """Builds typed semantics and explain artifacts for the legacy OR pipeline."""

    alias: str
    manifest: ExtensionManifest
    field_aliases: dict[str, dict[str, tuple[str, ...]]]
    stage_hints: dict[str, str]

    def build_model_artifact(self) -> str:
        """Return a grounded read-only description of the legacy four-stage OR pipeline."""
        return "\n".join(
            [
                "# default_or",
                "",
                "Это встроенный четырёхэтапный OR-конвейер:",
                "1. production — план выпуска продукции через LP.",
                "2. shipment — план отгрузки через min-cost flow.",
                "3. assignment — назначение ресурсов на клиентские задачи.",
                "4. routing — маршрутизация транспорта.",
                "",
                "Каждый этап принимает JSON-пейлоад по своему stage_id и использует результат",
                "предыдущих этапов как часть runtime-входа.",
            ]
        )

    def build_bundle_semantics(self) -> ExtensionBundleSemantics:
        """Build typed parser/NL/explain semantics for the legacy default OR bundle."""
        stages: list[ExtensionStageSemantics] = []
        for stage in self.manifest.stage_graph:
            fields: list[ExtensionFieldSemantics] = []
            field_aliases = self.field_aliases.get(stage.stage_id, {})
            for field in stage.field_specs:
                fields.append(
                    ExtensionFieldSemantics(
                        stage_id=stage.stage_id,
                        field_path=field.field_path,
                        label=field.label,
                        aliases=list(field_aliases.get(field.field_path, field.aliases)),
                        value_type="json",
                        help=field.description,
                        example=field.examples[0] if field.examples else None,
                    )
                )
            stages.append(
                ExtensionStageSemantics(
                    stage_id=stage.stage_id,
                    label=stage.label,
                    aliases=list(stage.aliases)
                    + list(self.manifest.stage_aliases.get(stage.stage_id, [])),
                    examples=list(stage.examples),
                    expectation_hint=self.stage_hints.get(stage.stage_id),
                    fields=fields,
                )
            )

        manifest_json = self.manifest.model_dump_json(indent=2)
        return ExtensionBundleSemantics(
            mode="runtime_bundle",
            alias=self.alias,
            dsl_format="default_or_legacy",
            stage_ids=list(DEFAULT_OR_STAGE_ORDER),
            inputs=[],
            stages=stages,
            artifacts=[
                ExtensionArtifactSemantics(
                    id="model",
                    kind="model",
                    label="Каноническая схема default_or",
                    language="markdown",
                    content=self.build_model_artifact(),
                    summary="Описание встроенного четырёхэтапного OR-конвейера.",
                ),
                ExtensionArtifactSemantics(
                    id="extension",
                    kind="extension",
                    label="Manifest default_or",
                    language="json",
                    content=manifest_json,
                    summary="Текущий manifest встроенного extension `default_or`.",
                ),
            ],
        )


@dataclass(frozen=True)
class DefaultOrStateSyncAdapter:
    """Bridges generic extension mirrors and the legacy `ScenarioDraft` state."""

    @staticmethod
    def to_extension_draft(draft: ScenarioDraft) -> dict[str, dict[str, Any]]:
        """Build a generic extension draft mirror from the legacy `ScenarioDraft`."""
        mirrored: dict[str, dict[str, Any]] = {}
        for stage_id in DEFAULT_OR_STAGE_ORDER:
            payload = getattr(draft, stage_id)
            if payload:
                mirrored[stage_id] = dict(payload)
        return mirrored

    @staticmethod
    def to_scenario_draft(draft: Mapping[str, object]) -> ScenarioDraft:
        """Build a legacy `ScenarioDraft` mirror from the generic extension draft."""
        return ScenarioDraft(
            production=dict(draft.get("production", {}) or {}),
            shipment=dict(draft.get("shipment", {}) or {}),
            assignment=dict(draft.get("assignment", {}) or {}),
            routing=dict(draft.get("routing", {}) or {}),
            preset_ref=(
                draft.get("preset_ref")
                if isinstance(draft.get("preset_ref"), str)
                else None
            ),
        )

    @classmethod
    def sync_legacy_from_generic(cls, session: AgentSession) -> None:
        """Synchronize legacy draft/result slots after generic mutations."""
        session.scenario_draft = cls.to_scenario_draft(session.extension_draft)
        if session.extension_result is None:
            session.or_result = None

    @classmethod
    def sync_generic_from_legacy(
        cls,
        *,
        session: AgentSession,
        manifest: ExtensionManifest,
        runtime: ExtensionRuntime,
        serialize_result: Callable[[Any], tuple[Any, str | None]],
        build_stage_statuses: Callable[..., list[StageStatusSnapshot]],
    ) -> None:
        """Synchronize generic mirrors after the legacy OR path updates its own state."""
        session.extension_draft = cls.to_extension_draft(session.scenario_draft)

        if session.or_result is None:
            session.extension_result = None
            session.extension_result_sections = []
        else:
            serialized_result, serialization_warning = serialize_result(session.or_result)
            session.extension_result = serialized_result
            session.extension_result_sections = runtime.build_result_sections(session.or_result)
            if serialization_warning and serialization_warning not in session.warnings:
                session.warnings.append(serialization_warning)

        stage_ids = manifest.topological_stage_ids()
        raw_errors = runtime.validate_draft(session.extension_draft)
        normalized_errors = {stage_id: list(raw_errors.get(stage_id, [])) for stage_id in stage_ids}
        session.validation_errors_by_stage = normalized_errors
        session.missing_fields = [stage_id for stage_id in stage_ids if normalized_errors[stage_id]]
        session.collection_state.ready_to_run = not session.missing_fields

        current_stage = session.collection_state.current_stage
        if (
            current_stage is None
            or current_stage not in stage_ids
            or current_stage not in session.missing_fields
        ):
            session.collection_state.current_stage = next(
                (stage_id for stage_id in stage_ids if stage_id in session.missing_fields),
                None,
            )

        session.extension_stage_statuses = build_stage_statuses(
            manifest=manifest,
            session=session,
        )
