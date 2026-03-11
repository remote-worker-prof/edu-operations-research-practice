"""Ядро исследовательских операций для учебного демо-проекта.

Пакет экспортирует:
- `ScenarioAssembler` для подготовки runtime-входа из draft;
- `ScenarioPresetLoader` для явной загрузки demo preset;
- `ORPipeline` для запуска полной цепочки оптимизации.
"""

from .pipeline import ORPipeline
from .scenario import ScenarioAssembler, ScenarioPresetLoader

__all__ = ["ORPipeline", "ScenarioAssembler", "ScenarioPresetLoader"]
