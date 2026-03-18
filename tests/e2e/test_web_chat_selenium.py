"""Browser E2E тесты HTMX-интерфейса через Selenium + Chromium."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

import httpx
import pytest
from extension_api import ExtensionManifest, ExtensionRegistry, ExtensionResultSection, StageSpec

pytestmark = pytest.mark.e2e


def _stage_json(stage: str, payload: dict) -> str:
    """Формирует команду `json <stage> {...}` из python-словаря."""
    return f"json {stage} {json.dumps(payload, ensure_ascii=False)}"


def _scenario_payloads(
    *,
    products: list[str],
    profits: list[int],
    pallet_factors: list[float],
    warehouses: list[str],
    clients: list[str],
    resources: list[str],
    shipment_cost_matrix: list[list[int]],
    assignment_cost_matrix: list[list[int]],
    routing_distance_matrix: list[list[int]],
) -> dict[str, dict]:
    """Собирает валидный набор входов для 4-stage OR-сценария."""
    return {
        "production": {
            "products": products,
            "profits": profits,
            "resource_matrix": [[2, 1], [1, 1.5]],
            "resource_limits": [240, 180],
            "demand_upper_bounds": [70, 80],
            "pallet_factors": pallet_factors,
        },
        "shipment": {
            "warehouses": warehouses,
            "warehouse_supply_ratio": [0.55, 0.45],
            "clients": clients,
            "client_demand": [42, 38, 40],
            "cost_matrix": shipment_cost_matrix,
            "capacity_matrix": [[50, 45, 40], [40, 45, 50]],
        },
        "assignment": {
            "resources": resources,
            "cost_matrix": assignment_cost_matrix,
        },
        "routing": {
            "distance_matrix": routing_distance_matrix,
            "depot_index": 0,
            "client_nodes": [1, 2, 3],
            "vehicle_capacities": [55, 45, 45],
        },
    }


FAST_PAYLOADS = _scenario_payloads(
    products=["A", "B"],
    profits=[40, 30],
    pallet_factors=[1.0, 0.8],
    warehouses=["W1", "W2"],
    clients=["C1", "C2", "C3"],
    resources=["truck_1", "truck_2", "truck_3"],
    shipment_cost_matrix=[[4, 6, 8], [5, 4, 3]],
    assignment_cost_matrix=[[8, 6, 7], [5, 8, 6], [7, 5, 9]],
    routing_distance_matrix=[[0, 10, 12, 8], [10, 0, 6, 7], [12, 6, 0, 9], [8, 7, 9, 0]],
)
MANUAL_VIDEO_PAYLOADS = _scenario_payloads(
    products=["Atlas", "Beacon"],
    profits=[52, 37],
    pallet_factors=[1.05, 0.9],
    warehouses=["North", "South"],
    clients=["Retail_A", "Retail_B", "Retail_C"],
    resources=["truck_red", "truck_blue", "truck_green"],
    shipment_cost_matrix=[[3, 6, 7], [6, 4, 5]],
    assignment_cost_matrix=[[7, 4, 6], [5, 7, 4], [6, 5, 8]],
    routing_distance_matrix=[[0, 9, 13, 7], [9, 0, 5, 8], [13, 5, 0, 10], [7, 8, 10, 0]],
)
NL_VIDEO_PAYLOADS = _scenario_payloads(
    products=["Nova", "Orbit"],
    profits=[46, 35],
    pallet_factors=[1.0, 0.95],
    warehouses=["East", "West"],
    clients=["Clinic_1", "Clinic_2", "Clinic_3"],
    resources=["van_1", "van_2", "van_3"],
    shipment_cost_matrix=[[5, 6, 7], [4, 5, 4]],
    assignment_cost_matrix=[[6, 5, 7], [5, 7, 4], [7, 4, 6]],
    routing_distance_matrix=[[0, 11, 12, 9], [11, 0, 7, 6], [12, 7, 0, 8], [9, 6, 8, 0]],
)
VALIDATION_VIDEO_PAYLOADS = _scenario_payloads(
    products=["Delta", "Echo"],
    profits=[50, 33],
    pallet_factors=[1.1, 0.85],
    warehouses=["Hub_A", "Hub_B"],
    clients=["School_1", "School_2", "School_3"],
    resources=["carrier_1", "carrier_2", "carrier_3"],
    shipment_cost_matrix=[[4, 7, 6], [5, 4, 5]],
    assignment_cost_matrix=[[7, 5, 6], [6, 7, 4], [5, 6, 8]],
    routing_distance_matrix=[[0, 8, 11, 10], [8, 0, 7, 6], [11, 7, 0, 9], [10, 6, 9, 0]],
)
AMBIGUITY_VIDEO_PAYLOADS = _scenario_payloads(
    products=["Flux", "Glow"],
    profits=[48, 34],
    pallet_factors=[1.0, 0.88],
    warehouses=["Depot_A", "Depot_B"],
    clients=["Market_1", "Market_2", "Market_3"],
    resources=["route_1", "route_2", "route_3"],
    shipment_cost_matrix=[[6, 5, 7], [5, 6, 4]],
    assignment_cost_matrix=[[5, 7, 6], [6, 5, 7], [7, 4, 5]],
    routing_distance_matrix=[[0, 12, 10, 9], [12, 0, 6, 8], [10, 6, 0, 7], [9, 8, 7, 0]],
)

PRODUCTION_JSON = _stage_json("production", FAST_PAYLOADS["production"])
SHIPMENT_JSON = _stage_json("shipment", FAST_PAYLOADS["shipment"])
ASSIGNMENT_JSON = _stage_json("assignment", FAST_PAYLOADS["assignment"])
ROUTING_JSON = _stage_json("routing", FAST_PAYLOADS["routing"])
SHIPMENT_SHORTCUT_JSON = json.dumps(FAST_PAYLOADS["shipment"], ensure_ascii=False)


@dataclass(frozen=True)
class ScreencastStep:
    """Один шаг видео-сценария поверх Selenium page-object."""

    kind: Literal["select_model", "type_message", "chunked_message", "pause"]
    value: str | float
    after_pause_seconds: float | None = None


@dataclass(frozen=True)
class _FakeEntryPoint:
    """Минимальный entry point stand-in для browser tests с custom registry."""

    name: str
    provider: object
    group: str = "edu_or_agent.extensions"
    module: str = "tests.e2e.fake_extension_provider"

    def load(self) -> object:
        return self.provider


def _build_fake_manifest(
    *,
    alias: str,
    title: str,
    description: str,
    stage_graph: list[StageSpec],
) -> ExtensionManifest:
    """Строит компактный fake manifest для browser startup coverage."""
    return ExtensionManifest(
        alias=alias,
        title=title,
        description=description,
        version="0.1.0",
        stage_graph=stage_graph,
    )


class _BrowserFakeRuntime:
    """Минимальный runtime для startup-discovery smoke в Selenium."""

    manifest: ExtensionManifest

    def __init__(self, manifest: ExtensionManifest) -> None:
        self.manifest = manifest

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        return {}

    def build_runtime_input(self, draft: dict[str, object]) -> object:
        return draft

    def run(self, runtime_input: object) -> object:
        return runtime_input

    def fallback_explain(self, result: object) -> str:
        return "fallback"

    def build_llm_explain_prompt(self, result: object) -> str:
        return "prompt"

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        return []

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        return []

    def build_nl_semantics(self) -> dict[str, object]:
        return {}


class _BrowserFakeProvider:
    """Фейковый provider для browser smoke с непустым registry."""

    def __init__(self, manifest: ExtensionManifest) -> None:
        self._manifest = manifest

    def get_manifest(self) -> ExtensionManifest:
        return self._manifest

    def create_runtime(self) -> _BrowserFakeRuntime:
        return _BrowserFakeRuntime(self.get_manifest())


def _registry_with_study_planner() -> ExtensionRegistry:
    """Строит непустой registry для browser tests текущего foundation-slice."""
    study_manifest = _build_fake_manifest(
        alias="study_planner",
        title="Study Planner",
        description="Sample extension manifest for Selenium startup coverage",
        stage_graph=[
            StageSpec(stage_id="courses", label="Courses"),
            StageSpec(stage_id="time_budget", label="Time Budget"),
            StageSpec(stage_id="priorities", label="Priorities", depends_on=["courses"]),
        ],
    )
    return ExtensionRegistry.discover(
        entry_points=[
            _FakeEntryPoint(
                name="study_planner",
                provider=_BrowserFakeProvider(study_manifest),
            )
        ]
    )


def _registry_with_multiple_extensions() -> ExtensionRegistry:
    """Строит registry с несколькими fake providers для startup browser coverage."""
    study_manifest = _build_fake_manifest(
        alias="study_planner",
        title="Study Planner",
        description="Study planning extension for Selenium coverage",
        stage_graph=[
            StageSpec(stage_id="courses", label="Courses"),
            StageSpec(stage_id="time_budget", label="Time Budget"),
            StageSpec(stage_id="priorities", label="Priorities", depends_on=["courses"]),
        ],
    )
    lab_manifest = _build_fake_manifest(
        alias="lab_planner",
        title="Lab Planner",
        description="Lab planning extension for Selenium coverage",
        stage_graph=[
            StageSpec(stage_id="labs", label="Labs"),
            StageSpec(stage_id="equipment", label="Equipment"),
            StageSpec(stage_id="calendar", label="Calendar", depends_on=["labs"]),
        ],
    )
    return ExtensionRegistry.discover(
        entry_points=[
            _FakeEntryPoint(
                name="study_planner",
                provider=_BrowserFakeProvider(study_manifest),
            ),
            _FakeEntryPoint(
                name="lab_planner",
                provider=_BrowserFakeProvider(lab_manifest),
                module="tests.e2e.fake_lab_extension_provider",
            ),
        ]
    )


_SHOWCASE_PAUSE_SECONDS = 6.0
_STATE_READING_PAUSE_SECONDS = 5.0
_SHORT_SHOWCASE_PAUSE_SECONDS = 1.5
_SHORT_STATE_READING_PAUSE_SECONDS = 1.3
_SHORT_ERROR_PAUSE_SECONDS = 1.7


def _commands_for_payloads(payloads: dict[str, dict]) -> list[str]:
    """Преобразует stage payloads в список `json <stage> ...` команд."""
    return [_stage_json(stage, payload) for stage, payload in payloads.items()]


def _run_screencast_script(chat_page, steps: list[ScreencastStep]) -> None:
    """Исполняет script-like последовательность шагов для видео-демо."""
    for step in steps:
        if step.kind == "select_model":
            chat_page.select_model(str(step.value), after_pause_seconds=step.after_pause_seconds)
            continue
        if step.kind == "type_message":
            chat_page.send_message(
                str(step.value),
                typing_mode="type",
                after_pause_seconds=step.after_pause_seconds,
            )
            continue
        if step.kind == "chunked_message":
            chat_page.send_message(
                str(step.value),
                typing_mode="chunked",
                after_pause_seconds=step.after_pause_seconds,
            )
            continue
        chat_page.pause(float(step.value))


def _assert_or_results_rendered(chat_page) -> None:
    """Проверяет, что UI показал результат OR-пайплайна."""
    assert chat_page.has_testid("production-result-card")
    assert chat_page.has_testid("shipment-result-card")
    assert chat_page.has_testid("assignment-result-card")
    assert chat_page.has_testid("routing-result-card")
    assert "build_routes" in chat_page.text_of("trace-value")
    assert chat_page.last_chat_message(role="assistant")


def _assert_openai_results_rendered(chat_page) -> None:
    """Проверяет, что real-provider flow завершился без deterministic fallback."""
    _assert_or_results_rendered(chat_page)
    assert not chat_page.has_testid("warnings-card")
    assert "Результат рассчитан детерминированным OR-пайплайном" not in chat_page.last_chat_message(
        role="assistant"
    )


def _draft_from_last_assistant_message(chat_page) -> dict[str, object]:
    """Парсит JSON-представление draft из последнего assistant-сообщения."""
    message = chat_page.last_chat_message(role="assistant")
    prefix = "Текущий draft:\n"
    if prefix not in message:
        raise AssertionError("Последнее assistant-сообщение не содержит сериализованный draft.")
    return json.loads(message.split(prefix, maxsplit=1)[1])


@pytest.fixture()
def require_openai_provider(request) -> None:
    """Пропускает real-provider сценарии без явного opt-in и API key."""
    needs_openai = (
        request.node.get_closest_marker("openai_smoke")
        or request.node.get_closest_marker("openai_video_demo")
        or request.node.get_closest_marker("openai_short_video_demo")
    )
    if not needs_openai:
        return
    if os.getenv("E2E_OPENAI_SMOKE") != "1":
        pytest.skip("Set E2E_OPENAI_SMOKE=1 to run real OpenAI browser scenarios.")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not present in the current shell environment.")


def test_homepage_renders_workspace_and_local_htmx(chat_page, live_server: str) -> None:
    """Проверяет первичный рендер страницы и локальную раздачу HTMX asset."""
    assert chat_page.session_id()
    assert chat_page.text_of("session-id-value") == chat_page.session_id()
    assert chat_page.find_by_testid("model-alias-select").get_attribute("value") == "openai_default"
    assert "load preset demo" in chat_page.last_chat_message(role="assistant")
    assert "/static/vendor/htmx-2.0.4.min.js" in chat_page.driver.page_source
    assert "https://unpkg.com" not in chat_page.driver.page_source

    asset_response = httpx.get(f"{live_server}/static/vendor/htmx-2.0.4.min.js", timeout=2.0)
    assert asset_response.status_code == 200
    assert "htmx" in asset_response.text


@pytest.mark.parametrize(
    "extension_registry",
    [pytest.param(_registry_with_study_planner(), id="study-planner-registry")],
    indirect=True,
)
def test_homepage_renders_with_non_empty_extension_registry(chat_page, web_app) -> None:
    """Проверяет browser startup-path с непустым custom extension registry."""
    assert web_app.state.extension_registry.aliases() == ["study_planner"]
    assert chat_page.session_id()
    assert chat_page.text_of("session-id-value") == chat_page.session_id()
    assert "load preset demo" in chat_page.last_chat_message(role="assistant")


@pytest.mark.parametrize(
    "extension_registry",
    [pytest.param(_registry_with_study_planner(), id="study-planner-registry")],
    indirect=True,
)
def test_default_browser_flow_still_runs_with_custom_extension_registry(chat_page, web_app) -> None:
    """Проверяет, что current HTMX OR-flow не ломается при наличии custom registry."""
    discovered = web_app.state.extension_registry.require("study_planner")
    assert discovered.manifest.topological_stage_ids() == [
        "courses",
        "time_budget",
        "priorities",
    ]

    chat_page.send_message("load preset demo")
    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


@pytest.mark.parametrize(
    "extension_registry",
    [pytest.param(_registry_with_multiple_extensions(), id="multi-extension-registry")],
    indirect=True,
)
def test_homepage_renders_with_multiple_extensions_in_registry(chat_page, web_app) -> None:
    """Проверяет startup browser path c несколькими fake extensions в registry."""
    assert web_app.state.extension_registry.aliases() == ["lab_planner", "study_planner"]
    assert web_app.state.extension_registry.require("lab_planner").manifest.title == "Lab Planner"
    assert (
        web_app.state.extension_registry.require("study_planner").manifest.title == "Study Planner"
    )
    assert chat_page.session_id()
    assert "load preset demo" in chat_page.last_chat_message(role="assistant")


@pytest.mark.parametrize(
    "extension_registry",
    [pytest.param(_registry_with_multiple_extensions(), id="multi-extension-registry")],
    indirect=True,
)
def test_default_browser_flow_still_runs_with_multiple_extensions_registry(
    chat_page, web_app
) -> None:
    """Проверяет, что default HTMX OR-flow не ломается при registry из нескольких extensions."""
    discovered = {
        item.alias: item.manifest.topological_stage_ids()
        for item in web_app.state.extension_registry.all()
    }
    assert set(discovered["lab_planner"][:2]) == {"labs", "equipment"}
    assert discovered["lab_planner"][-1] == "calendar"
    assert discovered["study_planner"] == ["courses", "time_budget", "priorities"]

    chat_page.send_message("load preset demo")
    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


def test_start_flow_shows_drafting_state_and_human_labels(chat_page) -> None:
    """Проверяет стартовый wizard flow после команды `start`."""
    chat_page.send_message("start")

    assert chat_page.text_of("collection-phase") == "drafting"
    assert chat_page.text_of("current-stage-value") == "production"
    assert "Заполните stage Production" in chat_page.last_chat_message(role="assistant")
    assert chat_page.has_testid("missing-fields-card")
    assert "1) Production" in [
        chip.text for chip in chat_page.find_all_by_testid("missing-field-chip")
    ]


def test_help_command_shows_cheat_sheet_in_chat(chat_page) -> None:
    """Проверяет, что `help` показывает пользователю список поддерживаемых команд."""
    chat_page.send_message("help")

    reply = chat_page.last_chat_message(role="assistant")
    assert "Команды: start, show input, next, run, load preset demo" in reply
    assert "edit <stage>, json <stage> {..}, set <stage>.<field> <value>, reset." in reply


def test_show_input_renders_serialized_draft_in_chat(chat_page) -> None:
    """Проверяет, что `show input` выводит сериализованный draft прямо в чат."""
    chat_page.send_message("load preset demo")
    chat_page.send_message("show input")

    reply = chat_page.last_chat_message(role="assistant")
    assert "Текущий draft:" in reply
    assert '"preset_ref": "demo"' in reply
    assert '"production": {' in reply


def test_load_preset_demo_and_run_renders_results(chat_page) -> None:
    """Проверяет быстрый happy-path `load preset demo` -> `run`."""
    chat_page.send_message("load preset demo")
    assert chat_page.text_of("preset-value") == "demo"
    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


def test_russian_command_aliases_cover_start_show_next_run_and_reset(chat_page) -> None:
    """Проверяет ru-aliases команд интерактивного flow через live UI."""
    chat_page.send_message("старт")
    assert chat_page.text_of("current-stage-value") == "production"

    chat_page.send_message("edit routing")
    assert chat_page.text_of("current-stage-value") == "routing"

    chat_page.send_message("далее")
    assert chat_page.text_of("current-stage-value") == "production"

    chat_page.send_message("загрузить демо")
    assert chat_page.text_of("preset-value") == "demo"
    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("показать")
    draft = _draft_from_last_assistant_message(chat_page)
    assert draft["preset_ref"] == "demo"

    chat_page.send_message("запуск")
    _assert_or_results_rendered(chat_page)

    chat_page.send_message("сброс")
    assert chat_page.has_testid("empty-results-card")
    assert not chat_page.has_testid("production-result-card")
    assert chat_page.text_of("ready-to-run-value") == "Нет"


def test_manual_command_flow_reaches_successful_run(chat_page) -> None:
    """Проверяет командный flow через `json` и `set` до успешного результата."""
    chat_page.send_message("start")
    chat_page.send_message(PRODUCTION_JSON)
    chat_page.send_message(SHIPMENT_JSON)
    chat_page.send_message(ASSIGNMENT_JSON)
    chat_page.send_message(ROUTING_JSON)
    chat_page.send_message("set production.profits [41,31]")

    assert chat_page.text_of("ready-to-run-value") == "Да"
    assert "production.profits" in chat_page.last_chat_message(role="assistant")

    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


def test_rejecting_nl_patches_clears_pending_state_without_mutating_draft(chat_page) -> None:
    """Проверяет явное отклонение `нет`: patch исчезает и draft не меняется."""
    chat_page.send_message("load preset demo")
    chat_page.send_message('production profits [41,31], products ["A","B"]')

    assert chat_page.has_testid("pending-patches-card")

    chat_page.send_message("нет")

    assert not chat_page.has_testid("pending-patches-card")
    assert "не применяю candidate patches" in chat_page.last_chat_message(role="assistant")
    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("show input")
    draft = _draft_from_last_assistant_message(chat_page)
    assert draft["production"]["profits"] == [40.0, 30.0]


def test_next_moves_to_first_missing_stage_and_updates_current_stage(chat_page) -> None:
    """Проверяет, что `next` возвращает wizard к первому незаполненному stage."""
    chat_page.send_message("start")
    chat_page.send_message(PRODUCTION_JSON)
    chat_page.send_message("edit routing")

    assert chat_page.text_of("current-stage-value") == "routing"

    chat_page.send_message("next")

    assert chat_page.text_of("current-stage-value") == "shipment"
    assert "Заполните stage Shipment" in chat_page.last_chat_message(role="assistant")


def test_edit_stage_then_raw_json_shortcut_updates_current_stage_payload(chat_page) -> None:
    """Проверяет `edit <stage>` + raw JSON shortcut без префикса `json`."""
    chat_page.send_message("start")
    chat_page.send_message("edit shipment")
    chat_page.send_message(SHIPMENT_SHORTCUT_JSON)

    assert chat_page.text_of("collection-mode") == "json"
    assert chat_page.text_of("stage-status-value-shipment") == "готов"

    chat_page.send_message("show input")

    reply = chat_page.last_chat_message(role="assistant")
    assert '"shipment": {' in reply
    assert '"warehouses": [' in reply
    assert '"client_demand": [' in reply


def test_post_run_input_change_invalidates_previous_result_until_explicit_rerun(chat_page) -> None:
    """Проверяет сброс OR-результата после изменения валидного draft post-run."""
    chat_page.send_message("load preset demo")
    chat_page.send_message("run")
    assert chat_page.has_testid("production-result-card")

    chat_page.send_message("set production.profits [44,34]")

    assert chat_page.has_testid("empty-results-card")
    assert not chat_page.has_testid("production-result-card")
    assert chat_page.has_testid("pre-run-summary-card")
    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("run")
    _assert_or_results_rendered(chat_page)


def test_partial_and_malformed_json_surface_validation_without_false_ready_state(chat_page) -> None:
    """Проверяет validation/error UX для partial и malformed JSON-команд."""
    chat_page.send_message("start")
    chat_page.send_message('json production {"products":["A","B"]}')

    assert chat_page.has_testid("validation-errors-card")
    assert chat_page.text_of("stage-status-value-production") == "не готов"
    assert chat_page.text_of("ready-to-run-value") == "Нет"
    assert not chat_page.has_testid("pre-run-summary-card")

    chat_page.send_message('json production {"products":["A","B"]')

    assert "Ошибка ввода: Некорректный JSON:" in chat_page.last_chat_message(role="assistant")
    assert chat_page.text_of("ready-to-run-value") == "Нет"
    assert chat_page.has_testid("validation-errors-card")
    assert not chat_page.has_testid("pre-run-summary-card")


def test_run_is_blocked_for_multi_stage_incomplete_draft(chat_page) -> None:
    """Проверяет блокировку `run`, когда заполнена только часть stage-ов."""
    chat_page.send_message("start")
    chat_page.send_message(PRODUCTION_JSON)
    chat_page.send_message(ASSIGNMENT_JSON)

    assert chat_page.text_of("ready-to-run-value") == "Нет"

    chat_page.send_message("run")

    assert not chat_page.has_testid("production-result-card")
    assert chat_page.has_testid("missing-fields-card")
    missing_chip_texts = [chip.text for chip in chat_page.find_all_by_testid("missing-field-chip")]
    assert "2) Shipment" in missing_chip_texts
    assert "4) Routing" in missing_chip_texts
    assert "Нельзя запустить OR" in chat_page.last_chat_message(role="assistant")


def test_stage_aliases_work_across_json_and_set_commands(chat_page) -> None:
    """Проверяет short stage aliases в `json` и `set` командах."""
    chat_page.send_message("start")
    chat_page.send_message(_stage_json("prod", FAST_PAYLOADS["production"]))
    chat_page.send_message(_stage_json("ship", FAST_PAYLOADS["shipment"]))
    chat_page.send_message(_stage_json("assign", FAST_PAYLOADS["assignment"]))
    chat_page.send_message(_stage_json("route", FAST_PAYLOADS["routing"]))
    chat_page.send_message("set prod.profits [41,31]")

    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("show input")
    draft = _draft_from_last_assistant_message(chat_page)
    assert draft["production"]["profits"] == [41, 31]
    assert draft["routing"]["depot_index"] == 0


def test_russian_stage_aliases_and_assignment_raw_json_shortcut_work(chat_page) -> None:
    """Проверяет ru stage aliases для `json`/`set`/`edit` и raw JSON для assignment."""
    chat_page.send_message("старт")
    chat_page.send_message(_stage_json("производство", FAST_PAYLOADS["production"]))
    chat_page.send_message("edit назначение")
    chat_page.send_message(json.dumps(FAST_PAYLOADS["assignment"], ensure_ascii=False))
    chat_page.send_message("set производство.profits [41,31]")

    assert chat_page.text_of("collection-mode") == "wizard"
    assert chat_page.text_of("stage-status-value-production") == "готов"
    assert chat_page.text_of("stage-status-value-assignment") == "готов"

    chat_page.send_message("show input")
    draft = _draft_from_last_assistant_message(chat_page)
    assert draft["production"]["profits"] == [41, 31]
    assert draft["assignment"]["resources"] == ["truck_1", "truck_2", "truck_3"]


def test_nl_flow_requires_confirmation_and_then_runs(chat_page) -> None:
    """Проверяет NL extraction -> подтверждение -> успешный `run`."""
    chat_page.send_message("load preset demo")
    chat_page.send_message('production profits [41,31], products ["A","B"]')

    assert chat_page.has_testid("pending-patches-card")
    assert any(
        "production.profits" in row.text
        for row in chat_page.find_all_by_testid("pending-patch-row")
    )

    chat_page.send_message("да")

    assert not chat_page.has_testid("pending-patches-card")
    assert "Параметры подтверждены" in chat_page.last_chat_message(role="assistant")

    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


def test_run_is_blocked_when_nl_patches_are_pending(chat_page) -> None:
    """Проверяет safety-блокировку `run` до подтверждения NL patch-ей."""
    chat_page.send_message("start")
    chat_page.send_message('production profits [40,30], products ["A","B"]')

    assert chat_page.has_testid("pending-patches-card")

    chat_page.send_message("run")

    assert chat_page.has_testid("pending-patches-card")
    assert "Нельзя запускать расчёт" in chat_page.last_chat_message(role="assistant")
    assert not chat_page.has_testid("production-result-card")


def test_ambiguity_flow_shows_precise_question_without_applying_patch(chat_page) -> None:
    """Проверяет ambiguity flow без применения неоднозначного ввода."""
    chat_page.send_message("для production и shipment задай cost_matrix [[1,2],[2,1]]")

    assert chat_page.has_testid("uncertainties-card")
    assert not chat_page.has_testid("pending-patches-card")
    assert "несколько stages" in chat_page.last_chat_message(role="assistant").lower()
    assert chat_page.text_of("stage-status-value-production") == "не готов"


def test_reset_clears_results_and_returns_to_initial_flow(chat_page) -> None:
    """Проверяет, что `reset` очищает результат и возвращает wizard к production."""
    chat_page.send_message("load preset demo")
    chat_page.send_message("run")
    assert chat_page.has_testid("production-result-card")

    chat_page.send_message("reset")

    assert not chat_page.has_testid("production-result-card")
    assert chat_page.has_testid("empty-results-card")
    assert chat_page.text_of("current-stage-value") == "production"
    assert "Черновик сброшен" in chat_page.last_chat_message(role="assistant")


def test_provider_unavailable_flow_uses_deterministic_explanation(chat_page, monkeypatch) -> None:
    """Проверяет fallback при недоступном локальном LLM-провайдере."""
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    chat_page.select_model("local_default")
    chat_page.send_message("load preset demo")
    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)
    assert chat_page.has_testid("warnings-card")
    assert "Результат рассчитан детерминированным OR-пайплайном" in chat_page.last_chat_message(
        role="assistant"
    )


@pytest.mark.openai_smoke
def test_openai_browser_smoke(chat_page, require_openai_provider) -> None:
    """Проверяет быстрый real-provider smoke без screencast-пауз."""
    del require_openai_provider

    chat_page.select_model("openai_default")
    chat_page.send_message("load preset demo")
    chat_page.send_message("run")

    _assert_openai_results_rendered(chat_page)


@pytest.mark.openai_short_video_demo
def test_openai_short_video_preset_overview(chat_page, require_openai_provider) -> None:
    """Короткий ролик: быстрый preset overview через OpenAI."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "load preset demo"),
            ScreencastStep("type_message", "run"),
        ],
    )

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_russian_aliases(chat_page, require_openai_provider) -> None:
    """Короткий ролик: русские alias-команды в живом чате."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "загрузить демо"),
            ScreencastStep(
                "type_message", "показать", after_pause_seconds=_SHORT_SHOWCASE_PAUSE_SECONDS
            ),
            ScreencastStep("type_message", "запуск"),
        ],
    )

    assert any("Текущий draft:" in message for message in chat_page.chat_messages(role="assistant"))
    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_wizard_and_raw_json(chat_page, require_openai_provider) -> None:
    """Короткий ролик: wizard + edit stage + raw JSON shortcut."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "start"),
            ScreencastStep("type_message", "edit shipment"),
            ScreencastStep(
                "chunked_message",
                SHIPMENT_SHORTCUT_JSON,
                after_pause_seconds=_SHORT_SHOWCASE_PAUSE_SECONDS,
            ),
            ScreencastStep("type_message", "show input"),
        ],
    )

    assert chat_page.text_of("stage-status-value-shipment") == "готов"
    assert '"shipment": {' in chat_page.last_chat_message(role="assistant")
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_manual_json_run(chat_page, require_openai_provider) -> None:
    """Короткий ролик: компактный deterministic DSL flow до `run`."""
    del require_openai_provider

    steps = [
        ScreencastStep("select_model", "openai_default"),
        ScreencastStep("type_message", "start"),
    ]
    steps.extend(
        ScreencastStep("chunked_message", command)
        for command in _commands_for_payloads(FAST_PAYLOADS)
    )
    steps.append(ScreencastStep("type_message", "run"))
    _run_screencast_script(chat_page, steps)

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_nl_confirm(chat_page, require_openai_provider) -> None:
    """Короткий ролик: NL patch -> подтверждение -> успешный run."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "load preset demo"),
            ScreencastStep(
                "chunked_message",
                'production profits [41,31], products ["A","B"]',
                after_pause_seconds=_SHORT_STATE_READING_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.has_testid("pending-patches-card")

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("type_message", "да"),
            ScreencastStep("type_message", "run"),
        ],
    )

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_nl_reject(chat_page, require_openai_provider) -> None:
    """Короткий ролик: отклонение candidate patches через `нет`."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "load preset demo"),
            ScreencastStep(
                "chunked_message",
                'production profits [41,31], products ["A","B"]',
                after_pause_seconds=_SHORT_STATE_READING_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.has_testid("pending-patches-card")

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("type_message", "нет"),
            ScreencastStep(
                "type_message", "show input", after_pause_seconds=_SHORT_SHOWCASE_PAUSE_SECONDS
            ),
        ],
    )

    assert not chat_page.has_testid("pending-patches-card")
    assert '"profits": [' in chat_page.last_chat_message(role="assistant")
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_validation_recovery(chat_page, require_openai_provider) -> None:
    """Короткий ролик: validation error и восстановление валидного stage."""
    del require_openai_provider

    partial_production = _stage_json(
        "production",
        {"products": FAST_PAYLOADS["production"]["products"]},
    )
    malformed_production = 'json production {"products":["A","B"]'
    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "start"),
            ScreencastStep(
                "chunked_message",
                partial_production,
                after_pause_seconds=_SHORT_ERROR_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                malformed_production,
                after_pause_seconds=_SHORT_ERROR_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                PRODUCTION_JSON,
                after_pause_seconds=_SHORT_SHOWCASE_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.text_of("stage-status-value-production") == "готов"
    assert chat_page.has_testid("validation-errors-card")
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_short_video_demo
def test_openai_short_video_ambiguity_resolution(chat_page, require_openai_provider) -> None:
    """Короткий ролик: ambiguity -> уточнение -> подтверждение -> run."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "load preset demo"),
            ScreencastStep(
                "chunked_message",
                "для production и shipment задай cost_matrix [[5,6,8],[4,5,3]]",
                after_pause_seconds=_SHORT_STATE_READING_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.has_testid("uncertainties-card")

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep(
                "chunked_message",
                "для shipment cost_matrix [[5,6,8],[4,5,3]]",
                after_pause_seconds=_SHORT_STATE_READING_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.has_testid("pending-patches-card")

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("type_message", "да"),
            ScreencastStep("type_message", "run"),
        ],
    )

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_video_demo
def test_openai_video_preset_overview(chat_page, require_openai_provider) -> None:
    """Пишет и проверяет базовый OpenAI video smoke с demo preset."""
    del require_openai_provider

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "load preset demo"),
            ScreencastStep(
                "type_message", "show input", after_pause_seconds=_SHOWCASE_PAUSE_SECONDS
            ),
            ScreencastStep("type_message", "run"),
        ],
    )

    assert any("Текущий draft:" in message for message in chat_page.chat_messages(role="assistant"))
    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_video_demo
def test_openai_video_manual_json_flow(chat_page, require_openai_provider) -> None:
    """Пишет длинный manual JSON flow с отдельным набором входных данных."""
    del require_openai_provider

    steps = [
        ScreencastStep("select_model", "openai_default"),
        ScreencastStep("type_message", "start"),
    ]
    steps.extend(
        ScreencastStep("chunked_message", command, after_pause_seconds=_STATE_READING_PAUSE_SECONDS)
        for command in _commands_for_payloads(MANUAL_VIDEO_PAYLOADS)
    )
    steps.extend(
        [
            ScreencastStep("type_message", "set production.profits [53,39]"),
            ScreencastStep(
                "type_message", "show input", after_pause_seconds=_SHOWCASE_PAUSE_SECONDS
            ),
            ScreencastStep("type_message", "run"),
        ]
    )
    _run_screencast_script(chat_page, list(steps))

    assert chat_page.text_of("ready-to-run-value") == "Да"
    assert "Atlas" in "\n".join(chat_page.chat_messages(role="assistant"))
    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_video_demo
def test_openai_video_nl_confirm_flow(chat_page, require_openai_provider) -> None:
    """Пишет OpenAI video flow со свободным текстом и подтверждением patch-ей."""
    del require_openai_provider

    setup_steps = [
        ScreencastStep("select_model", "openai_default"),
        ScreencastStep("type_message", "start"),
    ]
    setup_steps.extend(
        ScreencastStep("chunked_message", command, after_pause_seconds=_STATE_READING_PAUSE_SECONDS)
        for command in _commands_for_payloads(NL_VIDEO_PAYLOADS)
    )
    setup_steps.append(
        ScreencastStep(
            "chunked_message",
            "production profits [49,37], pallet_factors [1.0,0.95]",
            after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
        )
    )
    _run_screencast_script(chat_page, list(setup_steps))

    assert chat_page.has_testid("pending-patches-card")
    assert any(
        "production.profits" in row.text
        for row in chat_page.find_all_by_testid("pending-patch-row")
    )

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("type_message", "да"),
            ScreencastStep("type_message", "run"),
        ],
    )

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_video_demo
def test_openai_video_validation_recovery_flow(chat_page, require_openai_provider) -> None:
    """Пишет OpenAI video flow с validation error и последующим исправлением."""
    del require_openai_provider

    partial_production = _stage_json(
        "production",
        {"products": VALIDATION_VIDEO_PAYLOADS["production"]["products"]},
    )
    malformed_production = 'json production {"products":["Delta","Echo"]'
    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("select_model", "openai_default"),
            ScreencastStep("type_message", "start"),
            ScreencastStep(
                "chunked_message",
                partial_production,
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                malformed_production,
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                _stage_json("production", VALIDATION_VIDEO_PAYLOADS["production"]),
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                _stage_json("shipment", VALIDATION_VIDEO_PAYLOADS["shipment"]),
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                _stage_json("assignment", VALIDATION_VIDEO_PAYLOADS["assignment"]),
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep(
                "chunked_message",
                _stage_json("routing", VALIDATION_VIDEO_PAYLOADS["routing"]),
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
            ScreencastStep("type_message", "run"),
        ],
    )

    assert "Ошибка ввода: Некорректный JSON:" in "\n".join(
        chat_page.chat_messages(role="assistant")
    )
    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()


@pytest.mark.openai_video_demo
def test_openai_video_ambiguity_resolution_flow(chat_page, require_openai_provider) -> None:
    """Пишет OpenAI video flow с ambiguity, уточнением и подтверждением patch-а."""
    del require_openai_provider

    setup_steps = [
        ScreencastStep("select_model", "openai_default"),
        ScreencastStep("type_message", "start"),
    ]
    setup_steps.extend(
        ScreencastStep("chunked_message", command, after_pause_seconds=_STATE_READING_PAUSE_SECONDS)
        for command in _commands_for_payloads(AMBIGUITY_VIDEO_PAYLOADS)
    )
    setup_steps.append(
        ScreencastStep(
            "chunked_message",
            "для production и shipment задай cost_matrix [[5,6,8],[4,5,3]]",
            after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
        )
    )
    _run_screencast_script(chat_page, list(setup_steps))

    assert chat_page.has_testid("uncertainties-card")
    assert "несколько stages" in chat_page.last_chat_message(role="assistant").lower()

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep(
                "chunked_message",
                "для shipment cost_matrix [[5,6,8],[4,5,3]]",
                after_pause_seconds=_STATE_READING_PAUSE_SECONDS,
            ),
        ],
    )

    assert chat_page.has_testid("pending-patches-card")
    assert any(
        "shipment.cost_matrix" in row.text
        for row in chat_page.find_all_by_testid("pending-patch-row")
    )

    _run_screencast_script(
        chat_page,
        [
            ScreencastStep("type_message", "да"),
            ScreencastStep("type_message", "run"),
        ],
    )

    _assert_openai_results_rendered(chat_page)
    chat_page.pause_for_screencast_finish()
