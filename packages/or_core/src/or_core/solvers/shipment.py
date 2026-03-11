"""Shipment allocation solver using min-cost flow."""

from __future__ import annotations

import math

import networkx as nx

from or_core.exceptions import ShipmentAllocationError
from or_core.models import ShipmentLeg, ShipmentOutput, ShipmentTask, ShipmentTemplateInput


def _distribute_total(total: int, ratios: list[float]) -> list[int]:
    ratio_sum = sum(ratios)
    if ratio_sum <= 0:
        raise ShipmentAllocationError("warehouse_supply_ratio sum must be positive")
    raw = [total * (r / ratio_sum) for r in ratios]
    base = [int(math.floor(v)) for v in raw]
    remainder = total - sum(base)
    ranked = sorted(range(len(raw)), key=lambda idx: raw[idx] - base[idx], reverse=True)
    for idx in ranked[:remainder]:
        base[idx] += 1
    return base


def _scale_demands(client_demand: list[int], available: int) -> list[int]:
    total_demand = sum(client_demand)
    if total_demand == 0:
        return [0 for _ in client_demand]
    if available >= total_demand:
        return list(client_demand)

    raw = [d * available / total_demand for d in client_demand]
    scaled = [int(math.floor(v)) for v in raw]
    remainder = available - sum(scaled)
    ranked = sorted(range(len(raw)), key=lambda idx: raw[idx] - scaled[idx], reverse=True)
    for idx in ranked[:remainder]:
        scaled[idx] += 1
    return scaled


def solve_shipment_allocation(
    template: ShipmentTemplateInput,
    total_pallets: int,
) -> ShipmentOutput:
    """Allocate pallets via min-cost flow with capacity constraints."""
    total_demand = sum(template.client_demand)
    available = max(0, min(int(total_pallets), total_demand))
    scaled_demands = _scale_demands(template.client_demand, available)

    supplies = _distribute_total(available, template.warehouse_supply_ratio)

    graph = nx.DiGraph()
    for warehouse, supply in zip(template.warehouses, supplies, strict=True):
        graph.add_node(warehouse, demand=-supply)

    for client, demand in zip(template.clients, scaled_demands, strict=True):
        graph.add_node(client, demand=demand)

    for warehouse_idx, warehouse in enumerate(template.warehouses):
        for client_idx, client in enumerate(template.clients):
            graph.add_edge(
                warehouse,
                client,
                capacity=int(template.capacity_matrix[warehouse_idx][client_idx]),
                weight=int(round(template.cost_matrix[warehouse_idx][client_idx] * 100)),
            )

    try:
        flow = nx.min_cost_flow(graph)
    except (nx.NetworkXError, nx.NetworkXUnfeasible, nx.NetworkXUnbounded) as exc:
        raise ShipmentAllocationError(f"Shipment min-cost flow failed: {exc}") from exc

    legs: list[ShipmentLeg] = []
    client_delivery = {client: 0 for client in template.clients}
    total_cost = 0.0

    for warehouse_idx, warehouse in enumerate(template.warehouses):
        for client_idx, client in enumerate(template.clients):
            volume = int(flow[warehouse][client])
            if volume <= 0:
                continue
            unit_cost = float(template.cost_matrix[warehouse_idx][client_idx])
            legs.append(
                ShipmentLeg(
                    warehouse=warehouse,
                    client=client,
                    volume=volume,
                    unit_cost=unit_cost,
                )
            )
            client_delivery[client] += volume
            total_cost += volume * unit_cost

    tasks = [
        ShipmentTask(task_id=f"task-{idx + 1}", client=client, volume=client_delivery[client])
        for idx, client in enumerate(template.clients)
        if client_delivery[client] > 0
    ]

    unmet = {
        client: int(original - delivered)
        for client, original, delivered in zip(
            template.clients,
            template.client_demand,
            [client_delivery[c] for c in template.clients],
            strict=True,
        )
    }

    return ShipmentOutput(
        available_pallets=available,
        total_dispatched=sum(client_delivery.values()),
        unmet_demand=unmet,
        client_delivery=client_delivery,
        total_cost=round(total_cost, 2),
        legs=legs,
        tasks=tasks,
    )
