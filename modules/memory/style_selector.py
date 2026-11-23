# modules/memory/style_selector.py
"""零延迟群聊情境表达选择器与上下文格式化。

根据当前用户输入，结合分词关键词重叠、群内流行度（count）与注入冷却，
为回复挑选少量贴合语境的群表达习惯参考，使 Yuki 能自然玩群梗而不硬凑。
"""

import re
import time
from typing import List, Optional, Set

from modules.memory.style_store import StyleHabit, StyleStore, get_style_store

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]{2,}")

try:
    import jieba  # type: ignore

    def _tokenize(text: str) -> Set[str]:
        words = {w.strip().lower() for w in jieba.cut(text or "") if len(w.strip()) >= 2}
        return words or set(_TOKEN_RE.findall((text or "").lower()))

except Exception:

    def _tokenize(text: str) -> Set[str]:
        return set(_TOKEN_RE.findall((text or "").lower()))


def select_style_habits(
    chat_id: str,
    context_text: str,
    *,
    store: Optional[StyleStore] = None,
    limit: int = 3,
    cooldown_seconds: float = 180.0,
    now: Optional[float] = None,
) -> List[StyleHabit]:
    """为当前对话挑选最贴合的表达习惯（零 LLM 开销）。"""
    target_store = store or get_style_store()
    candidates = target_store.get_active_habits(str(chat_id), limit=60)
    if not candidates:
        return []

    current_ts = float(now) if now is not None else time.time()
    query_tokens = _tokenize(context_text)

    scored: List[tuple[float, StyleHabit]] = []
    for habit in candidates:
        # 冷却期内不重复推荐同一句，避免变复读机
        if cooldown_seconds > 0 and habit.last_used_at > 0:
            if (current_ts - habit.last_used_at) < cooldown_seconds:
                continue

        habit_tokens = _tokenize(f"{habit.situation} {habit.style}")
        overlap = len(query_tokens & habit_tokens) if (query_tokens and habit_tokens) else 0
        # 语义词重叠优先，其次叠加群内使用频次（上限封顶避免单一梗霸榜）
        score = overlap * 10.0 + min(habit.count, 20) * 0.5
        scored.append((score, habit))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    picked = [habit for _, habit in scored[: max(1, int(limit))]]
    target_store.mark_used([h.id for h in picked if h.id is not None], timestamp=current_ts)
    return picked


def format_style_habits_hint(habits: List[StyleHabit]) -> str:
    """将选中的表达习惯格式化为精简系统参考提示。"""
    if not habits:
        return ""
    lines = [
        "【本群常用表达参考】（群友在以下情境常这样说话；语境自然贴合时可顺手化用，"
        "但必须保持 Yuki 自己的少女口吻，不要生硬套用）："
    ]
    for habit in habits:
        lines.append(f"- 当「{habit.situation}」时：{habit.style}")
    return "\n".join(lines)
