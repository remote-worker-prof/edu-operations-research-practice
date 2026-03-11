"""Решатель линейного программирования для этапа производства."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from or_core.exceptions import ProductionOptimizationError
from or_core.models import ProductionInput, ProductionOutput


def solve_production(data: ProductionInput) -> ProductionOutput:
    """Решает LP-задачу для двух продуктов с максимизацией прибыли.

    Что делает:
    - формирует матрицы ограничений из `ProductionInput`;
    - запускает `scipy.optimize.linprog`;
    - преобразует решение в `ProductionOutput`.

    Зачем:
    - вычислить оптимальные объёмы выпуска и доступные паллеты для следующего этапа.
    """
    product_count = len(data.products)
    c = -np.array(data.profits, dtype=float)

    resource_matrix = np.array(data.resource_matrix, dtype=float)
    demand_upper_bounds = np.diag(np.ones(product_count, dtype=float))
    a_ub = np.vstack([resource_matrix, demand_upper_bounds])
    b_ub = np.array([*data.resource_limits, *data.demand_upper_bounds], dtype=float)

    result = linprog(
        c=c,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=[(0, None) for _ in range(product_count)],
        method="highs",
    )

    if not result.success or result.x is None:
        detail = result.message if result.message else "unknown LP failure"
        raise ProductionOptimizationError(f"Production LP failed: {detail}")

    quantities = {
        product: float(value) for product, value in zip(data.products, result.x, strict=True)
    }
    total_pallets = int(
        round(
            sum(
                float(value) * pallet_factor
                for value, pallet_factor in zip(result.x, data.pallet_factors, strict=True)
            )
        )
    )

    return ProductionOutput(
        quantities=quantities,
        objective_value=float(-result.fun),
        total_pallets=total_pallets,
        solver_status=result.message,
    )
