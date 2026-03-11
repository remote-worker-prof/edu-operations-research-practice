"""Explanation generation for OR results."""

from __future__ import annotations

from or_core.models import ORResult

from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.llm import LLMClient


def fallback_explanation(result: ORResult) -> str:
    """Deterministic explanation used when LLM provider is unavailable."""
    assignment_rows = ", ".join(
        f"{pair.resource}->{pair.client} ({pair.assigned_volume})"
        for pair in result.assignment.pairs
    )
    return (
        "Результат рассчитан детерминированным OR-пайплайном. "
        f"Производство: {result.production.quantities}. "
        f"Отгружено: {result.shipment.total_dispatched} паллет. "
        f"Назначения: {assignment_rows}. "
        f"Маршруты: суммарная длина {result.routing.total_distance}."
    )


def explain_result_for_student(
    *,
    result: ORResult,
    model_alias: str,
    llm_client: LLMClient,
) -> tuple[str, list[str]]:
    """Generate a student-friendly explanation with graceful fallback."""
    warnings: list[str] = []

    prompt = [
        {
            "role": "system",
            "content": (
                "Ты помощник преподавателя по исследованию операций. "
                "Объясни студенту решение простым языком, но структурно: "
                "1) что решили на каждом шаге, 2) итоговая рекомендация. "
                "Коротко, без воды."
            ),
        },
        {
            "role": "user",
            "content": (
                "Вот результат OR-пайплайна:\n"
                f"{result.model_dump_json(indent=2, ensure_ascii=False)}"
            ),
        },
    ]

    try:
        response = llm_client.complete(
            messages=prompt,
            model_alias=model_alias,
            task_mode="explain_result_for_student",
            temperature=0.1,
        )
        return response.content, warnings
    except ModelUnavailableError as exc:
        warnings.append(str(exc))
        return fallback_explanation(result), warnings
    except ModelProviderError as exc:
        warnings.append(str(exc))
        return fallback_explanation(result), warnings
