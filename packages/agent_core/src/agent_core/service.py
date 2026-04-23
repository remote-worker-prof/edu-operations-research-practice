"""Сервисный фасад agent_core для web-слоя и API.

Назначение модуля:
- инкапсулировать orchestration одного хода диалога;
- скрыть детали работы graph, storage и OR-зависимостей от роутеров FastAPI.
"""

from __future__ import annotations

import json
from pathlib import Path

from extension_api import ExtensionNotFoundError, ExtensionRegistry
from or_core.pipeline import ORPipeline
from or_core.scenario import ScenarioAssembler, ScenarioPresetLoader

from agent_core.config import DEFAULT_MODEL_ALIAS, default_scenario_path
from agent_core.default_or_extension import DEFAULT_OR_EXTENSION_ALIAS
from agent_core.dialog_graph import build_dialog_graph
from agent_core.extension_flow import (
    _pending_question,
    _recompute_extension_state,
    _sync_phase_and_summary,
    handle_extension_turn,
    is_default_or_extension,
    manifest_for_alias,
    reset_session_for_extension,
    session_is_empty,
    sync_default_or_compatibility_state,
)
from agent_core.extensions import (
    compose_extension_registry,
    tolerant_discovery_report,
)
from agent_core.interaction_state import (
    build_interaction_state,
    render_help_text,
    render_result_overview,
    render_semantics_json,
    render_steps_overview,
    render_validation_overview,
)
from agent_core.llm import LLMClient
from agent_core.models import AgentSession, ChatMessage, ChatTurnRequest, TurnResult
from agent_core.session_store import InMemorySessionStore
from agent_core.slash_commands import (
    parse_slash_command,
    translated_legacy_command,
    validate_payload_json,
)


class AgentService:
    """Фасад прикладного уровня для обработки реплик пользователя.

    Что делает:
    - создаёт и хранит зависимости:
      `session_store`, `LLMClient`, `ScenarioAssembler`, `ORPipeline`;
    - запускает `DialogGraph` для каждого входящего хода.

    Зачем:
    - web-слой остаётся тонким и не содержит бизнес-логики.
    """

    def __init__(
        self,
        *,
        scenario_path: Path | None = None,
        session_store: InMemorySessionStore | None = None,
        llm_client: LLMClient | None = None,
        extension_registry: ExtensionRegistry | None = None,
    ) -> None:
        """Инициализирует все зависимости сервиса.

        Входы:
        - `scenario_path`: путь к JSON preset-сценарию (опциональный demo preset);
        - `session_store`: кастомное хранилище сессий (опционально);
        - `llm_client`: кастомный LLM-клиент (опционально).
        """
        self._store = session_store or InMemorySessionStore()
        self._llm_client = llm_client or LLMClient()
        if extension_registry is not None:
            self._extension_registry = compose_extension_registry(extension_registry)
            self._extension_startup_warnings: list[str] = []
        else:
            discovery_report = tolerant_discovery_report()
            self._extension_registry = discovery_report.registry
            self._extension_startup_warnings = list(discovery_report.warnings)
        preset_path = scenario_path or default_scenario_path()
        self._scenario_assembler = ScenarioAssembler()
        self._preset_loader = ScenarioPresetLoader(preset_path)
        self._or_pipeline = ORPipeline()
        self._dialog_graph = build_dialog_graph(
            scenario_assembler=self._scenario_assembler,
            preset_loader=self._preset_loader,
            or_pipeline=self._or_pipeline,
            llm_client=self._llm_client,
        )

    @staticmethod
    def _append_assistant_error(
        *,
        session: AgentSession,
        user_message: str,
        assistant_message: str,
    ) -> TurnResult:
        """Appends a user turn plus one assistant-side policy/error reply."""
        updated_session = session.model_copy(deep=True)
        updated_session.errors = []
        updated_session.messages.append(ChatMessage(role="user", content=user_message.strip()))
        updated_session.messages.append(ChatMessage(role="assistant", content=assistant_message))
        return TurnResult(session=updated_session, assistant_message=assistant_message)

    @staticmethod
    def _append_assistant_reply(
        *,
        session: AgentSession,
        user_message: str,
        assistant_message: str,
    ) -> TurnResult:
        """Appends one user turn plus one assistant reply for slash/API helpers."""
        updated_session = session.model_copy(deep=True)
        updated_session.messages.append(ChatMessage(role="user", content=user_message.strip()))
        updated_session.messages.append(ChatMessage(role="assistant", content=assistant_message))
        return TurnResult(session=updated_session, assistant_message=assistant_message)

    def _resolve_session_for_request(self, request: ChatTurnRequest) -> AgentSession:
        """Loads or creates a session and applies basic request-scoped defaults."""
        session = self._store.get_or_create(request.session_id)
        session.model_alias = request.model_alias
        return session

    def _apply_requested_extension(
        self,
        *,
        session: AgentSession,
        request: ChatTurnRequest,
    ) -> TurnResult | AgentSession:
        """Validates and, when safe, switches the session to the requested extension."""
        requested_alias = (
            request.extension_alias or session.extension_alias or DEFAULT_OR_EXTENSION_ALIAS
        )

        if requested_alias == session.extension_alias:
            return session

        try:
            target_manifest = manifest_for_alias(self._extension_registry, requested_alias)
        except ExtensionNotFoundError:
            rejected = self._append_assistant_error(
                session=session,
                user_message=request.message,
                assistant_message=(
                    f"Extension `{requested_alias}` не найдено. "
                    f"Текущий extension остаётся `{session.extension_alias}`."
                ),
            )
            self._store.save(rejected.session)
            return rejected

        if not session_is_empty(session):
            rejected = self._append_assistant_error(
                session=session,
                user_message=request.message,
                assistant_message=(
                    "Нельзя сменить extension в непустой сессии. "
                    "Сначала отправьте `reset`, затем выберите новый extension."
                ),
            )
            self._store.save(rejected.session)
            return rejected

        reset_session_for_extension(session, alias=requested_alias, manifest=target_manifest)
        return session

    def _replace_last_user_message(
        self,
        *,
        session: AgentSession,
        original: str,
        translated: str,
    ) -> AgentSession:
        """Keeps backend history aligned with slash commands after legacy delegation."""
        updated = session.model_copy(deep=True)
        for message in reversed(updated.messages):
            if message.role == "user" and message.content == translated:
                message.content = original
                break
        self._store.save(updated)
        return updated

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        """Returns True when any case-normalized marker appears in the message."""
        return any(marker in text for marker in markers)

    def _render_show_target(
        self,
        *,
        session: AgentSession,
        target: str,
    ) -> str:
        """Renders one canonical `/show ...` response for both slash and plain-chat shortcuts."""
        interaction_state = build_interaction_state(
            session=session,
            registry=self._extension_registry,
        )
        if target == "steps":
            return render_steps_overview(interaction_state)
        if target == "draft":
            lines = [
                "Текущий draft:",
                json.dumps(interaction_state.draft, ensure_ascii=False, indent=2),
            ]
            if interaction_state.current_stage and interaction_state.expected_payload is not None:
                lines.append("")
                lines.append(f"Ожидаемая форма для `{interaction_state.current_stage}`:")
                lines.append(
                    json.dumps(
                        interaction_state.expected_payload,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return "\n".join(lines)
        if target == "result":
            return render_result_overview(session)
        return "Команда /show поддерживает только steps, draft или result."

    def _handle_plain_text_shortcut(
        self,
        *,
        session: AgentSession,
        user_message: str,
    ) -> TurnResult | None:
        """Handles safe informational plain-text requests in the new React shell.

        The new chat is beginner-first, so we accept a tiny layer of non-destructive
        natural-language shortcuts such as "какие этапы" or "покажи результат".
        This is intentionally not a full NL parser and never mutates the draft.
        """
        text = user_message.strip().lower()
        if not text:
            return None

        show_markers = ("покаж", "show", "какие", "спис", "доступ", "что есть")
        step_markers = ("этап", "этапы", "шаг", "шаги", "stage", "stages", "steps")
        draft_markers = ("черновик", "draft", "ввод", "input", "данные")
        result_markers = ("результат", "решение", "solution", "result")
        help_markers = (
            "помощ",
            "help",
            "что дальше",
            "как работать",
            "как пользоваться",
            "что делать",
        )
        explain_markers = ("объяс", "пояс", "explain")

        assistant_message: str | None = None
        if self._contains_any(text, step_markers) and self._contains_any(text, show_markers):
            assistant_message = self._render_show_target(session=session, target="steps")
        elif self._contains_any(text, draft_markers) and self._contains_any(text, show_markers):
            assistant_message = self._render_show_target(session=session, target="draft")
        elif self._contains_any(text, result_markers) and self._contains_any(text, show_markers):
            assistant_message = self._render_show_target(session=session, target="result")
        elif self._contains_any(text, help_markers):
            interaction_state = build_interaction_state(
                session=session,
                registry=self._extension_registry,
            )
            assistant_message = render_help_text(interaction_state)
        elif self._contains_any(text, explain_markers):
            assistant_message = render_result_overview(session)

        if assistant_message is None:
            return None

        result = self._append_assistant_reply(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        self._store.save(result.session)
        return result

    @property
    def store(self) -> InMemorySessionStore:
        """Возвращает используемое хранилище сессий (для тестов и интеграций)."""
        return self._store

    @property
    def extension_registry(self) -> ExtensionRegistry:
        """Возвращает startup-регистр обнаруженных extension-пакетов."""
        return self._extension_registry

    @property
    def extension_startup_warnings(self) -> list[str]:
        """Returns quarantine warnings collected during startup extension discovery."""
        return list(self._extension_startup_warnings)

    def create_session(self, model_alias: str = DEFAULT_MODEL_ALIAS) -> AgentSession:
        """Создаёт новую пользовательскую сессию и сохраняет её в store."""
        session = self._store.create()
        session.model_alias = model_alias
        sync_default_or_compatibility_state(session=session, registry=self._extension_registry)
        self._store.save(session)
        return session

    def list_sessions(self) -> list[AgentSession]:
        """Returns current chat threads sorted by last update time."""
        return self._store.list_sessions()

    def delete_session(self, session_id: str) -> bool:
        """Deletes one session/thread by id."""
        return self._store.delete(session_id)

    def get_session(self, session_id: str) -> AgentSession | None:
        """Ищет сессию по `session_id` и возвращает её копию, если найдена."""
        return self._store.get(session_id)

    def build_interaction_state(self, session_id: str) -> object | None:
        """Builds typed interaction state for the requested thread."""
        session = self._store.get(session_id)
        if session is None:
            return None
        if is_default_or_extension(session.extension_alias):
            sync_default_or_compatibility_state(
                session=session,
                registry=self._extension_registry,
            )
        return build_interaction_state(session=session, registry=self._extension_registry)

    def handle_turn(self, request: ChatTurnRequest) -> TurnResult:
        """Обрабатывает один ход диалога.

        Что делает:
        - получает или создаёт сессию;
        - записывает выбранный alias модели;
        - передаёт управление в `DialogGraph`;
        - сохраняет обновлённое состояние и возвращает `TurnResult`.

        Зачем:
        - унифицировать обработку хода для HTML и JSON endpoints.
        """
        session = self._resolve_session_for_request(request)
        prepared = self._apply_requested_extension(session=session, request=request)
        if isinstance(prepared, TurnResult):
            return prepared
        session = prepared

        if not is_default_or_extension(session.extension_alias):
            updated_session, assistant_message = handle_extension_turn(
                session=session,
                user_message=request.message,
                registry=self._extension_registry,
            )
            self._store.save(updated_session)
            return TurnResult(session=updated_session, assistant_message=assistant_message)

        output_state = self._dialog_graph.invoke(
            {
                "session": session,
                "user_message": request.message,
            }
        )
        updated_session = output_state["session"]
        sync_default_or_compatibility_state(
            session=updated_session,
            registry=self._extension_registry,
        )
        self._store.save(updated_session)

        return TurnResult(
            session=updated_session,
            assistant_message=output_state.get("assistant_message", ""),
        )

    def handle_slash_turn(self, request: ChatTurnRequest) -> TurnResult:
        """Handles the new slash-command contract without breaking legacy deterministic flow."""
        slash = parse_slash_command(request.message)
        if slash is None:
            session = self._resolve_session_for_request(request)
            prepared = self._apply_requested_extension(session=session, request=request)
            if isinstance(prepared, TurnResult):
                return prepared
            session = prepared

            shortcut = self._handle_plain_text_shortcut(
                session=session,
                user_message=request.message,
            )
            if shortcut is not None:
                return shortcut
            return self.handle_turn(request)

        session = self._resolve_session_for_request(request)
        prepared = self._apply_requested_extension(session=session, request=request)
        if isinstance(prepared, TurnResult):
            return prepared
        session = prepared

        payload_error = validate_payload_json(slash)
        if payload_error is not None:
            result = self._append_assistant_reply(
                session=session,
                user_message=request.message,
                assistant_message=payload_error,
            )
            self._store.save(result.session)
            return result

        if slash.name == "new":
            target_alias = slash.arg or session.extension_alias
            try:
                manifest = manifest_for_alias(self._extension_registry, target_alias)
            except ExtensionNotFoundError:
                result = self._append_assistant_reply(
                    session=session,
                    user_message=request.message,
                    assistant_message=f"Extension `{target_alias}` не найдено.",
                )
                self._store.save(result.session)
                return result

            reset_session_for_extension(session, alias=target_alias, manifest=manifest)
            self._store.save(session)
            delegated = self.handle_turn(
                ChatTurnRequest(
                    session_id=session.session_id,
                    model_alias=request.model_alias,
                    extension_alias=target_alias,
                    message="start",
                )
            )
            updated = self._replace_last_user_message(
                session=delegated.session,
                original=request.message.strip(),
                translated="start",
            )
            return TurnResult(session=updated, assistant_message=delegated.assistant_message)

        if slash.name == "use":
            if not slash.arg:
                result = self._append_assistant_reply(
                    session=session,
                    user_message=request.message,
                    assistant_message="Формат команды: /use <extension>.",
                )
                self._store.save(result.session)
                return result
            delegated = self.handle_turn(
                ChatTurnRequest(
                    session_id=session.session_id,
                    model_alias=request.model_alias,
                    extension_alias=slash.arg,
                    message="start",
                )
            )
            updated = self._replace_last_user_message(
                session=delegated.session,
                original=request.message.strip(),
                translated="start",
            )
            return TurnResult(session=updated, assistant_message=delegated.assistant_message)

        translated = translated_legacy_command(slash)
        if translated is not None:
            delegated = self.handle_turn(
                ChatTurnRequest(
                    session_id=session.session_id,
                    model_alias=request.model_alias,
                    extension_alias=request.extension_alias,
                    message=translated,
                )
            )
            updated = self._replace_last_user_message(
                session=delegated.session,
                original=request.message.strip(),
                translated=translated,
            )
            return TurnResult(session=updated, assistant_message=delegated.assistant_message)

        if is_default_or_extension(session.extension_alias):
            sync_default_or_compatibility_state(
                session=session,
                registry=self._extension_registry,
            )
        else:
            discovered = self._extension_registry.require(session.extension_alias)
            runtime = discovered.create_runtime()
            manifest = discovered.manifest
            _recompute_extension_state(session=session, manifest=manifest, runtime=runtime)
            _sync_phase_and_summary(session, manifest)
            session.pending_question = _pending_question(session, manifest, runtime)

        interaction_state = build_interaction_state(
            session=session,
            registry=self._extension_registry,
        )

        if slash.name == "show":
            assistant_message = self._render_show_target(
                session=session,
                target=slash.arg or "steps",
            )
        elif slash.name == "help":
            assistant_message = render_help_text(interaction_state)
        elif slash.name == "explain":
            assistant_message = render_result_overview(session)
        elif slash.name == "validate":
            assistant_message = render_validation_overview(interaction_state)
        elif slash.name == "semantics":
            assistant_message = render_semantics_json(interaction_state.semantics)
        else:
            assistant_message = (
                "Команда не распознана. Используйте /help, чтобы увидеть доступные варианты."
            )

        result = self._append_assistant_reply(
            session=session,
            user_message=request.message,
            assistant_message=assistant_message,
        )
        self._store.save(result.session)
        return result
