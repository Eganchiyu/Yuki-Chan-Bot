# core/tools/tools_status.py
"""主人状态相关工具与后台监控（合并自 modules/system_state）。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import re
import subprocess
import threading
import time

from core.toolchain import ToolResult


MASTER_PAUSED_SECONDS = 30
MASTER_AWAY_SECONDS = 2 * 60
MASTER_OFFLINE_SECONDS = 10 * 60
MONITOR_INTERVAL_SECONDS = 1

# Linux 侧通过子进程查询 logind / X11，代价较高，用短缓存避免每秒轮询
_LINUX_QUERY_CACHE_TTL = 5.0

_state_lock = threading.Lock()
_last_master_activity = 0.0
_monitor_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None

# (fetched_at, idle_since_us | None) / (fetched_at, title)
_linux_idle_cache: tuple[float, int | None] | None = None
_linux_window_cache: tuple[float, str] | None = None


def record_master_activity() -> None:
    global _last_master_activity
    with _state_lock:
        _last_master_activity = time.time()


def _monitor_loop() -> None:
    while not _monitor_stop_event.wait(MONITOR_INTERVAL_SECONDS):
        idle_seconds = _get_system_idle_seconds()
        if idle_seconds is not None and idle_seconds <= MASTER_OFFLINE_SECONDS:
            record_master_activity()


def start_monitor_service() -> None:
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        return
    _monitor_stop_event.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="master-state-monitor",
        daemon=True,
    )
    _monitor_thread.start()


def stop_monitor_service() -> None:
    _monitor_stop_event.set()


def _run_cmd(cmd: list[str]) -> str | None:
    """低开销执行子进程并返回去除首尾空白的 stdout；失败返回 None。"""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    out = proc.stdout.strip()
    return out or None


def _get_windows_foreground_window_title() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _get_linux_foreground_window_title() -> str:
    """通过 X11 的 _NET_ACTIVE_WINDOW 获取前台窗口标题。"""
    global _linux_window_cache
    now = time.time()
    if _linux_window_cache is not None and now - _linux_window_cache[0] <= _LINUX_QUERY_CACHE_TTL:
        return _linux_window_cache[1]

    title = ""
    active_line = _run_cmd(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    match = re.search(r"0x[0-9a-fA-F]+", active_line or "")
    window_id = match.group(0) if match else None
    if window_id and window_id != "0x0":
        name_line = _run_cmd(["xprop", "-id", window_id, "_NET_WM_NAME", "WM_NAME"])
        name_match = re.search(r'"([^"]*)"', name_line or "")
        if name_match:
            title = name_match.group(1).strip()

    _linux_window_cache = (now, title)
    return title


def _get_windows_idle_seconds() -> float | None:
    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]

    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(LastInputInfo)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    tick_count = ctypes.windll.kernel32.GetTickCount()
    return max(0.0, (tick_count - info.dwTime) / 1000.0)


def _get_linux_idle_seconds() -> float | None:
    """通过 systemd-logind 会话空闲时间戳判断桌面空闲（兼容 X11/Wayland）。"""
    global _linux_idle_cache
    now = time.time()
    session_id = os.environ.get("XDG_SESSION_ID")
    if not session_id:
        return None
    if _linux_idle_cache is None or now - _linux_idle_cache[0] > _LINUX_QUERY_CACHE_TTL:
        value = _run_cmd(["loginctl", "show-session", session_id, "-P", "IdleSinceHint"])
        try:
            idle_since_us = int(value) if value is not None else None
        except ValueError:
            idle_since_us = None
        _linux_idle_cache = (now, idle_since_us)

    idle_since_us = _linux_idle_cache[1]
    if idle_since_us is None:
        return None
    if idle_since_us <= 0:
        return 0.0
    return max(0.0, now - idle_since_us / 1_000_000)


def _get_foreground_window_title() -> str:
    if hasattr(ctypes, "windll"):
        return _get_windows_foreground_window_title()
    return _get_linux_foreground_window_title()


def _get_system_idle_seconds() -> float | None:
    if hasattr(ctypes, "windll"):
        return _get_windows_idle_seconds()
    return _get_linux_idle_seconds()


def master_status() -> dict:
    now = time.time()
    with _state_lock:
        last_activity = _last_master_activity
    idle_seconds = _get_system_idle_seconds()
    last_activity_seconds = max(0.0, now - last_activity) if last_activity else None

    if last_activity_seconds is None or last_activity_seconds > MASTER_OFFLINE_SECONDS:
        status = "offline"
    elif last_activity_seconds > MASTER_AWAY_SECONDS:
        status = "away"
    elif last_activity_seconds > MASTER_PAUSED_SECONDS:
        status = "paused"
    else:
        status = "online"

    return {
        "status": status,
        "online": status == "online",
        "active": idle_seconds is not None and idle_seconds <= MASTER_PAUSED_SECONDS,
        "foreground_window": _get_foreground_window_title(),
        "system_idle_seconds": idle_seconds,
        "last_activity_seconds": last_activity_seconds,
    }


async def get_master_status_tool(context):
    data = master_status()
    content = "；".join([
        f"主人在线：{data['online']}",
        f"活跃：{data['active']}",
        f"状态：{data.get('status', 'unknown')}",
        f"当前窗口：{data.get('foreground_window') or '未知'}",
    ])
    return ToolResult(
        success=True,
        content=content,
        data=data,
    )