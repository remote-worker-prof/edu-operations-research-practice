"""Ядро исследовательских операций для учебного демо-проекта.

Пакет экспортирует:
- `ScenarioBuilder` для подготовки runtime-входа;
- `ORPipeline` для запуска полной цепочки оптимизации.
"""

from .pipeline import ORPipeline
from .scenario import ScenarioBuilder

__all__ = ["ORPipeline", "ScenarioBuilder"]
