from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time


MASTER_PAUSED_SECONDS = 30
MASTER_AWAY_SECONDS = 2 * 60
MASTER_OFFLINE_SECONDS = 10 * 60
MONITOR_INTERVAL_SECONDS = 1

_state_lock = threading.Lock()
_last_master_activity = 0.0
_monitor_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None


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


def _get_foreground_window_title() -> str:
    if not hasattr(ctypes, "windll"):
        return ""
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


def _get_system_idle_seconds() -> float | None:
    if not hasattr(ctypes, "windll"):
        return None
    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]

    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(LastInputInfo)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    tick_count = ctypes.windll.kernel32.GetTickCount()
    return max(0.0, (tick_count - info.dwTime) / 1000.0)


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


