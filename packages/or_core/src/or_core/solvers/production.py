"""Production LP solver."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from or_core.exceptions import ProductionOptimizationError
from or_core.models import ProductionInput, ProductionOutput


def solve_production(data: ProductionInput) -> ProductionOutput:
    """Solve a 2-product LP maximizing total profit."""
    c = -np.array(data.profits, dtype=float)
    a_ub = np.array(
        [
            data.resource_matrix[0],
            data.resource_matrix[1],
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        dtype=float,
    )
    b_ub = np.array(
        [
            data.resource_limits[0],
            data.resource_limits[1],
            data.demand_upper_bounds[0],
            data.demand_upper_bounds[1],
        ],
        dtype=float,
    )

    result = linprog(
        c=c,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=[(0, None), (0, None)],
        method="highs",
    )

    if not result.success or result.x is None:
        detail = result.message if result.message else "unknown LP failure"
        raise ProductionOptimizationError(f"Production LP failed: {detail}")

    x1, x2 = result.x
    total_pallets = int(round(x1 * data.pallet_factors[0] + x2 * data.pallet_factors[1]))

    return ProductionOutput(
        quantities={data.products[0]: float(x1), data.products[1]: float(x2)},
        objective_value=float(-result.fun),
        total_pallets=total_pallets,
        solver_status=result.message,
    )
