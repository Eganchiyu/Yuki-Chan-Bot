# tests/test_sentence_splitter.py
"""智能语义断句器单元测试。"""

import asyncio
from unittest.mock import AsyncMock, patch

from core.sentence_splitter import parse_split_response, split_text_with_llm


def test_parse_split_response_strips_trailing_commas_and_preserves_text():
    original = "今天天气真好啊，我们去吃火锅吧？顺便买杯奶茶！"
    raw = '["今天天气真好啊，", "我们去吃火锅吧？", "顺便买杯奶茶！"]'
    parts = parse_split_response(original, raw)
    assert parts == ["今天天气真好啊", "我们去吃火锅吧？", "顺便买杯奶茶！"]


def test_parse_split_response_no_split_marker():
    original = "这是一句不需要拆分的完整回复。"
    assert parse_split_response(original, '"no_split"') == [original]
    assert parse_split_response(original, '["no_split"]') == [original]


def test_parse_split_response_rejects_rewritten_text():
    original = "刚才那个问题我已经帮你查清楚了，没问题的。"
    # 模型擅自改了字，应该安全回退原文
    raw = '["刚才那个问题我查清楚了，", "完全没问题的。"]'
    assert parse_split_response(original, raw) == [original]


def test_split_text_with_llm_skips_short_and_code_blocks():
    with patch("core.sentence_splitter.llm_chat", new_callable=AsyncMock) as mock_llm:
        assert asyncio.run(split_text_with_llm("太短了", min_length=18)) == ["太短了"]
        code_text = "给你写好了：\n```python\nprint('hi')\nprint('ok')\n```"
        assert asyncio.run(split_text_with_llm(code_text, min_length=5)) == [code_text]
        mock_llm.assert_not_awaited()


def test_split_text_with_llm_falls_back_on_error():
    text = "第一句话其实挺长的，第二句话也差不多长，应该拆开。"
    with patch("core.sentence_splitter.llm_chat", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        assert asyncio.run(split_text_with_llm(text, min_length=10)) == [text]


def test_split_text_with_llm_splits_normal_reply():
    text = "我刚刚看了一眼群消息，好像大家都在讨论晚饭吃什么。"
    mock_resp = '["我刚刚看了一眼群消息，", "好像大家都在讨论晚饭吃什么。"]'
    with patch("core.sentence_splitter.llm_chat", new_callable=AsyncMock, return_value=mock_resp):
        parts = asyncio.run(split_text_with_llm(text, min_length=10))
    assert parts == ["我刚刚看了一眼群消息", "好像大家都在讨论晚饭吃什么。"]
