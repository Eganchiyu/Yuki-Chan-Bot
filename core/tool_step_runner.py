# core/tool_step_runner.py
"""主对话引擎与自主轮沙盒共用的工具调用解析与结果载荷提取底座。"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from core.tool_markup import extract_text_tool_calls
from utils.logger import get_logger

logger = get_logger("toolchain")


def resolve_tool_calls(
    msg: dict[str, Any],
    valid_tool_names: Optional[Iterable[str]] = None,
    *,
    log_prefix: str = "[ToolChain]",
    chat_id: str = "",
) -> list[dict[str, Any]]:
    """提取模型响应中的工具调用：原生 `tool_calls` 优先，正文标记兜底还原并原位回写 `msg`。"""
    calls = list(msg.get("tool_calls") or [])
    if calls:
        return calls
    allowed = set(valid_tool_names) if valid_tool_names is not None else None
    text_calls, cleaned_content = extract_text_tool_calls(msg.get("content"), allowed)
    if text_calls:
        names = [(c.get("function") or {}).get("name") for c in text_calls]
        cid_part = f" {chat_id}" if chat_id else ""
        logger.warning(
            f"{log_prefix}{cid_part} 工具调用被写成正文文本，已解析为真实调用: {names}"
        )
        msg["content"] = cleaned_content
        msg["tool_calls"] = text_calls
        return text_calls
    return []


def parse_tool_result_payload(tool_message: dict[str, Any]) -> dict[str, Any]:
    """解析 `role='tool'` 消息中的标准 JSON 字符串载荷（异常或非字典返回空字典）。"""
    if not isinstance(tool_message, dict):
        return {}
    content = tool_message.get("content")
    if not isinstance(content, str) or not content:
        return {}
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
