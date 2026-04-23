"""Open-ended but guarded NL interpretation over typed extension semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from extension_api import (
    ExtensionBundleSemantics,
    ExtensionManifest,
    IntentResolution,
    PatchProposal,
    SemanticIntent,
)

from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.llm import LLMClient
from agent_core.semantic_schema import (
    field_catalog,
    resolve_field_path,
    resolve_stage_id,
    stage_alias_items_by_specificity,
    stage_catalog,
)

_COMMAND_PREFIXES = (
    "/",
    "start",
    "старт",
    "help",
    "помощь",
    "reset",
    "сброс",
    "show",
    "показать",
    "next",
    "далее",
    "json ",
    "set ",
    "edit ",
    "run",
    "запуск",
    "load preset demo",
    "preset demo",
    "load demo",
    "загрузить демо",
)

_SHOW_MARKERS = ("покажи", "показать", "show")
_STEPS_MARKERS = ("этап", "этапы", "шаг", "шаги", "steps", "stages")
_DRAFT_MARKERS = ("черновик", "draft", "ввод", "input", "данные")
_RESULT_MARKERS = ("результат", "решение", "итог", "result", "solution")
_RUN_MARKERS = ("реши", "посчитай", "запусти", "рассчитай", "solve", "run")
_VALIDATE_MARKERS = ("проверь", "валидац", "validate", "check")
_RESET_MARKERS = ("сбрось", "очисти", "reset")
_HELP_MARKERS = ("помощ", "help", "что дальше", "как работать", "как пользоваться")
_EXPLAIN_MARKERS = ("объяс", "пояс", "explain")
_MODEL_MARKERS = ("model", "model.orx", "модель")
_EXTENSION_MARKERS = (
    "extension",
    "extension.yaml",
    "sidecar",
    "конфиг",
    "extension.yaml",
)
_STEP_MARKERS = ("step", "stage", "шаг", "этап")
_CONFIRM_MARKERS = ("да", "подтверждаю", "подтвердить", "ок", "согласен")
_REJECT_MARKERS = ("нет", "отмена", "отклонить", "не подтверждаю")


def _contains_marker(lower: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lower) for marker in markers)


def _parse_json_object(raw: str) -> dict[str, object] | None:
    candidate = raw.strip()
    if candidate.startswith("```"):
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match is None:
            return None
        candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _read_balanced(*, text: str, start: int) -> tuple[str | None, int]:
    opening = text[start]
    closing = "]" if opening == "[" else "}"
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
        i += 1
    return None, start


def _parse_value_after_alias(*, text: str, alias_end: int) -> tuple[object, str] | None:
    i = alias_end
    while i < len(text) and text[i] in " \t:=-":
        i += 1
    if i >= len(text):
        return None

    if text[i] in "[{":
        value_text, _ = _read_balanced(text=text, start=i)
        if value_text is None:
            return None
        try:
            return json.loads(value_text), value_text
        except json.JSONDecodeError:
            return None

    token_end = i
    while token_end < len(text) and text[token_end] not in ",;\n":
        token_end += 1
    token = text[i:token_end].strip()
    if not token:
        return None
    try:
        return json.loads(token), token
    except json.JSONDecodeError:
        pass
    if re.fullmatch(r"-?\d+", token):
        return int(token), token
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token), token
    return token, token


def _find_alias_match(lower: str, aliases: list[str]) -> tuple[int, str] | None:
    best: tuple[int, str] | None = None
    for alias in aliases:
        match = re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", lower)
        if match is None:
            continue
        candidate = (match.end(), alias)
        if best is None or len(alias) > len(best[1]):
            best = candidate
    return best


@dataclass(frozen=True)
class NonMutatingIntentRecognizer:
    """Recognize read-only or navigation intents without producing draft patches."""

    def recognize(
        self,
        *,
        text: str,
        lower: str,
        current_stage: str | None,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution | None:
        if _contains_marker(lower, _SHOW_MARKERS):
            if _contains_marker(lower, _STEPS_MARKERS):
                target = "steps"
            elif _contains_marker(lower, _DRAFT_MARKERS):
                target = "draft"
            elif _contains_marker(lower, _RESULT_MARKERS):
                target = "result"
            else:
                target = "steps"
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="show", raw_message=text, target=target),
                confidence=0.85,
                grounded=True,
            )
        if _contains_marker(lower, _HELP_MARKERS):
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="help", raw_message=text),
                confidence=0.85,
                grounded=True,
            )
        if _contains_marker(lower, _RUN_MARKERS):
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="solve", raw_message=text),
                confidence=0.8,
                grounded=True,
            )
        if _contains_marker(lower, _VALIDATE_MARKERS):
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="validate", raw_message=text),
                confidence=0.8,
                grounded=True,
            )
        if _contains_marker(lower, _RESET_MARKERS):
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="reset", raw_message=text),
                confidence=0.8,
                grounded=True,
            )
        if _contains_marker(lower, _EXPLAIN_MARKERS):
            target = "result"
            if _contains_marker(lower, _MODEL_MARKERS):
                target = "model"
            elif _contains_marker(lower, _EXTENSION_MARKERS):
                target = "extension"
            elif _contains_marker(lower, _STEP_MARKERS):
                target = f"step {current_stage}" if current_stage else "step"
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="explain", raw_message=text, target=target),
                confidence=0.8,
                grounded=True,
            )

        if not _contains_marker(lower, _STEP_MARKERS):
            return None
        for stage in stage_catalog(manifest=manifest, semantics=semantics):
            aliases = [stage.stage_id, stage.label, *stage.aliases]
            if any(
                re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", lower)
                for alias in aliases
            ):
                return IntentResolution(
                    source="semantic_nl",
                    intent=SemanticIntent(kind="step", raw_message=text, stage_id=stage.stage_id),
                    confidence=0.75,
                    grounded=True,
                )
        return None


@dataclass(frozen=True)
class GroundedPatchExtractor:
    """Extract grounded patch proposals using only known stage/field semantics."""

    def extract(
        self,
        *,
        text: str,
        lower: str,
        current_stage: str | None,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> IntentResolution:
        explicit_stage_ids = self._explicit_stage_ids(
            lower=lower,
            manifest=manifest,
            semantics=semantics,
        )
        clarifications: list[str] = []

        if explicit_stage_ids:
            stage_ids = explicit_stage_ids
            explicit = True
        elif current_stage:
            stage_ids = [current_stage]
            explicit = False
        else:
            inferred_stage_ids, inferred_clarifications = self._infer_stage_ids_from_field_hits(
                lower=lower,
                manifest=manifest,
                semantics=semantics,
            )
            stage_ids = inferred_stage_ids
            explicit = False
            clarifications.extend(inferred_clarifications)

        proposals: list[PatchProposal] = []
        for stage_id in stage_ids:
            for field in field_catalog(
                manifest=manifest,
                semantics=semantics,
                stage_id=stage_id,
            ):
                aliases = [field.field_path, field.label, *field.aliases]
                match = _find_alias_match(lower, aliases)
                if match is None:
                    continue
                parsed = _parse_value_after_alias(text=text, alias_end=match[0])
                if parsed is None:
                    clarifications.append(
                        f"Не удалось распарсить значение для поля `{stage_id}.{field.field_path}`."
                    )
                    continue
                value, _ = parsed
                proposals.append(
                    PatchProposal(
                        stage_id=stage_id,
                        path=field.field_path,
                        value=value,
                        confidence=0.74 if explicit else 0.62,
                        source="semantic_nl",
                    )
                )

        grounded = bool(proposals)
        confidence = 0.0
        if grounded:
            confidence = min(
                0.92,
                (0.62 if explicit else 0.52)
                + 0.08 * len(proposals)
                - 0.15 * len(clarifications),
            )
            confidence = max(confidence, 0.35)
        elif not clarifications:
            clarifications.append(
                "Не удалось привязать сообщение к известным stage и полям текущего extension."
            )

        return IntentResolution(
            source="semantic_nl",
            intent=SemanticIntent(kind="patch_draft", raw_message=text),
            proposals=proposals,
            confidence=confidence,
            grounded=grounded,
            clarifications=clarifications,
        )

    def _explicit_stage_ids(
        self,
        *,
        lower: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> list[str]:
        detected: list[str] = []
        for alias, stage_id in stage_alias_items_by_specificity(
            manifest=manifest,
            semantics=semantics,
        ):
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower):
                detected.append(stage_id)
        return list(dict.fromkeys(detected))

    def _infer_stage_ids_from_field_hits(
        self,
        *,
        lower: str,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
    ) -> tuple[list[str], list[str]]:
        stage_hits: dict[str, int] = {}
        for stage in stage_catalog(manifest=manifest, semantics=semantics):
            hits = 0
            for field in stage.fields:
                aliases = [field.field_path, field.label, *field.aliases]
                if _find_alias_match(lower, aliases) is not None:
                    hits += 1
            if hits:
                stage_hits[stage.stage_id] = hits
        if len(stage_hits) == 1:
            return [next(iter(stage_hits))], []
        if len(stage_hits) > 1:
            ordered = ", ".join(stage_hits)
            return [], [
                f"Сообщение похоже затрагивает несколько этапов сразу: {ordered}. Уточните stage."
            ]
        return [], ["Stage не указан и не может быть выведен из известных полей."]


@dataclass(frozen=True)
class LlmFallbackExtractor:
    """Ask an LLM for a grounded patch plan when deterministic extraction is insufficient."""

    llm_client: LLMClient | None = None

    def extract(
        self,
        *,
        text: str,
        current_stage: str | None,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
        model_alias: str | None,
        deterministic_issues: list[str],
    ) -> IntentResolution | None:
        if self.llm_client is None or not model_alias:
            return None
        if model_alias not in self.llm_client.available_aliases():
            return None

        stage_lines: list[str] = []
        for stage in stage_catalog(manifest=manifest, semantics=semantics):
            field_names = ", ".join(field.field_path for field in stage.fields)
            stage_lines.append(f"- {stage.stage_id}: {field_names}")

        prompt = [
            {
                "role": "system",
                "content": (
                    "Ты извлекаешь intent и патчи только в терминах заданной "
                    "schema-driven semantics. Верни только JSON формата: "
                    '{"intent":"patch_draft","patches":[{"stage_id":"<stage>",'
                    '"field_path":"<field>","value":<json>}],"clarifications":["..."]}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Active stage: {current_stage or 'none'}\n"
                    f"Known stages and fields:\n"
                    + "\n".join(stage_lines)
                    + f"\nUser text: {text}"
                ),
            },
        ]
        try:
            response = self.llm_client.complete(
                messages=prompt,
                model_alias=model_alias,
                task_mode="semantic_intent_llm_fallback",
                temperature=0,
            )
            payload = _parse_json_object(response.content)
            if not isinstance(payload, dict):
                return None
            raw_patches = payload.get("patches", [])
            proposals: list[PatchProposal] = []
            if isinstance(raw_patches, list):
                for item in raw_patches:
                    if not isinstance(item, dict):
                        continue
                    stage_id = item.get("stage_id")
                    raw_field = item.get("field_path")
                    if not isinstance(stage_id, str) or not isinstance(raw_field, str):
                        continue
                    resolved_stage = resolve_stage_id(
                        raw=stage_id,
                        manifest=manifest,
                        semantics=semantics,
                    )
                    if resolved_stage is None:
                        continue
                    resolved_field = resolve_field_path(
                        raw=raw_field,
                        stage_id=resolved_stage,
                        manifest=manifest,
                        semantics=semantics,
                    )
                    if resolved_field is None:
                        continue
                    proposals.append(
                        PatchProposal(
                            stage_id=resolved_stage,
                            path=resolved_field,
                            value=item.get("value"),
                            confidence=0.68,
                            source="llm",
                            rationale="LLM fallback grounded in typed semantics.",
                        )
                    )
            raw_clarifications = payload.get("clarifications", [])
            clarifications = (
                [item for item in raw_clarifications if isinstance(item, str)]
                if isinstance(raw_clarifications, list)
                else []
            )
            if not proposals and not clarifications:
                return None
            if not proposals and deterministic_issues:
                return None
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="patch_draft", raw_message=text),
                proposals=proposals,
                confidence=0.68 if proposals else 0.3,
                grounded=bool(proposals),
                clarifications=clarifications,
            )
        except (ModelUnavailableError, ModelProviderError):
            return None
        except Exception:
            return None


@dataclass(frozen=True)
class SemanticIntentEngine:
    """Strategy that extracts typed intents and grounded patch proposals from NL."""

    llm_client: LLMClient | None = None

    def interpret(
        self,
        *,
        message: str,
        current_stage: str | None,
        manifest: ExtensionManifest,
        semantics: ExtensionBundleSemantics | None,
        model_alias: str | None,
    ) -> IntentResolution:
        text = message.strip()
        if not text:
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="unknown", raw_message=text),
                confidence=0.0,
                grounded=False,
            )

        lower = text.lower()
        if lower.startswith(_COMMAND_PREFIXES) or (text.startswith("{") and text.endswith("}")):
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="unknown", raw_message=text),
                confidence=0.0,
                grounded=False,
            )

        if lower in _CONFIRM_MARKERS:
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="confirm", raw_message=text),
                confidence=1.0,
                grounded=True,
            )
        if lower in _REJECT_MARKERS:
            return IntentResolution(
                source="semantic_nl",
                intent=SemanticIntent(kind="reject", raw_message=text),
                confidence=1.0,
                grounded=True,
            )

        recognizer = NonMutatingIntentRecognizer()
        non_mutating = recognizer.recognize(
            text=text,
            lower=lower,
            current_stage=current_stage,
            manifest=manifest,
            semantics=semantics,
        )
        if non_mutating is not None:
            return non_mutating

        grounded_extractor = GroundedPatchExtractor()
        deterministic = grounded_extractor.extract(
            text=text,
            lower=lower,
            current_stage=current_stage,
            manifest=manifest,
            semantics=semantics,
        )
        if deterministic.proposals and deterministic.grounded:
            return deterministic

        llm_fallback = LlmFallbackExtractor(llm_client=self.llm_client).extract(
            text=text,
            current_stage=current_stage,
            manifest=manifest,
            semantics=semantics,
            model_alias=model_alias,
            deterministic_issues=deterministic.clarifications,
        )
        return llm_fallback or deterministic
