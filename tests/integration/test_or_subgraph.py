"""Интеграционный тест OR-подграфа.

Проверяет, что шаги пайплайна выполняются в детерминированном ожидаемом порядке.
"""

from or_core.pipeline import ORPipeline


def test_or_subgraph_sequence(runtime_input) -> None:
    """Проверяет sequence всех узлов OR-пайплайна.

    Риск:
    - изменение рёбер графа может незаметно нарушить порядок вычислений.
    """
    # Arrange
    pipeline = ORPipeline()
    # Act
    result = pipeline.run(runtime_input)

    # Assert
    assert result.execution_trace == [
        "optimize_production",
        "allocate_shipments",
        "assign_resources",
        "build_routes",
    ]
    assert result.final_report


def test_or_subgraph_assignment_constraints_affect_routing(runtime_input) -> None:
    """Проверяет, что маршрутизация учитывает ограничения из assignment.

    Риск:
    - этапы 3 и 4 могут стать независимыми, если routing игнорирует назначенные ресурсы.
    """
    # Arrange
    pipeline = ORPipeline()
    base_result = pipeline.run(runtime_input)
    altered_input = runtime_input.model_copy(deep=True)
    altered_input.assignment_cost_matrix = [
        [1.0, 100.0, 100.0],
        [100.0, 1.0, 100.0],
        [100.0, 100.0, 1.0],
    ]

    # Act
    altered_result = pipeline.run(altered_input)

    # Assert
    base_assignment_by_client = {
        pair.client: pair.resource for pair in base_result.assignment.pairs
    }
    altered_assignment_by_client = {
        pair.client: pair.resource for pair in altered_result.assignment.pairs
    }
    assert base_assignment_by_client != altered_assignment_by_client

    node_to_client = {
        node: client
        for client, node in zip(
            altered_input.shipment_template.clients,
            altered_input.routing_template.client_nodes,
            strict=True,
        )
    }
    served_resource_by_client: dict[str, str] = {}
    for route in altered_result.routing.routes:
        for node in route.nodes:
            client = node_to_client.get(node)
            if client is not None:
                served_resource_by_client[client] = route.resource

    assert served_resource_by_client == altered_assignment_by_client
