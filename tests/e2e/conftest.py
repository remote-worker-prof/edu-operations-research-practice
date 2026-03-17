"""Pytest-fixtures для Selenium E2E поверх live FastAPI/HTMX приложения."""

from __future__ import annotations

import os
import re
import shutil
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from agent_core.service import AgentService
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webapp.main import create_app

from .helpers import ChatPage


def _find_free_port() -> int:
    """Находит свободный localhost-порт для live-server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _headless_enabled() -> bool:
    """Определяет, включён ли headless-режим для браузера."""
    value = os.getenv("E2E_HEADLESS", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _detect_chromium_binary() -> str | None:
    """Ищет подходящий Chromium/Chrome binary для Selenium."""
    env_binary = os.getenv("E2E_CHROMIUM_BINARY")
    if env_binary:
        candidate = Path(env_binary).expanduser()
        if candidate.exists():
            return str(candidate)

    for candidate in ("chromium", "chromium-browser", "google-chrome", "/snap/bin/chromium"):
        resolved = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if resolved:
            return resolved
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Сохраняет результаты фаз теста на node для post-test cleanup."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(scope="session")
def e2e_artifacts_dir() -> Path:
    """Каталог для screenshot/page-source артефактов Selenium-падений."""
    path = Path.cwd() / ".pytest_artifacts" / "e2e"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def web_app(scenario_path: Path):
    """Поднимает изолированный `FastAPI` app c отдельным `AgentService`."""
    service = AgentService(scenario_path=scenario_path)
    return create_app(service=service)


@pytest.fixture()
def live_server(web_app) -> str:
    """Запускает живой `uvicorn` server на свободном порту."""
    port = _find_free_port()
    config = uvicorn.Config(web_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if response.status_code == 200:
                break
        except Exception as exc:  # pragma: no cover - depends on local startup timing
            last_error = exc
            time.sleep(0.1)
    else:  # pragma: no cover - would indicate broken live-server startup
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Live server did not start successfully: {last_error}")

    yield base_url

    server.should_exit = True
    thread.join(timeout=10)
    if thread.is_alive():  # pragma: no cover - defensive cleanup
        raise RuntimeError("Live server thread did not stop in time.")


@pytest.fixture()
def browser(request, e2e_artifacts_dir: Path):
    """Создаёт Selenium `Chrome` driver для headless Chromium."""
    binary = _detect_chromium_binary()
    if binary is None:
        pytest.skip("Chromium binary not found. Set E2E_CHROMIUM_BINARY to run browser E2E tests.")

    options = ChromeOptions()
    options.binary_location = binary
    if _headless_enabled():
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-pipe")
    options.add_argument("--window-size=1440,1200")

    driver_path = os.getenv("E2E_CHROMEDRIVER_PATH")
    service = ChromeService(executable_path=driver_path) if driver_path else ChromeService()

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as exc:  # pragma: no cover - environment-specific failure
        pytest.fail(f"Could not start Selenium Chrome driver: {exc}")

    yield driver

    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
        screenshot_path = e2e_artifacts_dir / f"{slug}.png"
        html_path = e2e_artifacts_dir / f"{slug}.html"
        driver.save_screenshot(str(screenshot_path))
        html_path.write_text(driver.page_source, encoding="utf-8")

    driver.quit()


@pytest.fixture()
def chat_page(browser, live_server: str) -> ChatPage:
    """Готовит page-object для тестов чата."""
    return ChatPage(browser, live_server).open()
