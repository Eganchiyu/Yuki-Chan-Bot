from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import shutil
import subprocess
import sys
from typing import Any

"""跨平台获取全局光标屏幕坐标。

桌宠前端在 Electron 环境下优先走主进程的 cursor 轮询 IPC；这个模块服务于
浏览器 / pywebview 回退路径（`GET /api/cursor`）。

各平台实现：
- Windows：`user32.GetCursorPos`
- X11（含 XWayland）：libX11 的 `XQueryPointer`
- Wayland：合成器没有标准查询接口，按可用命令探测（hyprctl / swaymsg 等）

任何一条路径不可用时返回 `None`，调用方负责降级，绝不能因为拿不到光标就抛异常。
"""

_CACHE: dict[str, Any] = {}


def _windows_cursor() -> tuple[int, int] | None:
    """Windows：GetCursorPos 写入 POINT 结构。"""
    try:
        import ctypes.wintypes  # noqa: PLC0415 - 仅 Windows 可用，必须延迟导入
    except Exception:
        return None

    try:
        point = ctypes.wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
    except Exception:
        return None
    return int(point.x), int(point.y)


def _load_x11() -> Any | None:
    """加载并绑定 libX11，只做一次。"""
    if "x11" in _CACHE:
        return _CACHE["x11"]

    lib_name = ctypes.util.find_library("X11") or "libX11.so.6"
    x11: Any | None = None
    try:
        x11 = ctypes.CDLL(lib_name)
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XQueryPointer.restype = ctypes.c_int
        x11.XQueryPointer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
    except Exception:
        x11 = None

    _CACHE["x11"] = x11
    return x11


def _x11_cursor() -> tuple[int, int] | None:
    """X11 / XWayland：对根窗口做 XQueryPointer，拿全局坐标。"""
    if not os.environ.get("DISPLAY"):
        return None
    x11 = _load_x11()
    if x11 is None:
        return None

    display = x11.XOpenDisplay(None)
    if not display:
        return None
    try:
        root = x11.XDefaultRootWindow(display)
        root_return = ctypes.c_ulong()
        child_return = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        win_x = ctypes.c_int()
        win_y = ctypes.c_int()
        mask = ctypes.c_uint()
        ok = x11.XQueryPointer(
            display,
            root,
            ctypes.byref(root_return),
            ctypes.byref(child_return),
            ctypes.byref(root_x),
            ctypes.byref(root_y),
            ctypes.byref(win_x),
            ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        if not ok:
            return None
        return int(root_x.value), int(root_y.value)
    except Exception:
        return None
    finally:
        try:
            x11.XCloseDisplay(display)
        except Exception:
            pass


def _run_json_command(argv: list[str]) -> Any | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _hyprland_cursor() -> tuple[int, int] | None:
    """Hyprland：hyprctl -j cursorpos 输出 {"x": .., "y": ..}。"""
    payload = _run_json_command(["hyprctl", "-j", "cursorpos"])
    if isinstance(payload, dict) and "x" in payload and "y" in payload:
        try:
            return int(payload["x"]), int(payload["y"])
        except (TypeError, ValueError):
            return None
    return None


def _wayland_cursor() -> tuple[int, int] | None:
    """Wayland：没有协议级查询，按合成器逐个探测。"""
    return _hyprland_cursor()


def get_cursor_position() -> tuple[int, int] | None:
    """返回全局光标坐标 (x, y)；无法获取时返回 None。"""
    if sys.platform == "win32":
        return _windows_cursor()

    if sys.platform == "darwin":
        # 未适配 macOS，交给调用方降级
        return None

    # Linux：优先问合成器（Wayland 下唯一可靠来源），再退回 X11。
    if os.environ.get("WAYLAND_DISPLAY"):
        position = _wayland_cursor()
        if position is not None:
            return position
    return _x11_cursor()
