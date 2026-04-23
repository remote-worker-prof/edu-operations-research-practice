"""Browser E2E for the primary React chat shell served from `/app/*`."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def _assert_react_study_planner_results(react_chat_page) -> None:
    """Проверяет итоговые generic results для study_planner в React shell."""
    react_chat_page.wait_for_condition(
        lambda: len(react_chat_page.find_all_by_testid("result-section-title")) >= 6,
        failure_message="Study planner results did not appear in the React shell.",
    )
    assert react_chat_page.result_titles() == [
        "Всего часов в распоряжении",
        "Всего часов нужно",
        "Сколько часов распределили",
        "Сколько часов осталось",
        "Суммарная полезность плана",
        "План по курсам",
    ]
    rows = react_chat_page.result_rows()
    assert any("Math" in row for row in rows)
    assert any("Databases" in row for row in rows)


def _assert_react_transportation_results(react_chat_page) -> None:
    """Проверяет matrix/table results для transportation в React shell."""
    react_chat_page.wait_for_condition(
        lambda: len(react_chat_page.find_all_by_testid("result-section-title")) >= 5,
        failure_message="Transportation results did not appear in the React shell.",
    )
    assert react_chat_page.result_titles() == [
        "Всего доступно (груз)",
        "Всего требуется (груз)",
        "Всего перевезено (груз)",
        "Итоговая стоимость перевозки",
        "План перевозки",
    ]
    rows = react_chat_page.result_rows()
    assert any("North" in row for row in rows)
    assert any("15.0" in row or "15" in row for row in rows)


def test_root_redirects_to_primary_react_chat_shell(react_chat_page) -> None:
    """Product root should land the user in the new React shell under `/app/`."""
    assert react_chat_page.current_path() == "/app/"
    assert "Study Planner" in react_chat_page.text_of("active-extension-title")


def test_react_chat_guided_study_planner_flow_runs_without_raw_payloads(react_chat_page) -> None:
    """Beginner flow should complete study_planner entirely through generated editors."""
    assert "Study Planner" in react_chat_page.text_of("active-extension-title")
    assert react_chat_page.text_of("current-stage-value") == "courses"

    react_chat_page.fill_current_table(
        [
            ["Math", 30],
            ["ML", 24],
            ["Databases", 18],
        ]
    )
    react_chat_page.submit_current_step()
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("current-stage-value") == "time_budget",
        failure_message="Study planner did not advance to time_budget.",
    )

    react_chat_page.fill_current_scalars([12, 4])
    react_chat_page.submit_current_step()
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("current-stage-value") == "priorities",
        failure_message="Study planner did not advance to priorities.",
    )

    react_chat_page.fill_current_vector([0.5, 0.3, 0.2])
    react_chat_page.submit_current_step()
    react_chat_page.click_quick_action("solve-button")

    _assert_react_study_planner_results(react_chat_page)


def test_react_chat_transportation_matrix_flow_uses_generated_matrix_editor(
    react_chat_page,
) -> None:
    """The 2-D transportation bundle should run through table + matrix editors."""
    react_chat_page.create_new_thread("transportation")
    react_chat_page.wait_for_condition(
        lambda: "Transportation Planner" in react_chat_page.text_of("active-extension-title"),
        failure_message="Transportation thread did not become active.",
    )
    assert react_chat_page.text_of("current-stage-value") == "origins"

    react_chat_page.fill_current_table([["North", 20], ["South", 25]])
    react_chat_page.submit_current_step()
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("current-stage-value") == "destinations",
        failure_message="Transportation flow did not advance to destinations.",
    )

    react_chat_page.fill_current_table([["East", 15], ["West", 30]])
    react_chat_page.submit_current_step()
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("current-stage-value") == "costs",
        failure_message="Transportation flow did not advance to costs.",
    )

    react_chat_page.fill_current_matrix([[4, 6], [5, 4]])
    react_chat_page.submit_current_step()
    react_chat_page.click_quick_action("solve-button")

    _assert_react_transportation_results(react_chat_page)


def test_react_chat_keeps_default_or_available_in_plain_chat_mode(react_chat_page) -> None:
    """Legacy default_or should still work in the new shell through plain chat messaging."""
    react_chat_page.create_new_thread("default_or")
    react_chat_page.wait_for_condition(
        lambda: "Default OR Pipeline" in react_chat_page.text_of("active-extension-title"),
        failure_message="default_or thread did not become active.",
    )
    assert react_chat_page.find_by_testid("plain-chat-hint")

    react_chat_page.send_power_message(
        "Покажи, какие этапы сейчас доступны в стандартном OR-конвейере."
    )

    answer = react_chat_page.last_assistant_message().lower()
    assert "production" in answer
    assert "shipment" in answer
    assert "routing" in answer


def test_react_chat_guided_and_power_modes_change_nl_apply_behavior(react_chat_page) -> None:
    """Guided mode should confirm NL patches, while power mode may auto-apply them."""
    assert react_chat_page.text_of("interaction-mode-value") == "guided"

    react_chat_page.send_power_message(
        'courses course_names ["Math","Physics"], required_hours [12,18]'
    )
    react_chat_page.wait_for_condition(
        lambda: len(react_chat_page.find_all_by_testid("pending-proposals-card")) == 1,
        failure_message="Guided mode did not surface confirmation proposals.",
    )
    assert react_chat_page.text_of("current-stage-value") == "courses"

    react_chat_page.confirm_pending_proposals()
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("current-stage-value") == "time_budget",
        failure_message="Подтверждённые guided proposals не перевели сценарий к time_budget.",
    )

    react_chat_page.create_new_thread("default_or")
    react_chat_page.wait_for_condition(
        lambda: "Default OR Pipeline" in react_chat_page.text_of("active-extension-title"),
        failure_message="default_or thread did not become active.",
    )
    react_chat_page.set_interaction_mode("power")
    react_chat_page.send_power_message(
        'production products ["A","B"], profits [40,30], '
        'resource_matrix [[2,1],[1,1.5]], resource_limits [240,180], '
        'demand_upper_bounds [70,80], pallet_factors [1.0,0.8]'
    )
    react_chat_page.wait_for_condition(
        lambda: react_chat_page.text_of("interaction-mode-value") == "power"
        and "Изменения применены." in react_chat_page.last_assistant_message(),
        failure_message="Power mode не автоприменил grounded NL patch.",
    )
    assert react_chat_page.find_all_by_testid("pending-proposals-card") == []


def test_react_chat_can_explain_default_or_model_through_semantics_adapter(
    react_chat_page,
) -> None:
    """Migrated default_or should expose read-only model explanations in the new shell."""
    react_chat_page.create_new_thread("default_or")
    react_chat_page.wait_for_condition(
        lambda: "Default OR Pipeline" in react_chat_page.text_of("active-extension-title"),
        failure_message="default_or thread did not become active.",
    )

    react_chat_page.send_power_message("/explain model")
    answer = react_chat_page.last_assistant_message().lower()
    assert "четырёхэтапный or-конвейер" in answer
