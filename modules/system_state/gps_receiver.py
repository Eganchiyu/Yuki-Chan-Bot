from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - 运行环境未安装 websockets 时保持主程序可启动
    websockets = None
    ConnectionClosed = Exception


GPS_VPS_SERVER_URL = os.getenv("YUKI_GPS_VPS_SERVER_URL", "ws://8.217.41.28:8765")
GPS_VPS_FETCH_TIMEOUT_SECONDS = float(os.getenv("YUKI_GPS_VPS_FETCH_TIMEOUT_SECONDS", "5"))
GPS_VPS_STALE_SECONDS = float(os.getenv("YUKI_GPS_VPS_STALE_SECONDS", "300"))
AMAP_REVERSE_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/regeo"
AMAP_REVERSE_GEOCODE_TIMEOUT_SECONDS = 5

_cached_location: dict[str, Any] | None = None
_last_error: str | None = None


def _reverse_geocode(longitude: Any, latitude: Any) -> dict[str, Any] | None:
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key or longitude is None or latitude is None:
        return None

    params = urllib.parse.urlencode({
        "key": api_key,
        "location": f"{longitude},{latitude}",
        "extensions": "base",
        "output": "JSON",
    })
    url = f"{AMAP_REVERSE_GEOCODE_URL}?{params}"
    with urllib.request.urlopen(url, timeout=AMAP_REVERSE_GEOCODE_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data.get("status") != "1":
        raise ValueError(f"高德逆地理解析失败: {data.get('info', '未知错误')}")

    regeocode = data.get("regeocode") or {}
    component = regeocode.get("addressComponent") or {}
    street_number = component.get("streetNumber") or {}
    neighborhood = component.get("neighborhood") or {}
    return {
        "formatted_address": regeocode.get("formatted_address"),
        "country": component.get("country"),
        "province": component.get("province"),
        "city": component.get("city") or component.get("province"),
        "district": component.get("district"),
        "adcode": component.get("adcode"),
        "citycode": component.get("citycode"),
        "street": street_number.get("street"),
        "street_number": street_number.get("number"),
        "neighborhood": neighborhood.get("name"),
    }


def _build_location(data: dict[str, Any]) -> dict[str, Any]:
    location = {
        "longitude": data.get("longitude"),
        "latitude": data.get("latitude"),
        "timestamp": data.get("timestamp"),
        "received_at": datetime.now().astimezone().isoformat(),
    }
    try:
        address = _reverse_geocode(location["longitude"], location["latitude"])
        if address:
            location["address"] = address
    except Exception as exc:
        location["address_error"] = str(exc)
    return location


async def _fetch_latest_location() -> dict[str, Any]:
    if websockets is None:
        raise RuntimeError("websockets 未安装，GPS-VPS 接收端不可用")

    async with websockets.connect(GPS_VPS_SERVER_URL) as websocket:
        message = await asyncio.wait_for(websocket.recv(), timeout=GPS_VPS_FETCH_TIMEOUT_SECONDS)

    try:
        data = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(f"收到非 JSON GPS 消息: {message}") from exc
    return _build_location(data)


def _location_age_seconds(location: dict[str, Any]) -> float:
    received_at = datetime.fromisoformat(location["received_at"])
    return max(0.0, time.time() - received_at.timestamp())


def latest_gps_status() -> dict[str, Any]:
    global _cached_location, _last_error

    try:
        location = asyncio.run(_fetch_latest_location())
        _cached_location = location
        _last_error = None
    except TimeoutError:
        _last_error = "等待 GPS-VPS 最新位置超时"
    except ConnectionClosed as exc:
        _last_error = f"GPS-VPS 连接断开: code={exc.code}, reason={exc.reason}"
    except OSError as exc:
        _last_error = f"无法连接 GPS-VPS 服务器: {exc}"
    except Exception as exc:
        _last_error = f"GPS-VPS 获取最新位置失败: {exc}"

    if not _cached_location:
        return {
            "enabled": websockets is not None,
            "connected": False,
            "stale": True,
            "server_url": GPS_VPS_SERVER_URL,
            "location": None,
            "last_error": _last_error,
        }

    age_seconds = _location_age_seconds(_cached_location)
    return {
        "enabled": websockets is not None,
        "connected": _last_error is None,
        "stale": age_seconds > GPS_VPS_STALE_SECONDS,
        "server_url": GPS_VPS_SERVER_URL,
        "location": dict(_cached_location),
        "location_age_seconds": age_seconds,
        "last_error": _last_error,
    }
