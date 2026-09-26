# core/reply_format.py
"""回复标记格式容错。

模型偶尔会把内部标记的括号写错，例如把 `<layout>盘算</layout>` 写成
`[layout]盘算[/layout]`、`[layout]盘算</layout>`，或把 `[MEME:情绪]` 写成
`【MEME:情绪】`。错格式会让上游按正字面匹配的清理逻辑失效，导致：

1. 布局（内心思考）被当成正文发送出去；
2. 表情包标记被当成普通文本原样发出。

本模块提供统一的「归一化」与「可见文本清洗」入口，供回复生成、发送分段、
说说回复以及历史落盘共用，避免各处正则各写一份、各自漏配。
"""
import re

# ── 布局标记（layout）─────────────────────────────────────────
# 兼容 []、【】、［］、〈〉、<>、＜＞、｛｝、{}、（） 等中英日全半角括号组合。
_LAYOUT_TAG_RE = re.compile(
    r"[\[【［〔〈<＜｛{（(]\s*(/)?\s*layout\s*[\]】］〕〉>＞｝}）)]",
    re.IGNORECASE,
)
_LAYOUT_BLOCK_RE = re.compile(r"<layout>.*?</layout>", re.DOTALL)

# ── 表情包标记（MEME）─────────────────────────────────────────
# 规范形式：[MEME:情绪]；这里同样放开各种括号/冒号变体。
_MEME_TAGGED_RE = re.compile(
    r"[\[【［〔〈<＜｛{（(]\s*MEME\s*[:：]\s*([^\]】］〕〉>＞｝}）)]*?)\s*[\]】］〕〉>＞｝}）)]",
    re.IGNORECASE,
)
# 缺少情绪关键词的空标记（如 [MEME]、【MEME:】），无可检索信息，直接丢弃。
_MEME_BARE_RE = re.compile(
    r"[\[【［〔〈<＜｛{（(]\s*MEME\s*[:：]?\s*[\]】］〕〉>＞｝}）)]",
    re.IGNORECASE,
)

_FINISHED_RE = re.compile(r"\s*FINISHED\s*$", re.IGNORECASE)


def normalize_layout_tags(text: str) -> str:
    """把各种括号变体的 layout 开/闭标签统一成 `<layout>` / `</layout>`。"""
    if not text:
        return text or ""
    return _LAYOUT_TAG_RE.sub(lambda m: "</layout>" if m.group(1) else "<layout>", text)


def strip_layout_markup(text: str) -> str:
    """移除布局块（含括号写错的变体）。

    先把变体统一为规范标签，再成对剥离；若仍残留未闭合的开标签，则从该标签
    起全部视为内部思考丢弃——宁可少发一句，也不让盘算外泄。
    """
    if not text:
        return text or ""
    cleaned = normalize_layout_tags(text)
    cleaned = _LAYOUT_BLOCK_RE.sub("", cleaned)
    if "<layout>" in cleaned:
        cleaned = cleaned.split("<layout>", 1)[0]
    return cleaned.replace("</layout>", "")


def normalize_meme_tags(text: str) -> str:
    """把各种括号/大小写变体的表情包标记统一成 `[MEME:情绪]`，并丢弃空标记。"""
    if not text:
        return text or ""

    def _rewrite(match: re.Match) -> str:
        emotion = (match.group(1) or "").strip()
        return f"[MEME:{emotion}]" if emotion else ""

    cleaned = _MEME_TAGGED_RE.sub(_rewrite, text)
    return _MEME_BARE_RE.sub("", cleaned)


def strip_meme_tags(text: str) -> str:
    """移除所有表情包标记（含变体），用于只想要纯文本的场景。"""
    if not text:
        return text or ""
    cleaned = normalize_meme_tags(text)
    return re.sub(r"\[MEME:[^\]]*\]", "", cleaned)


def normalize_reply_markup(text: str) -> str:
    """回复标记归一化：保留规范 layout，统一 MEME，清掉控制尾标记。

    用于写入 history 前，确保模型下次看到的一直是正确格式，避免被自己的
    错误示例带偏。
    """
    if not text:
        return text or ""
    normalized = normalize_layout_tags(text)
    normalized = normalize_meme_tags(normalized)
    return _FINISHED_RE.sub("", normalized)


def clean_visible_reply(content: str) -> str:
    """清洗可对外发送的回复文本：剥离思考布局、归一化表情包标记、去掉控制尾标记。

    注意这里**保留**规范后的 `[MEME:情绪]`，因为发送阶段还要按它切分检索表情包；
    只想要纯文本时用 `strip_meme_tags()`。
    """
    if not content:
        return ""
    cleaned = normalize_meme_tags(content)
    cleaned = strip_layout_markup(cleaned)
    cleaned = _FINISHED_RE.sub("", cleaned)
    return cleaned.strip()
