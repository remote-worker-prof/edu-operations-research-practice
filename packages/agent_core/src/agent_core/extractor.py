"""Извлечение коэффициентов сценария из естественного языка пользователя.

Модуль использует гибридный подход:
- сначала пытается получить структурированный JSON от LLM;
- затем дополняет/страхует результат регулярными выражениями;
- в конце валидирует числовые границы.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.llm import LLMClient
from agent_core.models import ExtractionResult

_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_NUMBER_PATTERN = re.compile(r"([0-9]+(?:[\.,][0-9]+)?)")


def _to_float(value: str) -> float | None:
    """Пытается преобразовать строку в float с поддержкой запятой."""
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    """Извлекает JSON-объект из ответа LLM (включая fenced code block)."""
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
    """Локально извлекает коэффициенты спроса/ресурсов регулярными выражениями."""
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


def _parse_multiplier(
    *,
    field_name: str,
    raw_value: Any,
    errors: list[str],
) -> float | None:
    """Преобразует и валидирует одно значение коэффициента.

    Если значение некорректно, добавляет человеко-понятную ошибку в `errors`.
    """
    if raw_value is None:
        return None

    numeric: float | None
    if isinstance(raw_value, (int, float)):
        numeric = float(raw_value)
    elif isinstance(raw_value, str):
        numeric = _to_float(raw_value)
    else:
        numeric = None

    if numeric is None:
        errors.append(f"{field_name} должен быть числом в диапазоне (0, 2]")
        return None

    if not 0 < numeric <= 2:
        errors.append(f"{field_name} должен быть в диапазоне (0, 2]")
        return None

    return numeric


def extract_user_intent_and_params(
    message: str,
    model_alias: str,
    llm_client: LLMClient,
) -> ExtractionResult:
    """Извлекает коэффициенты сценария из текста пользователя.

    Что делает:
    - отправляет extraction-prompt в LLM;
    - разбирает JSON-ответ (если есть);
    - применяет regex-парсинг как fallback;
    - валидирует диапазоны коэффициентов `(0, 2]`.

    Зачем:
    - пользователь может писать свободным языком, а система всё равно получает
      валидные числовые параметры для OR-пайплайна.

    Входы:
    - `message`: текст реплики пользователя;
    - `model_alias`: выбранный alias модели;
    - `llm_client`: клиент доступа к LLM.

    Выходы:
    - `ExtractionResult` с коэффициентами, предупреждениями и ошибками.

    Ошибки:
    - сетевые/провайдерные сбои не пробрасываются наружу, а превращаются в warnings.

    Пример:
    - `message=\"спрос 1.2, ресурс 0.9\"` -> `demand_multiplier=1.2`, `resource_multiplier=0.9`.
    """
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

    # Локальный парсер работает как страховка, если провайдер недоступен
    # или вернул невалидный JSON. Это критично для устойчивости демо на занятии.
    regex_result = _extract_with_regex(message)
    for key, value in regex_result.items():
        extracted.setdefault(key, value)

    demand_multiplier = _parse_multiplier(
        field_name="demand_multiplier",
        raw_value=extracted.get("demand_multiplier"),
        errors=errors,
    )
    resource_multiplier = _parse_multiplier(
        field_name="resource_multiplier",
        raw_value=extracted.get("resource_multiplier"),
        errors=errors,
    )

    return ExtractionResult(
        demand_multiplier=demand_multiplier,
        resource_multiplier=resource_multiplier,
        warnings=warnings,
        errors=errors,
    )
