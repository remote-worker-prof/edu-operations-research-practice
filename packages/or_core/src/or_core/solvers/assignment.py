"""Решатель задачи назначения ресурсов на клиентские задачи."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from or_core.exceptions import AssignmentError
from or_core.models import AssignmentInput, AssignmentOutput, AssignmentPair


def solve_assignment(data: AssignmentInput) -> AssignmentOutput:
    """Решает задачу линейного назначения с минимальной суммарной стоимостью.

    Что делает:
    - проверяет базовую выполнимость (ресурсов не меньше задач);
    - запускает алгоритм Венгера через `linear_sum_assignment`;
    - формирует пары `resource -> task`.

    Зачем:
    - получить конкретное сопоставление ресурсов и задач перед маршрутизацией.
    """
    if len(data.resources) < len(data.tasks):
        msg = "Number of resources must be >= number of tasks"
        raise AssignmentError(msg)

    cost_matrix = np.array(data.cost_matrix, dtype=float)
    resource_idx, task_idx = linear_sum_assignment(cost_matrix)

    pairs: list[AssignmentPair] = []
    total_cost = 0.0
    for r_idx, t_idx in zip(resource_idx, task_idx, strict=True):
        task = data.tasks[t_idx]
        cost = float(cost_matrix[r_idx, t_idx])
        pairs.append(
            AssignmentPair(
                resource=data.resources[r_idx],
                task_id=task.task_id,
                client=task.client,
                assigned_volume=task.volume,
                cost=cost,
            )
        )
        total_cost += cost

    if len(pairs) != len(data.tasks):
        msg = "Assignment solver did not cover all tasks"
        raise AssignmentError(msg)

    return AssignmentOutput(total_cost=round(total_cost, 2), pairs=pairs)
