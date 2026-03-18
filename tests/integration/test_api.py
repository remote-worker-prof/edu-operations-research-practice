"""Интеграционные тесты API и HTMX-потока web-приложения.

Каждый тест проверяет конкретный пользовательский или деградированный сценарий,
чтобы минимизировать риск регрессий в учебном демо.
"""

import re
from dataclasses import dataclass
from typing import Any

from agent_core.config import model_aliases, model_options
from extension_api import (
    DiscoveredExtension,
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionResultSection,
    StageSpec,
    SummaryBlock,
)
from fastapi.testclient import TestClient
from or_core.exceptions import ORPipelineError
from pydantic import BaseModel
from webapp.main import app, create_app, service

client = TestClient(app)


@dataclass(frozen=True)
class _DataclassExtensionResult:
    """Structured dataclass result for API transport regression tests."""

    total_hours: float
    recommendation_count: int


class _PydanticExtensionResult(BaseModel):
    """Structured Pydantic result for API transport regression tests."""

    total_hours: float
    recommendation_count: int


class _OpaqueExtensionResult:
    """Stable repr-only result used to verify fallback warnings."""

    def __init__(self, total_hours: float) -> None:
        self.total_hours = total_hours

    def __repr__(self) -> str:
        return f"OpaqueExtensionResult(total_hours={self.total_hours})"


class _StructuredResultRuntime:
    """Tiny deterministic runtime used to verify generic JSON transport."""

    manifest: ExtensionManifest

    def __init__(self, manifest: ExtensionManifest, *, result_kind: str) -> None:
        self.manifest = manifest
        self._result_kind = result_kind

    def validate_draft(self, draft: dict[str, object]) -> dict[str, list[str]]:
        payload = draft.get("input")
        if not isinstance(payload, dict):
            return {"input": ["stage is empty"]}
        hours = payload.get("hours")
        if not isinstance(hours, (int, float)) or float(hours) <= 0:
            return {"input": ["input.hours должно быть числом > 0."]}
        return {"input": []}

    def build_runtime_input(self, draft: dict[str, object]) -> object:
        payload = draft["input"]
        assert isinstance(payload, dict)
        return {"hours": float(payload["hours"])}

    def run(self, runtime_input: object) -> object:
        assert isinstance(runtime_input, dict)
        hours = float(runtime_input["hours"])
        if self._result_kind == "dataclass":
            return _DataclassExtensionResult(
                total_hours=hours,
                recommendation_count=1,
            )
        if self._result_kind == "pydantic":
            return _PydanticExtensionResult(
                total_hours=hours,
                recommendation_count=1,
            )
        if self._result_kind == "opaque":
            return _OpaqueExtensionResult(total_hours=hours)
        raise AssertionError(f"Unknown result kind: {self._result_kind}")

    def fallback_explain(self, result: object) -> str:
        return "Structured extension result calculated."

    def build_llm_explain_prompt(self, result: object) -> str:
        return f"Explain: {result!r}"

    def build_result_sections(self, result: object) -> list[ExtensionResultSection]:
        return [
            ExtensionResultSection(
                section_id="structured-summary",
                title="Structured summary",
                blocks=[SummaryBlock(text="Structured result is available.")],
            )
        ]

    def build_teaching_hints(self, draft: dict[str, object]) -> list[dict[str, object]]:
        del draft
        return []

    def build_nl_semantics(self) -> dict[str, object]:
        return {"supported": False}


class _StructuredResultProvider:
    """Preset-capable provider for dataclass/Pydantic transport regression tests."""

    def __init__(self, *, alias: str, result_kind: str) -> None:
        self._alias = alias
        self._result_kind = result_kind

    def get_manifest(self) -> ExtensionManifest:
        return ExtensionManifest(
            alias=self._alias,
            title=f"{self._alias} demo",
            description="Regression-test extension for structured result transport.",
            version="0.1.0",
            default_preset="demo",
            stage_graph=[StageSpec(stage_id="input", label="Input")],
        )

    def create_runtime(self) -> _StructuredResultRuntime:
        return _StructuredResultRuntime(self.get_manifest(), result_kind=self._result_kind)

    def load_preset(self, preset_ref: str) -> dict[str, dict[str, Any]]:
        if preset_ref != "demo":
            raise ValueError(f"Unsupported preset: {preset_ref}")
        return {"input": {"hours": 8}}


def _client_with_extension_provider(provider: object) -> TestClient:
    """Creates an isolated TestClient with one additional extension provider."""
    manifest = provider.get_manifest()
    registry = ExtensionRegistry(
        [
            DiscoveredExtension(
                alias=manifest.alias,
                manifest=manifest,
                provider=provider,
                entry_point_name=manifest.alias,
                module=provider.__class__.__module__,
                source=f"test:{manifest.alias}",
            )
        ]
    )
    return TestClient(create_app(extension_registry=registry))


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
    assert payload["extension_state"]["alias"] == "default_or"
    assert payload["session"]["extension_state"]["alias"] == "default_or"
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
    select_match = re.search(
        r'<select id="model-alias-select"[^>]*>(.*?)</select>',
        page.text,
        flags=re.DOTALL,
    )
    assert select_match is not None
    options = re.findall(r'<option value="([^"]+)"', select_match.group(1))
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


def test_nl_mixed_run_and_parameters_prefers_extraction() -> None:
    """Проверяет, что mixed-реплика не теряет patch extraction из-за run-интенции.

    Риск:
    - greedy run-intent может перехватить сообщение с параметрами и не сохранить ввод.
    """
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    mixed_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": 'запусти production profits [41,31], products ["A","B"]',
        },
    )
    assert mixed_turn.status_code == 200
    payload = mixed_turn.json()
    assert payload["session"]["or_result"] is None
    assert payload["session"]["confirmation_state"]["pending_patches"]
    assert "Подтвердите `да`" in payload["assistant_message"]


def test_nl_state_cleanup_after_successful_run() -> None:
    """Проверяет очистку stale NL-состояния после успешного расчёта.

    Риск:
    - после run в сессии могут остаться старые uncertainty/вопросы и путать студента.
    """
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    ambiguous_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": "для production и shipment задай cost_matrix [[1,2],[2,1]]",
        },
    )
    assert ambiguous_turn.status_code == 200
    assert ambiguous_turn.json()["session"]["nl_uncertainties"]

    preset_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": "load preset demo",
        },
    )
    assert preset_turn.status_code == 200
    assert preset_turn.json()["session"]["nl_uncertainties"] == []

    run_turn = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": "run",
        },
    )
    assert run_turn.status_code == 200
    payload = run_turn.json()["session"]
    assert payload["or_result"] is not None
    assert payload["nl_uncertainties"] == []
    assert payload["nl_confidence"] is None
    assert payload["teaching_hints"] == []
    assert payload["pending_question"] is None


def test_confirmed_patches_are_deduplicated_and_bounded() -> None:
    """Проверяет dedup + bounded-retention для confirmation history.

    Риск:
    - confirmed_patches может расти без ограничений на длинных учебных сессиях.
    """
    start_turn = client.post(
        "/api/chat/turn",
        json={"model_alias": "openai_default", "message": "start"},
    )
    assert start_turn.status_code == 200
    session_id = start_turn.json()["session"]["session_id"]

    first_patch = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": 'production profits [40,30], products ["A","B"]',
        },
    )
    assert first_patch.status_code == 200
    first_confirm = client.post(
        "/api/chat/turn",
        json={"session_id": session_id, "model_alias": "openai_default", "message": "да"},
    )
    assert first_confirm.status_code == 200
    initial_len = len(first_confirm.json()["session"]["confirmation_state"]["confirmed_patches"])

    same_patch = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "openai_default",
            "message": 'production profits [40,30], products ["A","B"]',
        },
    )
    assert same_patch.status_code == 200
    same_confirm = client.post(
        "/api/chat/turn",
        json={"session_id": session_id, "model_alias": "openai_default", "message": "да"},
    )
    assert same_confirm.status_code == 200
    dedup_len = len(same_confirm.json()["session"]["confirmation_state"]["confirmed_patches"])
    assert dedup_len == initial_len

    for idx in range(70):
        patch_turn = client.post(
            "/api/chat/turn",
            json={
                "session_id": session_id,
                "model_alias": "openai_default",
                "message": f'production profits [{100 + idx},30], products ["A","B"]',
            },
        )
        assert patch_turn.status_code == 200
        confirm_turn = client.post(
            "/api/chat/turn",
            json={"session_id": session_id, "model_alias": "openai_default", "message": "да"},
        )
        assert confirm_turn.status_code == 200

    bounded_payload = confirm_turn.json()["session"]["confirmation_state"]["confirmed_patches"]
    assert len(bounded_payload) <= 64


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


def test_api_can_start_new_session_with_sample_extension() -> None:
    """Проверяет JSON API happy-path для `study_planner` без OR-подграфа."""
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "study_planner",
            "message": "start",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    session_id = payload["session"]["session_id"]
    assert payload["session"]["extension_alias"] == "study_planner"
    assert payload["session"]["extension_state"]["alias"] == "study_planner"
    assert payload["extension_state"]["alias"] == "study_planner"
    assert payload["session"]["collection_state"]["current_stage"] == "courses"

    commands = [
        ('json courses {"names":["Math","ML","Databases"],"hours_required":[30,24,18]}'),
        'json time_budget {"weekly_hours":12,"weeks":4}',
        'json priorities {"weights":[0.5,0.3,0.2]}',
        "run",
    ]

    for command in commands:
        response = client.post(
            "/api/chat/turn",
            json={
                "session_id": session_id,
                "model_alias": "local_default",
                "extension_alias": "study_planner",
                "message": command,
            },
        )
        assert response.status_code == 200
        payload = response.json()

    assert payload["session"]["or_result"] is None
    assert payload["session"]["extension_state"]["draft"]["courses"]["names"] == [
        "Math",
        "ML",
        "Databases",
    ]
    assert payload["extension_state"]["result"]["total_available_hours"] == 48.0
    assert payload["session"]["extension_result"]["total_available_hours"] == 48.0
    assert payload["session"]["extension_result_sections"][0]["title"] == "Итог плана"
    assert payload["session"]["extension_result_sections"][2]["blocks"][0]["rows"][0][0] == "Math"


def test_api_can_load_sample_extension_default_preset_and_run() -> None:
    """Проверяет честный preset path для non-default extension через JSON API."""
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "study_planner",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    preset_payload = preset_response.json()
    session_id = preset_payload["session"]["session_id"]

    assert preset_payload["session"]["extension_alias"] == "study_planner"
    assert preset_payload["session"]["extension_state"]["draft"]["courses"]["names"] == [
        "Math",
        "ML",
        "Databases",
    ]
    assert "Built-in preset `demo` загружен" in preset_payload["assistant_message"]

    run_response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "study_planner",
            "message": "run",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()

    assert payload["extension_state"]["result"]["total_available_hours"] == 48.0
    assert payload["session"]["extension_result"]["total_required_hours"] == 72.0
    assert payload["session"]["extension_result_sections"][0]["title"] == "Итог плана"


def test_api_serializes_dataclass_extension_results_in_turn_and_session_payloads() -> None:
    """Проверяет round-trip dataclass result через generic extension transport."""
    local_client = _client_with_extension_provider(
        _StructuredResultProvider(alias="dataclass_demo", result_kind="dataclass")
    )
    preset_response = local_client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "dataclass_demo",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    run_response = local_client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "dataclass_demo",
            "message": "run",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()

    assert payload["extension_state"]["result"] == {
        "total_hours": 8.0,
        "recommendation_count": 1,
    }
    assert "repr" not in payload["extension_state"]["result"]

    session_response = local_client.get(f"/api/session/{session_id}")
    assert session_response.status_code == 200
    assert session_response.json()["extension_result"] == {
        "total_hours": 8.0,
        "recommendation_count": 1,
    }


def test_api_serializes_pydantic_extension_results_in_turn_and_session_payloads() -> None:
    """Проверяет round-trip Pydantic result через generic extension transport."""
    local_client = _client_with_extension_provider(
        _StructuredResultProvider(alias="pydantic_demo", result_kind="pydantic")
    )
    preset_response = local_client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "pydantic_demo",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    run_response = local_client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "pydantic_demo",
            "message": "run",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()

    assert payload["session"]["extension_result"] == {
        "total_hours": 8.0,
        "recommendation_count": 1,
    }

    session_response = local_client.get(f"/api/session/{session_id}")
    assert session_response.status_code == 200
    assert session_response.json()["extension_state"]["result"] == {
        "total_hours": 8.0,
        "recommendation_count": 1,
    }


def test_api_falls_back_to_repr_with_warning_for_opaque_extension_results() -> None:
    """Проверяет безопасную деградацию для не-JSON-serializable extension result."""
    local_client = _client_with_extension_provider(
        _StructuredResultProvider(alias="opaque_demo", result_kind="opaque")
    )
    preset_response = local_client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "opaque_demo",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    run_response = local_client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "opaque_demo",
            "message": "run",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()

    assert payload["session"]["extension_result"] == {
        "repr": "OpaqueExtensionResult(total_hours=8.0)"
    }
    assert payload["session"]["warnings"]
    assert "not JSON-serializable" in " ".join(payload["session"]["warnings"])


def test_api_rejects_extension_switch_in_nonempty_session_until_reset() -> None:
    """Проверяет, что extension нельзя поменять в непустой сессии без `reset`."""
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    blocked = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "study_planner",
            "message": "start",
        },
    )
    assert blocked.status_code == 200
    payload = blocked.json()
    assert payload["session"]["extension_alias"] == "default_or"
    assert payload["session"]["scenario_draft"]["preset_ref"] == "demo"
    assert "Нельзя сменить extension" in payload["assistant_message"]


def test_api_reset_then_switch_extension_succeeds() -> None:
    """Проверяет двухшаговый policy-flow: `reset`, затем успешный switch extension."""
    preset_response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "message": "load preset demo",
        },
    )
    assert preset_response.status_code == 200
    session_id = preset_response.json()["session"]["session_id"]

    reset_response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "message": "reset",
        },
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["session"]["extension_alias"] == "default_or"

    switch_response = client.post(
        "/api/chat/turn",
        json={
            "session_id": session_id,
            "model_alias": "local_default",
            "extension_alias": "study_planner",
            "message": "start",
        },
    )
    assert switch_response.status_code == 200
    payload = switch_response.json()
    assert payload["session"]["extension_alias"] == "study_planner"
    assert payload["session"]["collection_state"]["current_stage"] == "courses"
    assert "Заполните stage Курсы" in payload["assistant_message"]


def test_api_unknown_extension_alias_returns_human_error_without_500() -> None:
    """Проверяет защиту от неизвестного `extension_alias`."""
    response = client.post(
        "/api/chat/turn",
        json={
            "model_alias": "local_default",
            "extension_alias": "unknown_extension",
            "message": "start",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["extension_alias"] == "default_or"
    assert "не найдено" in payload["assistant_message"]
