# core/tools/tools_rich.py
"""富文本消息解析工具：合并转发、小程序、JSON/XML/Markdown。"""
import json
import re
from urllib.parse import unquote

from core.toolchain import ToolResult

from .tools_common import _compact_text, logger


def _safe_json_loads(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = unquote(value).strip()
    try:
        return json.loads(text)
    except Exception:
        return None


def _pick_nested(data, keys):
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if value:
                return str(value)
        for value in data.values():
            picked = _pick_nested(value, keys)
            if picked:
                return picked
    elif isinstance(data, list):
        for item in data:
            picked = _pick_nested(item, keys)
            if picked:
                return picked
    return ""


def _summarize_structured_payload(raw_data, kind):
    parsed = _safe_json_loads(raw_data)
    if isinstance(parsed, dict):
        title = _pick_nested(parsed, ["title", "prompt", "desc", "name", "app", "appName"])
        summary = _pick_nested(parsed, ["summary", "content", "text", "desc", "description"])
        url = _pick_nested(parsed, ["url", "jumpUrl", "qqdocurl", "preview", "sourceUrl"])
        parts = [kind]
        if title:
            parts.append(f"标题:{_compact_text(title, 120)}")
        if summary and summary != title:
            parts.append(f"内容:{_compact_text(summary, 220)}")
        if url:
            parts.append(f"链接:{_compact_text(url, 180)}")
        return "[" + " | ".join(parts) + "]"
    if raw_data:
        return f"[{kind}:{_compact_text(raw_data, 400)}]"
    return f"[{kind}]"


def _segment_data(seg):
    return seg.get("data", {}) if isinstance(seg, dict) else {}


def _get_tool_meme_processor(context):
    processor = context.metadata.get("meme_processor")
    if processor:
        return processor
    try:
        from modules.vision.processor import MemeProcessor
        processor = MemeProcessor(image_store=context.image_store)
        context.metadata["meme_processor"] = processor
        return processor
    except Exception as exc:
        logger.debug(f"[RichMessage] 初始化图片理解器失败: {exc}")
        return None


async def _format_image_segment(context, data, is_meme=False):
    url = data.get("url") or data.get("file") or data.get("path")
    summary = data.get("summary") or data.get("name") or data.get("text")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        processor = _get_tool_meme_processor(context)
        if processor:
            result = await processor.understand_from_url(url, is_meme=is_meme)
            desc = result.get("description") if isinstance(result, dict) else result
            idx = result.get("index") if isinstance(result, dict) else None
            idx_tag = f"[img:{idx}]" if idx else ""
            kind = "表情" if is_meme else "图片"
            if desc:
                return f"[{kind}:{desc}]{idx_tag}"
    kind = "表情" if is_meme else "图片"
    return f"[{kind}:{_compact_text(summary or url, 120)}]" if (summary or url) else f"[{kind}]"


async def _format_message_segments(context, segments, depth=0, max_depth=3):
    if isinstance(segments, str):
        return _compact_text(segments, 800)
    if isinstance(segments, dict):
        segments = [segments]
    if not isinstance(segments, list):
        return "[未知消息]"

    parts = []
    for seg in segments:
        if not isinstance(seg, dict):
            parts.append(_compact_text(seg, 200))
            continue

        seg_type = str(seg.get("type") or "").lower()
        data = _segment_data(seg)
        if seg_type == "text":
            parts.append(str(data.get("text", "")))
        elif seg_type == "at":
            parts.append(f"@{data.get('name') or data.get('qq') or '未知'}")
        elif seg_type == "face":
            parts.append("[表情]")
        elif seg_type == "mface":
            parts.append(await _format_image_segment(context, data, is_meme=True))
        elif seg_type == "image":
            is_meme = str(data.get("sub_type", "")).lower() not in {"0", "normal"}
            parts.append(await _format_image_segment(context, data, is_meme=is_meme))
        elif seg_type == "record":
            file_id = data.get("file") or data.get("url") or data.get("path")
            parts.append(f"[语音:file_id={file_id}]" if file_id else "[语音]")
        elif seg_type == "video":
            file_id = data.get("file") or data.get("url") or data.get("path")
            parts.append(f"[视频:file_id={file_id}]" if file_id else "[视频]")
        elif seg_type in {"file", "onlinefile"}:
            file_id = data.get("id") or data.get("file_id") or data.get("file") or data.get("msgId")
            name = data.get("name") or data.get("fileName") or "文件"
            parts.append(f"[文件:{name},file_id={file_id}]" if file_id else f"[文件:{name}]")
        elif seg_type == "json":
            parts.append(_summarize_structured_payload(data.get("data"), "JSON富文本"))
        elif seg_type == "xml":
            parts.append(f"[XML富文本:{_compact_text(data.get('data'), 400)}]")
        elif seg_type == "markdown":
            parts.append(f"[Markdown:{_compact_text(data.get('content'), 500)}]")
        elif seg_type == "miniapp":
            parts.append(_summarize_structured_payload(data.get("data"), "小程序"))
        elif seg_type in {"node", "forward"}:
            forward_id = data.get("id")
            content = data.get("content")
            if content and depth < max_depth:
                name = data.get("nickname") or data.get("name") or data.get("user_id") or data.get("uin") or "转发节点"
                nested = await _format_message_segments(context, content, depth + 1, max_depth)
                parts.append(f"[合并转发节点:{name}: {nested}]")
            elif forward_id:
                parts.append(f"[合并转发:id={forward_id}]")
            else:
                parts.append("[合并转发]")
        elif seg_type == "music":
            title = data.get("title") or data.get("id") or "音乐"
            parts.append(f"[音乐:{_compact_text(title, 120)}]")
        elif seg_type == "location":
            title = data.get("title") or data.get("content") or "位置"
            parts.append(f"[位置:{_compact_text(title, 120)}]")
        else:
            parts.append(f"[{seg_type or '富文本'}:{_compact_text(data, 240)}]")

    return _compact_text("".join(parts), 2000)


def _extract_rich_items_from_segments(segments):
    if isinstance(segments, dict):
        segments = [segments]
    if not isinstance(segments, list):
        return []

    items = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        seg_type = str(seg.get("type") or "").lower()
        data = _segment_data(seg)
        if seg_type in {"forward", "node"}:
            forward_id = data.get("id")
            content = data.get("content")
            if forward_id:
                items.append({"type": "forward", "id": str(forward_id), "segment": seg})
            if content:
                items.append({"type": "forward_inline", "content": content, "segment": seg})
        elif seg_type in {"json", "xml", "markdown", "miniapp"}:
            items.append({"type": seg_type, "segment": seg})
    return items


def _find_recent_rich_items(context):
    items = []
    for message in context.metadata.get("message_objs") or []:
        for item in _extract_rich_items_from_segments(message.get("segments")):
            item["message_id"] = message.get("message_id")
            item["sender"] = message.get("name")
            items.append(item)

    text = context.combined_text or ""
    for forward_id in re.findall(r'\[合并转发(?::id=|,id=)([^\]]+)\]', text):
        items.append({"type": "forward", "id": forward_id})
    for forward_id in re.findall(r'\[CQ:forward,id=([^,\]]+)', text):
        items.append({"type": "forward", "id": forward_id})
    return items


def _normalize_forward_messages(data):
    if isinstance(data, dict):
        for key in ("messages", "message", "content"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if isinstance(data.get("data"), dict):
            return _normalize_forward_messages(data["data"])
    if isinstance(data, list):
        return data
    return []


async def _fetch_forward_messages(context, forward_id):
    gateway = context.sender
    params_options = [
        {"id": forward_id},
        {"message_id": forward_id},
        {"forward_id": forward_id},
    ]
    last_resp = None
    for params in params_options:
        resp = await gateway.call("get_forward_msg", params, timeout=60)
        last_resp = resp
        if resp and resp.get("status") == "ok":
            messages = _normalize_forward_messages(resp.get("data"))
            if messages:
                return messages, resp
    return [], last_resp


async def _render_forward_messages(context, messages, start, count, max_depth, depth=0):
    total = len(messages)
    start = max(1, int(start or 1))
    count = max(1, min(int(count or 20), 80))
    end = min(total, start + count - 1)
    selected = messages[start - 1:end]

    lines = [f"合并转发消息共 {total} 条，当前显示第 {start}-{end} 条，剩余 {max(0, total - end)} 条。"]
    for i, node in enumerate(selected, start):
        data = _segment_data(node) if isinstance(node, dict) and node.get("type") in {"node", "forward"} else node
        if not isinstance(data, dict):
            lines.append(f"{i}. {_compact_text(data, 600)}")
            continue

        sender = data.get("nickname") or data.get("name") or data.get("sender", {}).get("nickname") or data.get("user_id") or data.get("uin") or "未知"
        content = data.get("content") or data.get("message") or data.get("raw_message") or ""
        parsed = await _format_message_segments(context, content, depth=depth, max_depth=max_depth)
        lines.append(f"{i}. {sender}: {parsed}")

        if depth < max_depth:
            for item in _extract_rich_items_from_segments(content):
                if item["type"] == "forward_inline":
                    nested = await _render_forward_messages(context, item["content"], 1, min(count, 20), max_depth, depth + 1)
                    lines.append("  嵌套合并转发：" + nested["content"].replace("\n", "\n  "))
                elif item["type"] == "forward" and item.get("id"):
                    nested_messages, _ = await _fetch_forward_messages(context, item["id"])
                    if nested_messages:
                        nested = await _render_forward_messages(context, nested_messages, 1, min(count, 20), max_depth, depth + 1)
                        lines.append("  嵌套合并转发：" + nested["content"].replace("\n", "\n  "))

    if end < total:
        lines.append(f"还剩 {total - end} 条未读，可再次调用本工具并设置 start={end + 1}, count=想读的条数。")
    return {
        "content": "\n".join(lines),
        "total": total,
        "start": start,
        "end": end,
        "remaining": max(0, total - end),
    }


async def parse_rich_message_tool(context, rich_id=None, rich_type="auto", start=1, count=20, max_depth=3):
    """主动解析最近消息中的合并转发、小程序、JSON/XML/Markdown 等富文本。"""
    rich_type = str(rich_type or "auto").lower()
    items = _find_recent_rich_items(context)

    selected = None
    if rich_id:
        for item in items:
            if str(item.get("id", "")) == str(rich_id):
                selected = item
                break
        if not selected:
            selected = {"type": rich_type if rich_type != "auto" else "forward", "id": str(rich_id)}
    elif rich_type != "auto":
        if rich_type == "miniapp":
            selected = next((item for item in items if item["type"] in {"miniapp", "json"}), None)
        else:
            selected = next((item for item in items if item["type"] == rich_type), None)
    else:
        selected = items[0] if items else None

    if not selected:
        return ToolResult(
            success=False,
            content="最近消息里没有可主动解析的富文本。支持合并转发、小程序、JSON、XML、Markdown。",
            data={"available": []},
            error="rich_message_not_found",
        )

    item_type = selected.get("type")
    result_type = "miniapp" if rich_type == "miniapp" and item_type == "json" else item_type
    if item_type in {"json", "xml", "markdown", "miniapp"}:
        segment = selected["segment"]
        if result_type == "miniapp" and item_type == "json":
            segment = {**segment, "type": "miniapp"}
        parsed = await _format_message_segments(context, segment)
        return ToolResult(
            success=True,
            content=parsed,
            data={"type": result_type, "message_id": selected.get("message_id"), "sender": selected.get("sender")},
        )

    if item_type == "forward_inline":
        rendered = await _render_forward_messages(context, selected["content"], start, count, max_depth)
        return ToolResult(success=True, content=rendered["content"], data={"type": item_type, **rendered})

    forward_id = selected.get("id")
    if not forward_id:
        return ToolResult(success=False, content="缺少合并转发 ID。", error="missing_forward_id")

    messages, response = await _fetch_forward_messages(context, forward_id)
    if not messages:
        return ToolResult(
            success=False,
            content="获取合并转发内容失败，可能 NapCat 当前版本不支持 get_forward_msg 或该 ID 已失效。",
            data={"forward_id": forward_id, "response": response},
            error="fetch_forward_failed",
        )

    rendered = await _render_forward_messages(context, messages, start, count, max_depth)
    return ToolResult(success=True, content=rendered["content"], data={"type": "forward", "forward_id": forward_id, **rendered})
