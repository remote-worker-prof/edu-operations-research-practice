"""Конфигурационные функции для model aliases и путей сценариев.

Назначение модуля:
- хранить декларативный реестр поддерживаемых LLM alias;
- предоставлять функции доступа к именам моделей и путям сценариев.

Роль в архитектуре:
- единый источник истины для web-слоя и `LLMClient`;
- устраняет дублирование технических alias в UI и бизнес-логике.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelAliasConfig:
    """Описание одного alias модели в прикладном слое.

    Что делает:
    - хранит все параметры, необходимые для резолва модели и её провайдера.

    Зачем:
    - позволяет переключать провайдеры через конфиг, не меняя код бизнес-логики.

    Входы:
    - поля dataclass (`alias`, `display_name`, `model_env`, `default_model`, ...).

    Выходы:
    - неизменяемый объект конфигурации (благодаря `frozen=True`).

    Ошибки:
    - валидация полей выполняется на уровне Python-типов и использования.

    Пример:
    - `MODEL_ALIASES["openai_default"]` возвращает конфиг OpenAI-провайдера.
    """

    alias: str
    display_name: str
    model_env: str
    default_model: str
    api_key_env: str | None = None
    base_url_env: str | None = None


DEFAULT_MODEL_ALIAS = "openai_default"


MODEL_ALIASES: dict[str, ModelAliasConfig] = {
    DEFAULT_MODEL_ALIAS: ModelAliasConfig(
        alias=DEFAULT_MODEL_ALIAS,
        display_name="OpenAI (облачная)",
        model_env="OPENAI_MODEL",
        default_model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
    ),
    "gigachat_default": ModelAliasConfig(
        alias="gigachat_default",
        display_name="GigaChat (Sber)",
        model_env="GIGACHAT_MODEL",
        default_model="gigachat/GigaChat",
        api_key_env="GIGACHAT_API_KEY",
        base_url_env="GIGACHAT_BASE_URL",
    ),
    "local_default": ModelAliasConfig(
        alias="local_default",
        display_name="Локальная OpenAI-compatible",
        model_env="LOCAL_LLM_MODEL",
        default_model="openai/local-model",
        api_key_env="LOCAL_LLM_API_KEY",
        base_url_env="LOCAL_LLM_BASE_URL",
    ),
}


def model_aliases() -> list[str]:
    """Возвращает список технических alias моделей в порядке объявления.

    Что делает:
    - преобразует ключи словаря `MODEL_ALIASES` в список.

    Зачем:
    - используется в UI и тестах для единообразного выбора моделей.

    Входы:
    - отсутствуют.

    Выходы:
    - список alias (например, `openai_default`, `gigachat_default`, `local_default`).

    Ошибки:
    - не генерирует исключения в штатном сценарии.

    Пример:
    - `model_aliases()` -> `["openai_default", "gigachat_default", "local_default"]`.
    """
    return list(MODEL_ALIASES)


def model_options() -> list[dict[str, str]]:
    """Возвращает человеко-понятные опции моделей для UI.

    Что делает:
    - формирует список словарей вида `{"alias": ..., "label": ...}`.

    Зачем:
    - в шаблонах можно показывать дружелюбные названия, скрывая внутренние идентификаторы.

    Входы:
    - отсутствуют.

    Выходы:
    - список опций для `<select>` в web-интерфейсе.

    Ошибки:
    - отсутствуют в штатном режиме.

    Пример:
    - `model_options()[0]["label"]` -> `"OpenAI (облачная)"`.
    """
    return [
        {"alias": alias, "label": config.display_name} for alias, config in MODEL_ALIASES.items()
    ]


def resolve_model_name(alias: str) -> str:
    """Резолвит итоговое имя модели по alias.

    Что делает:
    - читает имя модели из переменной окружения;
    - если переменная не задана, возвращает `default_model`.

    Зачем:
    - позволяет менять модель без изменения исходного кода (через env).

    Входы:
    - `alias`: техническое имя из `MODEL_ALIASES`.

    Выходы:
    - строка с именем модели для LiteLLM.

    Ошибки:
    - `KeyError`, если alias отсутствует в `MODEL_ALIASES`.

    Пример:
    - `resolve_model_name("openai_default")` -> `"gpt-4o-mini"` (или значение `OPENAI_MODEL`).
    """
    config = MODEL_ALIASES[alias]
    return os.getenv(config.model_env, config.default_model)


def default_scenario_path() -> Path:
    """Определяет путь к базовому JSON-сценарию OR.

    Что делает:
    - сначала проверяет `SCENARIO_PATH` в окружении;
    - если переменная не задана, использует путь по умолчанию в репозитории.

    Зачем:
    - даёт гибкость для запуска с альтернативными учебными сценариями.

    Входы:
    - отсутствуют.

    Выходы:
    - абсолютный `Path` к файлу сценария.

    Ошибки:
    - не генерирует исключений при обычном формировании пути;
    - ошибки чтения сценария обрабатываются в `ScenarioBuilder`.

    Пример:
    - при пустом окружении вернёт `data/scenarios/base_scenario.json`.
    """
    env_path = os.getenv("SCENARIO_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "data" / "scenarios" / "base_scenario.json"
