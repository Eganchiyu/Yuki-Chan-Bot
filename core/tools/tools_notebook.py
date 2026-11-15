# core/tools/tools_notebook.py
"""小本本工具：Yuki 修改自己长期笔记的内容。"""
from core.notebook import NOTEBOOK_DAILY_MAX_CHARS, notebook_store
from core.toolchain import ToolResult

from .tools_common import logger


async def update_notebook_tool(context, content, zone="daily"):
    """覆盖更新小本本的指定分区（默认日常随记区）。"""
    logger.info(
        f"[ToolCall][update_notebook] chat_id={context.chat_id} zone={zone} "
        f"len={len(str(content or ''))}"
    )
    saved = notebook_store.save_zone(zone, content)
    limit = NOTEBOOK_DAILY_MAX_CHARS
    zone_label = "小本本"
    if str(zone or "") == "plans":
        limit = 160
        zone_label = "小本本的长期规划区"
    if len(str(content or "").strip()) > limit:
        return ToolResult(
            success=True,
            content=f"已更新{zone_label}（超出 {limit} 字的部分已截断）。",
            data={"length": len(saved), "zone": zone},
        )
    return ToolResult(
        success=True,
        content=f"已更新{zone_label}",
        data={"length": len(saved), "zone": zone},
    )
