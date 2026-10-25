# tests/test_reply_subscription.py
"""回复订阅（subscribe_reply）行为测试。"""
import asyncio
import os
import sys
from collections import defaultdict
from types import SimpleNamespace

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core import reply_watch
from core.reply_watch import (
    cancel_watch,
    get_watch,
    is_human_incoming,
    reset_reply_watch,
    resolve_watch,
    start_watch,
)
from core.session_pipeline import SessionPipeline
from core.toolchain import ToolContext, ToolRuntime


def _patch_min_timeout(value=0.02):
    """把 30 秒下限压到毫秒级，方便测试真实计时行为。"""
    reply_watch.MIN_TIMEOUT_SECONDS = value


def _restore_min_timeout():
    reply_watch.MIN_TIMEOUT_SECONDS = 30.0


def _build_context(callback):
    runtime = ToolRuntime(sender=SimpleNamespace(), yuki_state=SimpleNamespace())
    return ToolContext(
        chat_id="test_chat",
        mode="group",
        session=[],
        combined_text="测试订阅",
        runtime=runtime,
        metadata={"process_callback": callback},
    )


def test_subscribe_fires_one_followup():
    async def run():
        _patch_min_timeout()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append({"chat_id": chat_id, "mode": mode, **kwargs})

        try:
            watch = start_watch("c1", "group", callback, timeout_seconds=0.001, max_followups=1,
                                expectation="等回答")
            assert watch["timeout_seconds"] == 0.02
            assert watch["status"] == "waiting"

            await asyncio.sleep(0.06)

            assert len(calls) == 1
            assert calls[0]["chat_id"] == "c1"
            assert calls[0]["force_reply"] is True
            assert calls[0]["debounce_flag"] is False
            event = calls[0]["message_obj"]
            assert event["is_reply_watch_event"] is True
            assert "等待超时" in event["content"]
            # 次数用尽后订阅结束
            assert get_watch("c1") is None
        finally:
            reset_reply_watch()
            _restore_min_timeout()

    asyncio.run(run())


def test_human_message_resolves_watch():
    async def run():
        _patch_min_timeout()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            start_watch("c2", "group", callback, timeout_seconds=0.001)
            resolved = resolve_watch("c2", "human_message")
            assert resolved is not None
            assert resolved["status"] == "human_message"

            await asyncio.sleep(0.08)
            assert calls == []
            assert get_watch("c2") is None
        finally:
            reset_reply_watch()
            _restore_min_timeout()

    asyncio.run(run())


def test_followups_capped_at_two():
    async def run():
        _patch_min_timeout()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            start_watch("c3", "group", callback, timeout_seconds=0.001, max_followups=99)
            assert get_watch("c3")["max_followups"] == 2

            await asyncio.sleep(0.15)
            assert len(calls) == 2
            assert "第 1/2 次" in calls[0]["message_obj"]["content"]
            assert "第 2/2 次" in calls[1]["message_obj"]["content"]
            assert get_watch("c3") is None
        finally:
            reset_reply_watch()
            _restore_min_timeout()

    asyncio.run(run())


def test_timeout_lower_bound_is_30s():
    async def run():
        reset_reply_watch()

        async def callback(chat_id, mode, **kwargs):
            return None

        try:
            watch = start_watch("c4", "group", callback, timeout_seconds=5, max_followups=1)
            assert watch["timeout_seconds"] == 30
        finally:
            reset_reply_watch()

    asyncio.run(run())


def test_cancel_watch_stops_followup():
    async def run():
        _patch_min_timeout()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            start_watch("c5", "group", callback, timeout_seconds=0.001)
            cancelled = cancel_watch("c5", "tool_cancel")
            assert cancelled["status"] == "tool_cancel"
            await asyncio.sleep(0.08)
            assert calls == []
        finally:
            reset_reply_watch()
            _restore_min_timeout()

    asyncio.run(run())


def test_subscribe_tool_requires_callback_and_validates_timeout():
    async def run():
        from core.tools import subscribe_reply_tool

        reset_reply_watch()
        try:
            context = _build_context(None)
            result = await subscribe_reply_tool(context, timeout_seconds=5)
            assert result.success is False
            assert result.error == "callback_unavailable"

            calls = []

            async def callback(chat_id, mode, **kwargs):
                calls.append(kwargs)

            context = _build_context(callback)
            result = await subscribe_reply_tool(context, timeout_seconds=10, expectation="等回复")
            assert result.success is True
            assert result.data["timeout_seconds"] == 30
            assert "30 秒" in result.content

            cancel_result = await subscribe_reply_tool(context, action="cancel")
            assert cancel_result.success is True
            assert cancel_result.data["status"] == "tool_cancel"

            await asyncio.sleep(0.05)
            assert calls == []
        finally:
            reset_reply_watch()

    asyncio.run(run())


def test_is_human_incoming_filters_bots_and_events():
    assert is_human_incoming({"source": "napcat.group", "is_bot": False}) is True
    assert is_human_incoming({"source": "napcat.private", "is_bot": False}) is True
    assert is_human_incoming({"source": "napcat.group", "is_bot": True}) is False
    assert is_human_incoming({"source": "yuki.reply_watch", "is_reply_watch_event": True}) is False
    assert is_human_incoming({"content": "【定时任务到点】x", "is_timer_event": True}) is False
    assert is_human_incoming(None) is False


def test_pipeline_resolves_watch_on_human_message():
    async def run():
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        async def noop_run_once(*args, **kwargs):
            return None

        pipeline = SessionPipeline(
            {
                "sender": SimpleNamespace(),
                "meme_processor": None,
                "yuki": SimpleNamespace(message_buffer=defaultdict(list)),
                "history_manager": SimpleNamespace(),
                "memory_rag": SimpleNamespace(),
                "engine": SimpleNamespace(),
            },
            {},
        )
        pipeline.run_once = noop_run_once
        try:
            start_watch("c6", "group", callback, timeout_seconds=0.001, max_followups=1)
            await pipeline.enqueue_message(
                "c6", "group", message_obj={"content": "我回来啦", "source": "napcat.group"}, debounce_flag=False
            )
            assert get_watch("c6") is None
            await asyncio.sleep(0.02)
            assert calls == []
        finally:
            reset_reply_watch()

    asyncio.run(run())
