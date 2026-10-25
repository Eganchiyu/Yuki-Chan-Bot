# core/tools/tools_subscribe.py
"""回复订阅工具：期待回音时，超时后再开口追击。"""
from core.reply_watch import (
    MAX_FOLLOWUPS,
    MIN_TIMEOUT_SECONDS,
    cancel_watch,
    get_watch,
    start_watch,
)
from core.toolchain import ToolResult

from .tools_common import logger


async def subscribe_reply_tool(
    context,
    action="subscribe",
    timeout_seconds=60,
    max_followups=MAX_FOLLOWUPS,
    expectation=None,
):
    """订阅当前会话接下来的回应；超时则提醒 Yuki 追击（最多两次）。"""
    chat_id = str(context.chat_id)

    if action == "cancel":
        watch = cancel_watch(chat_id, "tool_cancel")
        if not watch:
            return ToolResult(success=True, content="当前没有等待中的订阅，不需要取消。", data=None)
        return ToolResult(success=True, content="已放弃等待，后续不会再追击。", data=watch)

    if action in {"status", "list"}:
        watch = get_watch(chat_id)
        if not watch:
            return ToolResult(success=True, content="当前没有等待中的订阅。", data=None)
        return ToolResult(success=True, content="当前订阅进行中。", data=watch)

    callback = context.metadata.get("process_callback") or getattr(context.yuki, "process_callback", None)
    if callback is None:
        logger.warning(f"[SubscribeReply] process_callback 未设置，无法建立订阅 chat_id={chat_id}")
        return ToolResult.failure("订阅失败：回复通道未就绪。", "callback_unavailable")

    try:
        watch = start_watch(
            chat_id,
            context.mode,
            callback,
            timeout_seconds=timeout_seconds,
            max_followups=max_followups,
            expectation=expectation,
        )
    except ValueError as exc:
        if str(exc) == "invalid_timeout":
            return ToolResult.failure(
                f"订阅失败：等待时间必须在 {MIN_TIMEOUT_SECONDS:.0f} 秒以上。",
                "timeout_too_short",
            )
        return ToolResult.failure(f"订阅失败：{exc}", str(exc))

    return ToolResult(
        success=True,
        content=(
            f"已订阅：{watch['timeout_seconds']:.0f} 秒内没人说话就会提醒你，最多追击 {watch['max_followups']} 次。"
            "期间收到任何人的新消息就视为得到回应，订阅自动结束。"
        ),
        data=watch,
    )
