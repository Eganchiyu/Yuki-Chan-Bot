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
from core.tools import tools_status as monitor


def test_master_status_records_recent_activity(monkeypatch):
    monkeypatch.setattr(monitor, "_get_system_idle_seconds", lambda: 12.0)
    monkeypatch.setattr(monitor, "_get_foreground_window_title", lambda: "测试窗口")
    monitor._last_master_activity = 0.0

    monitor.record_master_activity()
    status = monitor.master_status()

    assert status["online"] is True
    assert status["active"] is True
    assert status["foreground_window"] == "测试窗口"


def test_master_status_returns_false_when_activity_is_stale(monkeypatch):
    monkeypatch.setattr(monitor, "_get_system_idle_seconds", lambda: 600.0)
    monkeypatch.setattr(monitor, "_get_foreground_window_title", lambda: "")
    monitor._last_master_activity = 0.0

    status = monitor.master_status()

    assert status["online"] is False
    assert status["active"] is False
    assert status["foreground_window"] == ""


def test_master_status_tool_is_registered():
    spec = next(spec for spec in TOOL_SPECS if spec.name == "get_master_status")
    assert spec.handler is get_master_status_tool


def test_master_status_tool_returns_boolean_data(monkeypatch):
    master_status = {
        "online": True,
        "active": False,
        "status": "online",
        "foreground_window": "编辑器",
    }
    monkeypatch.setattr(monitor, "master_status", lambda: master_status)
    context = ToolContext(
        chat_id="test",
        mode="master_private",
        session=[],
        combined_text="状态",
        runtime=ToolRuntime(sender=SimpleNamespace(), yuki_state=SimpleNamespace()),
    )

    result = asyncio.run(get_master_status_tool(context))

    assert result.success is True
    assert result.data == master_status
    assert "主人在线：True" in result.content
    assert "活跃：False" in result.content
    assert "状态：online" in result.content
    assert "当前窗口：编辑器" in result.content
