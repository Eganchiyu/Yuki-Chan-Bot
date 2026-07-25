import asyncio
import os
import sys
from types import SimpleNamespace

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.tools import TOOL_SPECS, get_master_status_tool
from core.toolchain import ToolContext, ToolRuntime
from modules.system_state import gps_receiver, monitor


def test_master_status_records_recent_activity(monkeypatch):
    gps_status = {"enabled": True, "location": None}
    monkeypatch.setattr(monitor, "GPS_VPS_RECEIVER_ENABLED", True)
    monkeypatch.setattr(monitor, "_get_system_idle_seconds", lambda: 12.0)
    monkeypatch.setattr(monitor, "_get_foreground_window_title", lambda: "测试窗口")
    monkeypatch.setattr(monitor, "latest_gps_status", lambda: gps_status)
    monitor._last_master_activity = 0.0

    monitor.record_master_activity()
    status = monitor.master_status()

    assert status["online"] is True
    assert status["active"] is True
    assert status["foreground_window"] == "测试窗口"
    assert status["gps"] == gps_status


def test_master_status_returns_false_when_activity_is_stale(monkeypatch):
    monkeypatch.setattr(monitor, "_get_system_idle_seconds", lambda: 600.0)
    monkeypatch.setattr(monitor, "_get_foreground_window_title", lambda: "")
    monitor._last_master_activity = 0.0

    status = monitor.master_status()

    assert status["online"] is False
    assert status["active"] is False
    assert status["foreground_window"] == ""


def test_master_status_returns_disabled_gps_when_switch_is_off(monkeypatch):
    monkeypatch.setattr(monitor, "GPS_VPS_RECEIVER_ENABLED", False)
    monkeypatch.setattr(monitor, "_get_system_idle_seconds", lambda: 12.0)
    monkeypatch.setattr(monitor, "_get_foreground_window_title", lambda: "")
    monkeypatch.setattr(
        monitor,
        "latest_gps_status",
        lambda: (_ for _ in ()).throw(AssertionError("不应读取 GPS 状态")),
    )
    monitor._last_master_activity = 0.0

    monitor.record_master_activity()
    status = monitor.master_status()

    assert status["gps"] == {
        "enabled": False,
        "connected": False,
        "stale": True,
        "server_url": None,
        "location": None,
        "last_error": "GPS-VPS 接收端已关闭",
    }


def test_latest_gps_status_fetches_location_on_demand(monkeypatch):
    location = {
        "longitude": 114.169211,
        "latitude": 22.322653,
        "timestamp": "2026-07-24T03:19:47.991240+00:00",
        "received_at": "2026-07-24T11:19:48+08:00",
    }

    async def fake_fetch_latest_location():
        return location

    monkeypatch.setattr(gps_receiver, "_fetch_latest_location", fake_fetch_latest_location)
    monkeypatch.setattr(gps_receiver, "_cached_location", None)
    monkeypatch.setattr(gps_receiver, "_last_error", None)

    status = gps_receiver.latest_gps_status()

    assert status["connected"] is True
    assert status["location"] == location
    assert status["last_error"] is None


def test_latest_gps_status_returns_cached_location_on_fetch_timeout(monkeypatch):
    cached_location = {
        "longitude": 114.169211,
        "latitude": 22.322653,
        "timestamp": "2026-07-24T03:19:47.991240+00:00",
        "received_at": "2026-07-24T11:19:48+08:00",
    }

    async def fake_fetch_latest_location():
        raise TimeoutError()

    monkeypatch.setattr(gps_receiver, "_fetch_latest_location", fake_fetch_latest_location)
    monkeypatch.setattr(gps_receiver, "_cached_location", cached_location)
    monkeypatch.setattr(gps_receiver, "_last_error", None)

    status = gps_receiver.latest_gps_status()

    assert status["connected"] is False
    assert status["location"] == cached_location
    assert status["last_error"] == "等待 GPS-VPS 最新位置超时"


def test_master_status_tool_is_registered():
    spec = next(spec for spec in TOOL_SPECS if spec.name == "get_master_status")
    assert spec.handler is get_master_status_tool


def test_master_status_tool_returns_boolean_data(monkeypatch):
    monkeypatch.setattr(monitor, "master_status", lambda: {
        "online": True,
        "active": False,
        "foreground_window": "编辑器",
    })
    context = ToolContext(
        chat_id="test",
        mode="master_private",
        session=[],
        combined_text="状态",
        runtime=ToolRuntime(sender=SimpleNamespace(), yuki_state=SimpleNamespace()),
    )

    result = asyncio.run(get_master_status_tool(context))

    assert result.success is True
    assert result.data == {"online": True, "active": False, "foreground_window": "编辑器"}
