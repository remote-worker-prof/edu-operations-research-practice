"""Unit-тесты extraction-логики параметров сценария.

Фокус: устойчивость к шумным/невалидным значениям от LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.extractor import extract_user_intent_and_params
from agent_core.models import LLMResponse


@dataclass
class _StubLLMClient:
    """Минимальный тестовый double для подмены `LLMClient.complete`."""

    content: str

    def complete(
        self,
        messages: list[dict[str, str]],
        model_alias: str,
        task_mode: str,
        temperature: float = 0,
    ) -> LLMResponse:
        """Возвращает заранее заданный контент без сетевого вызова."""
        return LLMResponse(
            content=self.content,
            model_alias=model_alias,
            model_name="stub",
        )


def test_extractor_handles_non_numeric_llm_values() -> None:
    """Проверяет, что нечисловые значения не приводят к падению extraction.

    Риск:
    - ValueError/ValidationError при некорректном payload модели.
    """
    # Arrange
    llm = _StubLLMClient(content='{"demand_multiplier":"abc","resource_multiplier":"oops"}')

    # Act
    result = extract_user_intent_and_params(
        message="используй коэффициенты из модели",
        model_alias="openai_default",
        llm_client=llm,  # type: ignore[arg-type]
    )

    # Assert
    assert result.demand_multiplier is None
    assert result.resource_multiplier is None
    assert "demand_multiplier должен быть числом в диапазоне (0, 2]" in result.errors
    assert "resource_multiplier должен быть числом в диапазоне (0, 2]" in result.errors


def test_extractor_keeps_valid_value_when_other_value_invalid() -> None:
    """Проверяет смешанный кейс: одно значение валидно, второе нет.

    Риск:
    - потеря корректного значения из-за ошибки в соседнем поле.
    """
    # Arrange
    llm = _StubLLMClient(content='{"demand_multiplier":1.2,"resource_multiplier":"x"}')

    # Act
    result = extract_user_intent_and_params(
        message="прими параметры модели",
        model_alias="openai_default",
        llm_client=llm,  # type: ignore[arg-type]
    )

    # Assert
    assert result.demand_multiplier == 1.2
    assert result.resource_multiplier is None
    assert "resource_multiplier должен быть числом в диапазоне (0, 2]" in result.errors
