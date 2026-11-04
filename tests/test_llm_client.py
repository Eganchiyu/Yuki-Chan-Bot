"""LLM 客户端与重试/主备降级机制 (utils/llm_client.py) 单元测试。"""
from config import cfg
from utils import llm_client
from utils.llm_client import (
    _EMPTY_REPLY_NUDGE,
    _get_fallback_message,
    _message_is_empty,
    _normalize_url,
    _sanitize_payload,
    close_global_session,
    llm_chat_raw,
)


class _RequestRecorder:
    """替换 chat_completion_raw，按脚本逐个返回响应或抛异常。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, base_url, api_key, messages, model, timeout=60.0, **kwargs):
        self.calls.append({"messages": messages, "base_url": base_url})
        result = self.responses.pop(0) if self.responses else {"role": "assistant", "content": ""}
        if isinstance(result, Exception):
            raise result
        return result


async def _run_chat_raw(monkeypatch, responses, retries=3, messages=None, **kwargs):
    recorder = _RequestRecorder(responses)
    monkeypatch.setattr(llm_client, "chat_completion_raw", recorder)
    monkeypatch.setattr(cfg.model, "llm_max_retries", retries)
    monkeypatch.setitem(llm_client._fallback_state, "is_degraded", False)
    message = await llm_chat_raw(messages=messages or [{"role": "user", "content": "在吗"}], **kwargs)
    return message, recorder


def test_normalize_url_and_fallback_messages():
    """URL 规范化与按原因区分的降级提示文案。"""
    assert _normalize_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"
    assert _normalize_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    assert _normalize_url("https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com/v1"
    assert _normalize_url("") == ""
    assert _normalize_url(None) == ""

    net_msg = _get_fallback_message("network")
    assert "暂时连接不上网络" in net_msg and cfg.MASTER_NAME in net_msg
    assert "输出了空字符" in _get_fallback_message("empty")
    assert "暂时连接不上网络" in _get_fallback_message("unknown")


def test_sanitize_payload_rules():
    """payload 清洗：不自动注入 reasoning_effort、VL 模型去 response_format、Gemini 去 penalty。"""
    assert "reasoning_effort" not in _sanitize_payload("o1-preview", {"model": "o1-preview", "messages": []})

    vl_res = _sanitize_payload("qwen-vl-plus", {"model": "qwen-vl-plus", "response_format": {"type": "json_object"}})
    assert "response_format" not in vl_res

    normal_res = _sanitize_payload("deepseek-chat", {"model": "deepseek-chat", "response_format": {"type": "json_object"}})
    assert normal_res["response_format"] == {"type": "json_object"}

    gemini_res = _sanitize_payload(
        "gemini-3.1-flash-lite",
        {"temperature": 1.1, "top_p": 0.9, "frequency_penalty": 0.5, "presence_penalty": 0.4, "max_tokens": 520},
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    assert "frequency_penalty" not in gemini_res and "presence_penalty" not in gemini_res
    assert gemini_res["temperature"] == 1.1 and gemini_res["max_tokens"] == 520

    ds_res = _sanitize_payload("deepseek-v4-flash", {"frequency_penalty": 0.5, "presence_penalty": 0.4})
    assert ds_res["frequency_penalty"] == 0.5 and ds_res["presence_penalty"] == 0.4


async def test_global_session_lifecycle():
    """全局 aiohttp Session 创建与关闭清理。"""
    session = await llm_client._get_global_session()
    assert session is not None and not session.closed
    await close_global_session()
    assert llm_client._global_session is None


def test_message_is_empty_detection():
    """空回复判定支持纯文本、tool_calls 与多模态内容块。"""
    assert _message_is_empty({"role": "assistant", "content": ""}) is True
    assert _message_is_empty({"role": "assistant", "content": "   \n"}) is True
    assert _message_is_empty({"role": "assistant", "content": None}) is True
    assert _message_is_empty({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]}) is False
    assert _message_is_empty({"role": "assistant", "content": [{"type": "text", "text": "hi"}]}) is False
    assert _message_is_empty({"role": "assistant", "content": [{"type": "text", "text": "  "}]}) is True


async def test_empty_reply_retry_and_nudge_injection(monkeypatch):
    """空回复触发立即重试，后续重试末尾注入防空提示，且不污染调用方消息列表。"""
    caller_msgs = [{"role": "user", "content": "在吗"}]
    msg, recorder = await _run_chat_raw(
        monkeypatch,
        [
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "终于有内容"},
        ],
        messages=caller_msgs,
    )
    assert msg["content"] == "终于有内容"
    assert len(recorder.calls) == 3
    assert all(m.get("content") != _EMPTY_REPLY_NUDGE for m in recorder.calls[0]["messages"])
    for call in recorder.calls[1:]:
        assert call["messages"][-1] == {"role": "user", "content": _EMPTY_REPLY_NUDGE}
    assert caller_msgs == [{"role": "user", "content": "在吗"}]


async def test_request_failure_and_exhaustion_fallbacks(monkeypatch):
    """请求失败立即重试、耗尽后按原因返回降级文案，retries=0 时不重试。"""
    # 首轮主+备失败 -> 第二轮备用恢复
    msg, rec = await _run_chat_raw(
        monkeypatch,
        [RuntimeError("主挂"), RuntimeError("备挂"), {"role": "assistant", "content": "恢复了"}],
    )
    assert msg["content"] == "恢复了" and len(rec.calls) == 3

    # 空回复耗尽 (1 + 3 = 4 次)
    msg_empty, rec_empty = await _run_chat_raw(
        monkeypatch, [{"role": "assistant", "content": ""} for _ in range(10)], retries=3
    )
    assert "输出了空字符" in msg_empty["content"] and len(rec_empty.calls) == 4

    # 网络故障耗尽 (首轮主备 2 次 + 后续 3 轮备用 = 5 次)
    msg_net, rec_net = await _run_chat_raw(
        monkeypatch, [RuntimeError("断网") for _ in range(20)], retries=3
    )
    assert "暂时连接不上网络" in msg_net["content"] and len(rec_net.calls) == 5

    # retries=0 禁用重试
    msg_zero, rec_zero = await _run_chat_raw(
        monkeypatch, [{"role": "assistant", "content": ""}], retries=0
    )
    assert "输出了空字符" in msg_zero["content"] and len(rec_zero.calls) == 1


async def test_non_retryable_valid_responses(monkeypatch):
    """正常回复、带 tool_calls 回复、content_filter 拦截、仅含 layout/MEME 标记均不触发额外重试。"""
    for payload in (
        {"role": "assistant", "content": "普通回复"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "poke", "arguments": "{}"}}]},
        {"role": "assistant", "content": "", "_finish_reason": "content_filter"},
        {"role": "assistant", "content": "[layout]盘算[/layout]【MEME:坏笑】"},
    ):
        msg, rec = await _run_chat_raw(monkeypatch, [payload])
        assert msg == payload
        assert len(rec.calls) == 1


async def test_backup_line_degrades_vision_to_text_when_unsupported(monkeypatch):
    """主线路失败切备用时：备用不支持视觉则调用 fallback_messages_factory 降级为纯文本，支持则直接复用。"""
    calls = []

    async def fake_raw(base_url, api_key, messages, model, timeout=60.0, **kwargs):
        calls.append({"base_url": base_url, "messages": messages})
        if len(calls) == 1:
            raise RuntimeError("主线路不可用")
        return {"role": "assistant", "content": "备用线路回复"}

    factory_calls = []

    async def fallback_factory():
        factory_calls.append(True)
        return [{"role": "user", "content": "纯文本降级"}]

    monkeypatch.setattr(llm_client, "chat_completion_raw", fake_raw)
    monkeypatch.setitem(llm_client._fallback_state, "is_degraded", False)

    monkeypatch.setattr(cfg.model, "backup_native_vision_enabled", False)
    msg = await llm_chat_raw(
        messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}],
        fallback_messages_factory=fallback_factory,
    )
    assert msg["content"] == "备用线路回复"
    assert factory_calls == [True]
    assert calls[1]["messages"] == [{"role": "user", "content": "纯文本降级"}]

    calls.clear()
    factory_calls.clear()
    monkeypatch.setitem(llm_client._fallback_state, "is_degraded", False)
    monkeypatch.setattr(cfg.model, "backup_native_vision_enabled", True)
    await llm_chat_raw(
        messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}],
        fallback_messages_factory=fallback_factory,
    )
    assert factory_calls == []
