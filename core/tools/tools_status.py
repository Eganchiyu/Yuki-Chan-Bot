# core/tools/tools_status.py
"""主人状态相关工具。"""
from core.toolchain import ToolResult
from modules.system_state import monitor as system_state_monitor


def _format_master_gps_status(gps):
    if not gps:
        return "GPS：未启用"
    if not gps.get("enabled"):
        return f"GPS：未启用（{gps.get('last_error') or '已关闭'}）"

    location = gps.get("location") or {}
    if not location:
        error = gps.get("last_error") or "暂无定位"
        return f"GPS：暂无位置（{error}）"

    address = location.get("address") or {}
    address_text = address.get("formatted_address") or ""
    if not address_text:
        parts = [
            address.get("province"),
            address.get("city"),
            address.get("district"),
            address.get("street"),
            address.get("street_number"),
        ]
        address_text = "".join(str(part) for part in parts if part)

    coordinates = f"{location.get('longitude')},{location.get('latitude')}"
    stale_text = "，位置可能过期" if gps.get("stale") else ""
    error_text = f"，最近错误：{gps.get('last_error')}" if gps.get("last_error") else ""
    if address_text:
        return f"GPS：{address_text}（坐标：{coordinates}{stale_text}{error_text}）"
    return f"GPS：坐标 {coordinates}{stale_text}{error_text}"


async def get_master_status_tool(context):
    data = system_state_monitor.master_status()
    content = "；".join([
        f"主人在线：{data['online']}",
        f"活跃：{data['active']}",
        f"状态：{data.get('status', 'unknown')}",
        f"当前窗口：{data.get('foreground_window') or '未知'}",
        _format_master_gps_status(data.get("gps")),
    ])
    return ToolResult(
        success=True,
        content=content,
        data=data,
    )
