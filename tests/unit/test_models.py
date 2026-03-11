import pytest
from or_core.models import AssignmentInput, ShipmentTask
from pydantic import ValidationError


def test_assignment_input_rejects_dimension_mismatch() -> None:
    tasks = [ShipmentTask(task_id="t1", client="C1", volume=10)]
    with pytest.raises(ValidationError):
        AssignmentInput(
            resources=["r1", "r2"],
            tasks=tasks,
            cost_matrix=[[1.0], [2.0], [3.0]],
        )
