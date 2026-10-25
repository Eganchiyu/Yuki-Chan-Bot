# core/tools/tools_subscribe.py
"""回复订阅工具：到点没人回复，就让 Yuki 自己补一句。"""
from core.reply_watch import MIN_TIMEOUT_SECONDS, subscribe
from core.toolchain import ToolResult

from .tools_common import logger


async def subscribe_reply_tool(context, time=60):
    """订阅当前会话接下来的回应，到点没人回复就注入一条提醒。"""
    chat_id = str(context.chat_id)
    callback = context.metadata.get("process_callback") or getattr(context.yuki, "process_callback", None)
    if callback is None:
        logger.warning(f"[SubscribeReply] process_callback 未设置，无法建立订阅 chat_id={chat_id}")
        return ToolResult.failure("订阅失败：回复通道未就绪。", "callback_unavailable")

    try:
        watch = subscribe(chat_id, context.mode, callback, timeout_seconds=time)
    except ValueError as exc:
        if str(exc) == "invalid_timeout":
            return ToolResult.failure(
                f"订阅失败：等待时间必须在 {MIN_TIMEOUT_SECONDS:.0f} 秒以上。",
                "timeout_too_short",
            )
        return ToolResult.failure(f"订阅失败：{exc}", str(exc))

    return ToolResult(
        success=True,
        content=f"好，{watch['timeout_seconds']:.0f} 秒内没人回复的话我就来提醒你。",
        data=watch,
    )
