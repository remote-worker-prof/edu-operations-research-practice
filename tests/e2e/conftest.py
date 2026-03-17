"""Pytest-fixtures для Selenium E2E поверх live FastAPI/HTMX приложения."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
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


def _record_video_enabled() -> bool:
    """Определяет, включена ли запись видимого окна браузера."""
    value = os.getenv("E2E_RECORD_VIDEO", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    """Читает integer env-var с ограничением по минимальному значению."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


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


def _video_output_dir(e2e_artifacts_dir: Path) -> Path:
    """Возвращает каталог для mp4-артефактов Selenium-записи."""
    raw = os.getenv("E2E_VIDEO_OUTPUT_DIR")
    path = Path(raw).expanduser() if raw else e2e_artifacts_dir / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _node_slug(nodeid: str) -> str:
    """Преобразует pytest nodeid в безопасный slug для артефактов."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid)


def _normalize_display(display: str) -> str:
    """Нормализует DISPLAY для `ffmpeg -f x11grab`."""
    return display if "." in display else f"{display}.0"


@dataclass
class BrowserVideoRecorder:
    """Трекер живого ffmpeg-процесса для записи окна Chromium."""

    process: subprocess.Popen[bytes]
    output_path: Path


def _start_video_recorder(
    *,
    driver,
    request,
    e2e_artifacts_dir: Path,
) -> BrowserVideoRecorder | None:
    """Запускает mp4-запись браузерного окна через `ffmpeg + x11grab`."""
    if not _record_video_enabled():
        return None
    if _headless_enabled():
        pytest.fail("E2E_RECORD_VIDEO=1 требует visible browser. Установите E2E_HEADLESS=0.")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.fail("E2E_RECORD_VIDEO=1 требует установленный ffmpeg в PATH.")

    display = os.getenv("DISPLAY")
    if not display:
        pytest.fail("E2E_RECORD_VIDEO=1 требует DISPLAY для X11-записи окна Chromium.")

    desired_x = _int_env("E2E_WINDOW_X", 80)
    desired_y = _int_env("E2E_WINDOW_Y", 60)
    desired_width = _int_env("E2E_WINDOW_WIDTH", 1440, minimum=320)
    desired_height = _int_env("E2E_WINDOW_HEIGHT", 1200, minimum=240)
    fps = _int_env("E2E_VIDEO_FPS", 15, minimum=1)

    driver.set_window_rect(
        x=desired_x,
        y=desired_y,
        width=desired_width,
        height=desired_height,
    )
    time.sleep(0.4)
    rect = driver.get_window_rect()

    x = int(rect.get("x", desired_x))
    y = int(rect.get("y", desired_y))
    width = int(rect.get("width", desired_width))
    height = int(rect.get("height", desired_height))
    if width <= 0 or height <= 0:
        pytest.fail(f"Получен невалидный rect окна Chromium для записи: {rect!r}")

    slug = _node_slug(request.node.nodeid)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_path = _video_output_dir(e2e_artifacts_dir) / f"{slug}-{timestamp}.mp4"
    capture_target = f"{_normalize_display(display)}+{x},{y}"

    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "x11grab",
        "-framerate",
        str(fps),
        "-video_size",
        f"{width}x{height}",
        "-i",
        capture_target,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:  # pragma: no cover - environment-specific startup failure
        pytest.fail(f"Не удалось запустить ffmpeg для записи Selenium-окна: {exc}")

    time.sleep(0.8)
    if process.poll() is not None:
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        pytest.fail(
            "ffmpeg завершился сразу после старта записи Selenium-окна. "
            f"Команда: {' '.join(command)}. stderr: {stderr or '<empty>'}"
        )

    request.node.user_properties.append(("video_path", str(output_path)))
    return BrowserVideoRecorder(process=process, output_path=output_path)


def _stop_video_recorder(recorder: BrowserVideoRecorder | None) -> None:
    """Останавливает ffmpeg и проверяет, что mp4 успешно сохранён."""
    if recorder is None:
        return

    process = recorder.process
    if process.poll() is None and process.stdin is not None:
        try:
            process.stdin.write(b"q\n")
            process.stdin.flush()
        except OSError:
            pass

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            process.kill()
            process.wait(timeout=5)

    stderr = ""
    if process.stderr is not None:
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()

    if process.returncode not in {0, None}:
        pytest.fail(
            f"ffmpeg завершился с кодом {process.returncode} при записи Selenium-окна. "
            f"stderr: {stderr or '<empty>'}"
        )

    if not recorder.output_path.exists() or recorder.output_path.stat().st_size == 0:
        pytest.fail(
            f"Запись Selenium-окна завершилась без непустого mp4-файла: {recorder.output_path}"
        )


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
    """Создаёт Selenium `Chrome` driver и при необходимости пишет mp4 окна."""
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

    recorder = _start_video_recorder(
        driver=driver,
        request=request,
        e2e_artifacts_dir=e2e_artifacts_dir,
    )

    yield driver

    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        slug = _node_slug(request.node.nodeid)
        screenshot_path = e2e_artifacts_dir / f"{slug}.png"
        html_path = e2e_artifacts_dir / f"{slug}.html"
        driver.save_screenshot(str(screenshot_path))
        html_path.write_text(driver.page_source, encoding="utf-8")

    _stop_video_recorder(recorder)
    driver.quit()


@pytest.fixture()
def chat_page(browser, live_server: str) -> ChatPage:
    """Готовит page-object для тестов чата."""
    return ChatPage(browser, live_server).open()
