"""Вспомогательные Selenium-обёртки для legacy HTMX и нового React chat shell."""

from __future__ import annotations

import os
import time
from typing import Literal
from urllib.parse import urlparse

import httpx
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
    """Тонкая page-object обёртка над legacy HTMX-чатом проекта."""

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
        """Открывает legacy path и ждёт первичный workspace."""
        self.driver.get(f"{self.base_url}/legacy")
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


class ReactChatPage:
    """Page-object для нового React/CopilotKit чата поверх backend-owned threads."""

    def __init__(self, driver, base_url: str, timeout: int = 20) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.wait = WebDriverWait(driver, timeout)

    def open(self) -> "ReactChatPage":
        """Открывает product root, который должен redirect-ить в React shell."""
        self.driver.get(f"{self.base_url}/")
        self.wait_for_shell()
        return self

    def wait_for_shell(self):
        """Дожидается появления React shell и его первого рабочего guided state."""
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-web-root"]'))
        )
        self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="active-extension-title"]')
            )
        )
        return self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="new-thread-extension-select"]')
            )
        )

    def current_path(self) -> str:
        """Возвращает текущий path без схемы/хоста."""
        return urlparse(self.driver.current_url).path

    def find_by_testid(self, testid: str):
        """Возвращает первый элемент по `data-testid`."""
        return self.driver.find_element(By.CSS_SELECTOR, f'[data-testid="{testid}"]')

    def find_all_by_testid(self, testid: str) -> list:
        """Возвращает все элементы по `data-testid`."""
        return self.driver.find_elements(By.CSS_SELECTOR, f'[data-testid="{testid}"]')

    def text_of(self, testid: str) -> str:
        """Возвращает `.text` первого элемента по `data-testid`."""
        return self.find_by_testid(testid).text

    def _api_get(self, path: str) -> dict | list:
        """Читает JSON из backend thread API."""
        response = httpx.get(f"{self.base_url}{path}", timeout=5.0, trust_env=False)
        response.raise_for_status()
        return response.json()

    def current_thread_id(self) -> str:
        """Возвращает ID активного треда из UI или backend API."""
        active_cards = self.driver.find_elements(By.CSS_SELECTOR, ".thread-card--active")
        if active_cards:
            testid = active_cards[0].get_attribute("data-testid") or ""
            prefix = "thread-card-"
            if testid.startswith(prefix):
                return testid.removeprefix(prefix)
        threads = self._api_get("/api/chat/threads")
        if not threads:
            raise AssertionError("Backend не вернул ни одного треда для React shell.")
        return threads[0]["thread_id"]

    def thread_envelope(self) -> dict:
        """Возвращает текущий thread envelope через backend API."""
        thread_id = self.current_thread_id()
        return self._api_get(f"/api/chat/threads/{thread_id}")

    def interaction(self) -> dict:
        """Возвращает typed interaction snapshot текущего треда."""
        return self.thread_envelope()["interaction"]

    def session(self) -> dict:
        """Возвращает session snapshot текущего треда."""
        return self.thread_envelope()["session"]

    def assistant_messages(self) -> list[str]:
        """Возвращает assistant-реплики из backend-owned thread state."""
        return [
            message["content"]
            for message in self.session()["messages"]
            if message["role"] == "assistant"
        ]

    def last_assistant_message(self) -> str:
        """Возвращает последнюю assistant-реплику."""
        messages = self.assistant_messages()
        if not messages:
            raise AssertionError("В React shell ещё нет assistant-сообщений.")
        return messages[-1]

    def wait_for_condition(
        self,
        predicate,
        *,
        timeout: float = 20.0,
        poll_interval: float = 0.1,
        failure_message: str = "Ожидаемое состояние React shell не наступило вовремя.",
    ) -> None:
        """Poll-based ожидание для backend-owned thread state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(poll_interval)
        raise AssertionError(failure_message)

    def _message_count(self, thread_id: str | None = None) -> int:
        """Возвращает число сообщений в конкретном thread state."""
        current_thread = thread_id or self.current_thread_id()
        envelope = self._api_get(f"/api/chat/threads/{current_thread}")
        return len(envelope["session"]["messages"])

    def _replace_value(self, testid: str, value: str | int | float) -> None:
        """Надёжно заменяет значение controlled input/textarea."""
        field = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'[data-testid="{testid}"]'))
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            field,
        )
        field.click()
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(Keys.DELETE)
        field.send_keys(str(value))

    def _safe_click(self, testid: str) -> None:
        """Надёжно кликает по элементу даже при частичном перекрытии layout-слоем."""
        element = self.find_by_testid(testid)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            element,
        )
        try:
            element.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].click();", element)

    def _ensure_details_open(self, testid: str) -> None:
        """Открывает `<details>`-панель, если она свернута."""
        details = self.find_by_testid(testid)
        if details.get_attribute("open"):
            return
        summary = details.find_element(By.TAG_NAME, "summary")
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            summary,
        )
        try:
            summary.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].setAttribute('open', 'open');", details)

    def select_new_thread_extension(self, alias: str) -> None:
        """Выбирает шаблон extension для нового треда."""
        select = self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="new-thread-extension-select"]')
            )
        )
        Select(select).select_by_value(alias)

    def create_new_thread(self, alias: str) -> None:
        """Создаёт новый тред для указанного extension."""
        previous_thread_id = self.current_thread_id()
        self.select_new_thread_extension(alias)
        self._safe_click("new-thread-button")
        self.wait_for_condition(
            lambda: self.current_thread_id() != previous_thread_id,
            failure_message="Новый тред не появился после нажатия кнопки.",
        )

    def click_quick_action(self, testid: str) -> None:
        """Нажимает quick-action и ждёт ответа backend на текущий тред."""
        thread_id = self.current_thread_id()
        before = self._message_count(thread_id)
        self._safe_click(testid)
        self.wait_for_condition(
            lambda: self._message_count(thread_id) > before,
            failure_message=f"Команда {testid} не изменила thread state.",
        )

    def set_interaction_mode(self, mode: str) -> None:
        """Переключает guided/power mode через quick-action кнопку."""
        button = "power-mode-button" if mode == "power" else "guided-mode-button"
        self.click_quick_action(button)
        self.wait_for_condition(
            lambda: self.text_of("interaction-mode-value") == mode,
            failure_message=f"React shell не переключился в режим {mode}.",
        )

    def send_power_message(self, message: str) -> None:
        """Отправляет произвольное сообщение через power-user console."""
        thread_id = self.current_thread_id()
        before = self._message_count(thread_id)
        self._ensure_details_open("power-mode-card")
        self._replace_value("power-console-input", message)
        self._safe_click("power-console-send")
        self.wait_for_condition(
            lambda: self._message_count(thread_id) > before,
            failure_message="Power console не отправил сообщение в backend thread.",
        )

    def confirm_pending_proposals(self) -> None:
        """Подтверждает ожидающие NL-предложения через guided UI."""
        thread_id = self.current_thread_id()
        before = self._message_count(thread_id)
        self._safe_click("confirm-proposals-button")
        self.wait_for_condition(
            lambda: self._message_count(thread_id) > before,
            failure_message="Подтверждение предложений не изменило thread state.",
        )

    def _current_step(self) -> dict:
        """Возвращает semantics текущего шага редактора."""
        step = self.interaction()["current_step"]
        if step is None:
            raise AssertionError("У текущего extension нет активного guided шага.")
        return step

    def fill_current_table(self, rows: list[list[str | int | float]]) -> None:
        """Заполняет текущий табличный шаг согласно порядку key + columns."""
        step = self._current_step()
        shape = step["shape"]
        if shape is None or shape["kind"] != "table":
            raise AssertionError("Текущий шаг не является table-editor.")

        key_field = shape["key"]["field_path"]
        columns = shape["columns"]
        step_id = step["step_id"]
        existing_rows = len(
            self.driver.find_elements(
                By.CSS_SELECTOR,
                f'[data-testid^="table-{step_id}-"][data-testid$="-{key_field}"]',
            )
        )
        while existing_rows < len(rows):
            self._safe_click(f"add-row-{step_id}")
            existing_rows += 1

        for row_index, values in enumerate(rows):
            if len(values) != 1 + len(columns):
                raise AssertionError(
                    "Каждая строка table-editor должна содержать key и все columns."
                )
            self._replace_value(f"table-{step_id}-{row_index}-{key_field}", values[0])
            for column_index, column in enumerate(columns, start=1):
                self._replace_value(
                    f"table-{step_id}-{row_index}-{column['field_path']}",
                    values[column_index],
                )

    def fill_current_scalars(self, values: list[str | int | float]) -> None:
        """Заполняет scalar inputs по их semantic-порядку."""
        step = self._current_step()
        if len(values) != len(step["scalars"]):
            raise AssertionError("Число scalar-значений не совпадает с семантикой шага.")
        for index, field in enumerate(step["scalars"]):
            self._replace_value(f"scalar-{step['step_id']}-{field['field_path']}", values[index])

    def fill_current_vector(self, values: list[str | int | float], field_index: int = 0) -> None:
        """Заполняет один vector input по порядку элементов множества."""
        step = self._current_step()
        field = step["vectors"][field_index]
        for index, value in enumerate(values):
            self._replace_value(
                f"vector-{step['step_id']}-{field['field_path']}-{index}",
                value,
            )

    def fill_current_matrix(
        self,
        matrix: list[list[str | int | float]],
        field_index: int = 0,
    ) -> None:
        """Заполняет текущий matrix-editor в row-major порядке."""
        step = self._current_step()
        shape = step["shape"]
        if shape is None or shape["kind"] != "matrix":
            raise AssertionError("Текущий шаг не является matrix-editor.")
        field = shape["fields"][field_index]
        for row_index, row in enumerate(matrix):
            for col_index, value in enumerate(row):
                self._replace_value(
                    f"matrix-{step['step_id']}-{field['field_path']}-{row_index}-{col_index}",
                    value,
                )

    def submit_current_step(self) -> None:
        """Отправляет текущий guided step и ждёт обновления backend thread state."""
        thread_id = self.current_thread_id()
        before = self._message_count(thread_id)
        step_id = self._current_step()["step_id"]
        self._safe_click(f"submit-step-{step_id}")
        self.wait_for_condition(
            lambda: self._message_count(thread_id) > before,
            failure_message=f"Шаг {step_id} не отправился в backend thread.",
        )

    def result_titles(self) -> list[str]:
        """Возвращает заголовки result sections из React UI."""
        return [element.text for element in self.find_all_by_testid("result-section-title")]

    def result_rows(self) -> list[str]:
        """Возвращает строки result tables из React UI."""
        return [element.text for element in self.find_all_by_testid("result-table-row")]
