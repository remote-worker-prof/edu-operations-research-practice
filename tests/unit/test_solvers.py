from or_core.models import AssignmentInput
from or_core.solvers.assignment import solve_assignment
from or_core.solvers.production import solve_production
from or_core.solvers.routing import solve_routing
from or_core.solvers.shipment import solve_shipment_allocation


def test_production_solver(runtime_input) -> None:
    result = solve_production(runtime_input.production)
    assert result.quantities["A"] == 70.0
    assert result.quantities["B"] > 70.0
    assert result.total_pallets >= 120


def test_shipment_solver(runtime_input) -> None:
    production = solve_production(runtime_input.production)
    shipment = solve_shipment_allocation(runtime_input.shipment_template, production.total_pallets)

    assert shipment.total_dispatched == sum(shipment.client_delivery.values())
    assert shipment.total_dispatched > 0
    assert len(shipment.tasks) == 3


def test_assignment_solver(runtime_input) -> None:
    production = solve_production(runtime_input.production)
    shipment = solve_shipment_allocation(runtime_input.shipment_template, production.total_pallets)
    tasks = shipment.tasks
    assignment_input = AssignmentInput(
        resources=runtime_input.assignment_resources,
        tasks=tasks,
        cost_matrix=runtime_input.assignment_cost_matrix,
    )

    assignment = solve_assignment(assignment_input)
    assert len(assignment.pairs) == len(tasks)
    assert assignment.total_cost == 17.0


def test_routing_solver(runtime_input) -> None:
    routing = solve_routing(runtime_input.routing_template)
    visited = set()
    for route in routing.routes:
        visited.update(route.nodes)

    assert routing.total_distance > 0
    assert {1, 2, 3}.issubset(visited)
