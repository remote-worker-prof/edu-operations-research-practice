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
        "finalize_report",
    ]
    assert result.final_report
