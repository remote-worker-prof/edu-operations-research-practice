"""Pytest fixtures для Selenium E2E поверх live FastAPI/HTMX приложения."""

from __future__ import annotations

import json
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
from extension_api import ExtensionRegistry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webapp.main import create_app

from .helpers import ChatPage, ReactChatPage

_VIDEO_DURATION_TOLERANCE_SECONDS = 1.0
_MIN_BROWSER_WINDOW_SIDE = 200
_CLIENT_LIST_ATOMS = ("_NET_CLIENT_LIST_STACKING", "_NET_CLIENT_LIST")


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


def _required_binary(name: str) -> str:
    """Возвращает путь к системной утилите или завершает тест с понятной ошибкой."""
    binary = shutil.which(name)
    if binary is None:
        pytest.fail(f"E2E video capture requires `{name}` in PATH.")
    return binary


def _run_checked(command: list[str], *, failure_message: str) -> str:
    """Запускает системную команду и возвращает stdout, иначе завершает тест."""
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on local tool availability
        pytest.fail(f"{failure_message}: {exc}")
    except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on local X11 state
        stderr = (exc.stderr or exc.stdout or "").strip()
        pytest.fail(f"{failure_message}: {stderr or exc}")
    return result.stdout


def _descendant_process_ids(root_pid: int) -> set[int]:
    """Возвращает все дочерние PID-ы процесса, включая корневой PID."""
    output = _run_checked(
        ["ps", "-eo", "pid=,ppid="],
        failure_message="Could not inspect Chromium process tree",
    )
    children_by_parent: dict[int, list[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        pid, ppid = (int(part) for part in parts)
        children_by_parent.setdefault(ppid, []).append(pid)

    descendants = {root_pid}
    queue = [root_pid]
    while queue:
        parent = queue.pop()
        for child in children_by_parent.get(parent, []):
            if child in descendants:
                continue
            descendants.add(child)
            queue.append(child)
    return descendants


def _x11_client_window_ids() -> list[int]:
    """Возвращает top-level X11 window ids для текущего DISPLAY."""
    xprop = _required_binary("xprop")
    for atom in _CLIENT_LIST_ATOMS:
        result = subprocess.run(
            [xprop, "-root", atom],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        window_ids = [int(value, 16) for value in re.findall(r"0x[0-9a-fA-F]+", result.stdout)]
        if window_ids:
            return window_ids

    xwininfo = _required_binary("xwininfo")
    output = _run_checked(
        [xwininfo, "-root", "-tree"],
        failure_message="Could not enumerate X11 windows",
    )
    return [
        int(value, 16)
        for value in re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+"', output, flags=re.MULTILINE)
    ]


def _quoted_values(line: str) -> list[str]:
    """Извлекает quoted значения из строки вывода `xprop`."""
    return re.findall(r'"([^"]*)"', line)


def _x11_window_properties(window_id: int) -> tuple[int | None, str, str]:
    """Читает PID, заголовок и WM_CLASS для конкретного X11-окна."""
    xprop = _required_binary("xprop")
    result = subprocess.run(
        [xprop, "-id", hex(window_id), "_NET_WM_PID", "WM_CLASS", "WM_NAME"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, "", ""

    pid: int | None = None
    title = ""
    wm_class = ""
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("_NET_WM_PID"):
            match = re.search(r"=\s*(\d+)", stripped)
            if match:
                pid = int(match.group(1))
        elif stripped.startswith("WM_CLASS"):
            values = _quoted_values(stripped)
            wm_class = " / ".join(values) if values else stripped.split("=", maxsplit=1)[1].strip()
        elif stripped.startswith("WM_NAME"):
            values = _quoted_values(stripped)
            if values:
                title = values[0]
            elif "=" in stripped:
                title = stripped.split("=", maxsplit=1)[1].strip().strip('"')
    return pid, title, wm_class


def _x11_window_geometry(window_id: int) -> tuple[int, int]:
    """Читает Width/Height для конкретного X11-окна."""
    xwininfo = _required_binary("xwininfo")
    output = _run_checked(
        [xwininfo, "-id", hex(window_id)],
        failure_message=f"Could not inspect X11 window geometry for {hex(window_id)}",
    )
    width_match = re.search(r"Width:\s+(\d+)", output)
    height_match = re.search(r"Height:\s+(\d+)", output)
    if width_match is None or height_match is None:
        pytest.fail(f"Could not parse X11 geometry for window {hex(window_id)}.")
    return int(width_match.group(1)), int(height_match.group(1))


@dataclass(frozen=True)
class X11WindowInfo:
    """Метаданные клиентского Chromium-окна в X11."""

    window_id: int
    pid: int
    title: str
    wm_class: str
    width: int
    height: int


@dataclass
class BrowserVideoRecorder:
    """Живой ffmpeg recorder для текущего Selenium-сценария."""

    process: subprocess.Popen[bytes]
    output_path: Path
    window: X11WindowInfo
    started_at: float


def _resolve_chromium_window(chromedriver_pid: int) -> X11WindowInfo:
    """Находит реальное Chromium client window по процессному дереву chromedriver."""
    active_pids = _descendant_process_ids(chromedriver_pid)
    candidates: list[X11WindowInfo] = []

    for window_id in _x11_client_window_ids():
        pid, title, wm_class = _x11_window_properties(window_id)
        if pid is None or pid not in active_pids:
            continue
        normalized = f"{title} {wm_class}".lower()
        if "clipboard" in normalized or "mutter-x11-frames" in normalized:
            continue
        if "chromium" not in normalized and "chrome" not in normalized:
            continue
        width, height = _x11_window_geometry(window_id)
        if width < _MIN_BROWSER_WINDOW_SIDE or height < _MIN_BROWSER_WINDOW_SIDE:
            continue
        candidates.append(
            X11WindowInfo(
                window_id=window_id,
                pid=pid,
                title=title,
                wm_class=wm_class,
                width=width,
                height=height,
            )
        )

    if not candidates:
        pytest.fail(
            "Could not resolve a Chromium X11 window for Selenium video capture. "
            "Make sure DISPLAY is active and Chromium is running in visible mode."
        )

    return max(candidates, key=lambda item: (item.width * item.height, item.window_id))


def _probe_video_metadata(output_path: Path) -> tuple[float, int, int]:
    """Возвращает duration/width/height из готового mp4 через ffprobe."""
    ffprobe = _required_binary("ffprobe")
    output = _run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(output_path),
        ],
        failure_message=f"Could not read ffprobe metadata for {output_path}",
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive parser guard
        pytest.fail(f"Could not decode ffprobe JSON for {output_path}: {exc}")

    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        pytest.fail(f"ffprobe did not return a video stream for {output_path}.")

    duration_raw = payload.get("format", {}).get("duration")
    if duration_raw is None:
        pytest.fail(f"ffprobe did not return format.duration for {output_path}.")

    return float(duration_raw), int(video_stream["width"]), int(video_stream["height"])


class BrowserVideoCaptureController:
    """Ленивый контроллер записи Selenium-видео после открытия страницы."""

    def __init__(self, *, driver, request, e2e_artifacts_dir: Path) -> None:
        self.driver = driver
        self.request = request
        self.e2e_artifacts_dir = e2e_artifacts_dir
        self.recorder: BrowserVideoRecorder | None = None

    def start(self) -> None:
        """Стартует запись, если включён `E2E_RECORD_VIDEO=1`."""
        if self.recorder is not None or not _record_video_enabled():
            return
        if _headless_enabled():
            pytest.fail("E2E_RECORD_VIDEO=1 requires visible Chromium. Set E2E_HEADLESS=0.")

        ffmpeg = _required_binary("ffmpeg")
        _required_binary("ffprobe")
        _required_binary("xprop")
        _required_binary("xwininfo")

        display = os.getenv("DISPLAY")
        if not display:
            pytest.fail("E2E_RECORD_VIDEO=1 requires DISPLAY for X11 window capture.")

        chromedriver_pid = getattr(self.driver, "_e2e_chromedriver_pid", None)
        if chromedriver_pid is None:
            pytest.fail("Could not determine chromedriver PID for Selenium video capture.")

        window = _resolve_chromium_window(chromedriver_pid)
        fps = _int_env("E2E_VIDEO_FPS", 15, minimum=1)
        slug = _node_slug(self.request.node.nodeid)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = _video_output_dir(self.e2e_artifacts_dir) / f"{slug}-{timestamp}.mp4"

        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "x11grab",
            "-framerate",
            str(fps),
            "-window_id",
            str(window.window_id),
            "-i",
            _normalize_display(display),
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

        started_at = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:  # pragma: no cover - depends on local ffmpeg startup
            pytest.fail(f"Could not start ffmpeg for Selenium video capture: {exc}")

        time.sleep(0.4)
        if process.poll() is not None:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
            pytest.fail(
                "ffmpeg exited immediately when starting Selenium video capture. "
                f"Command: {' '.join(command)}. stderr: {stderr or '<empty>'}"
            )

        self.request.node.user_properties.append(("video_path", str(output_path)))
        self.request.node.user_properties.append(("x11_window_id", str(window.window_id)))
        self.recorder = BrowserVideoRecorder(
            process=process,
            output_path=output_path,
            window=window,
            started_at=started_at,
        )

    def stop(self) -> None:
        """Останавливает запись и проверяет размер/длительность итогового mp4."""
        if self.recorder is None:
            return

        recorder = self.recorder
        runtime_seconds = time.monotonic() - recorder.started_at
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
                f"ffmpeg exited with code {process.returncode} during Selenium video capture. "
                f"stderr: {stderr or '<empty>'}"
            )

        if not recorder.output_path.exists() or recorder.output_path.stat().st_size == 0:
            pytest.fail(
                f"Selenium video capture finished without a non-empty mp4: {recorder.output_path}"
            )

        duration_seconds, width, height = _probe_video_metadata(recorder.output_path)
        if (width, height) != (recorder.window.width, recorder.window.height):
            pytest.fail(
                "Recorded video dimensions do not match the resolved Chromium X11 window. "
                f"Expected {recorder.window.width}x{recorder.window.height}, got {width}x{height}."
            )
        if abs(duration_seconds - runtime_seconds) > _VIDEO_DURATION_TOLERANCE_SECONDS:
            pytest.fail(
                "Recorded video duration drifted too far from Selenium runtime. "
                f"Measured runtime={runtime_seconds:.2f}s, video={duration_seconds:.2f}s."
            )

        self.request.node.user_properties.append(
            ("video_duration_seconds", f"{duration_seconds:.2f}")
        )
        self.recorder = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Сохраняет результаты фаз теста на node для post-test cleanup."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(scope="session")
def e2e_artifacts_dir() -> Path:
    """Каталог для screenshot/page-source и video артефактов Selenium."""
    path = Path.cwd() / ".pytest_artifacts" / "e2e"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def extension_registry(request) -> ExtensionRegistry | None:
    """Позволяет отдельным E2E-тестам инжектировать custom registry через indirect param."""
    return getattr(request, "param", None)


@pytest.fixture()
def web_app(scenario_path: Path, extension_registry: ExtensionRegistry | None):
    """Поднимает изолированный `FastAPI` app c отдельным `AgentService`."""
    service = AgentService(scenario_path=scenario_path, extension_registry=extension_registry)
    return create_app(service=service, extension_registry=extension_registry)


@pytest.fixture(scope="session")
def chat_web_static_export_dir() -> Path:
    """Собирает static export нового React shell для browser cutover-сценариев."""
    export_dir = Path.cwd() / "apps" / "chat_web" / "out"
    result = subprocess.run(
        ["make", "chat-web-build"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        check=False,
    )
    if result.returncode != 0:  # pragma: no cover - depends on local node/npm toolchain
        stderr = (result.stderr or result.stdout or "").strip()
        pytest.fail(f"Could not build apps/chat_web static export: {stderr or result.returncode}")
    if not export_dir.exists():
        pytest.fail(f"Expected React chat static export at {export_dir}, but it was not created.")
    return export_dir


@pytest.fixture()
def react_web_app(
    scenario_path: Path,
    extension_registry: ExtensionRegistry | None,
    chat_web_static_export_dir: Path,
):
    """Поднимает FastAPI app, который раздаёт собранный React chat shell на `/app/*`."""
    service = AgentService(scenario_path=scenario_path, extension_registry=extension_registry)
    return create_app(
        service=service,
        extension_registry=extension_registry,
        chat_web_export_dir=chat_web_static_export_dir,
    )


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
            response = httpx.get(f"{base_url}/healthz", timeout=1.0, trust_env=False)
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
    thread.join(timeout=30)
    if thread.is_alive():  # pragma: no cover - defensive cleanup
        raise RuntimeError("Live server thread did not stop in time.")


@pytest.fixture()
def react_live_server(react_web_app) -> str:
    """Запускает живой uvicorn server c собранным React shell на `/app/*`."""
    port = _find_free_port()
    config = uvicorn.Config(react_web_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.0, trust_env=False)
            if response.status_code == 200:
                break
        except Exception as exc:  # pragma: no cover - depends on local startup timing
            last_error = exc
            time.sleep(0.1)
    else:  # pragma: no cover - would indicate broken live-server startup
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"React live server did not start successfully: {last_error}")

    yield base_url

    server.should_exit = True
    thread.join(timeout=30)
    if thread.is_alive():  # pragma: no cover - defensive cleanup
        raise RuntimeError("React live server thread did not stop in time.")


@pytest.fixture()
def browser(request, e2e_artifacts_dir: Path):
    """Создаёт Selenium `Chrome` driver для deterministic и visible E2E-сценариев."""
    del e2e_artifacts_dir
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

    driver._e2e_chromedriver_pid = service.process.pid if service.process else None

    yield driver

    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        slug = _node_slug(request.node.nodeid)
        screenshot_path = Path.cwd() / ".pytest_artifacts" / "e2e" / f"{slug}.png"
        html_path = Path.cwd() / ".pytest_artifacts" / "e2e" / f"{slug}.html"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screenshot_path))
        html_path.write_text(driver.page_source, encoding="utf-8")

    driver.quit()


@pytest.fixture()
def video_capture(browser, request, e2e_artifacts_dir: Path) -> BrowserVideoCaptureController:
    """Лениво включает window-id video capture только для нужных Selenium-прогонов."""
    controller = BrowserVideoCaptureController(
        driver=browser,
        request=request,
        e2e_artifacts_dir=e2e_artifacts_dir,
    )
    yield controller
    controller.stop()


@pytest.fixture()
def chat_page(browser, live_server: str, video_capture: BrowserVideoCaptureController) -> ChatPage:
    """Готовит page-object для тестов чата и стартует запись после первого render."""
    page = ChatPage(browser, live_server).open(pause_after_open=False)
    video_capture.start()
    page.pause_after_open()
    return page


@pytest.fixture()
def react_chat_page(
    browser,
    react_live_server: str,
    video_capture: BrowserVideoCaptureController,
) -> ReactChatPage:
    """Готовит page-object для нового React chat shell и стартует запись после render."""
    page = ReactChatPage(browser, react_live_server).open()
    video_capture.start()
    return page
