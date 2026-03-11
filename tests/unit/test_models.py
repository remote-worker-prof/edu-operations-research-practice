"""Unit-тесты валидации доменных Pydantic-моделей."""

import pytest
from or_core.models import (
    AssignmentInput,
    ORPipelineInput,
    ProductionInput,
    RoutingInput,
    RoutingTemplateInput,
    ShipmentTask,
)
from pydantic import ValidationError


def test_assignment_input_rejects_dimension_mismatch() -> None:
    """Проверяет отказ при несовпадении размерностей `cost_matrix`.

    Риск:
    - solver получает неконсистентные входы и падает глубже в runtime.
    """
    # Arrange
    tasks = [ShipmentTask(task_id="t1", client="C1", volume=10)]
    # Act / Assert
    with pytest.raises(ValidationError):
        AssignmentInput(
            resources=["r1", "r2"],
            tasks=tasks,
            cost_matrix=[[1.0], [2.0], [3.0]],
        )


def test_routing_input_rejects_invalid_allowed_vehicle_ids() -> None:
    """Проверяет отказ при некорректных ограничениях ТС для клиента.

    Риск:
    - routing может получить невалидные индексы ТС и упасть глубоко в OR-Tools.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        RoutingInput(
            distance_matrix=[[0, 1], [1, 0]],
            depot_index=0,
            client_nodes=[1],
            client_demands=[1],
            vehicle_capacities=[10],
            allowed_vehicle_ids_by_client={1: [3]},
        )


def test_or_pipeline_input_rejects_client_nodes_mismatch() -> None:
    """Проверяет согласованность клиентов shipment и client_nodes в routing.

    Риск:
    - несогласованный mapping клиент->узел ломает связку assignment и routing.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        ORPipelineInput.model_validate(
            {
                "production": {
                    "products": ["A", "B"],
                    "profits": [1.0, 1.0],
                    "resource_matrix": [[1.0, 1.0], [1.0, 1.0]],
                    "resource_limits": [10.0, 10.0],
                    "demand_upper_bounds": [10.0, 10.0],
                    "pallet_factors": [1.0, 1.0],
                },
                "shipment_template": {
                    "warehouses": ["W1", "W2"],
                    "warehouse_supply_ratio": [1.0, 1.0],
                    "clients": ["C1", "C2"],
                    "client_demand": [1, 1],
                    "cost_matrix": [[1.0, 1.0], [1.0, 1.0]],
                    "capacity_matrix": [[1, 1], [1, 1]],
                },
                "assignment_resources": ["truck_1", "truck_2"],
                "assignment_cost_matrix": [[1.0, 1.0], [1.0, 1.0]],
                "routing_template": {
                    "distance_matrix": [[0, 1, 1], [1, 0, 1], [1, 1, 0]],
                    "depot_index": 0,
                    "client_nodes": [1],
                    "vehicle_capacities": [2, 2],
                },
            }
        )


def test_production_input_supports_dynamic_dimensions() -> None:
    """Проверяет, что production-модель поддерживает произвольное число продуктов/ресурсов."""
    model = ProductionInput.model_validate(
        {
            "products": ["A", "B", "C"],
            "profits": [10.0, 12.0, 8.0],
            "resource_matrix": [[1.0, 0.5, 0.7], [0.3, 1.2, 0.4], [0.8, 0.6, 1.1]],
            "resource_limits": [120.0, 90.0, 100.0],
            "demand_upper_bounds": [40.0, 45.0, 50.0],
            "pallet_factors": [1.0, 0.9, 1.1],
        }
    )
    assert len(model.products) == 3


def test_routing_template_input_accepts_without_client_demands() -> None:
    """Проверяет, что routing-template описывает только независимые входы.

    Риск:
    - студента могут заставить вводить `client_demands`, хотя это derived-поле из shipment.
    """
    model = RoutingTemplateInput.model_validate(
        {
            "distance_matrix": [[0, 1, 2], [1, 0, 1], [2, 1, 0]],
            "depot_index": 0,
            "client_nodes": [1, 2],
            "vehicle_capacities": [5, 5],
        }
    )
    assert model.client_nodes == [1, 2]
