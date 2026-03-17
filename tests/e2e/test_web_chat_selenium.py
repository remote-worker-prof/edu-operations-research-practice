"""Browser E2E тесты HTMX-интерфейса через Selenium + headless Chromium."""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.e2e

PRODUCTION_JSON = (
    'json production {"products":["A","B"],"profits":[40,30],'
    '"resource_matrix":[[2,1],[1,1.5]],"resource_limits":[240,180],'
    '"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}'
)
SHIPMENT_JSON = (
    'json shipment {"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],'
    '"clients":["C1","C2","C3"],"client_demand":[42,38,40],'
    '"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}'
)
ASSIGNMENT_JSON = (
    'json assignment {"resources":["truck_1","truck_2","truck_3"],'
    '"cost_matrix":[[8,6,7],[5,8,6],[7,5,9]]}'
)
ROUTING_JSON = (
    'json routing {"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],'
    '"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}'
)


def _assert_or_results_rendered(chat_page) -> None:
    """Проверяет, что UI показал результат OR-пайплайна."""
    assert chat_page.has_testid("production-result-card")
    assert chat_page.has_testid("shipment-result-card")
    assert chat_page.has_testid("assignment-result-card")
    assert chat_page.has_testid("routing-result-card")
    assert "build_routes" in chat_page.text_of("trace-value")
    assert chat_page.last_chat_message(role="assistant")


@pytest.fixture()
def require_openai_smoke() -> None:
    """Пропускает real-provider smoke без явного opt-in и API key."""
    if os.getenv("E2E_OPENAI_SMOKE") != "1":
        pytest.skip("Set E2E_OPENAI_SMOKE=1 to run real OpenAI browser smoke tests.")
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


def test_load_preset_demo_and_run_renders_results(chat_page) -> None:
    """Проверяет быстрый happy-path `load preset demo` -> `run`."""
    chat_page.send_message("load preset demo")
    assert chat_page.text_of("preset-value") == "demo"
    assert chat_page.text_of("ready-to-run-value") == "Да"

    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)


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
def test_openai_browser_smoke(chat_page, require_openai_smoke) -> None:
    """Минимальный browser smoke через реальный OpenAI provider."""
    del require_openai_smoke
    chat_page.select_model("openai_default")
    chat_page.send_message("load preset demo")
    chat_page.send_message("run")

    _assert_or_results_rendered(chat_page)
    assert not chat_page.has_testid("warnings-card")
    assert "Результат рассчитан детерминированным OR-пайплайном" not in chat_page.last_chat_message(
        role="assistant"
    )
    chat_page.pause_for_screencast_finish()
