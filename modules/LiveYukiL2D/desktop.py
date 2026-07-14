from __future__ import annotations

import ctypes
import ctypes.wintypes
import socket
import threading
import time
from typing import Any

from server import HOST, PORT, load_config, main as run_server

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def is_server_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, PORT)) == 0


def set_mouse_passthrough(hwnd: int, enabled: bool) -> None:
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


class DesktopApi:
    def __init__(self, mouse_passthrough: bool) -> None:
        self._mouse_passthrough = mouse_passthrough
        self._window: Any | None = None

    def bind_window(self, window: Any) -> None:
        self._window = window

    def setIgnoreMouseEvent(self, ignored: bool) -> None:
        if not self._mouse_passthrough or self._window is None:
            return
        hwnd = getattr(self._window, "hwnd", None)
        if hwnd:
            set_mouse_passthrough(int(hwnd), ignored)

    def set_ignore_mouse_event(self, ignored: bool) -> None:
        self.setIgnoreMouseEvent(ignored)

    def getCursorPosition(self) -> dict[str, int]:
        point = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return {"x": point.x, "y": point.y}

    def getWindowPosition(self) -> dict[str, int]:
        hwnd = getattr(self._window, "hwnd", None) if self._window is not None else None
        if hwnd:
            rect = RECT()
            if ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
                return {"x": rect.left, "y": rect.top}
        return {"x": 0, "y": 0}

    def get_window_position(self) -> dict[str, int]:
        return self.getWindowPosition()

    def get_cursor_position(self) -> dict[str, int]:
        return self.getCursorPosition()


def start_server() -> None:
    run_server(handle_signals=False)


def ensure_server() -> None:
    if is_server_running():
        print(f"LiveYukiL2D server already running: http://{HOST}:{PORT}")
        return

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    for _ in range(30):
        if is_server_running():
            return
        time.sleep(0.1)

    raise RuntimeError(f"服务启动超时：http://{HOST}:{PORT}")


def main() -> None:
    try:
        import webview
    except ImportError as exc:
        raise SystemExit("缺少 pywebview。先运行：uv add pywebview 或 pip install pywebview") from exc

    config = load_config()
    pet_config = config.get("desktopPet", {})
    ensure_server()

    api = DesktopApi(bool(pet_config.get("mousePassthrough", True)))
    window = webview.create_window(
        "LiveYukiL2D",
        f"http://{HOST}:{PORT}",
        width=int(pet_config.get("width", 420)),
        height=int(pet_config.get("height", 640)),
        x=pet_config.get("x"),
        y=pet_config.get("y"),
        frameless=bool(pet_config.get("frameless", True)),
        transparent=bool(pet_config.get("transparent", True)),
        on_top=bool(pet_config.get("alwaysOnTop", True)),
        resizable=bool(pet_config.get("resizable", True)),
        js_api=api,
    )
    api.bind_window(window)

    def on_loaded() -> None:
        if pet_config.get("mousePassthrough", True):
            api.setIgnoreMouseEvent(True)

    window.events.loaded += on_loaded
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
