# modules/memory/jargon_matcher.py
"""群黑话零开销机械匹配与上下文注入格式化。

借鉴 MaiBot `jargon_context_matcher`：聊天推理时不做昂贵的向量或 LLM 检索，
直接将当前用户输入与已验证黑话表做归一化子串匹配，按本群权重与频次取 Top K 注入。
"""

import re
from typing import List, Optional, Tuple

from modules.memory.jargon_store import JargonRecord, JargonStore, get_jargon_store

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_match_text(text: str) -> str:
    return _WHITESPACE_RE.sub("", (text or "").strip().lower())


def match_jargons_for_text(
    chat_id: str,
    text: str,
    *,
    store: Optional[JargonStore] = None,
    limit: int = 8,
) -> List[Tuple[str, str]]:
    """从当前输入文本中机械匹配已确认的黑话，返回 [(词条, 释义), ...]。"""
    norm_input = _normalize_match_text(text)
    if not norm_input:
        return []

    target_store = store or get_jargon_store()
    candidates: List[JargonRecord] = target_store.load_verified_jargons(str(chat_id))
    if not candidates:
        return []

    cid = str(chat_id)
    scored: List[Tuple[float, JargonRecord]] = []
    for rec in candidates:
        key = _normalize_match_text(rec.content)
        if not key or key not in norm_input:
            continue
        local_cnt = rec.session_counts.get(cid, 0)
        # 本群出现过的词优先，再叠加总次数与词长（长词更精确）
        score = (1000.0 if local_cnt > 0 else 0.0) + local_cnt * 10.0 + rec.count + len(key) * 0.5
        scored.append((score, rec))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    return [(rec.content, rec.meaning) for _, rec in scored[: max(1, int(limit))]]


def format_jargon_reference(matches: List[Tuple[str, str]]) -> str:
    """将命中的黑话条目格式化为可直接注入上下文的精简提示。"""
    if not matches:
        return ""
    lines = [
        "【群聊黑话/梗参考】（以下释义来自过往群聊语境的猜测，仅作理解参考，不一定绝对准确，请结合当前情景判断）："
    ]
    for content, meaning in matches:
        lines.append(f"- {content}：{meaning}")
    return "\n".join(lines)
