# core/tools/tools_qzone.py
"""QQ 空间说说发布工具。"""
from core.toolchain import ToolResult

from .tools_common import _resolve_image_path, logger


async def publish_qzone_mood_tool(context, content, visible=1, image_paths=None):
    """发布 QQ 空间说说。支持纯文本和带图。image_paths 支持 [img:XXX] 索引。"""
    if not content:
        return ToolResult(success=False, content="缺少说说内容", error="missing_content")

    # 解析图片索引
    if image_paths:
        image_paths = [_resolve_image_path(context, p) for p in image_paths]

    from modules.qzone import publish_mood
    connector = context.sender.connector
    result = await publish_mood(connector, content, visible, image_paths)

    if result.get("success"):
        suffix = "（带图）" if result.get("has_image") else ""

        # 通知监控器记录新说说
        try:
            from modules.qzone.monitor import notify_new_post
            chat_context = []
            # 从历史中提取最近的群聊消息作为上下文
            cid = str(context.chat_id)
            if hasattr(context.yuki, 'message_buffer'):
                buf = context.yuki.message_buffer.get(cid, [])
                chat_context = [m.get("content", "")[:80] for m in buf[-5:] if m.get("content")]
            notify_new_post(
                tid=result.get("tid", ""),
                content=content[:100],
                source_chat=cid,
                chat_context=chat_context,
            )
        except Exception as e:
            logger.warning(f"[QZone] 通知监控器失败: {e}")

        return ToolResult(
            success=True,
            content=f"说说已发布{suffix}: {content}",
            data={"tid": result.get("tid"), "time": result.get("time")},
        )
    return ToolResult(
        success=False,
        content=f"发布失败: {result.get('message', '未知错误')}",
        data=result,
        error=result.get("message", "publish_failed"),
    )
