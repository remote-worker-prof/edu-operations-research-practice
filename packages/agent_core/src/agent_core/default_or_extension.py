"""Built-in compatibility extension provider for the legacy OR workflow."""

from __future__ import annotations

from typing import Any

from extension_api import (
    ExtensionArtifactSemantics,
    ExtensionBundleSemantics,
    ExtensionFieldSemantics,
    ExtensionManifest,
    ExtensionResultSection,
    ExtensionStageSemantics,
    FieldSpec,
    KVBlock,
    KVItem,
    StageSpec,
    SummaryBlock,
    TableBlock,
)
from or_core.models import ORResult, ScenarioDraft
from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioAssembler, ScenarioPresetLoader

from agent_core.config import default_scenario_path
from agent_core.default_or_contract import DEFAULT_OR_STAGE_ORDER

DEFAULT_OR_EXTENSION_ALIAS = "default_or"

_STAGE_EXAMPLES = {
    "production": (
        'json production {"products":["A","B"],"profits":[40,30],'
        '"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],'
        '"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}'
    ),
    "shipment": (
        'json shipment {"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],'
        '"clients":["C1","C2","C3"],"client_demand":[42,38,40],'
        '"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}'
    ),
    "assignment": (
        'json assignment {"resources":["truck_1","truck_2","truck_3"],'
        '"cost_matrix":[[8,6,7],[5,8,6],[7,5,9]]}'
    ),
    "routing": (
        'json routing {"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],'
        '"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}'
    ),
}

_DEFAULT_OR_FIELD_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "production": {
        "products": ("products", "продукты"),
        "profits": ("profits", "прибыль"),
        "resource_matrix": ("resource_matrix", "матрица ресурсов"),
        "resource_limits": ("resource_limits", "лимиты ресурсов"),
        "demand_upper_bounds": ("demand_upper_bounds", "верхние границы спроса", "спрос"),
        "pallet_factors": ("pallet_factors", "коэффициенты паллет"),
    },
    "shipment": {
        "warehouses": ("warehouses", "склады"),
        "warehouse_supply_ratio": ("warehouse_supply_ratio", "доли складов"),
        "clients": ("clients", "клиенты"),
        "client_demand": ("client_demand", "спрос клиентов"),
        "cost_matrix": ("cost_matrix", "матрица стоимости"),
        "capacity_matrix": ("capacity_matrix", "матрица пропускной способности", "capacity"),
    },
    "assignment": {
        "resources": ("resources", "ресурсы", "машины"),
        "cost_matrix": ("cost_matrix", "матрица назначения", "стоимость назначения"),
    },
    "routing": {
        "distance_matrix": ("distance_matrix", "матрица расстояний"),
        "depot_index": ("depot_index", "депо", "depot"),
        "client_nodes": ("client_nodes", "узлы клиентов"),
        "vehicle_capacities": ("vehicle_capacities", "емкости", "ёмкости", "capacities"),
        "objective": ("objective", "цель", "objective"),
    },
}

_DEFAULT_OR_STAGE_HINTS: dict[str, str] = {
    "production": "Введите продукты, прибыль, ресурсную матрицу и лимиты производства.",
    "shipment": "Введите склады, клиентов, спрос и матрицы стоимости/пропускной способности.",
    "assignment": "Введите ресурсы и матрицу стоимости назначения.",
    "routing": "Введите матрицу расстояний, depot, клиентов и ёмкости транспорта.",
}

_DEFAULT_OR_MANIFEST = ExtensionManifest(
    alias=DEFAULT_OR_EXTENSION_ALIAS,
    title="Default OR Pipeline",
    description=(
        "Встроенный учебный OR-конвейер из четырёх этапов: production -> shipment -> "
        "assignment -> routing."
    ),
    version="0.1.0",
    default_preset="demo",
    stage_graph=[
        StageSpec(
            stage_id="production",
            label="Production",
            aliases=["prod", "производство"],
            examples=[_STAGE_EXAMPLES["production"]],
            field_specs=[
                FieldSpec(field_path="products", label="Products"),
                FieldSpec(field_path="profits", label="Profits"),
                FieldSpec(field_path="resource_matrix", label="Resource matrix"),
                FieldSpec(field_path="resource_limits", label="Resource limits"),
                FieldSpec(field_path="demand_upper_bounds", label="Demand upper bounds"),
                FieldSpec(field_path="pallet_factors", label="Pallet factors"),
            ],
        ),
        StageSpec(
            stage_id="shipment",
            label="Shipment",
            aliases=["ship", "отгрузка"],
            examples=[_STAGE_EXAMPLES["shipment"]],
            field_specs=[
                FieldSpec(field_path="warehouses", label="Warehouses"),
                FieldSpec(field_path="warehouse_supply_ratio", label="Supply ratio"),
                FieldSpec(field_path="clients", label="Clients"),
                FieldSpec(field_path="client_demand", label="Client demand"),
                FieldSpec(field_path="cost_matrix", label="Cost matrix"),
                FieldSpec(field_path="capacity_matrix", label="Capacity matrix"),
            ],
        ),
        StageSpec(
            stage_id="assignment",
            label="Assignment",
            aliases=["assign", "назначение"],
            examples=[_STAGE_EXAMPLES["assignment"]],
            field_specs=[
                FieldSpec(field_path="resources", label="Resources"),
                FieldSpec(field_path="cost_matrix", label="Cost matrix"),
            ],
        ),
        StageSpec(
            stage_id="routing",
            label="Routing",
            aliases=["route", "маршрутизация"],
            examples=[_STAGE_EXAMPLES["routing"]],
            field_specs=[
                FieldSpec(field_path="distance_matrix", label="Distance matrix"),
                FieldSpec(field_path="depot_index", label="Depot index"),
                FieldSpec(field_path="client_nodes", label="Client nodes"),
                FieldSpec(field_path="vehicle_capacities", label="Vehicle capacities"),
            ],
        ),
    ],
    stage_aliases={
        "production": ["prod", "производство"],
        "shipment": ["ship", "отгрузка"],
        "assignment": ["assign", "назначение"],
        "routing": ["route", "маршрутизация"],
    },
    examples=[
        "load preset demo",
        _STAGE_EXAMPLES["production"],
        _STAGE_EXAMPLES["shipment"],
        _STAGE_EXAMPLES["assignment"],
        _STAGE_EXAMPLES["routing"],
        "run",
    ],
    labels={"kind": "default_or"},
    ui_metadata={"kind": "default_or", "legacy_or_pipeline": True},
)


class DefaultORCompatibilityRuntime:
    """Compatibility runtime that adapts the legacy OR pipeline to the extension SDK."""

    manifest = _DEFAULT_OR_MANIFEST

    def __init__(self) -> None:
        self._scenario_assembler = ScenarioAssembler()
        self._or_pipeline = ORPipeline()

    def _draft_model(self, draft: dict[str, object]) -> ScenarioDraft:
        preset_ref = draft.get("preset_ref") if isinstance(draft.get("preset_ref"), str) else None
        return ScenarioDraft(
            production=dict(draft.get("production", {}) or {}),
            shipment=dict(draft.get("shipment", {}) or {}),
            assignment=dict(draft.get("assignment", {}) or {}),
            routing=dict(draft.get("routing", {}) or {}),
            preset_ref=preset_ref,
        )

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        """Delegates validation to the existing `ScenarioAssembler`."""
        return self._scenario_assembler.stage_errors(self._draft_model(draft))

    def build_runtime_input(self, draft: dict[str, object]) -> object:
        """Builds the full OR runtime input from the generic draft."""
        return self._scenario_assembler.assemble(self._draft_model(draft))

    def run(self, runtime_input: object) -> ORResult:
        """Runs the deterministic OR pipeline."""
        return self._or_pipeline.run(runtime_input)

    def fallback_explain(self, result: object) -> str:
        """Returns a deterministic explanation fallback."""
        if isinstance(result, ORResult):
            return (
                "Результат рассчитан детерминированным OR-пайплайном. "
                f"Execution trace: {' -> '.join(result.execution_trace)}."
            )
        return "Результат рассчитан детерминированным OR-пайплайном."

    def build_llm_explain_prompt(self, result: object) -> str:
        """Builds a generic explanation prompt for the OR result."""
        return f"Explain the educational OR pipeline result for a student:\n{result!r}"

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        """Builds generic sections mirroring the classic OR cards."""
        if not isinstance(result, ORResult):  # pragma: no cover - defensive contract guard
            return []
        return [
            ExtensionResultSection(
                section_id="production",
                title="Production",
                blocks=[
                    KVBlock(
                        items=[
                            KVItem(key="Objective", value=result.production.objective_value),
                            KVItem(key="Total pallets", value=result.production.total_pallets),
                        ]
                    )
                ],
            ),
            ExtensionResultSection(
                section_id="shipment",
                title="Shipment",
                blocks=[
                    KVBlock(
                        items=[
                            KVItem(key="Dispatched", value=result.shipment.total_dispatched),
                            KVItem(key="Cost", value=result.shipment.total_cost),
                        ]
                    )
                ],
            ),
            ExtensionResultSection(
                section_id="assignment",
                title="Assignment",
                blocks=[
                    TableBlock(
                        columns=["Resource", "Client", "Volume", "Cost"],
                        rows=[
                            [pair.resource, pair.client, pair.assigned_volume, pair.cost]
                            for pair in result.assignment.pairs
                        ],
                    )
                ],
            ),
            ExtensionResultSection(
                section_id="routing",
                title="Routing",
                blocks=[
                    SummaryBlock(
                        text=(
                            f"Total distance: {result.routing.total_distance}. "
                            f"Max route distance: {result.routing.max_route_distance}."
                        )
                    )
                ],
            ),
        ]

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        """Returns no-op hints because the legacy dialog graph still owns OR teaching hints."""
        del draft
        return []

    def build_nl_semantics(self) -> dict[str, object]:
        """Returns typed semantics so the new chat can treat `default_or` generically."""
        return _build_default_or_semantics().model_dump(mode="json")


class DefaultORExtensionProvider:
    """Built-in provider that exposes the legacy OR flow as a first-class extension."""

    def get_manifest(self) -> ExtensionManifest:
        return _DEFAULT_OR_MANIFEST

    def create_runtime(self) -> DefaultORCompatibilityRuntime:
        return DefaultORCompatibilityRuntime()

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, Any]]:
        """Loads the built-in demo preset as a generic stage draft."""
        if preset_ref != "demo":
            raise ValueError(f"Unsupported default_or preset: {preset_ref}")

        draft = ScenarioPresetLoader(default_scenario_path()).load_demo_draft()
        return {
            "production": dict(draft.production),
            "shipment": dict(draft.shipment),
            "assignment": dict(draft.assignment),
            "routing": dict(draft.routing),
        }


def default_or_extension_draft_from_scenario_draft(
    draft: ScenarioDraft,
) -> dict[str, dict[str, Any]]:
    """Builds a generic extension draft mirror from the legacy ScenarioDraft."""
    mirrored: dict[str, dict[str, Any]] = {}
    for stage_id in DEFAULT_OR_STAGE_ORDER:
        payload = getattr(draft, stage_id)
        if payload:
            mirrored[stage_id] = dict(payload)
    return mirrored


def default_or_scenario_draft_from_extension_draft(
    draft: dict[str, object],
) -> ScenarioDraft:
    """Build a legacy `ScenarioDraft` mirror from the generic extension draft."""
    return ScenarioDraft(
        production=dict(draft.get("production", {}) or {}),
        shipment=dict(draft.get("shipment", {}) or {}),
        assignment=dict(draft.get("assignment", {}) or {}),
        routing=dict(draft.get("routing", {}) or {}),
        preset_ref=draft.get("preset_ref") if isinstance(draft.get("preset_ref"), str) else None,
    )


def _default_or_model_artifact() -> str:
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


def _build_default_or_semantics() -> ExtensionBundleSemantics:
    """Build typed parser/NL/explain semantics for the legacy default OR bundle."""
    stages: list[ExtensionStageSemantics] = []
    for stage in _DEFAULT_OR_MANIFEST.stage_graph:
        fields: list[ExtensionFieldSemantics] = []
        field_aliases = _DEFAULT_OR_FIELD_ALIASES.get(stage.stage_id, {})
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
                + list(_DEFAULT_OR_MANIFEST.stage_aliases.get(stage.stage_id, [])),
                examples=list(stage.examples),
                expectation_hint=_DEFAULT_OR_STAGE_HINTS.get(stage.stage_id),
                fields=fields,
            )
        )

    manifest_json = _DEFAULT_OR_MANIFEST.model_dump_json(indent=2)
    return ExtensionBundleSemantics(
        mode="runtime_bundle",
        alias=DEFAULT_OR_EXTENSION_ALIAS,
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
                content=_default_or_model_artifact(),
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
