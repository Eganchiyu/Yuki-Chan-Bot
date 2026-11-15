"""自主沙盒离线测试：投票收敛、轮数上限、上下文压缩、保底退出、工坊熔断与落盘。

全部离线：LLM 由脚本桩替代，不触网、不写真实 chat_history。
"""
import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import cfg
from core.modes.router import ModeRouter
from core.toolchain import FunctionRegistry, ToolSpec, ToolResult
from modules.autonomous import storage
from modules.autonomous.coordinator import AutonomousCoordinator
from modules.autonomous.inner_debate import InnerDebate
from modules.autonomous.sandbox_loop import AdaptorHistory, SilentSender
from modules.autonomous.tools import SandboxState


# ==================== 桩：脚本化 LLM ====================

class ScriptedLLM:
    """按脚本逐次返回 LLM 响应；脚本为空时返回纯文本。"""

    def __init__(self, script=None, default_text="（想了想）"):
        self.script = list(script or [])
        self.default_text = default_text
        self.calls = []

    async def __call__(self, messages, model=None, **kwargs):
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        if self.script:
            item = self.script.pop(0)
        else:
            item = {"content": self.default_text}
        if isinstance(item, str):
            item = {"content": item}
        return item


def tool_call(name, **args):
    return {
        "id": f"call_{name}_{abs(hash(json.dumps(args, ensure_ascii=False))) % 10000}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def vote(verdict, agree=True, note="共识"):
    return {"content": "（投一票）", "tool_calls": [tool_call("inner_vote", agree_to_end=agree,
                                                             verdict=verdict, consensus_note=note)]}


@pytest.fixture
def sandbox_data(tmp_path, monkeypatch):
    """把五层记忆的落盘路径全部指向 tmp_path，避免污染真实 data/。"""
    from modules.autonomous import storage as st

    stores = SimpleNamespace(
        state=SimpleNamespace(path=str(tmp_path / "autonomous_state.json")),
        sessions=SimpleNamespace(directory=str(tmp_path / "work_sessions"),
                                 index_path=str(tmp_path / "work_sessions" / "index.jsonl")),
        diary=SimpleNamespace(path=str(tmp_path / "work_diary.jsonl")),
        daily=SimpleNamespace(path=str(tmp_path / "daily_work_memory.json"),
                              archive_dir=str(tmp_path / "archive")),
    )
    state_store = storage.AutonomousStateStore(stores.state.path)
    session_store = storage.WorkSessionStore(stores.sessions.directory, stores.sessions.index_path)
    diary_store = storage.WorkDiaryStore(stores.diary.path)
    daily_store = storage.DailyWorkMemoryStore(stores.daily.path, stores.daily.archive_dir)

    monkeypatch.setattr("modules.autonomous.tools.work_session_store", session_store)
    monkeypatch.setattr("modules.autonomous.tools.work_diary_store", diary_store)
    monkeypatch.setattr("modules.autonomous.tools.daily_memory_store", daily_store)
    monkeypatch.setattr("modules.autonomous.coordinator.state_store", state_store)
    monkeypatch.setattr("modules.autonomous.coordinator.work_session_store", session_store)
    monkeypatch.setattr("modules.autonomous.storage.state_store", state_store)
    monkeypatch.setattr("modules.autonomous.storage.work_session_store", session_store)
    return SimpleNamespace(
        state_store=state_store,
        session_store=session_store,
        diary_store=diary_store,
        daily_store=daily_store,
        root=tmp_path,
    )


def _main_registry():
    async def dummy_handler(context, **kwargs):
        return ToolResult(success=True, content="ok")

    registry = FunctionRegistry()
    for name in ("search_diary", "search_group_snapshots", "bash", "work_finish",
                 "phone_start", "phone_action", "phone_macro", "phone_finish",
                 "art_start", "art_draw", "art_asset", "art_gacha", "art_finish"):
        registry.register(ToolSpec(name=name, description=f"{name}工具",
                                   parameters={"type": "object", "properties": {}},
                                   handler=dummy_handler))
    return registry


def _debate(script, sandbox_data, *, max_rounds=6, compress_every=8, chat_id="1057020972"):
    monkeypatch_cfg = cfg.autonomous
    monkeypatch_cfg.debate_max_rounds = max_rounds
    monkeypatch_cfg.debate_compress_every = compress_every
    state = SandboxState(run_id="run-test", chat_id=chat_id)
    llm = ScriptedLLM(script)
    debate = InnerDebate(
        chat_id=chat_id,
        chat_label="测试群",
        state=state,
        main_registry=_main_registry(),
        yuki=MagicMock(),
        sender=SilentSender(chat_id),
        max_rounds=max_rounds,
    )
    return debate, state, llm


# ==================== Phase 1：投票与轮数 ====================

async def test_vote_requires_two_consecutive_agree(sandbox_data, monkeypatch):
    debate, state, llm = _debate([], sandbox_data)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    state.record_vote("A", True, "start_work", "写小说")
    state.record_vote("B", True, "memo_only", "先记下来")
    assert state.consensus() is None            # verdict 不一致 → 不收敛
    state.record_vote("B", False, "memo_only", "再想想")
    assert state.consensus() is None            # 有人不同意 → 不收敛
    state.record_vote("A", True, "start_work", "写小说")
    state.record_vote("B", True, "start_work", "写小说")
    consensus = state.consensus()
    assert consensus and consensus["verdict"] == "start_work"


async def test_do_nothing_exit_leaves_no_trace(sandbox_data, monkeypatch):
    debate, state, llm = _debate(
        [vote("do_nothing", note="翻完日记觉得今天很平静"),
         vote("do_nothing", note="那就安静待会儿")],
        sandbox_data,
    )
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    result = await debate.run()
    assert result.stopped == "vote"
    assert result.verdict == "do_nothing"
    assert result.rounds == 2
    # 零副作用：没有任何工作会话/工作日记/今日记忆落盘，也没往外发消息
    assert sandbox_data.session_store.list() == []
    assert sandbox_data.diary_store.list() == []
    assert not (sandbox_data.root / "daily_work_memory.json").exists()
    assert debate.sender.outbox == []


async def test_debate_round_cap_and_consensus_from_last_6(sandbox_data, monkeypatch):
    debate, state, llm = _debate([], sandbox_data, max_rounds=10)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    result = await debate.run()
    assert result.stopped == "cap"
    assert result.rounds == 10
    assert result.verdict == "undecided"
    assert len(result.transcript) == 6                  # 只保留最近 6 轮
    assert "想了想" in result.summary()


async def test_context_compression_every_8_steps(sandbox_data, monkeypatch):
    debate, state, llm = _debate([], sandbox_data, max_rounds=10, compress_every=4)

    async def fake_llm_chat(messages, model=None, **kwargs):
        return "锚点：她想写一篇关于雪夜电台的短篇。"

    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    monkeypatch.setattr("modules.autonomous.inner_debate.llm_chat", fake_llm_chat)
    result = await debate.run()
    assert result.anchor.startswith("锚点")
    assert len(result.transcript) <= 6


async def test_debate_force_stop_breaks_loop(sandbox_data, monkeypatch):
    flag = {"stop": False}

    debate, state, llm = _debate([], sandbox_data, max_rounds=10)

    async def stop_soon(messages, model=None, **kwargs):
        flag["stop"] = True
        return {"content": "嗯……"}

    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", stop_soon)
    debate.stop_check = lambda: flag["stop"]
    result = await debate.run()
    assert result.stopped == "force"
    assert result.rounds == 1


# ==================== 模式接入：准入门禁与保底退出 ====================

class FakePipeline:
    def __init__(self):
        self.mode_router = ModeRouter()
        self.yuki = MagicMock()
        self.yuki.message_buffer = defaultdict(list)
        self.yuki.energy = {}
        self.yuki.last_message_time = {}
        self.yuki.mark_high_spirits = MagicMock()
        self.sender = AsyncMock()
        self.sender.get_group_meta = AsyncMock(return_value={"group_name": "测试群"})
        self.history_manager = MagicMock()
        self.memory_rag = MagicMock()
        self.image_store = None
        self.engine = MagicMock()
        self.engine.tool_registry = _main_registry()
        self.engine.process_callback = AsyncMock()
        self.handle_catchup = AsyncMock()

    async def enqueue_message(self, *args, **kwargs):
        return None


def _enable_autonomous(monkeypatch, groups=("1057020972",)):
    monkeypatch.setattr(cfg.autonomous, "enabled", True)
    monkeypatch.setattr(cfg.autonomous, "enabled_groups", list(groups))
    monkeypatch.setattr(cfg.autonomous, "max_wall_seconds", 60)


async def test_group_gate_whitelist(sandbox_data, monkeypatch):
    monkeypatch.setattr(cfg.autonomous, "enabled", False)
    monkeypatch.setattr(cfg.autonomous, "enabled_groups", [])
    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"

    refused = await coordinator.start_run(gid)
    assert refused["ok"] is False and "没开自主轮" in refused["reason"]

    _enable_autonomous(monkeypatch, groups=(gid,))
    assert coordinator.is_group_enabled(gid) is True
    other = "123456" if gid != "123456" else "654321"
    assert coordinator.is_group_enabled(other) is False

    # 运行时覆盖优先于配置
    sandbox_data.state_store.set_group_override(gid, False)
    assert coordinator.is_group_enabled(gid) is False
    sandbox_data.state_store.set_group_override(gid, True)
    assert coordinator.is_group_enabled(gid) is True


async def test_coordinator_do_nothing_keeps_data_clean(sandbox_data, monkeypatch):
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 4)
    llm = ScriptedLLM([vote("do_nothing"), vote("do_nothing")])
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    result = await coordinator._run(gid, trigger="manual", goal="", mode_arg="group",
                                   notify_master=False)
    assert result["outcome"] == "do_nothing"
    assert pipeline.mode_router.is_idle()
    assert sandbox_data.session_store.list() == []
    assert sandbox_data.diary_store.list() == []
    assert pipeline.handle_catchup.await_count == 0  # 期间没有缺席消息


async def test_coordinator_memo_only_writes_l1_l2_l4(sandbox_data, monkeypatch):
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 4)
    llm = ScriptedLLM([vote("memo_only", note="想整理一段春天的回忆"),
                       vote("memo_only", note="先写成随想")])
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    memo_calls = []

    def fake_save_memo(reflection, chat_id, session_id, kind="memo"):
        memo_calls.append(dict(reflection))
        return "mem_test_1"

    monkeypatch.setattr("modules.autonomous.coordinator.save_autonomous_memo", fake_save_memo)

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    reflection = {
        "action": "memo_only", "title": "春天的回忆",
        "memo_content": "想起刚建群那会儿的春天。", "work_diary_entry": "今天翻到了旧日记。",
        "notebook_pointer": "",
    }
    coordinator._reflect = AsyncMock(return_value=reflection)

    result = await coordinator._run(gid, trigger="manual", goal="", mode_arg="group",
                                   notify_master=False)
    assert result["outcome"] == "memo_only"
    assert memo_calls and memo_calls[0]["title"] == "春天的回忆"
    assert sandbox_data.diary_store.list()                     # L2 工作日记本
    assert "春天的回忆" not in "" and sandbox_data.daily_store.text()  # L4 今日工作记忆
    assert pipeline.mode_router.is_idle()


async def test_no_debate_trace_in_chat_history(sandbox_data, monkeypatch):
    """debate 全程不碰真实 HistoryManager，只在 AdaptorHistory 里留痕。"""
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 4)
    llm = ScriptedLLM([vote("do_nothing"), vote("do_nothing")])
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    await coordinator._run(gid, trigger="manual", goal="", mode_arg="group", notify_master=False)

    pipeline.history_manager.append_session_message.assert_not_called()
    pipeline.history_manager.replace_session.assert_not_called()
    pipeline.sender.send.assert_not_called()


# ==================== Phase 3：工坊 ====================

def _workshop(script, sandbox_data, *, max_calls=10, zero_retries=2,
              chat_id="1057020972", session_id="sess_test_01"):
    from modules.autonomous.workshop import Workshop

    monkeypatch_cfg = cfg.autonomous
    monkeypatch_cfg.workshop_max_tool_calls = max_calls
    monkeypatch_cfg.zero_tool_max_retries = zero_retries
    state = SandboxState(run_id="run-w", chat_id=chat_id, session_id=session_id)
    deps = SimpleNamespace(
        yuki=MagicMock(),
        sender=SilentSender(chat_id),
        main_registry=_main_registry(),
        history_manager=MagicMock(),
        memory_rag=MagicMock(),
        image_store=None,
        process_callback=None,
        gateway=None,
        image_attach=None,
    )
    workshop = Workshop(chat_id=chat_id, chat_label="测试群", state=state, deps=deps)
    return workshop, state, ScriptedLLM(script)


async def test_zero_tool_retry_then_fuse(sandbox_data, monkeypatch):
    workshop, state, llm = _workshop([], sandbox_data, zero_retries=2)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    outcome = await workshop.run()
    assert outcome.status == "fuse"
    # 第一次零工具 → 追问；第二次零工具 → 追问；第三次 → 熔断
    assert len(llm.calls) == 3
    assert outcome.work_log                      # 熔断也要留一份兜底工作日志
    record = sandbox_data.session_store.load(state.session_id)
    assert record and record["status"] == "paused"


async def test_workshop_60_call_cap_trims_tools_to_finish(sandbox_data, monkeypatch):
    """预算耗尽后只暴露 work_finish，模型被迫收尾。"""
    from modules.autonomous import workshop as ws_mod

    calls = [{"content": "继续", "tool_calls": [tool_call("bash", command="ls")]} for _ in range(5)]
    calls.append({"content": "收尾", "tool_calls": [tool_call(
        "work_finish", status="paused", work_log="写到第二章开头，产物 workspace/n.md",
        artifacts=["workspace/n.md"])]})
    workshop, state, llm = _workshop(calls, sandbox_data, max_calls=3, zero_retries=0)
    seen_tools = []

    original = ws_mod.Workshop._append_budget_reminder

    def spy(self, messages):
        seen_tools.append(set((msg.get("tool_calls") or [{}])[0].get("function", {}).get("name")
                              for msg in messages if msg.get("tool_calls")))
        return original(self, messages)

    monkeypatch.setattr(ws_mod.Workshop, "_append_budget_reminder", spy)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    outcome = await workshop.run()
    assert outcome.status == "paused"
    assert state.session_id == "sess_test_01"
    record = sandbox_data.session_store.load("sess_test_01")
    assert record["work_log"].startswith("写到第二章开头")
    assert record["artifacts"] == ["workspace/n.md"]
    # 预算耗尽后最后一轮的可见工具只剩 work_finish
    last_available = llm.calls[-1]["kwargs"].get("tools") or []
    assert [t["function"]["name"] for t in last_available] == ["work_finish"] or not last_available


async def test_work_log_512_truncation(sandbox_data, monkeypatch):
    long_log = "长" * 800
    script = [{"content": "收尾", "tool_calls": [tool_call(
        "work_finish", status="completed", work_log=long_log)]}]
    workshop, state, llm = _workshop(script, sandbox_data)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    outcome = await workshop.run()
    assert outcome.status == "completed"
    assert len(outcome.work_log) <= 512


async def test_session_resume_reads_512_log(sandbox_data, monkeypatch):
    """第二次进工坊时把上次的 512 字工作日志读进上下文。"""
    sandbox_data.session_store.save({
        "session_id": "sess_resume_01", "title": "雪夜电台", "kind": "creative",
        "status": "paused", "work_log": "第一章已写完，存在 workspace/novels/snow_radio_ch1.md，"
                                        "下次从第二章开始推演。",
        "artifacts": ["workspace/novels/snow_radio_ch1.md"], "chat_id": "1057020972",
    })
    script = [{"content": "收尾", "tool_calls": [tool_call(
        "work_finish", status="paused", work_log="继续写了第二章开头")]}]
    workshop, state, llm = _workshop(script, sandbox_data, session_id="sess_resume_01")
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    await workshop.run()
    joined = json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "snow_radio_ch1.md" in joined and "第二章" in joined


async def test_workshop_inner_event_merges_maid_report(sandbox_data, monkeypatch):
    workshop, state, llm = _workshop([], sandbox_data, zero_retries=0)
    workshop.queue_inner_event({"content": "小女仆：第一章草稿已写到 workspace/a.md"})
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    await workshop.run()
    joined = json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "小女仆汇报" in joined


async def test_workshop_subfocus_keeps_work_finish(sandbox_data, monkeypatch):
    """进入手机子聚焦后，可见工具仍包含 work_finish。"""
    from core.focus import focus_manager

    workshop, state, llm = _workshop([], sandbox_data)
    focus_manager.enter("1057020972", "phone", goal="点外卖")
    try:
        visible = workshop.loop.focus_view()
        assert "work_finish" in visible
        assert "phone_action" in visible
        assert "write_work_diary" in visible
    finally:
        focus_manager.abort("1057020972")
