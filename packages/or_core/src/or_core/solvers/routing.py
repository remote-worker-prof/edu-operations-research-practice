"""Решатель маршрутизации на OR-Tools для capacitated VRP."""

from __future__ import annotations

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from or_core.exceptions import RoutingError
from or_core.models import RoutingInput, RoutingOutput, VehicleRoute


def solve_routing(data: RoutingInput) -> RoutingOutput:
    """Решает CVRP и возвращает маршруты и агрегированные метрики.

    Что делает:
    - строит `RoutingIndexManager` и `RoutingModel`;
    - регистрирует callbacks расстояния и спроса;
    - задаёт ограничения по ёмкости;
    - извлекает маршруты из найденного решения.

    Зачем:
    - получить маршрутный план, согласованный с ограничениями спроса и вместимости.
    """
    node_count = len(data.distance_matrix)
    vehicle_count = len(data.vehicle_capacities)

    manager = pywrapcp.RoutingIndexManager(node_count, vehicle_count, data.depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        """Возвращает стоимость ребра (расстояние) между двумя индексами маршрутизатора."""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(data.distance_matrix[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    demand_map = {node: 0 for node in range(node_count)}
    for node, demand in zip(data.client_nodes, data.client_demands, strict=True):
        demand_map[node] = int(demand)

    def demand_callback(from_index: int) -> int:
        """Возвращает спрос узла для ограничения ёмкости транспортного средства."""
        from_node = manager.IndexToNode(from_index)
        return demand_map[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [int(cap) for cap in data.vehicle_capacities],
        True,
        "Capacity",
    )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.seconds = 5

    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise RoutingError("OR-Tools could not find a feasible route plan")

    routes: list[VehicleRoute] = []
    all_visited_nodes: set[int] = set()

    for vehicle_id in range(vehicle_count):
        index = routing.Start(vehicle_id)
        nodes = [manager.IndexToNode(index)]
        route_distance = 0
        route_load = 0

        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            to_node = manager.IndexToNode(next_index)

            route_distance += int(routing.GetArcCostForVehicle(index, next_index, vehicle_id))
            route_load += demand_map[to_node]

            index = next_index
            nodes.append(to_node)
            all_visited_nodes.add(to_node)

        resource = (
            data.resource_names[vehicle_id] if data.resource_names else f"vehicle_{vehicle_id + 1}"
        )

        routes.append(
            VehicleRoute(
                vehicle_id=vehicle_id,
                resource=resource,
                nodes=nodes,
                distance=route_distance,
                load=route_load,
            )
        )

    required_nodes = {
        node
        for node, demand in zip(data.client_nodes, data.client_demands, strict=True)
        if demand > 0
    }
    if not required_nodes.issubset(all_visited_nodes):
        missing = sorted(required_nodes.difference(all_visited_nodes))
        raise RoutingError(f"Some clients were not served by routes: {missing}")

    total_distance = sum(route.distance for route in routes)
    max_route_distance = max(route.distance for route in routes) if routes else 0

    return RoutingOutput(
        total_distance=total_distance,
        max_route_distance=max_route_distance,
        routes=routes,
    )
