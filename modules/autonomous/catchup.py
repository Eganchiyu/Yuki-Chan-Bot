# modules/autonomous/catchup.py
"""回群补台：把「你独处期间群里发生了什么」整理成一条系统注入消息。

按量自动切（docs/autonomous-sandbox-plan.md §4.2）：
- ≤ catchup_summarize_threshold 条：代码直拼，零 LLM；
- 更多：第三方 LLM 压成 ≤200 字（失败回落直拼最近 20 条）。
"""
from __future__ import annotations

import datetime

from config import cfg
from modules.autonomous.storage import group_name_cache
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("autonomous.catchup")

DIRECT_MAX_MESSAGES = 12
DIGEST_MAX_CHARS = 200
FALLBACK_MAX_MESSAGES = 20


def _fmt_time(message: dict) -> str:
    raw = message.get("time") or message.get("timestamp")
    if isinstance(raw, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(float(raw)).strftime("%H:%M")
        except (OSError, ValueError):
            return "--:--"
    text = str(raw or "")
    if len(text) >= 16 and "年" in text:
        return text[11:16]
    if len(text) >= 5 and ":" in text:
        return text[-5:]
    return "--:--"


def _is_real_message(message: dict) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("is_catchup") or message.get("is_reply_watch_event") or message.get("is_timer_event"):
        return False
    if message.get("is_maid_report"):
        return False
    source = str(message.get("source") or "")
    if source.startswith("yuki."):
        return False
    return bool(str(message.get("content") or "").strip())


def _line(message: dict) -> str:
    name = str(message.get("name") or message.get("user_id") or "某人").strip()
    content = " ".join(str(message.get("content") or "").split())
    if len(content) > 120:
        content = content[:119] + "…"
    return f"{_fmt_time(message)} {name}: {content}"


def _direct_digest(messages: list[dict], limit: int | None = None) -> str:
    rows = messages[-limit:] if limit else messages
    head = "（更早的消息省略）\n" if limit and len(messages) > limit else ""
    return head + "\n".join(_line(m) for m in rows)


async def build_digest(messages: list[dict], *, chat_id="") -> str:
    """把缺席期间的消息压成摘要，返回可直接注入的文本。"""
    if not messages:
        return ""
    limit = max(1, int(cfg.autonomous.catchup_max_messages))
    omitted = max(0, len(messages) - limit)
    trimmed = messages[-limit:]

    threshold = max(1, int(cfg.autonomous.catchup_summarize_threshold))
    if len(trimmed) <= threshold:
        head = f"（更早还有 {omitted} 条消息）\n" if omitted else ""
        return head + _direct_digest(trimmed)

    prompt_lines = "\n".join(_line(m) for m in trimmed)
    try:
        summary = await llm_chat(
            messages=[
                {"role": "system", "content": (
                    "把下面这段群聊记录压缩成不超过 200 字的客观摘要："
                    "只客观列出聊了什么话题、谁说了什么关键信息，按时间顺序；"
                    "不要角色扮演，不要评价，不要添加原文没有的内容。"
                )},
                {"role": "user", "content": prompt_lines[:6000]},
            ],
            model=(cfg.autonomous.digest_model or None),
            temperature=0.3,
            max_tokens=400,
        )
    except Exception as exc:
        logger.warning(f"[Catchup] 摘要模型失败，回落直拼: {exc}")
        summary = ""

    summary = " ".join(str(summary or "").split())
    if not summary:
        return _direct_digest(trimmed, limit=FALLBACK_MAX_MESSAGES)
    if len(summary) > DIGEST_MAX_CHARS:
        summary = summary[: DIGEST_MAX_CHARS - 1] + "…"
    head = f"（共 {len(trimmed)} 条消息" + (f"，更早还有 {omitted} 条" if omitted else "") + "）\n"
    return head + summary


async def build_catchup_event(pipeline, chat_id) -> dict | None:
    """从缓冲区取出冻结期间的消息并生成补台事件；没有新消息返回 None。"""
    cid = str(chat_id)
    try:
        buffer = pipeline.yuki.pop_buffer(cid) or []
    except Exception:
        buffer = []
    real = [m for m in buffer if _is_real_message(m)]
    if not real:
        return None

    group_label = group_name_cache.name(cid)
    digest = await build_digest(real, chat_id=cid)
    if not digest:
        return None

    content = (
        f"【你刚才在「{group_label}」的独处时间里，群里发生了什么】\n"
        f"{digest}\n"
        "（这些是你不在的时候发生的事，可以自然接话，也可以只挑一句感兴趣的问。）"
    )
    logger.info(f"[Catchup] {cid} 补台 {len(real)} 条消息（{len(digest)} 字）")
    return {
        "name": "系统",
        "content": content,
        "raw_text": "",
        "source": "yuki.catchup",
        "is_catchup": True,
        "tags": ["catchup"],
    }
