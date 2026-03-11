"""Детерминированный OR-пайплайн, собранный как подграф LangGraph."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from or_core.exceptions import AssignmentError, ORPipelineError
from or_core.models import (
    AssignmentInput,
    AssignmentOutput,
    ORPipelineInput,
    ORResult,
    ProductionOutput,
    RoutingOutput,
    ShipmentOutput,
)
from or_core.solvers import (
    solve_assignment,
    solve_production,
    solve_routing,
    solve_shipment_allocation,
)


class ORGraphState(TypedDict, total=False):
    """Состояние OR-подграфа между узлами вычислений.

    Поля добавляются по мере прохождения этапов:
    production -> shipment -> assignment -> routing -> report.
    """

    input: ORPipelineInput
    production: ProductionOutput
    shipment: ShipmentOutput
    assignment: AssignmentOutput
    routing: RoutingOutput
    final_report: str
    execution_trace: list[str]


def _append_trace(state: ORGraphState, step: str) -> list[str]:
    """Добавляет имя шага в execution-trace без мутации входного списка."""
    return [*state.get("execution_trace", []), step]


def _optimize_production(state: ORGraphState) -> ORGraphState:
    """Узел 1: решает LP производства и записывает результат в state."""
    production = solve_production(state["input"].production)
    return {
        "production": production,
        "execution_trace": _append_trace(state, "optimize_production"),
    }


def _allocate_shipments(state: ORGraphState) -> ORGraphState:
    """Узел 2: распределяет выпуск по клиентам через min-cost flow."""
    shipment = solve_shipment_allocation(
        template=state["input"].shipment_template,
        total_pallets=state["production"].total_pallets,
    )
    return {"shipment": shipment, "execution_trace": _append_trace(state, "allocate_shipments")}


def _assign_resources(state: ORGraphState) -> ORGraphState:
    """Узел 3: назначает ресурсы на сформированные shipment-задачи."""
    tasks = state["shipment"].tasks
    if not tasks:
        raise AssignmentError("No shipment tasks were produced, assignment cannot continue")

    clients = state["input"].shipment_template.clients
    client_to_idx = {client: idx for idx, client in enumerate(clients)}

    # Матрица стоимости в input задаётся по всем клиентам, а assignment
    # работает по фактически созданным shipment tasks. Здесь делаем проекцию.
    reduced_cost_matrix: list[list[float]] = []
    for row in state["input"].assignment_cost_matrix:
        reduced_cost_matrix.append([row[client_to_idx[task.client]] for task in tasks])

    assignment_input = AssignmentInput(
        resources=state["input"].assignment_resources,
        tasks=tasks,
        cost_matrix=reduced_cost_matrix,
    )
    assignment = solve_assignment(assignment_input)
    return {"assignment": assignment, "execution_trace": _append_trace(state, "assign_resources")}


def _build_routes(state: ORGraphState) -> ORGraphState:
    """Узел 4: строит маршруты на основе спроса и назначенных ресурсов."""
    client_delivery = state["shipment"].client_delivery
    client_order = state["input"].shipment_template.clients
    delivered_demands = [int(client_delivery.get(client, 0)) for client in client_order]

    routing_input = state["input"].routing_template.model_copy(
        update={
            "client_demands": delivered_demands,
            "resource_names": list(state["input"].assignment_resources),
        }
    )
    routing = solve_routing(routing_input)
    return {"routing": routing, "execution_trace": _append_trace(state, "build_routes")}


def _finalize_report(state: ORGraphState) -> ORGraphState:
    """Узел 5: собирает короткий финальный отчёт по всем этапам."""
    production = state["production"]
    shipment = state["shipment"]
    assignment = state["assignment"]
    routing = state["routing"]

    report = (
        "Суточный тактический план готов. "
        f"Выпуск: {production.quantities}. "
        f"Отгружено паллет: {shipment.total_dispatched}. "
        f"Назначений: {len(assignment.pairs)}. "
        f"Суммарная длина маршрутов: {routing.total_distance}."
    )

    return {"final_report": report, "execution_trace": _append_trace(state, "finalize_report")}


def build_or_graph() -> StateGraph:
    """Собирает и компилирует детерминированный OR-подграф.

    Что делает:
    - регистрирует узлы для 4 этапов оптимизации и финального отчёта;
    - задаёт фиксированный порядок рёбер;
    - возвращает готовый к `invoke` граф.
    """
    builder = StateGraph(ORGraphState)
    builder.add_node("optimize_production", _optimize_production)
    builder.add_node("allocate_shipments", _allocate_shipments)
    builder.add_node("assign_resources", _assign_resources)
    builder.add_node("build_routes", _build_routes)
    builder.add_node("finalize_report", _finalize_report)

    builder.add_edge(START, "optimize_production")
    builder.add_edge("optimize_production", "allocate_shipments")
    builder.add_edge("allocate_shipments", "assign_resources")
    builder.add_edge("assign_resources", "build_routes")
    builder.add_edge("build_routes", "finalize_report")
    builder.add_edge("finalize_report", END)

    return builder.compile()


class ORPipeline:
    """Публичный фасад OR-пайплайна для dialog-agent и API."""

    def __init__(self) -> None:
        """Создаёт и кеширует скомпилированный OR-граф."""
        self._graph = build_or_graph()

    def run(self, validated_input: ORPipelineInput) -> ORResult:
        """Запускает OR-пайплайн end-to-end.

        Что делает:
        - вызывает граф с валидированным входом;
        - нормализует неожиданные ошибки в `ORPipelineError`;
        - собирает итоговый `ORResult`.

        Зачем:
        - предоставляет единый API для всех потребителей OR-расчёта.
        """
        try:
            output_state = self._graph.invoke({"input": validated_input, "execution_trace": []})
        except ORPipelineError:
            raise
        except Exception as exc:
            raise ORPipelineError(f"Unexpected OR pipeline failure: {exc}") from exc

        return ORResult(
            production=output_state["production"],
            shipment=output_state["shipment"],
            assignment=output_state["assignment"],
            routing=output_state["routing"],
            final_report=output_state["final_report"],
            execution_trace=output_state.get("execution_trace", []),
        )
