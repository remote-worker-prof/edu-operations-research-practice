"""FastAPI application for the OR educational chat agent."""

from __future__ import annotations

from pathlib import Path

from agent_core.config import DEFAULT_MODEL_ALIAS, model_aliases, model_options
from agent_core.models import ChatTurnRequest
from agent_core.service import AgentService
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="OR AI Agent Demo", version="0.1.0")
service = AgentService()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

MISSING_FIELD_LABELS = {
    "demand_multiplier": "Коэффициент спроса",
    "resource_multiplier": "Коэффициент ресурсов",
}


def _render_context(*, request: Request, session) -> dict:
    return {
        "request": request,
        "session": session,
        "model_aliases": model_aliases(),
        "model_options": model_options(),
        "missing_field_labels": MISSING_FIELD_LABELS,
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    session = service.create_session()
    context = _render_context(request=request, session=session)
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/chat/turn", response_class=HTMLResponse)
def chat_turn(
    request: Request,
    session_id: str = Form(...),
    model_alias: str = Form(DEFAULT_MODEL_ALIAS),
    message: str = Form(...),
) -> HTMLResponse:
    result = service.handle_turn(
        ChatTurnRequest(
            session_id=session_id,
            model_alias=model_alias,
            message=message,
        )
    )
    context = _render_context(request=request, session=result.session)
    return templates.TemplateResponse(request, "_workspace.html", context)


@app.post("/api/chat/turn")
def api_chat_turn(payload: ChatTurnRequest) -> dict:
    result = service.handle_turn(payload)
    return result.model_dump(mode="json")


@app.get("/api/session/{session_id}")
def api_get_session(session_id: str) -> dict:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump(mode="json")
