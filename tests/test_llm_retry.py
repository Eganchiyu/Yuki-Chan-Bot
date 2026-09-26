# tests/test_llm_retry.py
"""LLM 空回复/请求失败重试机制回归测试。

覆盖需求：
1. 回复为空或请求失败时立即重试；
2. 出现过空回复后，后续重试在末尾追加「请不要输出空字符」；
3. 重试耗尽后按原因返回「输出了空字符」/「暂时连接不上网络」；
4. 工具调用回复不算空，不应触发重试；
5. 内容安全过滤不做无意义重试。
"""
import asyncio
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import cfg
from utils import llm_client
from utils.llm_client import (
    _EMPTY_REPLY_NUDGE,
    _message_is_empty,
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


def _run_with(responses, retries=3, messages=None, **kwargs):
    """在隔离的主备状态与指定重试次数下执行 llm_chat_raw。"""
    recorder = _RequestRecorder(responses)
    original_raw = llm_client.chat_completion_raw
    original_retries = cfg.model.llm_max_retries
    original_degraded = llm_client._fallback_state["is_degraded"]
    llm_client.chat_completion_raw = recorder
    cfg.model.llm_max_retries = retries
    llm_client._fallback_state["is_degraded"] = False
    try:
        message = asyncio.run(
            llm_chat_raw(messages=messages or [{"role": "user", "content": "在吗"}], **kwargs)
        )
    finally:
        llm_client.chat_completion_raw = original_raw
        cfg.model.llm_max_retries = original_retries
        llm_client._fallback_state["is_degraded"] = False
    return message, recorder


# ==================== 空回复判定 ====================

def test_message_is_empty_detects_blank_and_tool_calls():
    assert _message_is_empty({"role": "assistant", "content": ""}) is True
    assert _message_is_empty({"role": "assistant", "content": "   \n"}) is True
    assert _message_is_empty({"role": "assistant", "content": None}) is True
    # 有工具调用即视为有效响应
    assert _message_is_empty(
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]}
    ) is False
    # 多模态块至少一个非空文本
    assert _message_is_empty(
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}
    ) is False
    assert _message_is_empty(
        {"role": "assistant", "content": [{"type": "text", "text": "  "}]}
    ) is True


# ==================== 重试与提示注入 ====================

def test_empty_reply_retries_then_succeeds():
    """首次空回复后立即重试，第二次拿到正常内容。"""
    message, recorder = _run_with([
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "正常回复"},
    ])
    assert message["content"] == "正常回复"
    assert len(recorder.calls) == 2, "应在空回复后立即重试"


def test_nudge_injected_after_empty_reply():
    """出现过空回复后，后续重试末尾追加「请不要输出空字符」。"""
    message, recorder = _run_with([
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "终于有内容"},
    ])
    assert message["content"] == "终于有内容"

    # 第一次请求不带提示
    first = recorder.calls[0]["messages"]
    assert all(m.get("content") != _EMPTY_REPLY_NUDGE for m in first)

    # 之后每次请求都带提示，且为最后一条 user 消息
    for call in recorder.calls[1:]:
        last = call["messages"][-1]
        assert last == {"role": "user", "content": _EMPTY_REPLY_NUDGE}


def test_nudge_does_not_mutate_caller_messages():
    """提示只加在临时副本上，不污染调用方传入的列表。"""
    original = [{"role": "user", "content": "在吗"}]
    _, _ = _run_with(
        [
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "ok"},
        ],
        messages=original,
    )
    assert original == [{"role": "user", "content": "在吗"}]


def test_request_failure_retries_immediately():
    """主备都失败（返回 None）时立即重试，恢复后正常返回。"""
    message, recorder = _run_with([
        RuntimeError("主线路故障"), RuntimeError("备用线路故障"),
        {"role": "assistant", "content": "恢复了"},
    ])
    assert message["content"] == "恢复了"
    # 第 1 轮主+备各一次；进入降级后第 2 轮只打备用，共 3 次请求
    assert len(recorder.calls) == 3, "首次失败后应立即重试"


# ==================== 重试耗尽后的降级文案 ====================

def test_exhausted_empty_replies_returns_empty_notice():
    """3 次重试都为空，返回「输出了空字符」文案。"""
    message, recorder = _run_with(
        [{"role": "assistant", "content": ""} for _ in range(10)],
        retries=3,
    )
    assert "输出了空字符" in message["content"]
    assert len(recorder.calls) == 4, "首次 + 3 次重试"


def test_exhausted_request_failures_returns_network_notice():
    """3 次重试都请求失败，返回「暂时连接不上网络」文案。"""
    message, recorder = _run_with(
        [RuntimeError("连接失败") for _ in range(20)],
        retries=3,
    )
    assert "暂时连接不上网络" in message["content"]
    # 首轮主+备各一次（随后熔断进降级），其余 3 轮只打备用：2 + 3
    assert len(recorder.calls) == 5, "首次 + 3 次重试"


def test_zero_retries_disables_retry():
    """重试次数为 0 时不重试，直接降级。"""
    message, recorder = _run_with(
        [{"role": "assistant", "content": ""}],
        retries=0,
    )
    assert "输出了空字符" in message["content"]
    assert len(recorder.calls) == 1


# ==================== 不应重试的情况 ====================

def test_tool_call_reply_not_treated_as_empty():
    """带工具调用的空文本回复是有效响应，不重试。"""
    tool_message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "function": {"name": "poke", "arguments": "{}"}}],
    }
    message, recorder = _run_with([tool_message])
    assert message["tool_calls"]
    assert len(recorder.calls) == 1


def test_content_filter_returns_without_retry():
    """内容安全过滤不做无意义重试，原样返回。"""
    filtered = {"role": "assistant", "content": "", "_finish_reason": "content_filter"}
    message, recorder = _run_with([filtered])
    assert message["_finish_reason"] == "content_filter"
    assert len(recorder.calls) == 1


def test_normal_reply_no_extra_requests():
    message, recorder = _run_with([{"role": "assistant", "content": "普通回复"}])
    assert message["content"] == "普通回复"
    assert len(recorder.calls) == 1
