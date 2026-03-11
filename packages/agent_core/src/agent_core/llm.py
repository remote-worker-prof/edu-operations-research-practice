"""LiteLLM adapter with graceful fallback semantics."""

from __future__ import annotations

import os
from typing import Any

from litellm import completion

from agent_core.config import MODEL_ALIASES, resolve_model_name
from agent_core.exceptions import ModelProviderError, ModelUnavailableError
from agent_core.models import LLMResponse


class LLMClient:
    """Thin wrapper around LiteLLM for alias-based provider routing."""

    def available_aliases(self) -> list[str]:
        available: list[str] = []
        for alias in MODEL_ALIASES:
            if self._is_alias_available(alias):
                available.append(alias)
        return available

    def complete(
        self,
        messages: list[dict[str, str]],
        model_alias: str,
        task_mode: str,
        temperature: float = 0,
    ) -> LLMResponse:
        """Call LiteLLM for the requested alias or raise a descriptive error."""
        if model_alias not in MODEL_ALIASES:
            raise ModelUnavailableError(f"Unknown model alias: {model_alias}")

        if not self._is_alias_available(model_alias):
            available = self.available_aliases()
            hint = ", ".join(available) if available else "нет доступных провайдеров"
            raise ModelUnavailableError(
                f"Модель '{model_alias}' недоступна в текущем окружении. Доступно: {hint}"
            )

        model_name = resolve_model_name(model_alias)
        kwargs = self._completion_kwargs(model_alias)

        try:
            response: Any = completion(
                model=model_name,
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            content = response.choices[0].message.content
            if not content:
                raise ModelProviderError(
                    f"Провайдер '{model_alias}' вернул пустой ответ для режима {task_mode}"
                )
            return LLMResponse(content=content, model_alias=model_alias, model_name=model_name)
        except ModelProviderError:
            raise
        except Exception as exc:  # pragma: no cover - network/provider variance
            raise ModelProviderError(
                f"Ошибка вызова модели '{model_alias}' в режиме '{task_mode}': {exc}"
            ) from exc

    def _is_alias_available(self, model_alias: str) -> bool:
        config = MODEL_ALIASES[model_alias]
        if model_alias == "local_default":
            return bool(config.base_url_env and os.getenv(config.base_url_env))

        if config.api_key_env and not os.getenv(config.api_key_env):
            return False
        if config.base_url_env and not os.getenv(config.base_url_env):
            return False
        return True

    def _completion_kwargs(self, model_alias: str) -> dict[str, Any]:
        config = MODEL_ALIASES[model_alias]
        kwargs: dict[str, Any] = {}

        if model_alias != "local_default" and config.api_key_env:
            kwargs["api_key"] = os.getenv(config.api_key_env)

        if model_alias == "local_default":
            kwargs["api_base"] = os.getenv(config.base_url_env or "", "")
            kwargs["api_key"] = os.getenv(config.api_key_env or "", "local")
        elif config.base_url_env and os.getenv(config.base_url_env):
            kwargs["api_base"] = os.getenv(config.base_url_env)

        return kwargs
