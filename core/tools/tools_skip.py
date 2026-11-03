# core/tools/tools_skip.py
"""skip 工具：让 Yuki 在不该自己说话时选择保持安静。"""
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")


async def skip_reply_tool(context, reason: str = "") -> ToolResult:
    """跳过本轮回复：不发送任何消息，只把原因留在日志里。"""
    if context.mode != "group":
        return ToolResult.failure(
            "当前不是群聊模式，必须回复，不能跳过。请直接输出回复内容。",
            "skip_not_allowed",
            name="skip",
        )

    reason = str(reason or "").strip()
    logger.info(f"[Skip] chat={context.chat_id} 跳过本轮回复 | 原因: {reason or '未说明'}")
    return ToolResult(
        success=True,
        content="已跳过本轮回复，本轮不会再发出任何消息。保持安静，继续待着即可。",
        data={"skip_reply": True, "reason": reason},
    )
