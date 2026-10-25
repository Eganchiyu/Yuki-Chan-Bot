# tests/test_reply_subscription.py
"""自动回复订阅（reply_watch）行为测试。"""
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
    auto_subscribe,
    estimate_wait_seconds,
    expectation_score,
    get_watch,
    hit_trigger_word,
    is_human_incoming,
    is_question,
    reset_reply_watch,
    resolve,
    subscribe,
)
from core.session_pipeline import SessionPipeline


def _patch(min_timeout=0.02, threshold=0.0, jitter=0.0):
    reply_watch.MIN_TIMEOUT_SECONDS = min_timeout
    reply_watch.SCORE_THRESHOLD = threshold
    reply_watch.SCORE_JITTER = jitter


def _restore():
    reply_watch.MIN_TIMEOUT_SECONDS = 30.0
    reply_watch.SCORE_THRESHOLD = 0.55
    reply_watch.SCORE_JITTER = 0.15


def _build_pipeline(engine=None):
    yuki = SimpleNamespace(
        message_buffer=defaultdict(list),
        energy={},
        group_activity={},
        user_mapping=SimpleNamespace(tick=lambda chat_id: None),
    )
    pipeline = SessionPipeline(
        {
            "sender": SimpleNamespace(),
            "meme_processor": None,
            "yuki": yuki,
            "history_manager": SimpleNamespace(),
            "memory_rag": SimpleNamespace(),
            "engine": engine or SimpleNamespace(),
        },
        {},
    )

    async def noop_run_once(*args, **kwargs):
        return None

    pipeline.run_once = noop_run_once
    return pipeline


def test_question_and_trigger_detection():
    assert is_question("主人今晚回来吗？") is True
    assert is_question("在不在?") is True
    assert is_question("哼，人家先睡了[MEME:生气]") is False
    assert hit_trigger_word("你在吗") is True
    assert hit_trigger_word("好的呀") is False
    # 问句单独就能拿到较高分，普通陈述拿不到
    assert expectation_score("主人今晚回来吗？") > expectation_score("好的呀")


def test_score_components_add_up():
    base = expectation_score("好的呀")
    assert expectation_score("好的呀", energy_ratio=1.0) > base
    assert expectation_score("好的呀", bioclock_ratio=1.0) > base
    assert expectation_score("好的呀", activity_ratio=1.0) > base


def test_wait_seconds_from_recent_intervals():
    # 样本不足 -> 默认值
    assert estimate_wait_seconds([]) == 60.0
    assert estimate_wait_seconds([100.0]) == 60.0
    # 平均间隔 30 秒 -> 30 + 20
    assert estimate_wait_seconds([0.0, 30.0, 60.0]) == 50.0
    # 无上限：间隔 200 秒 -> 220 秒
    assert estimate_wait_seconds([0.0, 200.0]) == 220.0


def test_auto_subscribe_respects_threshold():
    async def run():
        _patch(threshold=0.99, jitter=0.0)
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            # 普通陈述分数不够 -> 不订阅
            assert auto_subscribe("a1", "group", callback, "好的呀") is None
            # 问句分数过线 -> 订阅
            _patch(threshold=0.3, jitter=0.0)
            watch = auto_subscribe("a1", "group", callback, "主人在吗？")
            assert watch is not None
            assert watch["timeout_seconds"] == 60
            # 已有订阅时不叠加
            assert auto_subscribe("a1", "group", callback, "主人在吗？") is None
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_timeout_injects_reminder():
    async def run():
        _patch()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append({"chat_id": chat_id, "mode": mode, **kwargs})

        try:
            watch = subscribe("c1", "group", callback, timeout_seconds=0.001)
            assert watch["timeout_seconds"] == 0.02

            await asyncio.sleep(0.03)
            assert len(calls) >= 1
            assert calls[0]["force_reply"] is True
            assert calls[0]["debounce_flag"] is False
            event = calls[0]["message_obj"]
            assert event["is_reply_watch_event"] is True
            assert "没有人回复" in event["content"]
            assert get_watch("c1")["followups"] >= 1
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_human_message_resolves_watch():
    async def run():
        _patch()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            subscribe("c2", "group", callback, timeout_seconds=0.001)
            resolved = resolve("c2", "human_message")
            assert resolved["status"] == "human_message"

            await asyncio.sleep(0.08)
            assert calls == []
            assert get_watch("c2") is None
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_reminders_capped_at_two():
    async def run():
        _patch()
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        try:
            subscribe("c3", "group", callback, timeout_seconds=0.001)
            await asyncio.sleep(0.15)
            assert len(calls) == 2
            assert get_watch("c3") is None
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_is_human_incoming_filters_bots_and_events():
    assert is_human_incoming({"source": "napcat.group", "is_bot": False}) is True
    assert is_human_incoming({"source": "napcat.group", "is_bot": True}) is False
    assert is_human_incoming({"source": "yuki.reply_watch", "is_reply_watch_event": True}) is False
    assert is_human_incoming({"content": "【定时任务到点】x", "is_timer_event": True}) is False
    assert is_human_incoming(None) is False


def test_pipeline_subscribes_after_question_reply():
    async def run():
        _patch(threshold=0.3)
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        pipeline = _build_pipeline(SimpleNamespace(process_callback=callback))
        try:
            context = {
                "chat_id": "g1",
                "mode": "group",
                "answer_text": "主人今晚回来吗？",
                "message_objs": [{"content": "晚安", "source": "napcat.group"}],
            }
            watch = pipeline._maybe_subscribe_reply(context)
            assert watch is not None
            # 无历史间隔 -> 默认等 60 秒
            assert watch["timeout_seconds"] == 60
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_pipeline_skips_events_and_plain_statements():
    async def run():
        _patch(threshold=0.3)
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        pipeline = _build_pipeline(SimpleNamespace(process_callback=callback))
        try:
            base = {"chat_id": "g2", "mode": "group", "answer_text": "主人今晚回来吗？"}
            # 注入提醒轮不订阅
            assert pipeline._maybe_subscribe_reply(
                {**base, "message_objs": [{"content": "【等待超时】", "is_reply_watch_event": True}]}
            ) is None
            # 定时任务轮不订阅
            assert pipeline._maybe_subscribe_reply(
                {**base, "message_objs": [{"content": "【定时任务到点】", "is_timer_event": True}]}
            ) is None
            # 破冰不订阅
            assert pipeline._maybe_subscribe_reply({**base, "ice_break": True, "message_objs": []}) is None
            # 普通陈述不订阅
            _patch(threshold=0.99)
            assert pipeline._maybe_subscribe_reply(
                {**base, "answer_text": "好的呀", "message_objs": []}
            ) is None
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_pipeline_wait_uses_recent_message_interval():
    async def run():
        _patch(threshold=0.3)
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        pipeline = _build_pipeline(SimpleNamespace(process_callback=callback))
        try:
            # 平均 30 秒一条 -> 等 50 秒
            pipeline._recent_msg_times["g3"] = [0.0, 30.0, 60.0]
            watch = pipeline._maybe_subscribe_reply(
                {"chat_id": "g3", "mode": "group", "answer_text": "有人在吗？", "message_objs": []}
            )
            assert watch["timeout_seconds"] == 50
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())


def test_pipeline_resolves_watch_on_human_message():
    async def run():
        _patch(threshold=0.3)
        reset_reply_watch()
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append(kwargs)

        pipeline = _build_pipeline(SimpleNamespace(process_callback=callback))
        try:
            subscribe("c6", "group", callback, timeout_seconds=0.001)
            await pipeline.enqueue_message(
                "c6", "group", message_obj={"content": "我回来啦", "source": "napcat.group"}, debounce_flag=False
            )
            assert get_watch("c6") is None
            assert pipeline._recent_msg_times["c6"]
            await asyncio.sleep(0.02)
            assert calls == []
        finally:
            reset_reply_watch()
            _restore()

    asyncio.run(run())
