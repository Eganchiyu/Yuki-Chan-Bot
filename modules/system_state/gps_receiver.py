from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime
from typing import Any

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - 运行环境未安装 websockets 时保持主程序可启动
    websockets = None
    ConnectionClosed = Exception


GPS_VPS_SERVER_URL = os.getenv("YUKI_GPS_VPS_SERVER_URL", "ws://8.217.41.28:8765")
GPS_VPS_RECONNECT_DELAY_SECONDS = float(os.getenv("YUKI_GPS_VPS_RECONNECT_DELAY_SECONDS", "5"))
GPS_VPS_STALE_SECONDS = float(os.getenv("YUKI_GPS_VPS_STALE_SECONDS", "300"))

_location_lock = threading.Lock()
_latest_location: dict[str, Any] | None = None
_last_error: str | None = None
_receiver_stop_event = threading.Event()
_receiver_thread: threading.Thread | None = None


def _set_latest_location(data: dict[str, Any]) -> None:
    global _latest_location, _last_error
    location = {
        "longitude": data.get("longitude"),
        "latitude": data.get("latitude"),
        "timestamp": data.get("timestamp"),
        "received_at": datetime.now().astimezone().isoformat(),
    }
    with _location_lock:
        _latest_location = location
        _last_error = None


def _set_error(message: str) -> None:
    global _last_error
    with _location_lock:
        _last_error = message


async def _receive_locations() -> None:
    if websockets is None:
        _set_error("websockets 未安装，GPS-VPS 接收端未启动")
        return

    while not _receiver_stop_event.is_set():
        try:
            async with websockets.connect(GPS_VPS_SERVER_URL) as websocket:
                async for message in websocket:
                    if _receiver_stop_event.is_set():
                        break
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        _set_error(f"收到非 JSON GPS 消息: {message}")
                        continue
                    _set_latest_location(data)
        except ConnectionClosed as exc:
            _set_error(f"GPS-VPS 连接断开: code={exc.code}, reason={exc.reason}")
        except OSError as exc:
            _set_error(f"无法连接 GPS-VPS 服务器: {exc}")
        except Exception as exc:
            _set_error(f"GPS-VPS 接收端异常: {exc}")

        await asyncio.sleep(GPS_VPS_RECONNECT_DELAY_SECONDS)


def _receiver_loop() -> None:
    asyncio.run(_receive_locations())


def start_gps_receiver_service() -> None:
    global _receiver_thread
    if _receiver_thread is not None and _receiver_thread.is_alive():
        return
    _receiver_stop_event.clear()
    _receiver_thread = threading.Thread(
        target=_receiver_loop,
        name="gps-vps-receiver",
        daemon=True,
    )
    _receiver_thread.start()


def stop_gps_receiver_service() -> None:
    _receiver_stop_event.set()


def latest_gps_status() -> dict[str, Any]:
    with _location_lock:
        location = dict(_latest_location) if _latest_location else None
        last_error = _last_error

    if not location:
        return {
            "enabled": websockets is not None,
            "connected": False,
            "stale": True,
            "server_url": GPS_VPS_SERVER_URL,
            "location": None,
            "last_error": last_error,
        }

    received_at = datetime.fromisoformat(location["received_at"])
    age_seconds = max(0.0, time.time() - received_at.timestamp())
    return {
        "enabled": websockets is not None,
        "connected": last_error is None,
        "stale": age_seconds > GPS_VPS_STALE_SECONDS,
        "server_url": GPS_VPS_SERVER_URL,
        "location": location,
        "location_age_seconds": age_seconds,
        "last_error": last_error,
    }
