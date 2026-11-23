# modules/memory/jargon_miner.py
"""群黑话（Jargon）后台抽取与三步防幻觉推断器。

借鉴 MaiBot `JargonMiner` 设计：
1. 仅从群友（user）发言中抽取候选黑话/缩写/圈内梗，不从机器人自己发言提取；
2. 采用阶梯阈值 [4, 8, 25, 100] 触发推断，避免高频重复调用 LLM；
3. 三步防幻觉对比：
   - Step 1 (with_context): 结合群聊证据片段推断含义；
   - Step 2 (content_only): 脱离上下文仅看词本身猜常见含义；
   - Step 3 (compare): 对比两者是否相同；若相同说明是普通白话，标记过滤；
     若语义明显偏移，则确认为群黑话并保存释义。
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from config import cfg
from modules.memory.jargon_store import JargonRecord, JargonStore, get_jargon_store
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("jargon_miner")

JARGON_INFERENCE_THRESHOLDS = (4, 8, 25, 100)
_MAX_INFER_PER_ROUND = 3
_FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_chat_locks: Dict[str, asyncio.Lock] = {}

_EXTRACT_PROMPT = """请从下面这段群聊用户的真实发言中提取“可能是黑话”的候选项（黑话/俚语/圈内缩写/口头禅）。

提取规则：
- 必须为对话中真实出现过的短词或短语（长度建议 2-10 个字符）
- 必须是脱离当前圈子不容易理解、或带有特定语境梗的词语
- 不要选择含义完全清晰的普通日常词汇
- 排除：人名、@、纯数字、纯标点、常规助词
- 最多提取 15 个，没有则返回空数组 []

输出要求：
仅输出 JSON 数组，每个元素格式如下（idx 为对应发言编号）：
[{{"content": "词条", "idx": 0}}]

聊天记录：
{dialogue_block}
"""

_INFER_WITH_CONTEXT_PROMPT = """**词条内容**：{content}
**词条出现的群聊上下文**：
{evidence_text}

请根据以上群聊上下文，推断“{content}”在这个圈子里的含义。
- 如果上下文信息不足以推断含义，请将 no_info 设为 true。
{prev_hint}
仅输出 JSON 对象：
{{"meaning": "详细含义说明（使用场景与解释）", "no_info": false}}"""

_INFER_CONTENT_ONLY_PROMPT = """**词条内容**：{content}

请仅根据这个词条本身的字面或常见网络用语含义，推断其含义（不要臆测特定小圈子背景）。
仅输出 JSON 对象：
{{"meaning": "常见含义说明"}}"""

_COMPARE_INFERENCE_PROMPT = """**推断结果1（基于群聊上下文）**：
{inference1}

**推断结果2（仅基于词条字面）**：
{inference2}

请比较这两个推断结果，判断它们的核心含义是否相同或基本一致。
仅输出 JSON 对象：
{{"is_similar": true, "reason": "简短理由"}}"""


def _get_lock(chat_id: str) -> asyncio.Lock:
    cid = str(chat_id)
    if cid not in _chat_locks:
        _chat_locks[cid] = asyncio.Lock()
    return _chat_locks[cid]


def _parse_json_payload(raw: str) -> Any:
    cleaned = _FENCED_JSON_RE.sub("", (raw or "").strip()).strip()
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        # 兜底尝试截取首个 [] 或 {}
        for open_ch, close_ch in (("[", "]"), ("{", "}")):
            start = cleaned.find(open_ch)
            end = cleaned.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except Exception:
                    continue
        return None


def should_infer_jargon(record: JargonRecord) -> bool:
    """判断是否达到下一个阶梯推断阈值。"""
    if record.is_complete:
        return False
    if record.count > JARGON_INFERENCE_THRESHOLDS[-1] and record.last_inference_count >= JARGON_INFERENCE_THRESHOLDS[-1]:
        return False
    for threshold in JARGON_INFERENCE_THRESHOLDS:
        if record.last_inference_count < threshold <= record.count:
            return True
    return False


def _build_user_lines(dialogue_msgs: List[Dict[str, Any]]) -> List[str]:
    """仅保留真实 user 消息文本用于黑话抽取与证据截取。"""
    lines: List[str] = []
    for msg in dialogue_msgs or []:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(p.get("text") or "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        text = " ".join(str(content or "").split())
        if text:
            lines.append(text)
    return lines


def _slice_evidence(user_lines: List[str], idx: int, window: int = 2) -> str:
    lo = max(0, idx - window)
    hi = min(len(user_lines), idx + window + 1)
    return "\n".join(user_lines[lo:hi])


async def _call_fast_llm(prompt: str, *, model: Optional[str] = None) -> str:
    target_model = model or getattr(cfg, "BACKUP_MODEL", "") or getattr(cfg, "LLM_MODEL", "")
    return await llm_chat(
        messages=[{"role": "user", "content": prompt}],
        model=target_model,
        temperature=0.2,
        max_tokens=1024,
    )


async def extract_candidates_from_dialogue(
    chat_id: str,
    dialogue_msgs: List[Dict[str, Any]],
    *,
    store: Optional[JargonStore] = None,
    model: Optional[str] = None,
) -> List[JargonRecord]:
    """从对话 user 消息中抽取候选黑话并写入存储，返回本次更新的记录。"""
    user_lines = _build_user_lines(dialogue_msgs)
    if len(user_lines) < 3:
        return []

    dialogue_block = "\n".join(f"[{i}] {line[:200]}" for i, line in enumerate(user_lines))
    prompt = _EXTRACT_PROMPT.format(dialogue_block=dialogue_block)

    try:
        raw_resp = await _call_fast_llm(prompt, model=model)
    except Exception as exc:
        logger.debug(f"[Jargon] 候选抽取 LLM 请求失败: {exc}")
        return []

    parsed = _parse_json_payload(raw_resp)
    if not isinstance(parsed, list):
        return []

    candidates: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for item in parsed[:15]:
        if not isinstance(item, dict):
            continue
        word = " ".join(str(item.get("content") or "").strip().split())
        if not word or len(word) < 2 or len(word) > 16:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)

        raw_idx = item.get("idx", 0)
        try:
            idx = int(raw_idx)
        except Exception:
            idx = 0
        idx = max(0, min(len(user_lines) - 1, idx))
        candidates.append((word, _slice_evidence(user_lines, idx)))

    if not candidates:
        return []

    target_store = store or get_jargon_store()
    return await asyncio.to_thread(target_store.record_candidates, str(chat_id), candidates)


async def infer_jargon_meaning(
    record: JargonRecord,
    *,
    store: Optional[JargonStore] = None,
    model: Optional[str] = None,
) -> Optional[bool]:
    """执行三步防幻觉黑话推断并更新存储；返回最终 is_jargon 状态。"""
    if not record.evidence:
        return record.is_jargon

    target_store = store or get_jargon_store()
    evidence_text = "\n---\n".join(record.evidence[-6:])
    prev_hint = (
        f"- 上一次推断含义供参考：{record.meaning}\n" if record.meaning.strip() else ""
    )

    # Step 1: 结合群聊上下文推断
    p1 = _INFER_WITH_CONTEXT_PROMPT.format(
        content=record.content,
        evidence_text=evidence_text,
        prev_hint=prev_hint,
    )
    inf1 = _parse_json_payload(await _call_fast_llm(p1, model=model))
    if not isinstance(inf1, dict):
        return None

    meaning1 = str(inf1.get("meaning") or "").strip()
    if inf1.get("no_info") or not meaning1:
        await asyncio.to_thread(
            target_store.update_inference_result,
            record.content,
            is_jargon=record.is_jargon,
            meaning=record.meaning,
            last_inference_count=record.count,
            is_complete=record.is_complete,
        )
        return record.is_jargon

    # Step 2: 脱离上下文仅凭词面猜常见义
    p2 = _INFER_CONTENT_ONLY_PROMPT.format(content=record.content)
    inf2 = _parse_json_payload(await _call_fast_llm(p2, model=model))
    if not isinstance(inf2, dict) or not str(inf2.get("meaning") or "").strip():
        return None

    # Step 3: 对比两者是否一致（一致 = 普通白话；不一致 = 真黑话）
    p3 = _COMPARE_INFERENCE_PROMPT.format(
        inference1=json.dumps(inf1, ensure_ascii=False),
        inference2=json.dumps(inf2, ensure_ascii=False),
    )
    cmp_res = _parse_json_payload(await _call_fast_llm(p3, model=model))
    if not isinstance(cmp_res, dict) or "is_similar" not in cmp_res:
        return None

    is_similar = bool(cmp_res.get("is_similar"))
    is_jargon = not is_similar
    is_complete = record.count >= JARGON_INFERENCE_THRESHOLDS[-1]
    final_meaning = meaning1 if is_jargon else ""

    await asyncio.to_thread(
        target_store.update_inference_result,
        record.content,
        is_jargon=is_jargon,
        meaning=final_meaning,
        last_inference_count=record.count,
        is_complete=is_complete,
    )
    logger.info(
        f"[Jargon] 推断完成: 「{record.content}」 count={record.count} "
        f"-> is_jargon={is_jargon}"
    )
    return is_jargon


async def mine_jargons_background(
    chat_id: str,
    dialogue_msgs: List[Dict[str, Any]],
    *,
    store: Optional[JargonStore] = None,
) -> None:
    """后台异步挖掘入口：在写日记等旁路安全执行，异常不外抛。"""
    cid = str(chat_id)
    lock = _get_lock(cid)
    if lock.locked():
        return
    async with lock:
        try:
            target_store = store or get_jargon_store()
            records = await extract_candidates_from_dialogue(
                cid, dialogue_msgs, store=target_store
            )
            pending = [r for r in records if should_infer_jargon(r)]
            for rec in pending[:_MAX_INFER_PER_ROUND]:
                await infer_jargon_meaning(rec, store=target_store)
        except Exception as exc:
            logger.debug(f"[Jargon] 后台挖掘异常 {cid}: {exc}")
