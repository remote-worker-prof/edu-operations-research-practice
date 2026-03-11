"""Доменные контракты входов/выходов для OR-пайплайна.

Модуль задаёт все ключевые структуры данных:
- что получает каждый этап оптимизации;
- что возвращает каждый этап;
- какие инварианты размерностей и ограничений проверяются заранее.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ScenarioParams(BaseModel):
    """Legacy-контракт коэффициентов сценария (сохранён для обратной совместимости)."""

    demand_multiplier: float = Field(..., gt=0, le=2)
    resource_multiplier: float = Field(..., gt=0, le=2)


class ProductionInput(BaseModel):
    """Входные данные этапа производства (LP).

    Модель описывает двухпродуктовую постановку: прибыль, ограничения ресурсов,
    верхние границы спроса и коэффициенты перевода в паллеты.
    """

    products: list[str] = Field(..., min_length=1)
    profits: list[float] = Field(..., min_length=1)
    resource_matrix: list[list[float]] = Field(..., min_length=1)
    resource_limits: list[float] = Field(..., min_length=1)
    demand_upper_bounds: list[float] = Field(..., min_length=1)
    pallet_factors: list[float] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ProductionInput":
        """Проверяет согласованность размерностей LP-постановки `R x P`."""
        product_count = len(self.products)
        if len(self.profits) != product_count:
            msg = "profits length must match products length"
            raise ValueError(msg)
        if len(self.demand_upper_bounds) != product_count:
            msg = "demand_upper_bounds length must match products length"
            raise ValueError(msg)
        if len(self.pallet_factors) != product_count:
            msg = "pallet_factors length must match products length"
            raise ValueError(msg)
        resource_count = len(self.resource_matrix)
        if resource_count == 0:
            msg = "resource_matrix must contain at least one row"
            raise ValueError(msg)
        if any(len(row) != product_count for row in self.resource_matrix):
            msg = "resource_matrix must be R x P where P is number of products"
            raise ValueError(msg)
        if len(self.resource_limits) != resource_count:
            msg = "resource_limits length must match number of resource rows"
            raise ValueError(msg)
        return self


class ProductionOutput(BaseModel):
    """Результат оптимизации производства: объёмы, objective и итог в паллетах."""

    quantities: dict[str, float]
    objective_value: float
    total_pallets: int
    solver_status: str


class ShipmentTemplateInput(BaseModel):
    """Шаблон входа для этапа отгрузки (min-cost flow)."""

    warehouses: list[str] = Field(..., min_length=1)
    warehouse_supply_ratio: list[float] = Field(..., min_length=1)
    clients: list[str] = Field(..., min_length=1)
    client_demand: list[int] = Field(..., min_length=1)
    cost_matrix: list[list[float]] = Field(..., min_length=1)
    capacity_matrix: list[list[int]] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ShipmentTemplateInput":
        """Проверяет консистентность размерностей `warehouses x clients`."""
        warehouse_count = len(self.warehouses)
        client_count = len(self.clients)
        if len(self.warehouse_supply_ratio) != warehouse_count:
            msg = "warehouse_supply_ratio length must match warehouses length"
            raise ValueError(msg)
        if len(self.client_demand) != client_count:
            msg = "client_demand length must match clients length"
            raise ValueError(msg)
        if len(self.cost_matrix) != warehouse_count or any(
            len(row) != client_count for row in self.cost_matrix
        ):
            msg = "cost_matrix must be W x C where W=warehouses and C=clients"
            raise ValueError(msg)
        if len(self.capacity_matrix) != warehouse_count or any(
            len(row) != client_count for row in self.capacity_matrix
        ):
            msg = "capacity_matrix must be W x C where W=warehouses and C=clients"
            raise ValueError(msg)
        if sum(self.warehouse_supply_ratio) <= 0:
            msg = "warehouse_supply_ratio sum must be > 0"
            raise ValueError(msg)
        return self


class ShipmentLeg(BaseModel):
    """Одна ненулевая дуга отгрузки `склад -> клиент`."""

    warehouse: str
    client: str
    volume: int
    unit_cost: float


class ShipmentTask(BaseModel):
    """Агрегированная клиентская задача, которую получает этап назначения."""

    task_id: str
    client: str
    volume: int


class ShipmentOutput(BaseModel):
    """Результат этапа отгрузки: поток, стоимость, задачи и недопоставки."""

    available_pallets: int
    total_dispatched: int
    unmet_demand: dict[str, int]
    client_delivery: dict[str, int]
    total_cost: float
    legs: list[ShipmentLeg]
    tasks: list[ShipmentTask]


class AssignmentInput(BaseModel):
    """Вход этапа назначения ресурсов на задачи."""

    resources: list[str] = Field(..., min_length=1)
    tasks: list[ShipmentTask] = Field(..., min_length=1)
    cost_matrix: list[list[float]] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "AssignmentInput":
        """Проверяет размерность матрицы стоимости `resources x tasks`."""
        rows = len(self.resources)
        cols = len(self.tasks)
        if len(self.cost_matrix) != rows:
            msg = "cost_matrix rows must equal number of resources"
            raise ValueError(msg)
        if any(len(row) != cols for row in self.cost_matrix):
            msg = "cost_matrix columns must equal number of tasks"
            raise ValueError(msg)
        return self


class AssignmentPair(BaseModel):
    """Одна пара назначения: какой ресурс обслуживает какую задачу."""

    resource: str
    task_id: str
    client: str
    assigned_volume: int
    cost: float


class AssignmentOutput(BaseModel):
    """Результат этапа назначения: список пар и суммарная стоимость."""

    total_cost: float
    pairs: list[AssignmentPair]


class AssignmentTemplateInput(BaseModel):
    """Независимые входные данные assignment-этапа до появления shipment tasks."""

    resources: list[str] = Field(..., min_length=1)
    cost_matrix: list[list[float]] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "AssignmentTemplateInput":
        """Проверяет размерность `resources x clients` для шаблона назначения."""
        rows = len(self.resources)
        if len(self.cost_matrix) != rows:
            msg = "cost_matrix rows must equal number of resources"
            raise ValueError(msg)
        column_count = len(self.cost_matrix[0]) if self.cost_matrix else 0
        if column_count == 0:
            msg = "cost_matrix must contain at least one client column"
            raise ValueError(msg)
        if any(len(row) != column_count for row in self.cost_matrix):
            msg = "all rows in cost_matrix must have equal length"
            raise ValueError(msg)
        return self


class RoutingInput(BaseModel):
    """Вход этапа маршрутизации (OR-Tools CVRP)."""

    distance_matrix: list[list[int]] = Field(..., min_length=2)
    depot_index: int = 0
    client_nodes: list[int] = Field(..., min_length=1)
    client_demands: list[int] = Field(..., min_length=1)
    vehicle_capacities: list[int] = Field(..., min_length=1)
    resource_names: list[str] = Field(default_factory=list)
    allowed_vehicle_ids_by_client: dict[int, list[int]] = Field(default_factory=dict)
    objective: Literal["total_distance", "max_route_distance"] = "total_distance"

    @model_validator(mode="after")
    def validate_dimensions(self) -> "RoutingInput":
        """Проверяет квадратность матрицы расстояний и согласованность массивов."""
        node_count = len(self.distance_matrix)
        if any(len(row) != node_count for row in self.distance_matrix):
            msg = "distance_matrix must be square"
            raise ValueError(msg)
        if self.depot_index < 0 or self.depot_index >= node_count:
            msg = "depot_index must be a valid node index"
            raise ValueError(msg)
        if len(self.client_nodes) != len(self.client_demands):
            msg = "client_nodes length must match client_demands length"
            raise ValueError(msg)
        if self.depot_index in self.client_nodes:
            msg = "depot_index must not be listed in client_nodes"
            raise ValueError(msg)
        if len(set(self.client_nodes)) != len(self.client_nodes):
            msg = "client_nodes must not contain duplicates"
            raise ValueError(msg)
        if any(node < 0 or node >= node_count for node in self.client_nodes):
            msg = "client_nodes must be valid node indexes from distance_matrix"
            raise ValueError(msg)
        if self.resource_names and len(self.resource_names) != len(self.vehicle_capacities):
            msg = "resource_names length must match vehicle_capacities length"
            raise ValueError(msg)
        client_node_set = set(self.client_nodes)
        vehicle_count = len(self.vehicle_capacities)
        for client_node, vehicle_ids in self.allowed_vehicle_ids_by_client.items():
            if client_node not in client_node_set:
                msg = "allowed_vehicle_ids_by_client keys must be subset of client_nodes"
                raise ValueError(msg)
            if not vehicle_ids:
                msg = "allowed_vehicle_ids_by_client values must not be empty"
                raise ValueError(msg)
            for vehicle_id in vehicle_ids:
                if vehicle_id < 0 or vehicle_id >= vehicle_count:
                    msg = "allowed vehicle id out of range for vehicle_capacities"
                    raise ValueError(msg)
        return self


class VehicleRoute(BaseModel):
    """Маршрут одной единицы транспорта (или ресурса)."""

    vehicle_id: int
    resource: str
    nodes: list[int]
    distance: int
    load: int


class RoutingOutput(BaseModel):
    """Результат маршрутизации: маршруты и агрегированные метрики расстояния."""

    total_distance: int
    max_route_distance: int
    routes: list[VehicleRoute]


class ORPipelineInput(BaseModel):
    """Полный runtime-вход для запуска всего OR-пайплайна."""

    production: ProductionInput
    shipment_template: ShipmentTemplateInput
    assignment_resources: list[str] = Field(..., min_length=1)
    assignment_cost_matrix: list[list[float]] = Field(..., min_length=1)
    routing_template: RoutingInput

    @model_validator(mode="after")
    def validate_assignment_template(self) -> "ORPipelineInput":
        """Проверяет, что шаблон назначения согласован с количеством клиентов."""
        rows = len(self.assignment_resources)
        client_count = len(self.shipment_template.clients)
        if len(self.assignment_cost_matrix) != rows:
            msg = "assignment_cost_matrix rows must match assignment_resources"
            raise ValueError(msg)
        if any(len(row) != client_count for row in self.assignment_cost_matrix):
            msg = "assignment_cost_matrix columns must match number of clients"
            raise ValueError(msg)
        if len(self.routing_template.vehicle_capacities) != rows:
            msg = "routing_template.vehicle_capacities length must match assignment_resources"
            raise ValueError(msg)
        if len(self.routing_template.client_nodes) != client_count:
            msg = "routing_template.client_nodes length must match number of shipment clients"
            raise ValueError(msg)
        return self


class ORResult(BaseModel):
    """Итог полного расчёта: результаты 4 этапов + отчёт + trace."""

    production: ProductionOutput
    shipment: ShipmentOutput
    assignment: AssignmentOutput
    routing: RoutingOutput
    final_report: str
    execution_trace: list[str]


class ScenarioSeed(BaseModel):
    """Seed-сценарий в формате JSON, из которого строятся runtime-входы."""

    production: ProductionInput
    shipment: ShipmentTemplateInput
    assignment_resources: list[str]
    assignment_cost_matrix: list[list[float]]
    routing: RoutingInput


class ScenarioDraft(BaseModel):
    """Черновик независимых входов, собираемых интерактивно в чате."""

    production: dict[str, Any] = Field(default_factory=dict)
    shipment: dict[str, Any] = Field(default_factory=dict)
    assignment: dict[str, Any] = Field(default_factory=dict)
    routing: dict[str, Any] = Field(default_factory=dict)
    preset_ref: str | None = None
