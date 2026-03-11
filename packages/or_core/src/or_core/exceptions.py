"""Исключения доменной области OR-пайплайна.

Классы ошибок сгруппированы по этапам, чтобы студент видел:
- где именно произошёл сбой;
- как сопоставлять тип исключения с этапом оптимизации.
"""


class ORPipelineError(RuntimeError):
    """Базовое исключение для всех ошибок детерминированного OR-пайплайна."""


class ScenarioValidationError(ORPipelineError):
    """Ошибка валидации входного сценария или его структуры."""


class ProductionOptimizationError(ORPipelineError):
    """Ошибка этапа производства (LP не решился или вернул невалидный результат)."""


class ShipmentAllocationError(ORPipelineError):
    """Ошибка этапа отгрузки (min-cost flow не нашёл допустимое решение)."""


class AssignmentError(ORPipelineError):
    """Ошибка этапа назначения ресурсов (невалидный вход или infeasible)."""


class RoutingError(ORPipelineError):
    """Ошибка маршрутизации (OR-Tools не построил корректный план)."""
