"""主会话管线 (SessionPipeline)、破冰流程、自动回复订阅 (reply_watch)、空闲总结与模式管理测试。"""
import asyncio
from collections import defaultdict
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import reply_watch
from core.engine.engine import YukiEngine
from core.engine.engine_diary import EngineDiaryService
from core.prompts import build_chat_context, get_ice_break_instructions
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
from core.session_pipeline import IncomingMessage, SessionPipeline


def _create_mock_pipeline():
    components = {
        "sender": AsyncMock(),
        "meme_processor": MagicMock(),
        "yuki": MagicMock(),
        "history_manager": MagicMock(),
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
    }
    pipeline = SessionPipeline(components, {})
    pipeline.yuki.lock = asyncio.Lock()
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.energy = {}
    pipeline.yuki.group_activity = {}
    pipeline.yuki.message_buffer = defaultdict(list)
    pipeline.yuki.buffer_tasks = {}
    pipeline.yuki.boost_activity = AsyncMock()
    pipeline.yuki.pop_buffer = MagicMock(return_value=[])
    pipeline.yuki.consume_energy = MagicMock()
    pipeline.yuki.get_setting = MagicMock(return_value="测试系统提示")
    pipeline.yuki.user_mapping = SimpleNamespace(tick=lambda cid: None)
    pipeline.history_manager.load.return_value = {}
    pipeline.history_manager.save = MagicMock()
    pipeline.history_manager.append_to_log = MagicMock()
    pipeline.engine.do_summarize = AsyncMock(return_value=[])
    pipeline.engine.decide_to_reply = AsyncMock(return_value=True)
    pipeline.engine.api_reply = AsyncMock(return_value=("原始", "回复", ""))
    pipeline.memory_rag.search_diaries = MagicMock(return_value=[])
    pipeline.meme_processor.extract_urls_from_text = MagicMock(return_value=("", []))
    pipeline.sender.parse_cq_codes = AsyncMock(side_effect=lambda text, group_id: text)
    return pipeline


# ==================== 破冰指令与主管道各阶段 ====================

async def test_ice_break_prompt_and_context_injection():
    """get_ice_break_instructions 包含时间与字数要求，且仅在 ice_break=True 时注入系统提示。"""
    instructions = get_ice_break_instructions()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    assert "破冰模式指令" in instructions and "30-60 字" in instructions and now_str in instructions

    yuki = MagicMock()
    yuki.get_setting.return_value = "你是测试机器人"
    history = {"12345": [{"role": "system", "content": "你是测试机器人"}]}

    msgs_ice = await build_chat_context(yuki, "12345", "测试", history, "group", [], ice_break=True)
    assert any("破冰模式指令" in m["content"] for m in msgs_ice if m["role"] == "system")

    msgs_normal = await build_chat_context(yuki, "12345", "测试", history, "group", [], ice_break=False)
    assert not any("破冰模式指令" in m["content"] for m in msgs_normal if m["role"] == "system")


async def test_pipeline_ice_break_and_private_reply_stages():
    """破冰模式跳过防抖/规范化/潜水决策并递增计数；私聊始终跳过群聊潜水决策。"""
    pipeline = _create_mock_pipeline()
    pipeline.history_manager.get_session.return_value = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "之前的消息"},
    ]

    # prepare_message_batch 破冰合成上下文
    prep = await pipeline.prepare_message_batch({
        "chat_id": "99999", "mode": "group", "debounce_flag": True, "force_reply": True, "ice_break": True,
    })
    assert "之前的消息" in prep["combined_text"] and prep["message_objs"] == []

    # normalize_incoming_content 破冰跳过
    norm = await pipeline.normalize_incoming_content({"chat_id": "99999", "ice_break": True, "combined_text": "已有"})
    assert norm["combined_text"] == "已有"

    # decide_reply_action 破冰与私聊均强制通过，不调用 decide_to_reply
    for ctx in (
        {"chat_id": "99999", "mode": "group", "ice_break": True, "message_objs": [], "force_reply": True},
        {"chat_id": "12345", "mode": "private", "ice_break": False, "message_objs": [], "force_reply": None},
    ):
        dec = await pipeline.decide_reply_action(ctx)
        assert not dec.get("stop")
    pipeline.engine.decide_to_reply.assert_not_called()

    # finalize_conversation 仅在破冰时递增失败计数
    pipeline.yuki.ice_break_fail_count = {"99999": 0}
    base_fin = {
        "chat_id": "99999",
        "history_dict": {"99999": [{"role": "system", "content": "系统"}]},
        "answer_text": "回复", "answer_raw": "回复", "current_time_str": "2026年06月06日12:00",
    }
    await pipeline.finalize_conversation({**base_fin, "ice_break": False})
    assert pipeline.yuki.ice_break_fail_count["99999"] == 0
    await pipeline.finalize_conversation({**base_fin, "ice_break": True})
    assert pipeline.yuki.ice_break_fail_count["99999"] == 1


async def test_pipeline_enqueue_metadata_and_stage_propagation():
    """enqueue_message 保留入站消息元数据；run_once 将上下文标记传播到所有阶段。"""
    pipeline = _create_mock_pipeline()
    await pipeline.enqueue_message(
        "12345", "private",
        message_obj=IncomingMessage(
            name="用户A", content="你好", raw_text="你好",
            user_id=12345, source="napcat.private", owner_id="12345", tags={"private"},
        ),
        debounce_flag=False, force_reply=True,
    )
    task = pipeline._timer_tasks.pop("12345")
    task.cancel()
    await asyncio.sleep(0)

    stored = pipeline.yuki.message_buffer["12345"][0]
    assert stored["source"] == "napcat.private" and stored["owner_id"] == "12345"
    assert stored["status"] == "received" and stored["tags"] == ["private"]

    # 验证 run_once 传播
    seen_stages = []
    orig_stages = pipeline.stages

    def _wrap(stage):
        async def _captured(ctx):
            seen_stages.append((stage.__name__, ctx.get("ice_break")))
            return ctx
        _captured.__name__ = stage.__name__
        return _captured

    pipeline.stages = [_wrap(s) for s in orig_stages]
    try:
        await pipeline.run_once("99999", "group", debounce_flag=False, force_reply=True, ice_break=True)
    finally:
        pipeline.stages = orig_stages

    assert len(seen_stages) == len(orig_stages)
    assert all(flag is True for _, flag in seen_stages)


# ==================== 自动回复订阅 (reply_watch) ====================

@pytest.fixture
def fast_watch(monkeypatch):
    monkeypatch.setattr(reply_watch, "MIN_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(reply_watch, "SCORE_THRESHOLD", 0.3)
    monkeypatch.setattr(reply_watch, "SCORE_JITTER", 0.0)
    reset_reply_watch()
    yield
    reset_reply_watch()


def test_reply_watch_pure_heuristics():
    """问句/触发词检测、期望分累加、动态等待时间计算与人类消息过滤。"""
    assert is_question("主人今晚回来吗？") is True
    assert is_question("哼，人家先睡了[MEME:生气]") is False
    assert hit_trigger_word("你在吗") is True and hit_trigger_word("好的呀") is False
    assert expectation_score("主人今晚回来吗？") > expectation_score("好的呀")

    base = expectation_score("好的呀")
    assert expectation_score("好的呀", energy_ratio=1.0) > base
    assert expectation_score("好的呀", bioclock_ratio=1.0) > base
    assert expectation_score("好的呀", activity_ratio=1.0) > base

    assert estimate_wait_seconds([]) == 60.0 and estimate_wait_seconds([100.0]) == 60.0
    assert estimate_wait_seconds([0.0, 30.0, 60.0]) == 50.0
    assert estimate_wait_seconds([0.0, 200.0]) == 220.0

    assert is_human_incoming({"source": "napcat.group", "is_bot": False}) is True
    assert is_human_incoming({"source": "napcat.group", "is_bot": True}) is False
    assert is_human_incoming({"source": "yuki.reply_watch", "is_reply_watch_event": True}) is False
    assert is_human_incoming({"content": "【定时任务到点】x", "is_timer_event": True}) is False
    assert is_human_incoming(None) is False


async def test_reply_watch_lifecycle_and_pipeline_integration(fast_watch, monkeypatch):
    """订阅阈值、超时提醒（最多 2 次）、人类消息到达自动解除订阅，以及管线集成。"""
    calls = []

    async def callback(chat_id, mode, **kwargs):
        calls.append({"chat_id": chat_id, "mode": mode, **kwargs})

    # 阈值过滤与防重复叠加
    monkeypatch.setattr(reply_watch, "SCORE_THRESHOLD", 0.99)
    assert auto_subscribe("a1", "group", callback, "好的呀") is None
    monkeypatch.setattr(reply_watch, "SCORE_THRESHOLD", 0.3)
    watch = auto_subscribe("a1", "group", callback, "主人在吗？")
    assert watch is not None and watch["timeout_seconds"] == 60
    assert auto_subscribe("a1", "group", callback, "主人在吗？") is None
    resolve("a1", "cleanup")

    # 超时提醒最多 2 次后自动清除
    subscribe("c_cap", "group", callback, timeout_seconds=0.001)
    await asyncio.sleep(0.12)
    assert len(calls) == 2
    assert calls[0]["force_reply"] is True and calls[0]["message_obj"]["is_reply_watch_event"] is True
    assert get_watch("c_cap") is None

    # 管线集成：问句订阅、动态间隔、跳过系统事件、收到人类消息自动解除
    calls.clear()
    pipeline = _create_mock_pipeline()
    pipeline.engine.process_callback = callback
    pipeline.run_once = AsyncMock()

    pipeline._recent_msg_times["g1"] = [0.0, 30.0, 60.0]
    w_g1 = pipeline._maybe_subscribe_reply({
        "chat_id": "g1", "mode": "group", "answer_text": "有人在吗？",
        "message_objs": [{"content": "hi", "source": "napcat.group"}],
    })
    assert w_g1 is not None and w_g1["timeout_seconds"] == 50

    # 系统事件轮与破冰轮不订阅
    for special_ctx in (
        {"chat_id": "g2", "mode": "group", "answer_text": "在吗？", "message_objs": [{"is_reply_watch_event": True}]},
        {"chat_id": "g2", "mode": "group", "answer_text": "在吗？", "message_objs": [{"is_timer_event": True}]},
        {"chat_id": "g2", "mode": "group", "answer_text": "在吗？", "ice_break": True, "message_objs": []},
    ):
        assert pipeline._maybe_subscribe_reply(special_ctx) is None

    # 人类消息入队立即解除已有订阅
    await pipeline.enqueue_message(
        "g1", "group", message_obj={"content": "我回来啦", "source": "napcat.group"}, debounce_flag=False
    )
    assert get_watch("g1") is None


# ==================== 引擎空闲总结 ====================

async def test_engine_idle_summarize():
    """空闲会话总结只替换目标会话。"""
    diary_service = EngineDiaryService(MagicMock(), MagicMock())
    diary_service.do_summarize = AsyncMock(return_value=[{"role": "system", "content": "系统"}])

    source_session = [{"role": "system", "content": "系统"}, {"role": "user", "content": "旧消息"}]
    await diary_service.summarize_idle_session("12345", source_session)
    diary_service.do_summarize.assert_awaited_once_with(12345, source_session)
    diary_service.history.replace_session.assert_called_once_with("12345", [{"role": "system", "content": "系统"}])
    diary_service.history.save.assert_not_called()

