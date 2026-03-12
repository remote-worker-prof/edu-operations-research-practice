"""NL-слой поверх командного parser-а для учебного сбора OR-входов.

Модуль не изменяет состояние сессии напрямую. Его задача:
- попытаться извлечь candidate patches из свободного текста;
- вернуть уверенность и неопределённости;
- при необходимости вызвать optional LLM-assisted fallback;
- отдать управление диалоговому графу, который решает, что применять.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.llm import LLMClient
from agent_core.models import CandidatePatch, NLParseResult, StageName, TeachingHint

_COMMAND_PREFIXES = (
    "start",
    "старт",
    "reset",
    "сброс",
    "show input",
    "show",
    "показать ввод",
    "next",
    "далее",
    "json ",
    "set ",
    "edit ",
    "load preset demo",
    "preset demo",
    "load demo",
    "загрузить демо",
)

_RUN_MARKERS = ("run", "запусти", "запуск", "посчитай", "рассчитай")
_HELP_MARKERS = ("help", "помощь", "что дальше", "как вводить")
_CONFIRM_MARKERS = ("да", "подтверждаю", "подтвердить", "ок", "согласен")
_REJECT_MARKERS = ("нет", "отмена", "не подтверждаю", "отклонить", "не так")

_STAGE_ALIASES: dict[StageName, tuple[str, ...]] = {
    "production": ("production", "prod", "производство", "выпуск"),
    "shipment": ("shipment", "ship", "отгрузка", "доставка"),
    "assignment": ("assignment", "assign", "назначение"),
    "routing": ("routing", "route", "маршрутизация", "маршруты"),
}

_FIELD_ALIASES: dict[StageName, dict[str, tuple[str, ...]]] = {
    "production": {
        "products": ("products", "продукты"),
        "profits": ("profits", "прибыль"),
        "resource_matrix": ("resource_matrix", "матрица ресурсов"),
        "resource_limits": ("resource_limits", "лимиты ресурсов"),
        "demand_upper_bounds": ("demand_upper_bounds", "верхние границы спроса", "спрос"),
        "pallet_factors": ("pallet_factors", "коэффициенты паллет"),
    },
    "shipment": {
        "warehouses": ("warehouses", "склады"),
        "warehouse_supply_ratio": ("warehouse_supply_ratio", "доли складов"),
        "clients": ("clients", "клиенты"),
        "client_demand": ("client_demand", "спрос клиентов"),
        "cost_matrix": ("cost_matrix", "матрица стоимости"),
        "capacity_matrix": ("capacity_matrix", "матрица пропускной способности", "capacity"),
    },
    "assignment": {
        "resources": ("resources", "ресурсы", "машины"),
        "cost_matrix": ("cost_matrix", "матрица назначения", "стоимость назначения"),
    },
    "routing": {
        "distance_matrix": ("distance_matrix", "матрица расстояний"),
        "depot_index": ("depot_index", "депо", "depot"),
        "client_nodes": ("client_nodes", "узлы клиентов"),
        "vehicle_capacities": ("vehicle_capacities", "емкости", "ёмкости", "capacities"),
        "objective": ("objective", "цель", "objective"),
    },
}

_HINTS: dict[tuple[StageName, str], TeachingHint] = {
    ("production", "profits"): TeachingHint(
        field="production.profits",
        meaning="Прибыль на единицу каждого продукта в LP-модели.",
        units="денежные единицы/шт",
        example="[40, 30]",
    ),
    ("shipment", "client_demand"): TeachingHint(
        field="shipment.client_demand",
        meaning="Спрос клиентов для min-cost flow этапа.",
        units="паллеты",
        example="[42, 38, 40]",
    ),
    ("assignment", "cost_matrix"): TeachingHint(
        field="assignment.cost_matrix",
        meaning="Стоимость назначения ресурса на клиента.",
        units="условная стоимость",
        example="[[8,6,7],[5,8,6],[7,5,9]]",
    ),
    ("routing", "distance_matrix"): TeachingHint(
        field="routing.distance_matrix",
        meaning="Матрица расстояний для CVRP.",
        units="км (или условные единицы расстояния)",
        example="[[0,10,12],[10,0,6],[12,6,0]]",
    ),
}


def teaching_hints_for_patches(patches: list[CandidatePatch]) -> list[TeachingHint]:
    """Возвращает учебные подсказки по списку candidate patches."""
    hints: list[TeachingHint] = []
    seen_fields: set[str] = set()
    for patch in patches:
        key = (patch.stage, patch.field_path)
        hint = _HINTS.get(key)
        if hint is None or hint.field in seen_fields:
            continue
        seen_fields.add(hint.field)
        hints.append(hint)
    return hints


def parse_nl_turn(
    *,
    message: str,
    current_stage: StageName | None,
    llm_client: LLMClient | None = None,
    model_alias: str | None = None,
) -> NLParseResult:
    """Пытается извлечь структурированные параметры OR из свободной реплики."""
    text = message.strip()
    if not text:
        return NLParseResult(intent="none", source_text=text)

    lower = text.lower()
    if lower.startswith(_COMMAND_PREFIXES):
        return NLParseResult(intent="none", source_text=text)

    if lower in _CONFIRM_MARKERS:
        return NLParseResult(intent="confirm", confidence=1.0, source_text=text)
    if lower in _REJECT_MARKERS:
        return NLParseResult(intent="reject", confidence=1.0, source_text=text)

    has_any_field_alias = _contains_any_field_alias(lower)
    if _contains_marker(lower, _RUN_MARKERS) and not has_any_field_alias:
        return NLParseResult(intent="run", confidence=0.9, source_text=text)
    if _contains_marker(lower, _HELP_MARKERS) and not has_any_field_alias:
        return NLParseResult(intent="help", confidence=0.9, source_text=text)

    stage, stage_is_explicit, stage_issues = _resolve_stage(
        lower=lower, current_stage=current_stage
    )
    if stage is None:
        uncertainties = stage_issues or ["Не удалось определить stage. Укажите один из 4 этапов."]
        allow_llm_stage_fallback = not any(
            "несколько stages" in issue.lower() for issue in uncertainties
        )
        if allow_llm_stage_fallback:
            llm_result = _try_llm_fallback_any_stage(
                text=text,
                llm_client=llm_client,
                model_alias=model_alias,
                deterministic_uncertainties=uncertainties,
            )
            if llm_result is not None:
                return llm_result
        return NLParseResult(
            intent="patch",
            uncertainties=uncertainties,
            confidence=0.25,
            source_text=text,
        )

    patches, parse_issues = _extract_patches_for_stage(text=text, lower=lower, stage=stage)
    uncertainties = [*stage_issues, *parse_issues]
    if not patches:
        uncertainties.append(
            f"Не нашёл значения полей для stage {stage}. Укажите хотя бы одно поле и его значение."
        )

    result = _build_patch_result(
        stage=stage,
        source_text=text,
        patches=patches,
        uncertainties=uncertainties,
        stage_is_explicit=stage_is_explicit,
    )
    if _needs_llm_fallback(result):
        llm_result = _try_llm_fallback(
            text=text,
            stage=stage,
            llm_client=llm_client,
            model_alias=model_alias,
            deterministic_uncertainties=uncertainties,
        )
        if llm_result is not None:
            return llm_result
    return result


def _build_patch_result(
    *,
    stage: StageName,
    source_text: str,
    patches: list[CandidatePatch],
    uncertainties: list[str],
    stage_is_explicit: bool,
) -> NLParseResult:
    """Формирует унифицированный NLParseResult для patch-интерпретации."""
    base_confidence = 0.6 if stage_is_explicit else 0.45
    confidence = max(
        0.0,
        min(0.98, base_confidence + 0.08 * len(patches) - 0.2 * len(uncertainties)),
    )
    return NLParseResult(
        intent="patch",
        candidate_patches=patches,
        uncertainties=uncertainties,
        confidence=confidence,
        source_text=source_text,
    )


def _needs_llm_fallback(result: NLParseResult) -> bool:
    """Определяет, нужен ли LLM-assisted fallback поверх детерминированного парсинга."""
    return result.intent == "patch" and (not result.candidate_patches or result.confidence < 0.5)


def _try_llm_fallback(
    *,
    text: str,
    stage: StageName,
    llm_client: LLMClient | None,
    model_alias: str | None,
    deterministic_uncertainties: list[str],
) -> NLParseResult | None:
    """Пробует улучшить extraction через LLM, если провайдер доступен."""
    if llm_client is None or not model_alias:
        return None
    if model_alias not in llm_client.available_aliases():
        return None

    prompt = [
        {
            "role": "system",
            "content": (
                "Ты извлекаешь структурированные параметры OR-модели. "
                "Верни только JSON формата: "
                '{"stage":"<stage>","patches":[{"field_path":"<name>","value":<json_value>}],"uncertainties":["..."]}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stage: {stage}\n"
                f"User text: {text}\n"
                "Извлеки только поля этого stage. Если не уверен, добавь uncertainties."
            ),
        },
    ]
    try:
        response = llm_client.complete(
            messages=prompt,
            model_alias=model_alias,
            task_mode="parse_nl_turn_llm_fallback",
            temperature=0,
        )
        payload = _parse_json_object(response.content)
        if not isinstance(payload, dict):
            return None
        llm_stage = payload.get("stage")
        if isinstance(llm_stage, str) and llm_stage != stage:
            return None

        raw_patches = payload.get("patches", [])
        parsed_patches: list[CandidatePatch] = []
        if isinstance(raw_patches, list):
            for item in raw_patches:
                if not isinstance(item, dict):
                    continue
                field_path = item.get("field_path")
                if not isinstance(field_path, str):
                    continue
                parsed_patches.append(
                    CandidatePatch(
                        stage=stage,
                        field_path=field_path,
                        value=item.get("value"),
                        source_text=text,
                    )
                )
        raw_uncertainties = payload.get("uncertainties", [])
        uncertainties = (
            [u for u in raw_uncertainties if isinstance(u, str)]
            if isinstance(raw_uncertainties, list)
            else []
        )

        if not parsed_patches and not uncertainties:
            return None

        # LLM fallback должен быть полезнее детерминированного baseline, иначе
        # оставляем исходную ветку с её объяснимыми ошибками.
        if not parsed_patches and deterministic_uncertainties:
            return None

        return NLParseResult(
            intent="patch",
            candidate_patches=parsed_patches,
            uncertainties=uncertainties,
            confidence=0.72 if parsed_patches else 0.35,
            source_text=text,
        )
    except (ModelUnavailableError, ModelProviderError):
        return None
    except Exception:
        return None


def _try_llm_fallback_any_stage(
    *,
    text: str,
    llm_client: LLMClient | None,
    model_alias: str | None,
    deterministic_uncertainties: list[str],
) -> NLParseResult | None:
    """Пробует LLM-assisted extraction, когда stage не удалось определить детерминированно."""
    if llm_client is None or not model_alias:
        return None
    if model_alias not in llm_client.available_aliases():
        return None

    prompt = [
        {
            "role": "system",
            "content": (
                "Ты извлекаешь структурированные параметры OR-модели. "
                "Разрешённые stage: production, shipment, assignment, routing. "
                "Верни только JSON формата: "
                '{"stage":"<stage>","patches":[{"field_path":"<name>","value":<json_value>}],"uncertainties":["..."]}'
            ),
        },
        {
            "role": "user",
            "content": f"User text: {text}",
        },
    ]
    try:
        response = llm_client.complete(
            messages=prompt,
            model_alias=model_alias,
            task_mode="parse_nl_turn_llm_stage_fallback",
            temperature=0,
        )
        payload = _parse_json_object(response.content)
        if not isinstance(payload, dict):
            return None
        raw_stage = payload.get("stage")
        if not isinstance(raw_stage, str):
            return None
        normalized_stage = raw_stage.strip().lower()
        if normalized_stage not in _STAGE_ALIASES:
            return None
        stage = cast(StageName, normalized_stage)
        raw_patches = payload.get("patches", [])
        parsed_patches: list[CandidatePatch] = []
        if isinstance(raw_patches, list):
            for item in raw_patches:
                if not isinstance(item, dict):
                    continue
                field_path = item.get("field_path")
                if not isinstance(field_path, str):
                    continue
                parsed_patches.append(
                    CandidatePatch(
                        stage=stage,
                        field_path=field_path,
                        value=item.get("value"),
                        source_text=text,
                    )
                )
        raw_uncertainties = payload.get("uncertainties", [])
        uncertainties = (
            [u for u in raw_uncertainties if isinstance(u, str)]
            if isinstance(raw_uncertainties, list)
            else []
        )

        if not parsed_patches and not uncertainties:
            return None
        if not parsed_patches and deterministic_uncertainties:
            return None
        return NLParseResult(
            intent="patch",
            candidate_patches=parsed_patches,
            uncertainties=uncertainties,
            confidence=0.68 if parsed_patches else 0.35,
            source_text=text,
        )
    except (ModelUnavailableError, ModelProviderError):
        return None
    except Exception:
        return None


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Извлекает JSON-объект из ответа модели (включая fenced блоки)."""
    candidate = raw.strip()
    if candidate.startswith("```"):
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            return None
        candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _contains_any_field_alias(lower: str) -> bool:
    """Проверяет, содержит ли реплика маркеры структурированных полей."""
    for stage_fields in _FIELD_ALIASES.values():
        for aliases in stage_fields.values():
            if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower) for alias in aliases):
                return True
    return False


def _contains_marker(lower: str, markers: tuple[str, ...]) -> bool:
    """Проверяет наличие intent-маркера как отдельного токена/фразы."""
    return any(re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lower) for marker in markers)


def _resolve_stage(
    *,
    lower: str,
    current_stage: StageName | None,
) -> tuple[StageName | None, bool, list[str]]:
    """Определяет stage для реплики и возвращает возможные неопределённости."""
    detected: list[StageName] = []
    for stage, aliases in _STAGE_ALIASES.items():
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower) for alias in aliases):
            detected.append(stage)

    if len(detected) > 1:
        return (
            None,
            False,
            ["В одном сообщении найдено несколько stages. Укажите только один stage."],
        )
    if len(detected) == 1:
        return detected[0], True, []
    if current_stage is not None:
        return current_stage, False, []
    return None, False, ["Stage не указан и не выбран в wizard-контексте."]


def _extract_patches_for_stage(
    *,
    text: str,
    lower: str,
    stage: StageName,
) -> tuple[list[CandidatePatch], list[str]]:
    """Извлекает candidate patches по полям выбранного stage."""
    patches: list[CandidatePatch] = []
    issues: list[str] = []
    for field, aliases in _FIELD_ALIASES[stage].items():
        start = _find_alias_position(lower=lower, aliases=aliases)
        if start is None:
            continue
        parsed = _parse_value_after_alias(text=text, alias_end=start)
        if parsed is None:
            issues.append(f"Не удалось распарсить значение для поля `{stage}.{field}`.")
            continue
        value, source_fragment = parsed
        patches.append(
            CandidatePatch(
                stage=stage,
                field_path=field,
                value=value,
                source_text=source_fragment,
            )
        )
    return patches, issues


def _find_alias_position(*, lower: str, aliases: tuple[str, ...]) -> int | None:
    """Возвращает позицию конца найденного алиаса поля в строке."""
    for alias in aliases:
        match = re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", lower)
        if match is not None:
            return match.end()
    return None


def _parse_value_after_alias(*, text: str, alias_end: int) -> tuple[object, str] | None:
    """Разбирает значение поля, идущее после алиаса и возможного разделителя."""
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


def _read_balanced(*, text: str, start: int) -> tuple[str | None, int]:
    """Считывает сбалансированный JSON-фрагмент массива/объекта."""
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
