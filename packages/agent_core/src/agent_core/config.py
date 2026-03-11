"""Configuration helpers for model aliases and scenario paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelAliasConfig:
    alias: str
    model_env: str
    default_model: str
    api_key_env: str | None = None
    base_url_env: str | None = None


MODEL_ALIASES: dict[str, ModelAliasConfig] = {
    "openai_default": ModelAliasConfig(
        alias="openai_default",
        model_env="OPENAI_MODEL",
        default_model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
    ),
    "gigachat_default": ModelAliasConfig(
        alias="gigachat_default",
        model_env="GIGACHAT_MODEL",
        default_model="gigachat/GigaChat",
        api_key_env="GIGACHAT_API_KEY",
        base_url_env="GIGACHAT_BASE_URL",
    ),
    "local_default": ModelAliasConfig(
        alias="local_default",
        model_env="LOCAL_LLM_MODEL",
        default_model="openai/local-model",
        api_key_env="LOCAL_LLM_API_KEY",
        base_url_env="LOCAL_LLM_BASE_URL",
    ),
}


def resolve_model_name(alias: str) -> str:
    config = MODEL_ALIASES[alias]
    return os.getenv(config.model_env, config.default_model)


def default_scenario_path() -> Path:
    env_path = os.getenv("SCENARIO_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "scenarios" / "base_scenario.json"
