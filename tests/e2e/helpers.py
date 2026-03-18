"""Вспомогательные Selenium-обёртки для HTMX-чата."""

from __future__ import annotations

import os
import time
from typing import Literal

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

_DEMO_CHUNK_SIZE = 12
_DEMO_CHUNK_DELAY_SECONDS = 0.32


def _demo_mode_enabled() -> bool:
    """Определяет, включён ли screencast/demo режим для Selenium."""
    value = os.getenv("E2E_DEMO_MODE", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    """Читает float-переменную окружения с безопасным fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return default


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    """Читает int-переменную окружения с безопасным fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


class ChatPage:
    """Тонкая page-object обёртка над web-чатом проекта."""

    def __init__(self, driver, base_url: str, timeout: int = 20) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.wait = WebDriverWait(driver, timeout)
        self.demo_mode = _demo_mode_enabled()
        self.demo_initial_delay = _float_env("E2E_DEMO_INITIAL_DELAY_SECONDS", 2.0)
        self.demo_step_delay = _float_env("E2E_DEMO_STEP_DELAY_SECONDS", 2.5)
        self.demo_type_delay = _float_env("E2E_DEMO_TYPE_DELAY_SECONDS", 0.09)
        self.demo_final_delay = _float_env("E2E_DEMO_FINAL_DELAY_SECONDS", 8.0)
        self.demo_chunk_size = _int_env("E2E_DEMO_CHUNK_SIZE", _DEMO_CHUNK_SIZE, minimum=1)
        self.demo_chunk_delay = _float_env(
            "E2E_DEMO_CHUNK_DELAY_SECONDS", _DEMO_CHUNK_DELAY_SECONDS
        )

    def _pause(self, seconds: float) -> None:
        """Делает реальную паузу только в demo-режиме."""
        if self.demo_mode and seconds > 0:
            time.sleep(seconds)

    def _step_pause_seconds(self, override: float | None) -> float:
        """Возвращает задержку после смыслового шага в demo-режиме."""
        return self.demo_step_delay if override is None else max(override, 0.0)

    def open(self, *, pause_after_open: bool = True) -> "ChatPage":
        """Открывает стартовую страницу и ждёт первичный workspace."""
        self.driver.get(f"{self.base_url}/")
        self.wait_for_workspace()
        if pause_after_open:
            self.pause_after_open()
        return self

    def pause_after_open(self) -> "ChatPage":
        """Держит первый отрендеренный кадр перед началом сценария."""
        self._pause(self.demo_initial_delay)
        return self

    def wait_for_workspace(self):
        """Дожидается появления корневого HTMX-workspace."""
        return self.wait.until(EC.presence_of_element_located((By.ID, "workspace")))

    def find_by_testid(self, testid: str):
        """Возвращает первый элемент по `data-testid`."""
        return self.driver.find_element(By.CSS_SELECTOR, f'[data-testid="{testid}"]')

    def find_all_by_testid(self, testid: str) -> list:
        """Возвращает все элементы по `data-testid`."""
        return self.driver.find_elements(By.CSS_SELECTOR, f'[data-testid="{testid}"]')

    def has_testid(self, testid: str) -> bool:
        """Проверяет наличие хотя бы одного элемента по `data-testid`."""
        return bool(self.find_all_by_testid(testid))

    def text_of(self, testid: str) -> str:
        """Возвращает `.text` первого элемента по `data-testid`."""
        return self.find_by_testid(testid).text

    def session_id(self) -> str:
        """Читает текущий `session_id` из скрытого input."""
        return self.driver.find_element(By.ID, "session-id-input").get_attribute("value")

    def select_model(
        self,
        alias: str,
        *,
        after_pause_seconds: float | None = None,
    ) -> "ChatPage":
        """Выбирает alias модели в `<select>`."""
        select = Select(self.driver.find_element(By.ID, "model-alias-select"))
        select.select_by_value(alias)
        self._pause(self._step_pause_seconds(after_pause_seconds))
        return self

    def select_extension(
        self,
        alias: str,
        *,
        after_pause_seconds: float | None = None,
    ) -> "ChatPage":
        """Выбирает alias extension в `<select>`."""
        select = Select(self.driver.find_element(By.ID, "extension-alias-select"))
        select.select_by_value(alias)
        self._pause(self._step_pause_seconds(after_pause_seconds))
        return self

    def pause(self, seconds: float | None = None) -> "ChatPage":
        """Делает публичную demo-паузу между смысловыми шагами сценария."""
        self._pause(self.demo_step_delay if seconds is None else seconds)
        return self

    def send_message(
        self,
        message: str,
        *,
        typing_mode: Literal["auto", "type", "paste", "chunked"] = "auto",
        after_pause_seconds: float | None = None,
    ) -> "ChatPage":
        """Отправляет сообщение и ждёт HTMX replacement для `#workspace`."""
        previous_workspace = self.wait_for_workspace()
        message_input = self.wait.until(EC.element_to_be_clickable((By.ID, "chat-message-input")))
        message_input.clear()
        effective_mode = typing_mode
        if effective_mode == "auto":
            effective_mode = "type" if self.demo_mode and len(message) <= 80 else "chunked"
        if not self.demo_mode and effective_mode == "chunked":
            effective_mode = "paste"
        if self.demo_mode and effective_mode == "type":
            for character in message:
                message_input.send_keys(character)
                self._pause(self.demo_type_delay)
            self._pause(self.demo_step_delay)
        elif self.demo_mode and effective_mode == "chunked":
            for index in range(0, len(message), self.demo_chunk_size):
                message_input.send_keys(message[index : index + self.demo_chunk_size])
                if index + self.demo_chunk_size < len(message):
                    self._pause(self.demo_chunk_delay)
            self._pause(self.demo_step_delay)
        else:
            message_input.send_keys(message)
            self._pause(self.demo_step_delay)
        self.driver.find_element(By.ID, "chat-submit-button").click()
        self.wait.until(EC.staleness_of(previous_workspace))
        self.wait_for_workspace()
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-message"]'))
        )
        self._pause(self._step_pause_seconds(after_pause_seconds))
        return self

    def pause_for_screencast_finish(self) -> "ChatPage":
        """Держит финальный кадр открытым в demo-режиме."""
        self._pause(self.demo_final_delay)
        return self

    def chat_messages(self, *, role: str | None = None) -> list[str]:
        """Возвращает тексты сообщений чата, при необходимости фильтруя по роли."""
        selector = '[data-testid="chat-message"]'
        if role is not None:
            selector += f'[data-role="{role}"]'
        return [element.text for element in self.driver.find_elements(By.CSS_SELECTOR, selector)]

    def last_chat_message(self, *, role: str | None = None) -> str:
        """Возвращает последнюю реплику чата."""
        messages = self.chat_messages(role=role)
        if not messages:
            raise AssertionError("В чате нет сообщений для чтения.")
        return messages[-1]
