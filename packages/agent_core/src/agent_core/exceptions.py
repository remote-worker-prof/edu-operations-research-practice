"""Иерархия исключений для слоя `agent_core`.

Эти типы позволяют отличать:
- ошибки недоступности провайдера (конфигурация/окружение);
- runtime-ошибки вызова модели.
"""


class AgentError(RuntimeError):
    """Базовое исключение для оркестрации диалога в `agent_core`."""


class ModelUnavailableError(AgentError):
    """Ошибка: выбранный alias модели недоступен в текущем окружении."""


class ModelProviderError(AgentError):
    """Ошибка: провайдер модели вернул runtime-сбой во время запроса."""
