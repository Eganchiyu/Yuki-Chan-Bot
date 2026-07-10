# modules/debug/context_snapshot.py
import copy
import datetime
import re
import threading
import uuid
from collections import deque
from typing import Any, Optional


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"tp-[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(authorization\s*[:=]\s*)[^\s,;}]+", re.IGNORECASE),
    re.compile(r"(napcat[_-]?token\s*[:=]\s*)[^\s,;}]+", re.IGNORECASE),
]


PIPELINE_STAGES = [
    "prepare_message_batch",
    "normalize_incoming_content",
    "prepare_chat_context",
    "decide_reply_action",
    "retrieve_memories",
    "generate_reply",
    "send_reply",
    "finalize_conversation",
]


def utc_now_str() -> str:
    """返回统一格式的快照时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def estimate_tokens(text: str) -> int:
    """第一版使用字符数粗估 token。"""
    if not text:
        return 0
    return max(1, len(str(text)) // 2)


def redact_text(text: str) -> str:
    """脱敏字符串中的 API Key 和 token。"""
    value = str(text)
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(authorization") or pattern.pattern.startswith("(napcat"):
            value = pattern.sub(r"\1<REDACTED>", value)
        else:
            value = pattern.sub("<REDACTED>", value)
    return value


def sanitize_value(value: Any) -> Any:
    """递归脱敏快照内容，避免 Debug 页面暴露密钥。"""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_str = str(key)
            if re.search(r"api[_-]?key|secret|token|authorization|password", key_str, re.IGNORECASE):
                sanitized[key_str] = "<REDACTED>" if item else item
            else:
                sanitized[key_str] = sanitize_value(item)
        return sanitized
    return value


def build_token_estimate(messages: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """按 role 统计字符数与 token 粗估。"""
    by_role = {}
    total_chars = 0
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        content = message.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        char_count = len(content)
        total_chars += char_count
        by_role[role] = by_role.get(role, 0) + estimate_tokens(content)
    return {
        "total_chars": total_chars,
        "estimated_tokens": estimate_tokens("x" * total_chars) if total_chars else 0,
        "by_role": by_role,
    }


def summarize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """生成列表视图所需的轻量摘要。"""
    combined_text = str(snapshot.get("combined_text") or "")
    latency = snapshot.get("latency") or {}
    token_estimate = snapshot.get("token_estimate") or {}
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "chat_id": snapshot.get("chat_id"),
        "mode": snapshot.get("mode"),
        "created_at": snapshot.get("created_at"),
        "updated_at": snapshot.get("updated_at"),
        "stage": snapshot.get("stage"),
        "combined_text_preview": combined_text[:120],
        "message_count": snapshot.get("message_count", 0),
        "should_reply": snapshot.get("should_reply"),
        "built_message_count": len(snapshot.get("built_messages") or []),
        "estimated_tokens": token_estimate.get("estimated_tokens", 0),
        "latency_total": latency.get("total"),
        "errors": snapshot.get("errors") or [],
    }


class ContextSnapshotStore:
    """线程安全的内存快照存储，只保留最近 N 条。"""

    def __init__(self, maxlen: int = 200):
        self._items = deque(maxlen=maxlen)
        self._lock = threading.RLock()

    def put(self, snapshot: dict[str, Any]) -> str:
        """写入新快照并返回 snapshot_id。"""
        now = utc_now_str()
        item = sanitize_value(copy.deepcopy(snapshot or {}))
        snapshot_id = str(item.get("snapshot_id") or uuid.uuid4())
        item["snapshot_id"] = snapshot_id
        item.setdefault("created_at", now)
        item["updated_at"] = now
        item.setdefault("stage", "created")
        item.setdefault("latency", {})
        item.setdefault("errors", [])
        item.setdefault("built_messages", [])
        item["token_estimate"] = build_token_estimate(item.get("built_messages"))
        with self._lock:
            self._items.append(item)
        return snapshot_id

    def update(self, snapshot_id: str, **fields) -> None:
        """按 snapshot_id 更新快照字段，未命中时静默忽略。"""
        if not snapshot_id:
            return
        updates = sanitize_value(copy.deepcopy(fields))
        updates["updated_at"] = utc_now_str()
        with self._lock:
            for item in reversed(self._items):
                if item.get("snapshot_id") == snapshot_id:
                    item.update(updates)
                    if "built_messages" in updates or "token_estimate" not in item:
                        item["token_estimate"] = build_token_estimate(item.get("built_messages"))
                    return

    def latest(self, chat_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """查询全局或指定 chat_id 的最新快照。"""
        cid = str(chat_id) if chat_id else None
        with self._lock:
            for item in reversed(self._items):
                if cid is None or str(item.get("chat_id")) == cid:
                    return copy.deepcopy(item)
        return None

    def list_recent(self, limit: int = 50, chat_id: Optional[str] = None) -> list[dict[str, Any]]:
        """返回最近快照摘要列表。"""
        cid = str(chat_id) if chat_id else None
        limit = max(1, min(int(limit or 50), 200))
        rows = []
        with self._lock:
            for item in reversed(self._items):
                if cid is not None and str(item.get("chat_id")) != cid:
                    continue
                rows.append(summarize_snapshot(item))
                if len(rows) >= limit:
                    break
        return rows

    def get(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """按 snapshot_id 获取完整快照。"""
        with self._lock:
            for item in self._items:
                if item.get("snapshot_id") == snapshot_id:
                    return copy.deepcopy(item)
        return None

    def status(self) -> dict[str, Any]:
        """返回全局状态摘要。"""
        with self._lock:
            items = list(self._items)
        active_chats = sorted({str(item.get("chat_id")) for item in items if item.get("chat_id")})
        latest = items[-1] if items else None
        return {
            "ok": True,
            "generated_at": utc_now_str(),
            "snapshot_count": len(items),
            "active_chats": active_chats,
            "latest_snapshot_id": latest.get("snapshot_id") if latest else None,
            "latest_snapshot_at": latest.get("updated_at") if latest else None,
        }


context_snapshot_store = ContextSnapshotStore()
