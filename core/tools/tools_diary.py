# core/tools/tools_diary.py
"""日记/记忆检索工具。"""
import asyncio

from core.maid.maid import search_diary_fast
from core.toolchain import ToolResult

from .tools_common import logger


async def search_diary_tool(context, date_str=None, keyword=None):
    """查询 Yuki 日记。"""
    logger.info(
        f"[ToolCall][search_diary] chat_id={context.chat_id} date_str={date_str} keyword={keyword}"
    )
    result = await asyncio.to_thread(search_diary_fast, date_str, keyword)
    return ToolResult(success=True, content=result)
