"""Вспомогательные Selenium-обёртки для HTMX-чата."""

from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


class ChatPage:
    """Тонкая page-object обёртка над web-чатом проекта."""

    def __init__(self, driver, base_url: str, timeout: int = 10) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.wait = WebDriverWait(driver, timeout)

    def open(self) -> "ChatPage":
        """Открывает стартовую страницу и ждёт первичный workspace."""
        self.driver.get(f"{self.base_url}/")
        self.wait_for_workspace()
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

    def select_model(self, alias: str) -> "ChatPage":
        """Выбирает alias модели в `<select>`."""
        select = Select(self.driver.find_element(By.ID, "model-alias-select"))
        select.select_by_value(alias)
        return self

    def send_message(self, message: str) -> "ChatPage":
        """Отправляет сообщение и ждёт HTMX replacement для `#workspace`."""
        previous_workspace = self.wait_for_workspace()
        message_input = self.wait.until(EC.element_to_be_clickable((By.ID, "chat-message-input")))
        message_input.clear()
        message_input.send_keys(message)
        self.driver.find_element(By.ID, "chat-submit-button").click()
        self.wait.until(EC.staleness_of(previous_workspace))
        self.wait_for_workspace()
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-message"]'))
        )
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
