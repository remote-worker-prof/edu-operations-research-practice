"""Интеграционные тесты API и HTMX-потока web-приложения.

Каждый тест проверяет конкретный пользовательский или деградированный сценарий,
чтобы минимизировать риск регрессий в учебном демо.
"""

import re

from agent_core.config import model_aliases, model_options
from fastapi.testclient import TestClient
from or_core.exceptions import ORPipelineError
from webapp.main import app, service

client = TestClient(app)


def test_api_chat_turn_success(monkeypatch) -> None:
    """Проверяет happy-path JSON endpoint с корректными входными параметрами.

    Риск:
    - базовый end-to-end путь может сломаться при изменении графа/сервиса.
    """
    # Arrange
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    # Act: сначала загружаем preset
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "run",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is not None


def test_api_run_without_manual_routing_demands() -> None:
    """Проверяет, что `routing.client_demands` не требуется во входном draft.

    Риск:
    - чат может требовать ручной ввод derived-поля, что ломает идею связного OR-конвейера.
    """
    # Arrange / Act
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    commands = [
        (
            "json production "
            '{"products":["A","B"],"profits":[40,30],"resource_matrix":[[2,1],[1,1.5]],'
            '"resource_limits":[240,180],"demand_upper_bounds":[70,80],"pallet_factors":[1.0,0.8]}'
        ),
        (
            "json shipment "
            '{"warehouses":["W1","W2"],"warehouse_supply_ratio":[0.55,0.45],'
            '"clients":["C1","C2","C3"],"client_demand":[42,38,40],'
            '"cost_matrix":[[4,6,8],[5,4,3]],"capacity_matrix":[[50,45,40],[40,45,50]]}'
        ),
        (
            "json assignment "
            '{"resources":["truck_1","truck_2","truck_3"],"cost_matrix":[[8,6,7],[5,8,6],[7,5,9]]}'
        ),
        (
            "json routing "
            '{"distance_matrix":[[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]],'
            '"depot_index":0,"client_nodes":[1,2,3],"vehicle_capacities":[55,45,45]}'
        ),
        "run",
    ]

    response_payload = None
    for command in commands:
        response = client.post(
            "/api/chat/turn",
            json={
                "session_id": session_id,
                "model_alias": "openai_default",
                "message": command,
            },
        )
        assert response.status_code == 200
        response_payload = response.json()

    # Assert
    assert response_payload is not None
    assert response_payload["session"]["or_result"] is not None
    assert "client_demands" not in response_payload["session"]["scenario_draft"]["routing"]


def test_api_provider_unavailable_warning(monkeypatch) -> None:
    """Проверяет fallback-объяснение при недоступном локальном провайдере.

    Риск:
    - при отсутствии провайдера система может перестать возвращать полезный ответ.
    """
    # Arrange
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    # Act
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "run",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["warnings"]
    assert payload["session"]["explanation"] is not None
    assert (
        "Результат рассчитан детерминированным OR-пайплайном" in payload["session"]["explanation"]
    )


def test_htmx_turn_full_cycle(monkeypatch) -> None:
    """Проверяет полный HTMX-цикл: старт страницы -> отправка формы -> рендер результата.

    Риск:
    - нарушение связки между HTML-формой и серверным partial-rendering.
    """
    # Arrange
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    page = client.get("/")
    assert page.status_code == 200

    match = re.search(r'name="session_id" value="([^"]+)"', page.text)
    assert match is not None
    session_id = match.group(1)

    preset_partial = client.post(
        "/chat/turn",
        data={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_partial.status_code == 200

    partial = client.post(
        "/chat/turn",
        data={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "run",
        },
    )
    # Assert
    assert partial.status_code == 200
    assert "Суммарная длина" in partial.text


def test_index_model_aliases_match_config() -> None:
    """Проверяет, что список alias в UI совпадает с конфигом.

    Риск:
    - расхождение между реальным конфигом и отображаемыми вариантами в интерфейсе.
    """
    # Arrange / Act
    page = client.get("/")
    assert page.status_code == 200

    # Assert
    options = re.findall(r'<option value="([^"]+)"', page.text)
    assert options == model_aliases()


def test_index_uses_human_friendly_model_labels() -> None:
    """Проверяет, что UI показывает понятные названия моделей вместо технических alias.

    Риск:
    - ухудшение учебного UX из-за утечки внутренних идентификаторов в интерфейс.
    """
    # Arrange / Act
    page = client.get("/")
    assert page.status_code == 200

    # Assert
    for option in model_options():
        assert option["label"] in page.text
        assert f">{option['alias']}<" not in page.text


def test_htmx_missing_fields_show_human_labels(monkeypatch) -> None:
    """Проверяет русские человеко-понятные подписи для недостающих параметров.

    Риск:
    - пользователь видит технические поля и не понимает, что вводить.
    """
    # Arrange
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    page = client.get("/")
    assert page.status_code == 200

    match = re.search(r'name="session_id" value="([^"]+)"', page.text)
    assert match is not None
    session_id = match.group(1)

    # Act
    partial = client.post(
        "/chat/turn",
        data={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "start",
        },
    )
    # Assert
    assert partial.status_code == 200
    assert "1) Production" in partial.text
    assert "2) Shipment" in partial.text
    assert "production" not in partial.text or "json production" in partial.text


def test_api_chat_turn_invalid_command_return_user_errors(monkeypatch) -> None:
    """Проверяет устойчивость к невалидной команде в чате.

    Риск:
    - parser может вернуть runtime-ошибку вместо человеко-понятного ответа.
    """

    # Act
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "openai_default",
            "message": "абракадабра без команды",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is None
    assert payload["assistant_message"]
    assert (
        "Ошибка ввода" in payload["assistant_message"]
        or "stage" in payload["assistant_message"].lower()
    )


def test_nl_happy_path_confirmation_and_run() -> None:
    """Проверяет NL-путь: извлечение -> подтверждение -> запуск расчёта.

    Риск:
    - natural-language путь может не собирать полный draft и не доходить до run.
    """
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    turns = [
        (
            'production products ["A","B"], profits [40,30], '
            "resource_matrix [[2,1],[1,1.5]], resource_limits [240,180], "
            "demand_upper_bounds [70,80], pallet_factors [1.0,0.8]"
        ),
        "да",
        (
            'shipment warehouses ["W1","W2"], warehouse_supply_ratio [0.55,0.45], '
            'clients ["C1","C2","C3"], client_demand [42,38,40], '
            "cost_matrix [[4,6,8],[5,4,3]], capacity_matrix [[50,45,40],[40,45,50]]"
        ),
        "да",
        (
            'assignment resources ["truck_1","truck_2","truck_3"], '
            "cost_matrix [[8,6,7],[5,8,6],[7,5,9]]"
        ),
        "да",
        (
            "routing distance_matrix [[0,10,12,8],[10,0,6,7],[12,6,0,9],[8,7,9,0]], "
            "depot_index 0, client_nodes [1,2,3], vehicle_capacities [55,45,45]"
        ),
        "да",
        "запусти расчёт",
    ]

    last_payload = None
    for message in turns:
        response = client.post(
            "/api/chat/turn",
            json={
                "session_id": session_id,
                "model_alias": "openai_default",
                "message": message,
            },
        )
        assert response.status_code == 200
        last_payload = response.json()

    assert last_payload is not None
    assert last_payload["session"]["or_result"] is not None
    assert last_payload["session"]["collection_state"]["phase"] in {"ready_to_run", "running"}


def test_nl_ambiguity_asks_one_precise_question() -> None:
    """Проверяет, что неоднозначная реплика не применяется без уточнения.

    Риск:
    - агент может испортить draft, если применит неуверенное извлечение.
    """
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "openai_default",
            "message": "для production и shipment задай cost_matrix [[1,2],[2,1]]",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["confirmation_state"]["pending_patches"] == []
    assert payload["session"]["nl_uncertainties"]
    assert "несколько stages" in payload["assistant_message"].lower()


def test_run_blocked_when_nl_patches_not_confirmed() -> None:
    """Проверяет safety-блокировку run при неподтверждённых NL-патчах.

    Риск:
    - система может запустить OR на непроверенных параметрах.
    """
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    patch_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": 'production profits [40,30], products ["A","B"]',
        },
    )
    assert patch_turn.status_code == 200
    assert patch_turn.json()["session"]["confirmation_state"]["pending_patches"]

    run_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": "run",
        },
    )
    assert run_turn.status_code == 200
    payload = run_turn.json()
    assert payload["session"]["or_result"] is None
    assert "неподтверждёнными" in payload["assistant_message"]


def test_api_chat_turn_or_pipeline_error(monkeypatch) -> None:
    """Проверяет пользовательскую обработку ошибки OR-пайплайна.

    Риск:
    - исключение OR-слоя может проброситься наружу и сломать HTTP-ответ.
    """

    def _raise_pipeline_error(*args, **kwargs):
        raise ORPipelineError("forced OR failure for test")

    # Arrange
    monkeypatch.setattr(service._or_pipeline, "run", _raise_pipeline_error)

    # Act
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "run",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is None
    assert payload["session"]["errors"]
    assert "forced OR failure for test" in " ".join(payload["session"]["errors"])
    assert "Не удалось выполнить шаг" in payload["assistant_message"]
