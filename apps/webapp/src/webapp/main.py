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

import os
from pathlib import Path

from agent_core.config import DEFAULT_MODEL_ALIAS, model_aliases, model_options
from agent_core.copilotkit_agent import SemanticsChatAgent
from agent_core.extension_flow import (
    manifest_for_alias,
    stage_label_map_for_manifest,
    stage_order_for_manifest,
)
from agent_core.models import ChatTurnRequest
from agent_core.service import AgentService
from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from extension_api import ExtensionRegistry
from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
router = APIRouter()


class ThreadCreateRequest(BaseModel):
    """Payload for creating one backend-owned chat thread."""

    model_alias: str = DEFAULT_MODEL_ALIAS
    extension_alias: str | None = None


class ThreadTurnRequest(BaseModel):
    """Payload for sending one message into an existing backend-owned thread."""

    model_alias: str = DEFAULT_MODEL_ALIAS
    extension_alias: str | None = None
    message: str = Field(..., min_length=1)


def _cors_origins() -> list[str]:
    """Returns dev-friendly origins for the new React chat shell."""
    configured = os.getenv("CHAT_WEB_ORIGINS", "").strip()
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    return [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]


def _thread_summary(session, request: Request) -> dict[str, object]:
    """Builds a compact thread card for the React chat shell."""
    registry = request.app.state.extension_registry
    manifest = manifest_for_alias(registry, session.extension_alias)
    last_user = next(
        (msg.content for msg in reversed(session.messages) if msg.role == "user"),
        None,
    )
    return {
        "thread_id": session.session_id,
        "extension_alias": session.extension_alias,
        "extension_title": manifest.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": len(session.messages),
        "last_user_message": last_user,
        "pending_question": session.pending_question,
    }


def _get_service(request: Request) -> AgentService:
    """Возвращает `AgentService`, прикреплённый к текущему приложению."""
    return request.app.state.service


def _manifest_context(
    request: Request, session
) -> tuple[dict[str, str], list[dict[str, object]], object]:
    """Builds manifest-driven stage labels and progress rows for the current session."""
    registry = request.app.state.extension_registry
    manifest = manifest_for_alias(registry, session.extension_alias)
    label_map = stage_label_map_for_manifest(manifest)
    stage_status_map = {row.stage_id: row for row in session.extension_stage_statuses}
    stage_rows = []
    for stage_id in stage_order_for_manifest(manifest):
        status = stage_status_map.get(stage_id)
        stage_rows.append(
            {
                "stage_id": stage_id,
                "label": label_map.get(stage_id, stage_id),
                "ready": status.ready if status is not None else False,
            }
        )
    return label_map, stage_rows, manifest


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
    missing_field_labels, stage_status_rows, manifest = _manifest_context(request, session)
    extension_options = [
        {
            "alias": item.alias,
            "title": item.manifest.title,
            "description": item.manifest.description,
        }
        for item in request.app.state.extension_registry.all()
    ]
    return {
        "request": request,
        "session": session,
        "model_aliases": model_aliases(),
        "model_options": model_options(),
        "missing_field_labels": missing_field_labels,
        "stage_status_rows": stage_status_rows,
        "current_extension_manifest": manifest,
        "extension_options": extension_options,
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
    extension_alias: str | None = Form(None),
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
            extension_alias=extension_alias,
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


@router.get("/api/chat/extensions")
def api_chat_extensions(request: Request) -> list[dict[str, object]]:
    """Returns all discovered extensions for the new React chat shell."""
    registry = request.app.state.extension_registry
    return [
        {
            "alias": item.alias,
            "title": item.manifest.title,
            "description": item.manifest.description,
        }
        for item in registry.all()
    ]


@router.get("/api/chat/threads")
def api_chat_threads(request: Request) -> list[dict[str, object]]:
    """Lists backend-owned chat threads for the new React shell."""
    service = _get_service(request)
    return [_thread_summary(session, request) for session in service.list_sessions()]


@router.post("/api/chat/threads")
def api_create_chat_thread(payload: ThreadCreateRequest, request: Request) -> dict[str, object]:
    """Creates one new backend-owned chat thread and returns its initial state."""
    service = _get_service(request)
    session = service.create_session(model_alias=payload.model_alias)
    if payload.extension_alias and payload.extension_alias != session.extension_alias:
        start = service.handle_slash_turn(
            ChatTurnRequest(
                session_id=session.session_id,
                model_alias=payload.model_alias,
                message=f"/use {payload.extension_alias}",
            )
        )
        session = start.session
    interaction = service.build_interaction_state(session.session_id)
    return {
        "thread": _thread_summary(session, request),
        "session": session.model_dump(mode="json"),
        "interaction": interaction.model_dump(mode="json") if interaction is not None else None,
    }


@router.get("/api/chat/threads/{thread_id}")
def api_get_chat_thread(thread_id: str, request: Request) -> dict[str, object]:
    """Returns one thread plus the typed interaction snapshot for the React shell."""
    service = _get_service(request)
    session = service.get_session(thread_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    interaction = service.build_interaction_state(thread_id)
    return {
        "thread": _thread_summary(session, request),
        "session": session.model_dump(mode="json"),
        "interaction": interaction.model_dump(mode="json") if interaction is not None else None,
    }


@router.delete("/api/chat/threads/{thread_id}")
def api_delete_chat_thread(thread_id: str, request: Request) -> dict[str, bool]:
    """Deletes one backend-owned chat thread."""
    service = _get_service(request)
    removed = service.delete_session(thread_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"ok": True}


@router.post("/api/chat/threads/{thread_id}/turn")
def api_chat_thread_turn(
    thread_id: str,
    payload: ThreadTurnRequest,
    request: Request,
) -> dict[str, object]:
    """Sends one slash/text turn through the new backend-owned thread API."""
    service = _get_service(request)
    result = service.handle_slash_turn(
        ChatTurnRequest(
            session_id=thread_id,
            model_alias=payload.model_alias,
            extension_alias=payload.extension_alias,
            message=payload.message,
        )
    )
    interaction = service.build_interaction_state(result.session.session_id)
    return {
        "turn": result.model_dump(mode="json"),
        "interaction": interaction.model_dump(mode="json") if interaction is not None else None,
    }


@router.get("/api/chat/threads/{thread_id}/interaction")
def api_chat_thread_interaction(thread_id: str, request: Request) -> dict[str, object]:
    """Returns the typed interaction state for one backend-owned thread."""
    service = _get_service(request)
    interaction = service.build_interaction_state(thread_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return interaction.model_dump(mode="json")


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
    if service is not None and extension_registry is not None:
        missing_aliases = [
            alias
            for alias in extension_registry.aliases()
            if alias not in service.extension_registry
        ]
        if missing_aliases:
            raise ValueError(
                "create_app received both `service` and `extension_registry`, but the service "
                "registry does not include these aliases: " + ", ".join(sorted(missing_aliases))
            )
    if (
        service is not None
        and extension_registry is not None
        and service.extension_registry is extension_registry
    ):
        pass
    elif (
        service is not None
        and extension_registry is not None
        and service.extension_registry is not extension_registry
    ):
        # Accept composition where the service registry additionally includes built-ins.
        extension_registry = service.extension_registry

    app = FastAPI(title="OR AI Agent Demo", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    resolved_service = service or AgentService(extension_registry=extension_registry)
    app.state.service = resolved_service
    app.state.extension_registry = app.state.service.extension_registry
    app.state.extension_startup_warnings = app.state.service.extension_startup_warnings
    app.state.chat_agent = SemanticsChatAgent(service=resolved_service)
    app.state.copilotkit_sdk = CopilotKitRemoteEndpoint(agents=[app.state.chat_agent])
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
    app.include_router(router)
    add_fastapi_endpoint(app, app.state.copilotkit_sdk, "/api/copilotkit")
    return app


app = create_app()
service = app.state.service
