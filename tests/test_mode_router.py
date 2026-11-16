"""模式层（ModeRouter / ModeAwarePipeline）离线测试：路由、冻结、唯一体性、内部事件、补台。"""
import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.modes import (
    CHAT_MODE,
    ROUTE_CHAT,
    ROUTE_FROZEN,
    ROUTE_MODE,
    ModeAwarePipeline,
    ModeBusyError,
    ModeRouter,
)
from core.modes.base import Mode, ModeCapabilities
from core.session_pipeline import IncomingMessage, SessionPipeline


class FakeMode(Mode):
    name = "fake"
    capabilities = ModeCapabilities(
        can_send=False, writes_chat_history=False, accepts_human_input=False,
        allow_sub_focus=False, triggers_diary=False, accepts_inner_event=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inputs = []
        self.inner_events = []
        self.inner_handled = True
        self.ran = False

    async def run(self):
        self.ran = True
        return {"status": "completed"}

    def on_input(self, message):
        self.inputs.append(message)

    def on_inner_event(self, event):
        self.inner_events.append(event)
        return self.inner_handled


def _make_pipeline(router=None):
    components = {
        "sender": AsyncMock(),
        "meme_processor": MagicMock(),
        "yuki": MagicMock(),
        "history_manager": MagicMock(),
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
    }
    pipeline = ModeAwarePipeline(components, {}, router or ModeRouter())
    pipeline.yuki.lock = asyncio.Lock()
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.energy = {}
    pipeline.yuki.group_activity = {}
    pipeline.yuki.message_buffer = defaultdict(list)
    pipeline.yuki.buffer_tasks = {}
    pipeline.yuki.user_mapping = SimpleNamespace(tick=lambda cid: None)
    pipeline.history_manager.load.return_value = {}
    pipeline.history_manager.get_session.return_value = []
    pipeline.history_manager.append_to_log = MagicMock()
    pipeline.meme_processor.extract_urls_from_text = MagicMock(return_value=("", []))
    pipeline.sender.parse_cq_codes = AsyncMock(side_effect=lambda text, group_id: text)
    return pipeline


def _msg(text="在吗", uid=111, **extra):
    data = {
        "name": "月白",
        "content": f'【"月白"】说: {text}',
        "raw_text": text,
        "user_id": uid,
        "source": "napcat.message",
    }
    data.update(extra)
    return data


# ==================== 路由 ====================

def test_route_chat_when_idle():
    router = ModeRouter()
    assert router.is_idle()
    assert router.route("1", "group") == (ROUTE_CHAT, None)
    assert router.current_mode("1") == CHAT_MODE


def test_route_to_mode_and_frozen():
    router = ModeRouter()
    state = router.enter("1", "fake")
    assert router.route("1", "group")[0] == ROUTE_MODE
    assert router.route("2", "group")[0] == ROUTE_FROZEN
    assert router.global_run is state
    assert router.exit("1").chat_id == "1"
    assert router.is_idle()
    assert router.route("2", "group")[0] == ROUTE_CHAT


def test_global_single_active_run_rejects_second_mode():
    router = ModeRouter()
    router.enter("1", "fake")
    with pytest.raises(ModeBusyError):
        router.enter("2", "fake")


async def test_noop_passthrough_when_router_idle(monkeypatch):
    """router 空闲时 ModeAwarePipeline 必须原样透传父类，不建额外任务。"""
    calls = []

    async def fake_parent(self, chat_id, mode, message_obj=None, debounce_flag=True,
                          force_reply=None, ice_break=False):
        calls.append((chat_id, mode, message_obj, debounce_flag, force_reply, ice_break))
        return "parent-task"

    monkeypatch.setattr(SessionPipeline, "enqueue_message", fake_parent)
    pipeline = _make_pipeline()
    task = await pipeline.enqueue_message("12345", "group", message_obj=_msg(), debounce_flag=False)
    assert task == "parent-task"
    assert len(calls) == 1
    assert calls[0][0] == "12345"
    assert pipeline.yuki.message_buffer["12345"] == []
    assert pipeline._timer_tasks == {}


# ==================== 非 chat 模式 ====================

async def test_non_chat_mode_buffers_input_without_task():
    router = ModeRouter()
    mode = FakeMode(chat_id="12345", router=router)
    router.enter("12345", "fake", instance=mode)
    pipeline = _make_pipeline(router)

    result = await pipeline.enqueue_message("12345", "group", message_obj=_msg())
    assert result is None
    assert len(pipeline.yuki.message_buffer["12345"]) == 1
    assert pipeline._timer_tasks == {}
    # 该群自己也算「独处期间群里有新消息」，退出后要补台
    assert router.pending_catchups()["12345"].messages == 1
    assert mode.inputs and mode.inputs[0]["raw_text"] == "在吗"


async def test_frozen_group_collects_catchup():
    router = ModeRouter()
    router.enter("A", "fake", instance=FakeMode(chat_id="A", router=router))
    handled = []

    async def catchup(cid):
        handled.append(cid)

    pipeline = _make_pipeline(router)
    # 补台处理器由 pipeline 构造时接管，这里换成测试桩
    router.set_catchup_handler(catchup)

    await pipeline.enqueue_message("B", "group", message_obj=_msg("B群消息", uid=222))
    assert pipeline.yuki.message_buffer["B"]
    assert "B" in router.pending_catchups()
    assert "A" not in router.pending_catchups()  # A 期间没有新消息

    done = await router.dispatch_catchups()
    assert done == ["B"] and handled == ["B"]
    assert router.pending_catchups() == {}


async def test_inner_event_delivered_not_buffered():
    router = ModeRouter()
    mode = FakeMode(chat_id="A", router=router)
    router.enter("A", "workshop", instance=mode)
    pipeline = _make_pipeline(router)

    event = _msg("小女仆汇报", is_maid_report=True)
    await pipeline.enqueue_message("A", "group", message_obj=event, force_reply=True)
    assert mode.inner_events and mode.inner_events[0]["is_maid_report"] is True
    assert pipeline.yuki.message_buffer["A"] == []
    assert router.pending_catchups() == {}


async def test_inner_event_from_history_when_no_message_obj():
    """maid_worker 只写历史不传 message_obj，路由要能从历史里捡回汇报。"""
    router = ModeRouter()
    mode = FakeMode(chat_id="A", router=router)
    router.enter("A", "workshop", instance=mode)
    pipeline = _make_pipeline(router)
    pipeline.history_manager.get_session.return_value = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "【小女仆汇报】写完了", "is_maid_report": True},
    ]

    await pipeline.enqueue_message("A", "group", force_reply=True)
    assert mode.inner_events and mode.inner_events[0]["is_maid_report"] is True


def test_force_release_requests_stop():
    router = ModeRouter()
    mode = FakeMode(chat_id="A", router=router)
    router.enter("A", "debate", instance=mode)
    released = router.force_release("test")
    assert released.chat_id == "A"
    assert mode.stop_requested is True
    assert mode.stop_reason == "test"


async def test_catchup_message_is_not_human_incoming(monkeypatch):
    """补台消息不能解除 reply_watch、也不能算真人到达。"""
    from core import reply_watch

    resolved = []
    monkeypatch.setattr(reply_watch, "resolve", lambda cid, reason: resolved.append((cid, reason)))
    pipeline = _make_pipeline()
    catchup = IncomingMessage(
        name="系统", content="【你刚才在独处】…", source="yuki.catchup", is_catchup=True,
    )
    incoming = pipeline._buffer_incoming("12345", catchup)
    assert incoming.is_system_injected is True
    assert resolved == []
    assert pipeline.yuki.message_buffer["12345"][0]["is_catchup"] is True


async def test_catchup_forces_reply_in_prepare_batch():
    pipeline = _make_pipeline()
    from config import cfg

    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "12345"
    pipeline.group_active_state[gid] = True  # 2026-11-16 起缺省=休眠
    pipeline.yuki.pop_buffer = MagicMock(return_value=[{
        "name": "系统", "content": "【你刚才在独处】…", "is_catchup": True,
    }])
    pipeline.yuki.boost_activity = AsyncMock()
    context = {"chat_id": gid, "mode": "group", "force_reply": None}
    context = await pipeline.prepare_message_batch(context)
    assert context["force_reply"] is True
    assert context.get("stop") is not True


async def test_catchup_skipped_while_group_sleeping():
    """休眠群的补台会被管线直接丢弃，所以这里先跳过注入、把消息留在缓冲区。"""
    from modules.autonomous import catchup as cp

    pipeline = _make_pipeline()
    pipeline.group_active_state["12345"] = False
    pipeline.yuki.pop_buffer = MagicMock(return_value=[{"name": "月白", "content": "在吗"}])
    called = []
    original = cp.build_catchup_event

    async def spy(*args, **kwargs):
        called.append(args)
        return None

    cp.build_catchup_event = spy
    try:
        await pipeline.handle_catchup("12345")
    finally:
        cp.build_catchup_event = original
    assert called == []
    pipeline.yuki.pop_buffer.assert_not_called()
