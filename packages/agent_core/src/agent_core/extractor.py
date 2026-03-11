"""Parameter extraction for dialog turns."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.llm import LLMClient
from agent_core.models import ExtractionResult

_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_NUMBER_PATTERN = re.compile(r"([0-9]+(?:[\.,][0-9]+)?)")


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    candidate = raw

    if raw.startswith("```"):
        match = _JSON_PATTERN.search(raw)
        if not match:
            return None
        candidate = match.group(0)

    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return None
    return None


def _extract_with_regex(message: str) -> dict[str, float]:
    normalized = message.lower()
    extracted: dict[str, float] = {}

    demand_keywords = ["спрос", "demand"]
    resource_keywords = ["ресурс", "resource"]

    for keyword in demand_keywords:
        if keyword in normalized:
            tail = normalized.split(keyword, maxsplit=1)[1]
            number_match = _NUMBER_PATTERN.search(tail)
            if number_match:
                parsed = _to_float(number_match.group(1))
                if parsed is not None:
                    extracted["demand_multiplier"] = parsed
                    break

    for keyword in resource_keywords:
        if keyword in normalized:
            tail = normalized.split(keyword, maxsplit=1)[1]
            number_match = _NUMBER_PATTERN.search(tail)
            if number_match:
                parsed = _to_float(number_match.group(1))
                if parsed is not None:
                    extracted["resource_multiplier"] = parsed
                    break

    # If user only gives two numbers, assume demand then resources.
    if len(extracted) < 2:
        numbers = [_to_float(match) for match in _NUMBER_PATTERN.findall(normalized)]
        numbers = [value for value in numbers if value is not None]
        if len(numbers) >= 2:
            extracted.setdefault("demand_multiplier", float(numbers[0]))
            extracted.setdefault("resource_multiplier", float(numbers[1]))

    if "баз" in normalized and "demand_multiplier" not in extracted:
        extracted["demand_multiplier"] = 1.0
    if "баз" in normalized and "resource_multiplier" not in extracted:
        extracted["resource_multiplier"] = 1.0

    return extracted


def extract_user_intent_and_params(
    message: str,
    model_alias: str,
    llm_client: LLMClient,
) -> ExtractionResult:
    """Extract scenario multipliers from free-form user text."""
    warnings: list[str] = []
    errors: list[str] = []
    extracted: dict[str, Any] = {}

    prompt = [
        {
            "role": "system",
            "content": (
                "Извлеки параметры сценария из сообщения пользователя. "
                "Верни ТОЛЬКО JSON вида "
                '{"demand_multiplier": <float|null>, "resource_multiplier": <float|null>}.'
            ),
        },
        {"role": "user", "content": message},
    ]

    try:
        llm_response = llm_client.complete(
            messages=prompt,
            model_alias=model_alias,
            task_mode="extract_user_intent_and_params",
            temperature=0,
        )
        payload = _parse_llm_json(llm_response.content)
        if payload:
            extracted.update(payload)
        else:
            warnings.append("LLM вернул не-JSON формат, применён локальный парсер")
    except ModelUnavailableError as exc:
        warnings.append(str(exc))
    except ModelProviderError as exc:
        warnings.append(str(exc))

    regex_result = _extract_with_regex(message)
    for key, value in regex_result.items():
        extracted.setdefault(key, value)

    try:
        return ExtractionResult(
            demand_multiplier=extracted.get("demand_multiplier"),
            resource_multiplier=extracted.get("resource_multiplier"),
            warnings=warnings,
            errors=errors,
        )
    except ValidationError:
        for field_name in ("demand_multiplier", "resource_multiplier"):
            value = extracted.get(field_name)
            if value is not None and not (0 < float(value) <= 2):
                errors.append(f"{field_name} должен быть в диапазоне (0, 2]")
        return ExtractionResult(warnings=warnings, errors=errors)
