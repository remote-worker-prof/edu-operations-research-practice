"""Интеграционные тесты API и HTMX-потока web-приложения.

Каждый тест проверяет конкретный пользовательский или деградированный сценарий,
чтобы минимизировать риск регрессий в учебном демо.
"""

import re

from agent_core.config import model_aliases, model_options
from agent_core.llm import LLMClient
from agent_core.models import LLMResponse
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
    # Act
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is not None


def test_api_provider_unavailable_warning(monkeypatch) -> None:
    """Проверяет fallback-объяснение при недоступном локальном провайдере.

    Риск:
    - при отсутствии провайдера система может перестать возвращать полезный ответ.
    """
    # Arrange
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    # Act
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
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

    # Act
    partial = client.post(
        "/chat/turn",
        data={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
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
            "message": "Привет",
        },
    )
    # Assert
    assert partial.status_code == 200
    assert "Коэффициент спроса" in partial.text
    assert "Коэффициент ресурсов" in partial.text
    assert "demand_multiplier" not in partial.text
    assert "resource_multiplier" not in partial.text


def test_api_chat_turn_invalid_llm_values_return_user_errors(monkeypatch) -> None:
    """Проверяет устойчивость к нечисловым значениям, пришедшим от LLM.

    Риск:
    - невалидные данные extraction могут привести к падению вместо управляемой ошибки.
    """

    def _fake_complete(
        self: LLMClient,
        messages: list[dict[str, str]],
        model_alias: str,
        task_mode: str,
        temperature: float = 0,
    ) -> LLMResponse:
        return LLMResponse(
            content='{"demand_multiplier":"abc","resource_multiplier":"xyz"}',
            model_alias=model_alias,
            model_name="stub",
        )

    # Arrange
    monkeypatch.setattr(LLMClient, "complete", _fake_complete)

    # Act
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "openai_default",
            "message": "используй параметры из модели",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is None
    assert payload["session"]["errors"]
    assert "должен быть числом" in " ".join(payload["session"]["errors"])
    assert "Не удалось выполнить шаг" in payload["assistant_message"]


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
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "спрос 1.0 ресурс 1.0",
        },
    )
    # Assert
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["or_result"] is None
    assert payload["session"]["errors"]
    assert "forced OR failure for test" in " ".join(payload["session"]["errors"])
    assert "Не удалось выполнить шаг" in payload["assistant_message"]
