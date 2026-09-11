# core/tools/tools_snapshot.py
"""群聊上下文截屏留忆工具。"""
import os

from core.toolchain import ToolResult
from modules.shot_memory import render_snapshot, shot_live_buffer

from .tools_common import logger, shot_memory_store


async def capture_group_snapshot_tool(context, note, limit=12):
    """把当前群聊最近上下文渲染成永久保存的伪截屏。"""
    if not note:
        return ToolResult(success=False, content="缺少截屏备注", error="missing_note")
    if context.mode not in ("group", "master_private"):
        return ToolResult(success=False, content="截屏留念目前只适合群聊上下文。", error="unsupported_mode")

    chat_id = str(context.chat_id)
    limit = max(4, min(int(limit or 12), 20))
    history = context.session[-limit:]
    message_objs = context.metadata.get("message_objs") or []
    live_messages = shot_live_buffer.snapshot(chat_id, limit=limit)

    try:
        image_bytes, meta = await render_snapshot(
            chat_id,
            note,
            history,
            message_objs,
            gateway=context.sender,
            live_messages=live_messages,
        )
        record = shot_memory_store.save_record(chat_id, note, image_bytes, metadata=meta)
    except Exception as e:
        logger.error(f"[ShotMemory] 截屏失败: {e}")
        return ToolResult(success=False, content=f"截屏失败: {str(e)}", error=str(e))

    return ToolResult(
        success=True,
        content=f"截屏已保存: {record['note']}",
        data={
            "file_path": record["file_path"],
            "note": record["note"],
            "created_at": record["created_at"],
            "group_name": record.get("group_name", ""),
        },
    )


async def search_group_snapshots_tool(context, keyword=None, limit=5):
    """搜索当前群聊的永久截屏记录，并预热 [shot:N] 索引。"""
    chat_id = str(context.chat_id)
    keyword = (keyword or "").strip()
    limit = max(1, min(int(limit or 5), 5))

    if keyword:
        records = shot_memory_store.search(chat_id, keyword=keyword, limit=limit)
        mode_text = "找到"
    else:
        records = shot_memory_store.random_records(chat_id, limit=limit)
        mode_text = "随机找到"

    prepared = shot_memory_store.preload(chat_id, records)
    if not prepared:
        return ToolResult(success=True, content="没有找到本群相关截屏记录。", data={"records": []})

    lines = [f"{mode_text} {len(prepared)} 条本群截屏记录，已预热为 [shot:编号]："]
    for item in prepared:
        lines.append(
            f"{item['shot_tag']} {item.get('created_at', '')} | {item.get('note', '')}\n"
            f"文件名: {item.get('filename', os.path.basename(item['absolute_path']))}\n"
            f"路径: {item['absolute_path']}"
        )
    return ToolResult(success=True, content="\n".join(lines), data={"records": prepared})
