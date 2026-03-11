"""Unit-тесты численных солверов OR-пайплайна.

Тесты проверяют инварианты и ожидаемые численные свойства каждого этапа.
"""

from or_core.models import AssignmentInput, RoutingInput
from or_core.solvers.assignment import solve_assignment
from or_core.solvers.production import solve_production
from or_core.solvers.routing import solve_routing
from or_core.solvers.shipment import solve_shipment_allocation


def test_production_solver(runtime_input) -> None:
    """Проверяет базовые численные инварианты LP-решения производства.

    Риск:
    - изменение коэффициентов/ограничений ломает ожидаемую структуру результата.
    """
    # Arrange / Act
    result = solve_production(runtime_input.production)
    # Assert
    assert result.quantities["A"] == 70.0
    assert result.quantities["B"] > 70.0
    assert result.total_pallets >= 120


def test_shipment_solver(runtime_input) -> None:
    """Проверяет согласованность результата min-cost flow отгрузки.

    Риск:
    - рассогласование `client_delivery`, `total_dispatched` и списка задач.
    """
    # Arrange
    production = solve_production(runtime_input.production)
    # Act
    shipment = solve_shipment_allocation(runtime_input.shipment_template, production.total_pallets)

    # Assert
    assert shipment.total_dispatched == sum(shipment.client_delivery.values())
    assert shipment.total_dispatched > 0
    assert len(shipment.tasks) == 3


def test_assignment_solver(runtime_input) -> None:
    """Проверяет корректность этапа назначения ресурсов.

    Риск:
    - assignment может не покрыть все задачи или вернуть нестабильную стоимость.
    """
    # Arrange
    production = solve_production(runtime_input.production)
    shipment = solve_shipment_allocation(runtime_input.shipment_template, production.total_pallets)
    tasks = shipment.tasks
    assignment_input = AssignmentInput(
        resources=runtime_input.assignment_resources,
        tasks=tasks,
        cost_matrix=runtime_input.assignment_cost_matrix,
    )

    # Act
    assignment = solve_assignment(assignment_input)
    # Assert
    assert len(assignment.pairs) == len(tasks)
    assert assignment.total_cost == 17.0


def test_routing_solver(runtime_input) -> None:
    """Проверяет, что маршрутизация обслуживает всех обязательных клиентов.

    Риск:
    - отдельные узлы спроса не попадают в построенные маршруты.
    """
    # Arrange
    production = solve_production(runtime_input.production)
    shipment = solve_shipment_allocation(runtime_input.shipment_template, production.total_pallets)
    routing_template = runtime_input.routing_template
    delivered_demands = [
        int(shipment.client_delivery.get(client, 0))
        for client in runtime_input.shipment_template.clients
    ]
    routing_input = RoutingInput(
        distance_matrix=routing_template.distance_matrix,
        depot_index=routing_template.depot_index,
        client_nodes=routing_template.client_nodes,
        client_demands=delivered_demands,
        vehicle_capacities=routing_template.vehicle_capacities,
        resource_names=list(runtime_input.assignment_resources),
    )

    # Act
    routing = solve_routing(routing_input)
    visited = set()
    for route in routing.routes:
        visited.update(route.nodes)

    # Assert
    assert routing.total_distance > 0
    assert {1, 2, 3}.issubset(visited)
