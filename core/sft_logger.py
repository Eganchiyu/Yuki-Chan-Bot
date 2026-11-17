# core/sft_logger.py
"""全量 SFT 训练轨迹落盘器（只追加 JSONL）。

将每次进入回复生成的完整上下文（built_messages）、本轮工具调用中间消息
（tool_calls / tool 输出）、以及保留了 `<layout>` 与 `[MEME:...]` 的原始回复
（answer_raw）按轮次写为自包含 JSON Block，落盘到 `data/sft/traces_YYYY-MM.jsonl`。

所有落盘字段先做 base64 图片剥离与敏感信息脱敏；I/O 异常仅记日志不阻断主管道。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import mimetypes
import os
import threading
import uuid
from typing import Any, Optional

from config import cfg
from modules.debug.context_snapshot import sanitize_value
from utils.logger import get_logger

logger = get_logger("sft_logger")

POSITIVE_EMOJI_IDS = frozenset({
    "76",     # QQ 赞
    "66",     # QQ 爱心
    "201",    # QQ 点赞
    "319",    # QQ 比心
    "128077", # Unicode 👍
    "10084",  # Unicode ❤️
    "2764",   # Unicode ❤
    "👍",
    "❤️",
    "❤",
    "💖",
    "✨",
})

NEGATIVE_EMOJI_IDS = frozenset({
    "77",     # QQ 踩
    "128078", # Unicode 👎
    "👎",
    "❔",      # 主人疑惑/不认可
    "10068",   # Unicode ❔
    "💦",      # 主人尴尬/出戏/不满意
    "128166",  # Unicode 💦
})


def _extra_emoji_set(env_key: str) -> frozenset[str]:
    raw = os.environ.get(env_key, "")
    if not raw:
        return frozenset()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def classify_emoji_label(emoji_id: Any, is_add: bool = True) -> str:
    """将 NapCat emoji_id 映射为打标分类（perfect / bad / reaction / removed）。"""
    if not is_add:
        return "removed"
    eid = str(emoji_id or "").strip()
    pos = POSITIVE_EMOJI_IDS | _extra_emoji_set("YUKI_SFT_POSITIVE_EMOJIS")
    neg = NEGATIVE_EMOJI_IDS | _extra_emoji_set("YUKI_SFT_NEGATIVE_EMOJIS")
    if eid in pos:
        return "perfect"
    if eid in neg:
        return "bad"
    return "reaction"


def _default_sft_dir() -> str:
    env_dir = os.environ.get("YUKI_SFT_DIR")
    if env_dir:
        return env_dir
    log_dir = os.path.dirname(os.path.abspath(cfg.LOG_FILE))
    return os.path.join(log_dir, "sft")


def strip_media_and_sanitize(value: Any) -> Any:
    """剥离多模态消息中的大体积 base64 图片载荷，并对密钥/token 脱敏。"""
    cleaned = _strip_base64(value)
    return sanitize_value(cleaned)


def _strip_base64(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("data:image/") and len(value) > 256:
            return "<image_omitted>"
        return value
    if isinstance(value, list):
        return [_strip_base64(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_base64(item) for item in value]
    if isinstance(value, dict):
        if value.get("type") == "image_url":
            img_obj = value.get("image_url")
            url = img_obj.get("url", "") if isinstance(img_obj, dict) else ""
            if isinstance(url, str) and (url.startswith("data:image/") or len(url) > 512):
                return {"type": "image_url", "image_url": {"url": "<image_omitted>"}}
        return {str(k): _strip_base64(v) for k, v in value.items()}
    return value


class SFTTraceLogger:
    """线程安全的只追加 SFT 轨迹落盘器。"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir
        self._lock = threading.Lock()
        self._msg_to_turn: dict[str, str] = {}
        self._loaded_index_dir: Optional[str] = None

    def resolve_dir(self) -> str:
        return self.base_dir or _default_sft_dir()

    def trace_path_for(self, now: Optional[datetime.datetime] = None) -> str:
        dt = now or datetime.datetime.now()
        return os.path.join(self.resolve_dir(), f"traces_{dt.strftime('%Y-%m')}.jsonl")

    def msg_index_path(self) -> str:
        return os.path.join(self.resolve_dir(), "msg_index.jsonl")

    def labels_path(self) -> str:
        return os.path.join(self.resolve_dir(), "labels.jsonl")

    def image_dir(self, turn_id: str) -> str:
        safe_id = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in str(turn_id)
        ) or "unknown"
        return os.path.join(self.resolve_dir(), "images", safe_id)

    def archive_images(self, turn_id: str, attachments: list[Any], image_store: Any) -> list[dict[str, Any]]:
        """复制本轮可用的原生图片附件，并返回可随轨迹迁移的元数据。"""
        if not attachments or not image_store:
            return []
        archived = []
        target_dir = self.image_dir(turn_id)
        for position, attachment in enumerate(attachments, 1):
            if not isinstance(attachment, dict):
                continue
            try:
                source = image_store.resolve_attachment_path(attachment)
                if not source or not os.path.isfile(source):
                    continue
                with open(source, "rb") as src:
                    payload = src.read()
                digest = hashlib.sha256(payload).hexdigest()
                ext = os.path.splitext(source)[1].lower() or ".bin"
                if not ext.startswith("."):
                    ext = ".bin"
                os.makedirs(target_dir, exist_ok=True)
                filename = f"{position:03d}-{digest[:16]}{ext}"
                destination = os.path.join(target_dir, filename)
                if not os.path.exists(destination):
                    temp = destination + ".tmp"
                    with open(temp, "wb") as dst:
                        dst.write(payload)
                    os.replace(temp, destination)
                relpath = os.path.relpath(destination, self.resolve_dir())
                archived.append({
                    "path": relpath,
                    "sha256": digest,
                    "bytes": len(payload),
                    "mime": mimetypes.guess_type(source)[0] or "application/octet-stream",
                    "source_index": str(attachment.get("index") or ""),
                })
            except Exception as exc:
                logger.warning(f"[SFT] 归档图片失败: {exc}")
        return archived

    def _ensure_index_loaded_locked(self) -> None:
        cur_dir = self.resolve_dir()
        if self._loaded_index_dir == cur_dir:
            return
        self._msg_to_turn = {}
        self._loaded_index_dir = cur_dir
        path = os.path.join(cur_dir, "msg_index.jsonl")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    mid = item.get("message_id")
                    tid = item.get("turn_id")
                    if mid is not None and tid:
                        self._msg_to_turn[str(mid)] = str(tid)
        except Exception as exc:
            logger.warning(f"[SFT] 加载消息索引失败: {exc}")

    @staticmethod
    def build_record(data: dict[str, Any], now: Optional[datetime.datetime] = None) -> dict[str, Any]:
        dt = now or datetime.datetime.now()
        diaries_raw = data.get("relevant_diaries") or []
        diaries = []
        for item in diaries_raw:
            if isinstance(item, dict):
                diaries.append({
                    "content": sanitize_value(item.get("content", "")),
                    "score": item.get("score"),
                })
            elif item is not None:
                diaries.append({"content": sanitize_value(str(item)), "score": None})

        sent_ids = [str(mid) for mid in (data.get("sent_message_ids") or []) if mid is not None]
        turn_id = str(data.get("turn_id") or uuid.uuid4().hex[:12])

        return {
            "schema_version": 1,
            "turn_id": turn_id,
            "ts": data.get("ts") or dt.strftime("%Y-%m-%d %H:%M:%S"),
            "chat_id": str(data.get("chat_id") or ""),
            "mode": str(data.get("mode") or ""),
            "model": str(data.get("model") or ""),
            "ice_break": bool(data.get("ice_break", False)),
            "outcome": str(data.get("outcome") or "reply"),
            "llm_rounds": int(data.get("llm_rounds") or 0),
            "senders": list(data.get("senders") or []),
            "combined_text": sanitize_value(data.get("combined_text") or ""),
            "relevant_diaries": diaries,
            "input_messages": strip_media_and_sanitize(data.get("input_messages") or []),
            "turn_messages": strip_media_and_sanitize(data.get("turn_messages") or []),
            "tools_used": list(data.get("tools_used") or []),
            "tool_trace": strip_media_and_sanitize(data.get("tool_trace") or []),
            "image_assets": list(data.get("image_assets") or []),
            "answer_raw": sanitize_value(data.get("answer_raw") or ""),
            "answer_text": sanitize_value(data.get("answer_text") or ""),
            "sent_message_ids": sent_ids,
        }

    def record_turn(self, data: dict[str, Any], now: Optional[datetime.datetime] = None) -> Optional[dict[str, Any]]:
        """把单轮完整交互块追加写入当月 JSONL 文件。"""
        dt = now or datetime.datetime.now()
        try:
            record = self.build_record(data, now=dt)
            path = self.trace_path_for(dt)
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
            with self._lock:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
            return record
        except Exception as exc:
            logger.warning(f"[SFT] 写入训练轨迹失败: {exc}")
            return None

    def index_messages(
        self,
        turn_id: str,
        message_ids: list[Any],
        chat_id: str = "",
        now: Optional[datetime.datetime] = None,
    ) -> int:
        """持久化 message_id -> turn_id 映射，供贴表情事件反查整轮轨迹。"""
        if not turn_id or not message_ids:
            return 0
        dt = now or datetime.datetime.now()
        ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        valid_ids = [str(mid).strip() for mid in message_ids if mid is not None and str(mid).strip()]
        if not valid_ids:
            return 0
        try:
            with self._lock:
                self._ensure_index_loaded_locked()
                path = self.msg_index_path()
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    for mid in valid_ids:
                        self._msg_to_turn[mid] = str(turn_id)
                        row = {
                            "message_id": mid,
                            "turn_id": str(turn_id),
                            "chat_id": str(chat_id),
                            "ts": ts,
                        }
                        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            return len(valid_ids)
        except Exception as exc:
            logger.warning(f"[SFT] 写入消息索引失败: {exc}")
            return 0

    def resolve_turn_id(self, message_id: Any) -> Optional[str]:
        """根据 QQ message_id 反查对应的 turn_id；未命中返回 None。"""
        if message_id is None:
            return None
        mid = str(message_id).strip()
        if not mid:
            return None
        with self._lock:
            self._ensure_index_loaded_locked()
            return self._msg_to_turn.get(mid)

    def record_label(
        self,
        *,
        message_id: Any,
        chat_id: Any = "",
        user_id: Any = "",
        emoji_id: Any = "",
        is_add: bool = True,
        label: Optional[str] = None,
        source: str = "emoji_like",
        turn_id: Optional[str] = None,
        now: Optional[datetime.datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """追加写入一条人工打标事件到 labels.jsonl；未关联到 Yuki 轨迹时跳过。"""
        resolved_tid = turn_id or self.resolve_turn_id(message_id)
        if not resolved_tid:
            logger.debug(f"[SFT] 忽略未关联轨迹的打标事件: mid={message_id} source={source}")
            return None
        dt = now or datetime.datetime.now()
        final_label = label or classify_emoji_label(emoji_id, is_add=is_add)
        record = {
            "schema_version": 1,
            "ts": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "turn_id": str(resolved_tid),
            "message_id": str(message_id),
            "chat_id": str(chat_id or ""),
            "user_id": str(user_id or ""),
            "emoji_id": str(emoji_id or ""),
            "is_add": bool(is_add),
            "label": str(final_label),
            "source": str(source),
        }
        try:
            path = self.labels_path()
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self._lock:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
            logger.info(
                f"[SFT] 样本打标已记录: turn_id={resolved_tid} mid={message_id} "
                f"emoji={emoji_id} label={final_label}"
            )
            return record
        except Exception as exc:
            logger.warning(f"[SFT] 写入打标事件失败: {exc}")
            return None


sft_trace_logger = SFTTraceLogger()
