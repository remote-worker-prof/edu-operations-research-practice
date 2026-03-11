"""Загрузка и параметризация учебного OR-сценария.

Назначение:
- прочитать базовый JSON-сценарий;
- масштабировать его под пользовательские коэффициенты;
- вернуть строго валидированный `ORPipelineInput`.
"""

from __future__ import annotations

import json
from pathlib import Path

from or_core.exceptions import ScenarioValidationError
from or_core.models import ORPipelineInput, ScenarioParams, ScenarioSeed


class ScenarioBuilder:
    """Строит runtime-вход OR-пайплайна из seed-сценария и коэффициентов пользователя.

    Что делает:
    - хранит валидированный seed в памяти;
    - на каждый запрос формирует новый `ORPipelineInput`.
    """

    def __init__(self, scenario_path: Path) -> None:
        """Инициализирует builder и загружает seed-сценарий из файла."""
        self._scenario_path = scenario_path
        self._seed = self._load_seed(scenario_path)

    @staticmethod
    def _load_seed(path: Path) -> ScenarioSeed:
        """Читает JSON и валидирует его как `ScenarioSeed`."""
        if not path.exists():
            raise ScenarioValidationError(f"Scenario file does not exist: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ScenarioSeed.model_validate(payload)
        except Exception as exc:  # pragma: no cover - impossible to enumerate all parse errors
            raise ScenarioValidationError(f"Failed to load scenario JSON: {exc}") from exc

    @property
    def seed(self) -> ScenarioSeed:
        """Возвращает загруженный seed-сценарий (read-only доступ)."""
        return self._seed

    def build(self, params: ScenarioParams) -> ORPipelineInput:
        """Собирает валидный runtime-вход из seed и коэффициентов пользователя.

        Что делает:
        - масштабирует ресурсные лимиты и спрос;
        - синхронизирует шаблоны shipment/routing;
        - возвращает типизированный `ORPipelineInput`.

        Зачем:
        - отделяет «данные сценария» от «данных конкретного расчёта».
        """
        scaled_resource_limits = [
            round(limit * params.resource_multiplier, 3)
            for limit in self._seed.production.resource_limits
        ]
        production_input = self._seed.production.model_copy(
            update={"resource_limits": scaled_resource_limits}
        )

        scaled_client_demand = [
            max(0, int(round(demand * params.demand_multiplier)))
            for demand in self._seed.shipment.client_demand
        ]
        shipment_template = self._seed.shipment.model_copy(
            update={"client_demand": scaled_client_demand}
        )

        routing_template = self._seed.routing.model_copy(
            update={"client_demands": list(scaled_client_demand)}
        )

        return ORPipelineInput(
            production=production_input,
            shipment_template=shipment_template,
            assignment_resources=list(self._seed.assignment_resources),
            assignment_cost_matrix=[row[:] for row in self._seed.assignment_cost_matrix],
            routing_template=routing_template,
        )
