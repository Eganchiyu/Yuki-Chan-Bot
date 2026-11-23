# core/sentence_splitter.py
"""基于轻量 LLM 的语义断句器。

借鉴 MaiBot 的 `llm_sentence_splitter`，将较长的口语回复按自然语义切分为
适合逐条发送的短气泡，同时严格校验原文非空白字符零增删、剥离气泡末尾逗号，
并对代码块、列表、过短文本及异常情况自动回退为原样发送。
"""

import json
import re
from typing import List

from config import cfg
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("sentence_splitter")

_NO_SPLIT_MARKER = "no_split"

_SPLITTER_PROMPT = (
    "请不要思考，快速地把下面的回复进行断句，按自然语义拆成若干条适合逐条发送的消息。\n"
    "要求：\n"
    '1. 只能返回 JSON 字符串数组，例如 ["第一句。", "第二句？"]，不要 Markdown、解释或代码块。\n'
    "2. 只能在原文已有字符之间选择切分位置，不能改写文本、增删或调整顺序。\n"
    "3. 不要把括号、引号、颜文字、URL 或代码从中间拆开。如果是单独的句子，不要在结尾留逗号。\n"
    '4. 如果是完整代码、公式、多行清单或适合整体阅读的文段，不需要拆分，返回 "no_split"。\n'
    '5. 如果是本身比较短、或者表意清晰的句子，不需要拆分，返回 "no_split"。\n\n'
    "原文：\n"
)

# 全角 ASCII 标点及常见中文标点归一，仅用于切分前后的无损校验
_PUNCTUATION_TABLE = str.maketrans(
    {
        **{chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)},
        "\u3000": " ",
        "\u3002": ".",
        "\u3001": ",",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u3010": "[",
        "\u3011": "]",
        "\u300a": "<",
        "\u300b": ">",
    }
)

_CODE_FENCE_RE = re.compile(r"```")
_LIST_LINE_RE = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)、])\s+")
_FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _strip_whitespace(text: str) -> str:
    """去除全部空白字符，并归一中英文标点，用于无损校验。"""
    return "".join(text.split()).translate(_PUNCTUATION_TABLE)


def _should_skip_split(text: str, min_length: int) -> bool:
    """过短、含代码块或多行清单的文本直接跳过切分，避免误拆格式。"""
    stripped = (text or "").strip()
    if not stripped or len(stripped) < max(1, int(min_length)):
        return True
    if _CODE_FENCE_RE.search(stripped):
        return True
    if len(_LIST_LINE_RE.findall(stripped)) >= 2:
        return True
    return False


def _extract_trailing_comma(sentence: str) -> str:
    """去掉独立气泡末尾多余的逗号，保留句号/问号/叹号/波浪号等语气标点。"""
    trimmed = sentence.rstrip("，, \t\r\n")
    if trimmed.strip() and len(trimmed) < len(sentence) and any(
        ch in sentence[len(trimmed):] for ch in ("，", ",")
    ):
        return trimmed
    return sentence


def _map_sentences_to_original(text: str, sentences: List[str]) -> List[str]:
    """按各句的非空白字符数将切分位置精确映射回原文，保留原文标点与格式。"""
    counts = [len(_strip_whitespace(s)) for s in sentences]
    counts = [c for c in counts if c > 0]
    if not counts:
        return [text]

    result: List[str] = []
    start = 0
    consumed = 0
    target = 0
    n = len(text)

    for index, count in enumerate(counts):
        target += count
        if index == len(counts) - 1:
            tail = text[start:].strip()
            if tail:
                result.append(_extract_trailing_comma(tail))
            break
        end = start
        while end < n and consumed < target:
            if not text[end].isspace():
                consumed += 1
            end += 1
        seg = text[start:end].strip()
        if seg:
            result.append(_extract_trailing_comma(seg))
        while end < n and text[end].isspace():
            end += 1
        start = end

    return result or [text]


def parse_split_response(text: str, raw_response: str) -> List[str]:
    """解析并校验 LLM 返回的断句 JSON；不合法或发生改写时回退原文。"""
    payload = _FENCED_JSON_RE.sub("", (raw_response or "").strip()).strip()
    if not payload or payload.strip('"').strip() == _NO_SPLIT_MARKER:
        return [text]

    try:
        parsed = json.loads(payload)
    except Exception:
        return [text]

    if parsed == [_NO_SPLIT_MARKER] or not isinstance(parsed, list) or not parsed:
        return [text]
    if not all(isinstance(item, str) for item in parsed):
        return [text]

    if _strip_whitespace("".join(parsed)) != _strip_whitespace(text):
        logger.debug("[SentenceSplitter] 断句结果与原文字符不一致，回退原文本")
        return [text]

    return _map_sentences_to_original(text, parsed)


async def split_text_with_llm(
    text: str,
    *,
    model: str | None = None,
    min_length: int | None = None,
) -> List[str]:
    """将回复文本按语义拆分为多条适合逐条发送的气泡；任何异常安全回退原文。"""
    if not text or not text.strip():
        return []

    threshold = (
        int(min_length)
        if min_length is not None
        else int(getattr(cfg, "SENTENCE_SPLIT_MIN_LENGTH", 18))
    )
    if _should_skip_split(text, threshold):
        return [text]

    target_model = model or getattr(cfg, "BACKUP_MODEL", "") or getattr(cfg, "LLM_MODEL", "")
    try:
        raw_resp = await llm_chat(
            messages=[{"role": "user", "content": _SPLITTER_PROMPT + text}],
            model=target_model,
            temperature=0.1,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.debug(f"[SentenceSplitter] LLM 断句请求失败，回退原文: {exc}")
        return [text]

    if not raw_resp or raw_resp == "Filtered":
        return [text]

    segments = parse_split_response(text, raw_resp)
    return [seg for seg in segments if seg and seg.strip()] or [text]
