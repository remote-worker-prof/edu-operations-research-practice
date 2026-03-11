"""Typed contracts for OR pipeline inputs and outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ScenarioParams(BaseModel):
    """User-provided multipliers that specialize the base educational scenario."""

    demand_multiplier: float = Field(..., gt=0, le=2)
    resource_multiplier: float = Field(..., gt=0, le=2)


class ProductionInput(BaseModel):
    """Input for the production optimization LP solver."""

    products: list[str] = Field(default_factory=lambda: ["A", "B"])
    profits: list[float] = Field(..., min_length=2, max_length=2)
    resource_matrix: list[list[float]] = Field(..., min_length=2, max_length=2)
    resource_limits: list[float] = Field(..., min_length=2, max_length=2)
    demand_upper_bounds: list[float] = Field(..., min_length=2, max_length=2)
    pallet_factors: list[float] = Field(..., min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ProductionInput":
        if len(self.products) != 2:
            msg = "ProductionInput requires exactly 2 products for the educational scenario"
            raise ValueError(msg)
        if any(len(row) != 2 for row in self.resource_matrix):
            msg = "resource_matrix must be 2x2"
            raise ValueError(msg)
        return self


class ProductionOutput(BaseModel):
    """Result of production optimization."""

    quantities: dict[str, float]
    objective_value: float
    total_pallets: int
    solver_status: str


class ShipmentTemplateInput(BaseModel):
    """Template input for shipment allocation."""

    warehouses: list[str] = Field(default_factory=lambda: ["W1", "W2"], min_length=2, max_length=2)
    warehouse_supply_ratio: list[float] = Field(..., min_length=2, max_length=2)
    clients: list[str] = Field(..., min_length=1)
    client_demand: list[int] = Field(..., min_length=1)
    cost_matrix: list[list[float]] = Field(..., min_length=2, max_length=2)
    capacity_matrix: list[list[int]] = Field(..., min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ShipmentTemplateInput":
        client_count = len(self.clients)
        if len(self.client_demand) != client_count:
            msg = "client_demand length must match clients length"
            raise ValueError(msg)
        if len(self.cost_matrix) != 2 or any(len(row) != client_count for row in self.cost_matrix):
            msg = "cost_matrix must be 2xN where N is number of clients"
            raise ValueError(msg)
        if len(self.capacity_matrix) != 2 or any(
            len(row) != client_count for row in self.capacity_matrix
        ):
            msg = "capacity_matrix must be 2xN where N is number of clients"
            raise ValueError(msg)
        if sum(self.warehouse_supply_ratio) <= 0:
            msg = "warehouse_supply_ratio sum must be > 0"
            raise ValueError(msg)
        return self


class ShipmentLeg(BaseModel):
    """A single non-zero shipment leg from warehouse to client."""

    warehouse: str
    client: str
    volume: int
    unit_cost: float


class ShipmentTask(BaseModel):
    """Aggregated client-level task used for assignment."""

    task_id: str
    client: str
    volume: int


class ShipmentOutput(BaseModel):
    """Result of min-cost flow shipment allocation."""

    available_pallets: int
    total_dispatched: int
    unmet_demand: dict[str, int]
    client_delivery: dict[str, int]
    total_cost: float
    legs: list[ShipmentLeg]
    tasks: list[ShipmentTask]


class AssignmentInput(BaseModel):
    """Input to linear assignment solver."""

    resources: list[str] = Field(..., min_length=1)
    tasks: list[ShipmentTask] = Field(..., min_length=1)
    cost_matrix: list[list[float]] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "AssignmentInput":
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
    """One resource-to-task assignment decision."""

    resource: str
    task_id: str
    client: str
    assigned_volume: int
    cost: float


class AssignmentOutput(BaseModel):
    """Result of assignment optimization."""

    total_cost: float
    pairs: list[AssignmentPair]


class RoutingInput(BaseModel):
    """Input for OR-Tools routing solver."""

    distance_matrix: list[list[int]] = Field(..., min_length=2)
    depot_index: int = 0
    client_nodes: list[int] = Field(..., min_length=1)
    client_demands: list[int] = Field(..., min_length=1)
    vehicle_capacities: list[int] = Field(..., min_length=1)
    resource_names: list[str] = Field(default_factory=list)
    objective: Literal["total_distance", "max_route_distance"] = "total_distance"

    @model_validator(mode="after")
    def validate_dimensions(self) -> "RoutingInput":
        node_count = len(self.distance_matrix)
        if any(len(row) != node_count for row in self.distance_matrix):
            msg = "distance_matrix must be square"
            raise ValueError(msg)
        if len(self.client_nodes) != len(self.client_demands):
            msg = "client_nodes length must match client_demands length"
            raise ValueError(msg)
        if self.depot_index in self.client_nodes:
            msg = "depot_index must not be listed in client_nodes"
            raise ValueError(msg)
        if self.resource_names and len(self.resource_names) != len(self.vehicle_capacities):
            msg = "resource_names length must match vehicle_capacities length"
            raise ValueError(msg)
        return self


class VehicleRoute(BaseModel):
    """A solved route for one vehicle/resource."""

    vehicle_id: int
    resource: str
    nodes: list[int]
    distance: int
    load: int


class RoutingOutput(BaseModel):
    """Result of routing optimization."""

    total_distance: int
    max_route_distance: int
    routes: list[VehicleRoute]


class ORPipelineInput(BaseModel):
    """Runtime input for the full deterministic OR pipeline."""

    production: ProductionInput
    shipment_template: ShipmentTemplateInput
    assignment_resources: list[str] = Field(..., min_length=1)
    assignment_cost_matrix: list[list[float]] = Field(..., min_length=1)
    routing_template: RoutingInput

    @model_validator(mode="after")
    def validate_assignment_template(self) -> "ORPipelineInput":
        rows = len(self.assignment_resources)
        client_count = len(self.shipment_template.clients)
        if len(self.assignment_cost_matrix) != rows:
            msg = "assignment_cost_matrix rows must match assignment_resources"
            raise ValueError(msg)
        if any(len(row) != client_count for row in self.assignment_cost_matrix):
            msg = "assignment_cost_matrix columns must match number of clients"
            raise ValueError(msg)
        return self


class ORResult(BaseModel):
    """End-to-end output of all OR stages."""

    production: ProductionOutput
    shipment: ShipmentOutput
    assignment: AssignmentOutput
    routing: RoutingOutput
    final_report: str
    execution_trace: list[str]


class ScenarioSeed(BaseModel):
    """Serialized base scenario stored in JSON."""

    production: ProductionInput
    shipment: ShipmentTemplateInput
    assignment_resources: list[str]
    assignment_cost_matrix: list[list[float]]
    routing: RoutingInput
