# core/private_context.py
"""
主人私聊上下文管理器

当群聊中发生重要事件时，send_master_private 工具会把当时的群聊上下文
打包保存到 JSON 文件。主人私聊时可通过 recall_private_context 工具
召回这些上下文，了解群里发生了什么。
"""

import datetime
import json
import os
from typing import Optional

from utils.logger import get_logger

logger = get_logger("private_context")

# 上下文存储路径
CONTEXT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "private_context.json")
MAX_SNAPSHOTS = 50  # 最多保留50条快照


def _load_store() -> dict:
    """加载上下文存储文件。"""
    if not os.path.exists(CONTEXT_FILE):
        return {"snapshots": []}
    try:
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"[PrivateContext] 加载上下文文件失败: {e}")
        return {"snapshots": []}


def _save_store(store: dict):
    """保存上下文存储文件。"""
    os.makedirs(os.path.dirname(CONTEXT_FILE), exist_ok=True)
    try:
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"[PrivateContext] 保存上下文文件失败: {e}")


def save_context_snapshot(
    source_chat_id: str,
    message: str,
    reason: str,
    recent_messages: list,
) -> str:
    """
    保存一次上下文快照。

    Args:
        source_chat_id: 来源群聊 ID
        message: 发送给主人的私信内容
        reason: 触发原因（如"重要消息"、"有人提到主人"等）
        recent_messages: 当时群聊的最近消息列表，格式同 history_dict

    Returns:
        快照 ID
    """
    store = _load_store()

    snapshot_id = f"snap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    snapshot = {
        "id": snapshot_id,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_chat_id": str(source_chat_id),
        "reason": reason,
        "message": message,
        "context": recent_messages[-10:],  # 只保留最近10条
    }

    store["snapshots"].append(snapshot)

    # 超过上限时裁剪最旧的
    if len(store["snapshots"]) > MAX_SNAPSHOTS:
        store["snapshots"] = store["snapshots"][-MAX_SNAPSHOTS:]

    _save_store(store)
    logger.info(f"[PrivateContext] 已保存快照 {snapshot_id}，来源群聊 {source_chat_id}")
    return snapshot_id


def recall_context(limit: int = 5, source_chat_id: Optional[str] = None) -> list:
    """
    召回最近的上下文快照。

    Args:
        limit: 返回的快照数量上限
        source_chat_id: 可选，只返回指定群聊的快照

    Returns:
        快照列表（最新的在前）
    """
    store = _load_store()
    snapshots = store.get("snapshots", [])

    if source_chat_id:
        snapshots = [s for s in snapshots if s.get("source_chat_id") == str(source_chat_id)]

    # 最新的在前
    snapshots = list(reversed(snapshots))
    return snapshots[:limit]


def format_context_for_prompt(snapshots: list) -> str:
    """
    将快照列表格式化为可注入 prompt 的文本块。

    Args:
        snapshots: 快照列表

    Returns:
        格式化的文本
    """
    if not snapshots:
        return ""

    lines = ["## 【群聊上下文快照】", "以下是最近从群聊中发给你的通知及当时的上下文：", ""]

    for snap in snapshots:
        ts = snap.get("timestamp", "未知时间")
        reason = snap.get("reason", "未知原因")
        message = snap.get("message", "")
        source = snap.get("source_chat_id", "?")

        lines.append(f"### [{ts}] 来源群聊 {source} | 原因: {reason}")
        lines.append(f"**通知内容**: {message}")

        context_msgs = snap.get("context", [])
        if context_msgs:
            lines.append("**当时群聊上下文**:")
            for msg in context_msgs[-5:]:  # 每个快照最多展示5条
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:100]
                time_str = msg.get("time", "")
                if role == "user":
                    lines.append(f"  - [{time_str}] 用户: {content}")
                elif role == "assistant":
                    lines.append(f"  - [{time_str}] Yuki: {content}")
        lines.append("")

    return "\n".join(lines)
