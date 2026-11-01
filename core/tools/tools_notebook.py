# core/tools/tools_notebook.py
"""小本本工具：Yuki 修改自己长期笔记的内容。"""
from core.notebook import NOTEBOOK_MAX_CHARS, notebook_store
from core.toolchain import ToolResult

from .tools_common import logger


async def update_notebook_tool(context, content):
    """覆盖更新小本本。"""
    logger.info(
        f"[ToolCall][update_notebook] chat_id={context.chat_id} len={len(str(content or ''))}"
    )
    saved = notebook_store.save(content)
    if len(str(content or "").strip()) > NOTEBOOK_MAX_CHARS:
        return ToolResult(
            success=True,
            content=f"已更新小本本（超出 {NOTEBOOK_MAX_CHARS} 字的部分已截断）。",
            data={"length": len(saved)},
        )
    return ToolResult(
        success=True,
        content="已更新小本本",
        data={"length": len(saved)},
    )
