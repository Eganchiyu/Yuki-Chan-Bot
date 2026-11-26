# modules/memory/style_learner.py
"""群聊情境表达习惯后台提取器。

借鉴 MaiBot `learn_style.prompt`：从群友（user）真实发言中提取
「在什么情境下 -> 用什么口癖/梗/表达方式」，过滤 Bot 自身发言与人名，
挂载于写日记旁路异步执行。
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from config import cfg
from modules.memory.style_store import StyleHabit, StyleStore, get_style_store
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("style_learner")

_FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_chat_locks: Dict[str, asyncio.Lock] = {}

_LEARN_STYLE_PROMPT = """请从下面这段群聊用户的真实发言中提取语言风格、常用梗和说话方式。
规则：
1. 只从群友的真实文字发言中提取，不要涉及具体人名和敏感内容
2. 重点捕捉群里反复出现的梗、口头禅、语气词或特定句式
3. 每条总结为“在什么情境下 -> 用什么表达方式”
4. 最多提取 5 条，没有明显特色表达则返回空数组 []

输出格式（仅输出 JSON 数组）：
[
  {{"situation": "对某件事表示十分惊叹", "style": "使用 我嘞个xxxx"}},
  {{"situation": "表示调侃或敷衍赞同", "style": "使用 对对对"}}
]

字段限制：
- situation：简短情境概括（不超过 20 字）
- style：对应的常用表达、黑话或句式（不超过 24 字）

聊天记录：
{dialogue_block}
"""


def _get_lock(chat_id: str) -> asyncio.Lock:
    cid = str(chat_id)
    if cid not in _chat_locks:
        _chat_locks[cid] = asyncio.Lock()
    return _chat_locks[cid]


def _parse_json_list(raw: str) -> List[Dict[str, Any]]:
    cleaned = _FENCED_JSON_RE.sub("", (raw or "").strip()).strip()
    if not cleaned:
        return []
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []


def _extract_user_lines(dialogue_msgs: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for msg in dialogue_msgs or []:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(p.get("text") or "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        text = " ".join(str(content or "").split())
        if text:
            lines.append(text)
    return lines


async def _call_style_llm(prompt: str, *, model: Optional[str] = None) -> str:
    target_model = model or None
    return await llm_chat(
        messages=[{"role": "user", "content": prompt}],
        model=target_model,
        temperature=0.2,
        max_tokens=512,
    )


async def extract_styles_from_dialogue(
    chat_id: str,
    dialogue_msgs: List[Dict[str, Any]],
    *,
    store: Optional[StyleStore] = None,
    model: Optional[str] = None,
) -> List[StyleHabit]:
    """从对话 user 消息中抽取情境表达习惯并写入存储。"""
    user_lines = _extract_user_lines(dialogue_msgs)
    if len(user_lines) < 4:
        return []

    dialogue_block = "\n".join(line[:180] for line in user_lines)
    prompt = _LEARN_STYLE_PROMPT.format(dialogue_block=dialogue_block)

    try:
        raw_resp = await _call_style_llm(prompt, model=model)
    except Exception as exc:
        logger.debug(f"[StyleLearner] 抽取请求失败: {exc}")
        return []

    items = _parse_json_list(raw_resp)
    pairs: List[Tuple[str, str]] = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        sit = " ".join(str(item.get("situation") or "").strip().split())
        sty = " ".join(str(item.get("style") or "").strip().split())
        if 2 <= len(sit) <= 30 and 2 <= len(sty) <= 36:
            pairs.append((sit, sty))

    if not pairs:
        return []

    target_store = store or get_style_store()
    return await asyncio.to_thread(target_store.record_habits, str(chat_id), pairs)


async def learn_styles_background(
    chat_id: str,
    dialogue_msgs: List[Dict[str, Any]],
    *,
    store: Optional[StyleStore] = None,
) -> None:
    """写日记旁路异步学习表达习惯，异常不外抛。"""
    cid = str(chat_id)
    lock = _get_lock(cid)
    if lock.locked():
        return
    async with lock:
        try:
            saved = await extract_styles_from_dialogue(cid, dialogue_msgs, store=store)
            if saved:
                logger.info(f"[StyleLearner] [{cid}] 学习/强化 {len(saved)} 条群表达习惯")
        except Exception as exc:
            logger.debug(f"[StyleLearner] 后台学习异常 {cid}: {exc}")
