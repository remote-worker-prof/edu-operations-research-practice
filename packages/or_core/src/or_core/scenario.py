"""Сборка runtime-входа OR-пайплайна из интерактивного draft.

Модуль поддерживает два режима:
- основной: сборка `ORPipelineInput` из пользовательского `ScenarioDraft`;
- вспомогательный: загрузка demo preset из JSON (`base_scenario.json`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from or_core.exceptions import ScenarioValidationError
from or_core.models import (
    AssignmentTemplateInput,
    ORPipelineInput,
    ProductionInput,
    RoutingTemplateInput,
    ScenarioDraft,
    ScenarioSeed,
    ShipmentTemplateInput,
)

_STAGES = ("production", "shipment", "assignment", "routing")


class ScenarioAssembler:
    """Собирает финальный `ORPipelineInput` из интерактивного `ScenarioDraft`.

    Что делает:
    - валидирует каждый stage draft независимыми моделями;
    - проверяет кросс-этапную согласованность через `ORPipelineInput`;
    - возвращает готовый input для запуска OR-подграфа.
    """

    def stage_errors(self, draft: ScenarioDraft) -> dict[str, list[str]]:
        """Возвращает ошибки валидации по каждому stage draft."""
        errors: dict[str, list[str]] = {
            "production": self._validate_production_payload(draft.production),
            "shipment": self._validate_shipment_payload(draft.shipment),
            "assignment": self._validate_assignment_payload(draft.assignment),
            "routing": self._validate_routing_payload(draft.routing),
        }
        return errors

    def missing_stages(self, draft: ScenarioDraft) -> list[str]:
        """Возвращает список stage, которые ещё не готовы к сборке input."""
        errors = self.stage_errors(draft)
        return [stage for stage in _STAGES if errors[stage]]

    def build_from_draft(self, draft: ScenarioDraft) -> ORPipelineInput:
        """Собирает `ORPipelineInput` из полного корректного draft.

        Ошибки:
        - бросает `ScenarioValidationError`, если stage пуст/невалиден
          или кросс-этапные размерности не согласованы.
        """
        stage_errors = self.stage_errors(draft)
        missing = [stage for stage in _STAGES if stage_errors[stage]]
        if missing:
            details = "; ".join(f"{stage}: {', '.join(stage_errors[stage])}" for stage in missing)
            raise ScenarioValidationError(f"Scenario draft is incomplete or invalid: {details}")

        production = ProductionInput.model_validate(draft.production)
        shipment = ShipmentTemplateInput.model_validate(draft.shipment)
        assignment = AssignmentTemplateInput.model_validate(draft.assignment)
        routing = RoutingTemplateInput.model_validate(draft.routing)

        try:
            return ORPipelineInput(
                production=production,
                shipment_template=shipment,
                assignment_resources=assignment.resources,
                assignment_cost_matrix=assignment.cost_matrix,
                routing_template=routing,
            )
        except Exception as exc:
            raise ScenarioValidationError(f"Cross-stage validation failed: {exc}") from exc

    @staticmethod
    def _collect_validation_errors(
        *,
        parser,
        payload: dict[str, Any],
        required_fields: list[str],
    ) -> list[str]:
        errors: list[str] = []
        if not payload:
            return ["stage is empty"]
        for field in required_fields:
            if field not in payload:
                errors.append(f"missing field: {field}")
        if errors:
            return errors
        try:
            parser.model_validate(payload)
            return []
        except Exception as exc:
            return [str(exc)]

    def _validate_production_payload(self, payload: dict[str, Any]) -> list[str]:
        return self._collect_validation_errors(
            parser=ProductionInput,
            payload=payload,
            required_fields=[
                "products",
                "profits",
                "resource_matrix",
                "resource_limits",
                "demand_upper_bounds",
                "pallet_factors",
            ],
        )

    def _validate_shipment_payload(self, payload: dict[str, Any]) -> list[str]:
        return self._collect_validation_errors(
            parser=ShipmentTemplateInput,
            payload=payload,
            required_fields=[
                "warehouses",
                "warehouse_supply_ratio",
                "clients",
                "client_demand",
                "cost_matrix",
                "capacity_matrix",
            ],
        )

    def _validate_assignment_payload(self, payload: dict[str, Any]) -> list[str]:
        return self._collect_validation_errors(
            parser=AssignmentTemplateInput,
            payload=payload,
            required_fields=["resources", "cost_matrix"],
        )

    def _validate_routing_payload(self, payload: dict[str, Any]) -> list[str]:
        return self._collect_validation_errors(
            parser=RoutingTemplateInput,
            payload=payload,
            required_fields=[
                "distance_matrix",
                "depot_index",
                "client_nodes",
                "vehicle_capacities",
            ],
        )


class ScenarioPresetLoader:
    """Загружает demo-preset из JSON и преобразует в `ScenarioDraft`."""

    def __init__(self, preset_path: Path) -> None:
        self._preset_path = preset_path
        self._seed = self._load_seed(preset_path)

    @staticmethod
    def _load_seed(path: Path) -> ScenarioSeed:
        if not path.exists():
            raise ScenarioValidationError(f"Scenario file does not exist: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ScenarioSeed.model_validate(payload)
        except Exception as exc:  # pragma: no cover - parse errors are environment-dependent
            raise ScenarioValidationError(f"Failed to load scenario JSON: {exc}") from exc

    @property
    def seed(self) -> ScenarioSeed:
        """Возвращает валидированный seed preset."""
        return self._seed

    def load_demo_draft(self) -> ScenarioDraft:
        """Возвращает полноценный draft из preset без автозапуска OR."""
        return ScenarioDraft(
            production=self._seed.production.model_dump(mode="json"),
            shipment=self._seed.shipment.model_dump(mode="json"),
            assignment={
                "resources": list(self._seed.assignment_resources),
                "cost_matrix": [row[:] for row in self._seed.assignment_cost_matrix],
            },
            routing=self._seed.routing.model_dump(mode="json"),
            preset_ref="demo",
        )
