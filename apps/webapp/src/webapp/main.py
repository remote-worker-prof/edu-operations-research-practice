"""HTTP-слой учебного OR-AI приложения.

Назначение модуля:
- объявить `FastAPI`-приложение и фабрику `create_app`;
- связать HTML/HTMX интерфейс с `AgentService`;
- предоставить JSON API для интеграционных тестов, Selenium E2E и внешних клиентов.

Роль в архитектуре:
- это единственная точка входа web-слоя;
- модуль не содержит бизнес-логики оптимизации и не вызывает OR-решатели напрямую.

Главные зависимости:
- `agent_core.service.AgentService` — оркестрация одного хода диалога;
- `Jinja2Templates` — серверный рендеринг HTML;
- `FastAPI` — маршрутизация HTTP-запросов.
"""

from __future__ import annotations

from pathlib import Path

from agent_core.config import DEFAULT_MODEL_ALIAS, model_aliases, model_options
from agent_core.models import ChatTurnRequest
from agent_core.service import AgentService
from extension_api import ExtensionRegistry
from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
router = APIRouter()

MISSING_FIELD_LABELS = {
    "production": "1) Production",
    "shipment": "2) Shipment",
    "assignment": "3) Assignment",
    "routing": "4) Routing",
}


def _get_service(request: Request) -> AgentService:
    """Возвращает `AgentService`, прикреплённый к текущему приложению."""
    return request.app.state.service


def _render_context(*, request: Request, session) -> dict:
    """Собирает единый контекст рендеринга для Jinja2-шаблонов.

    Что делает:
    - формирует словарь, который одинаково используется для `index.html` и `_workspace.html`.

    Зачем:
    - избежать дублирования одинаковых полей контекста в разных endpoint-функциях.

    Входы:
    - `request`: объект текущего HTTP-запроса FastAPI;
    - `session`: текущее состояние сессии агента.

    Выходы:
    - словарь с данными для шаблонов (сессия, список моделей, человеко-понятные лейблы полей).

    Ошибки:
    - не генерирует исключения в штатном сценарии.

    Пример:
    - используется внутри `index()` и `chat_turn()` перед `TemplateResponse`.
    """
    return {
        "request": request,
        "session": session,
        "model_aliases": model_aliases(),
        "model_options": model_options(),
        "missing_field_labels": MISSING_FIELD_LABELS,
    }


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Возвращает минимальную проверку доступности сервиса.

    Что делает:
    - отвечает фиксированным JSON `{"status": "ok"}`.

    Зачем:
    - используется для health-check в dev/docker и в автоматических проверках.

    Входы:
    - отсутствуют.

    Выходы:
    - словарь со статусом приложения.

    Ошибки:
    - в штатном режиме отсутствуют.

    Пример:
    - `GET /healthz` -> `{"status": "ok"}`.
    """
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Рендерит стартовую страницу с новой пользовательской сессией.

    Что делает:
    - создаёт сессию через `AgentService`;
    - подготавливает контекст интерфейса;
    - возвращает HTML главной страницы.

    Зачем:
    - стартовый экран всегда должен иметь валидный `session_id` для следующих HTMX-запросов.

    Входы:
    - `request`: HTTP-запрос браузера.

    Выходы:
    - HTML-ответ с шаблоном `index.html`.

    Ошибки:
    - возможны только при системных проблемах шаблонизатора/инфраструктуры.

    Пример:
    - пользователь открывает `/` и видит чат + панель параметров.
    """
    service = _get_service(request)
    session = service.create_session()
    context = _render_context(request=request, session=session)
    return templates.TemplateResponse(request, "index.html", context)


@router.post("/chat/turn", response_class=HTMLResponse)
def chat_turn(
    request: Request,
    session_id: str = Form(...),
    model_alias: str = Form(DEFAULT_MODEL_ALIAS),
    message: str = Form(...),
) -> HTMLResponse:
    """Обрабатывает один ход диалога в HTMX-режиме и возвращает partial HTML.

    Что делает:
    - собирает входные данные формы;
    - вызывает `AgentService.handle_turn`;
    - рендерит обновлённый `_workspace.html`.

    Зачем:
    - HTMX позволяет обновлять только рабочую область интерфейса без полной перезагрузки страницы.

    Входы:
    - `request`: HTTP-запрос;
    - `session_id`: идентификатор текущей сессии;
    - `model_alias`: выбранный пользователем alias модели;
    - `message`: текстовая реплика пользователя.

    Выходы:
    - HTML-фрагмент с обновлённым диалогом, ошибками/предупреждениями и результатами OR.

    Ошибки:
    - бизнес-ошибки не пробрасываются в HTTP 500, а попадают в `session.errors` и рендерятся в UI.

    Пример:
    - `POST /chat/turn` с формой -> обновлённый блок `#workspace`.
    """
    service = _get_service(request)
    result = service.handle_turn(
        ChatTurnRequest(
            session_id=session_id,
            model_alias=model_alias,
            message=message,
        )
    )
    context = _render_context(request=request, session=result.session)
    return templates.TemplateResponse(request, "_workspace.html", context)


@router.post("/api/chat/turn")
def api_chat_turn(payload: ChatTurnRequest, request: Request) -> dict:
    """JSON endpoint для одного хода диалога.

    Что делает:
    - принимает сериализованный запрос `ChatTurnRequest`;
    - запускает обработку в `AgentService`;
    - возвращает полное состояние `TurnResult` в JSON.

    Зачем:
    - используется интеграционными тестами и внешними клиентами без HTML/HTMX.

    Входы:
    - `payload`: модель запроса с `session_id`, `model_alias`, `message`.

    Выходы:
    - JSON-словарь результата сессии и ответа ассистента.

    Ошибки:
    - валидационные ошибки входа обрабатываются FastAPI автоматически (422).

    Пример:
    - `POST /api/chat/turn` с JSON-пейлоадом из тестов в `tests/integration/test_api.py`.
    """
    service = _get_service(request)
    result = service.handle_turn(payload)
    return result.model_dump(mode="json")


@router.get("/api/session/{session_id}")
def api_get_session(session_id: str, request: Request) -> dict:
    """Возвращает состояние сессии по идентификатору.

    Что делает:
    - ищет сессию в in-memory хранилище;
    - если сессия есть, сериализует её в JSON;
    - если нет, возвращает HTTP 404.

    Зачем:
    - даёт возможность дебага/интеграций читать текущее состояние диалога.

    Входы:
    - `session_id`: идентификатор сессии.

    Выходы:
    - JSON-представление `AgentSession`.

    Ошибки:
    - `HTTPException(404)`, если сессия не найдена.

    Пример:
    - `GET /api/session/<id>` после нескольких ходов диалога.
    """
    service = _get_service(request)
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump(mode="json")


def create_app(
    *,
    service: AgentService | None = None,
    extension_registry: ExtensionRegistry | None = None,
) -> FastAPI:
    """Создаёт и настраивает `FastAPI`-приложение для runtime и тестов.

    Что делает:
    - создаёт новый экземпляр `FastAPI`;
    - прикрепляет `AgentService` в `app.state`;
    - монтирует локальные static assets;
    - подключает router c HTML и JSON endpoints.

    Зачем:
    - Selenium/live-server тесты могут поднимать изолированное приложение
      с отдельным in-memory состоянием и без общих module-global side effects.
    """
    app = FastAPI(title="OR AI Agent Demo", version="0.1.0")
    resolved_registry = extension_registry or getattr(service, "extension_registry", None)
    app.state.service = service or AgentService(extension_registry=resolved_registry)
    app.state.extension_registry = app.state.service.extension_registry
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
    app.include_router(router)
    return app


app = create_app()
service = app.state.service
