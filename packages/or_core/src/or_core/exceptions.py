"""Domain-specific exceptions for OR pipeline failures."""


class ORPipelineError(RuntimeError):
    """Base class for deterministic OR pipeline errors."""


class ScenarioValidationError(ORPipelineError):
    """Raised when scenario input is invalid."""


class ProductionOptimizationError(ORPipelineError):
    """Raised when production linear program has no valid solution."""


class ShipmentAllocationError(ORPipelineError):
    """Raised when min-cost flow allocation fails."""


class AssignmentError(ORPipelineError):
    """Raised when assignment solver input is invalid or infeasible."""


class RoutingError(ORPipelineError):
    """Raised when routing solver cannot produce a route plan."""
