# core/sft_logger.py
"""全量 SFT 训练轨迹落盘器（只追加 JSONL）。

将每次进入回复生成的完整上下文（built_messages）、本轮工具调用中间消息
（tool_calls / tool 输出）、以及保留了 `<layout>` 与 `[MEME:...]` 的原始回复
（answer_raw）按轮次写为自包含 JSON Block，落盘到 `data/sft/traces_YYYY-MM.jsonl`。

所有落盘字段先做 base64 图片剥离与敏感信息脱敏；I/O 异常仅记日志不阻断主管道。
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from typing import Any, Optional

from config import cfg
from modules.debug.context_snapshot import sanitize_value
from utils.logger import get_logger

logger = get_logger("sft_logger")


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

    def resolve_dir(self) -> str:
        return self.base_dir or _default_sft_dir()

    def trace_path_for(self, now: Optional[datetime.datetime] = None) -> str:
        dt = now or datetime.datetime.now()
        return os.path.join(self.resolve_dir(), f"traces_{dt.strftime('%Y-%m')}.jsonl")

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


sft_trace_logger = SFTTraceLogger()
