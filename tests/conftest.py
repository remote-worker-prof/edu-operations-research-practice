from pathlib import Path

import pytest
from agent_core.service import AgentService
from or_core.models import ScenarioParams
from or_core.scenario import ScenarioBuilder


@pytest.fixture(scope="session")
def scenario_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "scenarios" / "base_scenario.json"


@pytest.fixture(scope="session")
def scenario_builder(scenario_path: Path) -> ScenarioBuilder:
    return ScenarioBuilder(scenario_path)


@pytest.fixture()
def runtime_input(scenario_builder: ScenarioBuilder):
    return scenario_builder.build(
        ScenarioParams(demand_multiplier=1.0, resource_multiplier=1.0)
    )


@pytest.fixture()
def agent_service(scenario_path: Path) -> AgentService:
    return AgentService(scenario_path=scenario_path)
