"""Общие pytest-фикстуры для unit/integration тестов проекта.

Модуль объясняет, как собирается стандартный runtime-контекст:
- путь к seed-сценарию;
- `ScenarioPresetLoader`;
- `ScenarioAssembler`;
- валидный `runtime_input`;
- готовый `AgentService`.
"""

from pathlib import Path

import pytest
from agent_core.service import AgentService
from or_core.scenario import ScenarioAssembler, ScenarioPresetLoader


@pytest.fixture(scope="session")
def scenario_path() -> Path:
    """Возвращает путь к базовому JSON-сценарию для всех тестов."""
    return Path(__file__).resolve().parents[1] / "data" / "scenarios" / "base_scenario.json"


@pytest.fixture(scope="session")
def scenario_preset_loader(scenario_path: Path) -> ScenarioPresetLoader:
    """Создаёт `ScenarioPresetLoader` поверх базового сценария."""
    return ScenarioPresetLoader(scenario_path)


@pytest.fixture()
def runtime_input(scenario_preset_loader: ScenarioPresetLoader):
    """Готовит валидный `ORPipelineInput` из demo draft preset."""
    assembler = ScenarioAssembler()
    draft = scenario_preset_loader.load_demo_draft()
    return assembler.build_from_draft(draft)


@pytest.fixture()
def agent_service(scenario_path: Path) -> AgentService:
    """Создаёт `AgentService` для интеграционных тестов API/диалога."""
    return AgentService(scenario_path=scenario_path)
