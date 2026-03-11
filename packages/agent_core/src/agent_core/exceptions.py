"""Agent-specific exceptions."""


class AgentError(RuntimeError):
    """Base error for dialog agent orchestration."""


class ModelUnavailableError(AgentError):
    """Raised when a requested model alias cannot be used from current env."""


class ModelProviderError(AgentError):
    """Raised when provider call fails at runtime."""
