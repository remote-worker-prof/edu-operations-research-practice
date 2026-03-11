"""Unit-тесты валидации доменных Pydantic-моделей."""

import pytest
from or_core.models import AssignmentInput, ShipmentTask
from pydantic import ValidationError


def test_assignment_input_rejects_dimension_mismatch() -> None:
    """Проверяет отказ при несовпадении размерностей `cost_matrix`.

    Риск:
    - solver получает неконсистентные входы и падает глубже в runtime.
    """
    # Arrange
    tasks = [ShipmentTask(task_id="t1", client="C1", volume=10)]
    # Act / Assert
    with pytest.raises(ValidationError):
        AssignmentInput(
            resources=["r1", "r2"],
            tasks=tasks,
            cost_matrix=[[1.0], [2.0], [3.0]],
        )
