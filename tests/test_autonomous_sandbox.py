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

    transcript_dir = tmp_path / "logs" / "autonomous"
    stores = SimpleNamespace(
        state=SimpleNamespace(path=str(tmp_path / "autonomous_state.json")),
        sessions=SimpleNamespace(directory=str(tmp_path / "work_sessions"),
                                 index_path=str(tmp_path / "work_sessions" / "index.jsonl")),
        diary=SimpleNamespace(path=str(tmp_path / "work_diary.jsonl")),
        daily=SimpleNamespace(path=str(tmp_path / "daily_work_memory.json"),
                              archive_dir=str(tmp_path / "archive")),
        transcripts=transcript_dir,
    )
    state_store = storage.AutonomousStateStore(stores.state.path)
    session_store = storage.WorkSessionStore(stores.sessions.directory, stores.sessions.index_path)
    diary_store = storage.WorkDiaryStore(stores.diary.path)
    daily_store = storage.DailyWorkMemoryStore(stores.daily.path, stores.daily.archive_dir)

    from core.notebook import NotebookStore
    from modules.autonomous.inspiration import InspirationStore

    notebook_store = NotebookStore(str(tmp_path / "notebook.json"))
    insp_store = InspirationStore(str(tmp_path / "inspiration_inbox.json"))
    monkeypatch.setattr("core.notebook.notebook_store", notebook_store)
    monkeypatch.setattr("modules.autonomous.coordinator.notebook_store", notebook_store, raising=False)
    monkeypatch.setattr("modules.autonomous.inspiration.inspiration_store", insp_store)
    monkeypatch.setattr("modules.autonomous.tools.inspiration_store", insp_store)
    monkeypatch.setattr(cfg.autonomous, "corner_base_url", "")
    monkeypatch.setattr(cfg.autonomous, "corner_token", "")

    monkeypatch.setattr("modules.autonomous.transcript.TRANSCRIPT_DIR", str(transcript_dir))

    monkeypatch.setattr("modules.autonomous.tools.work_session_store", session_store)
    monkeypatch.setattr("modules.autonomous.tools.work_diary_store", diary_store)
    monkeypatch.setattr("modules.autonomous.tools.daily_memory_store", daily_store)
    monkeypatch.setattr("modules.autonomous.coordinator.state_store", state_store)
    monkeypatch.setattr("modules.autonomous.coordinator.work_session_store", session_store)
    monkeypatch.setattr("modules.autonomous.inner_debate.work_session_store", session_store)
    monkeypatch.setattr("modules.autonomous.storage.state_store", state_store)
    monkeypatch.setattr("modules.autonomous.storage.work_session_store", session_store)
    return SimpleNamespace(
        state_store=state_store,
        session_store=session_store,
        diary_store=diary_store,
        daily_store=daily_store,
        inspiration_store=insp_store,
        transcripts=transcript_dir,
        root=tmp_path,
    )


def _main_registry():
    async def dummy_handler(context, **kwargs):
        return ToolResult(success=True, content="ok")

    registry = FunctionRegistry()
    for name in ("search_diary", "search_group_snapshots", "work_finish",
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


async def test_debate_retrieval_window_then_pure_discussion(sandbox_data, monkeypatch):
    """前 N 步可用检索工具，之后收起只剩投票，越窗调用会被工具层拒绝。"""
    monkeypatch.setattr(cfg.autonomous, "debate_retrieval_steps", 2)
    script = [
        {"content": "先翻翻旧日记。", "tool_calls": [tool_call("search_diary", keyword="雪夜电台")]},
        {"content": "那段电台夜聊我还记得。"},
        {"content": "再确认一下细节。", "tool_calls": [tool_call("search_diary", keyword="电台")]},
        {"content": "好吧，凭记忆也能往下想。"},
    ]
    debate, state, llm = _debate(script, sandbox_data, max_rounds=4)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    await debate.run()

    full = {"inspect_work_session", "inner_vote", "list_recent_work_sessions",
            "search_diary", "search_group_snapshots"}
    step_tools = [
        {t["function"]["name"] for t in (call["kwargs"].get("tools") or [])}
        for call in llm.calls
    ]
    assert step_tools[0] == full and step_tools[1] == full     # 窗口内：检索 + 投票
    assert step_tools[2] == {"inner_vote"}                     # 窗口外：纯讨论
    assert step_tools[3] == {"inner_vote"}
    assert debate._visible_tools(2) == full
    assert debate._visible_tools(3) == {"inner_vote"}

    records = [json.loads(line) for line in
               (sandbox_data.transcripts / "run-test.jsonl").read_text(encoding="utf-8").splitlines()]
    steps = {r["step"]: r for r in records if r["kind"] == "debate_step"}
    assert steps[1]["tools"][0]["success"] is True
    assert steps[3]["tools"][0]["success"] is False
    assert "未展开" in steps[3]["tools"][0]["content"]


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

    calls = [{"content": "继续", "tool_calls": [tool_call("search_diary", keyword="雪夜")]}
             for _ in range(5)]
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


# ==================== P6：补台 / 心情高涨 / 自动触发 ====================

def _msgs(n, name="月白"):
    return [{"name": name, "content": f"第{i}条消息", "source": "napcat.message",
             "user_id": 100 + i, "time": f"2026-11-15 14:{i:02d}"} for i in range(n)]


async def test_catchup_digest_direct_vs_llm(sandbox_data, monkeypatch):
    from modules.autonomous import catchup as cp

    # ≤12 条：代码直拼，零 LLM
    called = []
    async def fake_llm_chat(messages, model=None, **kwargs):
        called.append(messages)
        return "摘要"

    monkeypatch.setattr(cp, "llm_chat", fake_llm_chat)
    monkeypatch.setattr(cfg.autonomous, "catchup_summarize_threshold", 12)
    direct = await cp.build_digest(_msgs(5))
    assert "14:00 月白: 第0条消息" in direct
    assert called == []

    # >12 条：走 sub-LLM 压到 ≤200 字
    long_summary = "他" * 500
    async def long_llm(messages, model=None, **kwargs):
        called.append(messages)
        return long_summary

    monkeypatch.setattr(cp, "llm_chat", long_llm)
    digest = await cp.build_digest(_msgs(20))
    assert called and len(digest) <= 240
    assert digest.endswith("…")

    # LLM 失败：回落直拼最近 20 条
    async def boom(messages, model=None, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(cp, "llm_chat", boom)
    fallback = await cp.build_digest(_msgs(20))
    assert "14:19 月白" in fallback


async def test_catchup_event_skips_system_messages(sandbox_data, monkeypatch):
    from modules.autonomous import catchup as cp

    pipeline = FakePipeline()
    pipeline.yuki.pop_buffer = MagicMock(return_value=[
        {"name": "系统", "content": "【等待超时】", "is_reply_watch_event": True,
         "source": "yuki.reply_watch"},
        {"name": "月白", "content": "在吗", "source": "napcat.message", "user_id": 1},
    ])
    event = await cp.build_catchup_event(pipeline, "1057020972")
    assert event and event["is_catchup"] is True
    assert "月白" in event["content"] and "等待超时" not in event["content"]


async def test_catchup_no_messages_returns_none(sandbox_data):
    from modules.autonomous import catchup as cp

    pipeline = FakePipeline()
    pipeline.yuki.pop_buffer = MagicMock(return_value=[])
    assert await cp.build_catchup_event(pipeline, "1") is None


async def test_high_spirits_boosts_reply_desire():
    from core.brain import YukiState
    from core.engine.engine_decision import EngineDecisionService

    import datetime as _dt

    yuki = YukiState()
    yuki.energy["1"] = 70.0
    yuki.last_update["1"] = _dt.datetime.now()
    yuki.group_activity["1"] = 0.0
    service = EngineDecisionService(yuki)

    baseline = await service.decide_to_reply(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "嗯"}],
        [{"raw_text": "随便说说", "is_bot": False}], "1",
    )
    yuki.energy["1"] = 70.0
    yuki.last_update["1"] = _dt.datetime.now()
    yuki.group_activity["1"] = 0.0
    yuki.mark_high_spirits("1")
    boosted = await service.decide_to_reply(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "嗯"}],
        [{"raw_text": "随便说说", "is_bot": False}], "1",
    )
    assert baseline is False and boosted is True


async def test_high_spirits_followup_window_uses_short_timeout(monkeypatch):
    from core import reply_watch

    reply_watch.reset_reply_watch()
    events = []
    watch = reply_watch.subscribe(
        "1", "group", AsyncMock(), timeout_seconds=12, min_timeout_seconds=12,
        event_builder=lambda w: {"content": "想再说几句", "source": "yuki.high_spirits",
                                 "is_reply_watch_event": True},
    )
    assert watch["timeout_seconds"] == 12
    reply_watch.reset_reply_watch()


def test_daily_work_memory_ttl_and_archive(sandbox_data, monkeypatch):
    store = sandbox_data.daily_store
    store.ttl_hours = 18
    store.add(summary="写完第一章", status="可接续", session_id="sess_1",
              artifacts=["workspace/a.md"], now=1_800_000_000)
    assert "写完第一章" in store.text(now=1_800_000_000)
    assert store.text(now=1_800_000_000 + 19 * 3600) == ""     # 过期不再常驻

    # 次日 04:00 后归档到 daily_work_memory_archive/<date>.json
    store2 = storage.DailyWorkMemoryStore(str(sandbox_data.root / "dwm2.json"),
                                          str(sandbox_data.root / "arch"),
                                          ttl_hours=1000)
    import datetime as _dt
    day1 = _dt.datetime(2026, 11, 15, 12, 0).timestamp()
    store2.add(summary="昨天做的事", status="完成", now=day1)
    day2 = _dt.datetime(2026, 11, 16, 5, 0).timestamp()
    assert store2.archive_if_due(now=day2) is True
    assert store2.text(now=day2) == ""
    assert (sandbox_data.root / "arch" / "2026-11-15.json").exists()


async def test_auto_trigger_requires_whitelist_and_quota(sandbox_data, monkeypatch):
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "enabled", True)
    monkeypatch.setattr(cfg.autonomous, "auto_trigger_enabled", True)
    monkeypatch.setattr(cfg.autonomous, "enabled_groups", [])
    monkeypatch.setattr(cfg.autonomous, "min_group_idle_minutes", 0)
    monkeypatch.setattr(cfg.autonomous, "min_energy", 0.0)
    monkeypatch.setattr(cfg.autonomous, "quiet_hours", [])
    monkeypatch.setattr(cfg.autonomous, "cooldown_minutes", 0)
    monkeypatch.setattr(cfg.autonomous, "daily_max_runs", 1)

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    pipeline.yuki.last_message_time[gid] = 0.0
    pipeline.yuki.energy[gid] = 100.0

    # 白名单为空：不触发
    assert await coordinator.auto_trigger_check() is None

    monkeypatch.setattr(cfg.autonomous, "enabled_groups", [gid])
    started = []

    async def fake_start_run(chat_id, **kwargs):
        started.append((chat_id, kwargs))
        return {"ok": True}

    coordinator.start_run = fake_start_run
    assert (await coordinator.auto_trigger_check()) is not None
    assert started and started[0][0] == gid and started[0][1]["trigger"] == "auto"
    # 日配额 1 次，第二条不再触发
    assert await coordinator.auto_trigger_check() is None
    assert sandbox_data.state_store.auto_runs_today() == 1


async def test_auto_trigger_respects_runtime_override_and_target_groups(sandbox_data, monkeypatch):
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "enabled", True)
    monkeypatch.setattr(cfg.autonomous, "enabled_groups", [gid])

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    assert coordinator.is_group_enabled(gid) is True

    sandbox_data.state_store.set_group_override(gid, False)
    assert coordinator.is_group_enabled(gid) is False
    # 覆盖落盘后重建 coordinator（模拟重启）仍是关
    reloaded = storage.AutonomousStateStore(sandbox_data.state_store.path)
    assert reloaded.get_group_override(gid) is False
    assert str(gid) not in coordinator.enabled_group_ids()


async def test_sweep_stale_runs_marks_session_paused(sandbox_data, monkeypatch):
    sandbox_data.session_store.save({
        "session_id": "sess_stale_01", "title": "旧任务", "kind": "creative",
        "status": "active", "work_log": "写到一半", "chat_id": "1",
    })
    sandbox_data.state_store.set_active_mode("1", "workshop", "run-old", session_id="sess_stale_01")

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    assert coordinator.sweep_stale_runs() == 1
    record = sandbox_data.session_store.load("sess_stale_01")
    assert record["status"] == "paused" and "自动暂停" in record["work_log"]
    assert sandbox_data.state_store.get_active_mode() == {}


# ==================== 全链路：debate → 复盘 → 工坊 ====================

async def test_full_run_start_work_enters_workshop(sandbox_data, monkeypatch):
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 6)
    monkeypatch.setattr(cfg.autonomous, "workshop_max_tool_calls", 5)

    script = [
        vote("start_work", note="想写一篇《雪夜电台》"),
        vote("start_work", note="先写第一章"),
        {"content": "好，那我先动手。", "tool_calls": [tool_call(
            "conclude_reflection", action="start_work", title="雪夜电台",
            memo_content="想把上周聊的深夜电台写成短篇。",
            work_diary_entry="今晚先写第一章。",
            notebook_pointer="[sess] 雪夜电台第一章待写",
        )]},
        {"content": "先翻翻旧日记", "tool_calls": [tool_call("search_diary", keyword="深夜电台")]},
        {"content": "写完第一章", "tool_calls": [tool_call(
            "work_finish", status="paused",
            work_log="写了《雪夜电台》第一章约1800字，存在 workspace/novels/snow_radio_ch1.md，下次写第二章。",
            artifacts=["workspace/novels/snow_radio_ch1.md"],
        )]},
    ]
    llm = ScriptedLLM(script)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    memo_calls = []
    monkeypatch.setattr(
        "modules.autonomous.coordinator.save_autonomous_memo",
        lambda reflection, chat_id, session_id, kind="memo": memo_calls.append(reflection) or "mem_x",
    )

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    result = await coordinator._run(gid, trigger="manual", goal="", mode_arg="group",
                                   notify_master=False)
    assert result["outcome"] == "start_work"

    sessions = sandbox_data.session_store.list()
    assert sessions and sessions[0]["status"] == "paused"
    record = sandbox_data.session_store.load(sessions[0]["session_id"])
    assert record["artifacts"] == ["workspace/novels/snow_radio_ch1.md"]
    assert "第二章" in record["work_log"]
    assert memo_calls and memo_calls[0]["title"] == "雪夜电台"
    assert "雪夜电台" in sandbox_data.daily_store.text() or record["work_log"][:8] in sandbox_data.daily_store.text()
    assert pipeline.mode_router.is_idle()
    pipeline.sender.send.assert_not_called()

    from core.notebook import notebook_store

    assert "雪夜电台" in notebook_store.load_zone("plans")
    assert notebook_store.load_zone("daily") == ""      # 测试不碰真实小本本日常区


async def test_do_nothing_does_not_mark_high_spirits(sandbox_data, monkeypatch):
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 4)
    llm = ScriptedLLM([vote("do_nothing"), vote("do_nothing")])
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    pipeline = FakePipeline()
    pipeline.yuki.message_buffer[gid] = []
    coordinator = AutonomousCoordinator(pipeline)
    await coordinator._run(gid, trigger="manual", goal="", mode_arg="group", notify_master=False)
    pipeline.yuki.mark_high_spirits.assert_not_called()
    pipeline.engine.process_callback.assert_not_awaited()
    assert pipeline.handle_catchup.await_count == 0


async def test_runtime_override_beats_global_switch(sandbox_data, monkeypatch):
    """`/自主轮 开` 是主人当场授权：即使总开关关着，本群也应该能用 /深思。"""
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "enabled", False)
    monkeypatch.setattr(cfg.autonomous, "enabled_groups", [])

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    assert coordinator.is_group_enabled(gid) is False
    assert "总开关" in coordinator.gate_reason(gid)

    sandbox_data.state_store.set_group_override(gid, True)
    assert coordinator.is_group_enabled(gid) is True
    assert "运行时覆盖" in coordinator.gate_reason(gid)

    # 总开关即使开着，运行时 `/自主轮 关` 仍然优先
    monkeypatch.setattr(cfg.autonomous, "enabled", True)
    sandbox_data.state_store.set_group_override(gid, False)
    assert coordinator.is_group_enabled(gid) is False

    # 非目标群：运行时覆盖也救不了（本来就不收这个群的消息）
    if cfg.TARGET_GROUPS:
        outsider = str(int(cfg.TARGET_GROUPS[0]) + 1)
        sandbox_data.state_store.set_group_override(outsider, True)
        assert coordinator.is_group_enabled(outsider) is False


# ==================== 逐轮记录（logs/autonomous/<run_id>.jsonl） ====================

async def test_transcript_records_debate_and_reflection(sandbox_data, monkeypatch):
    _enable_autonomous(monkeypatch)
    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    monkeypatch.setattr(cfg.autonomous, "debate_max_rounds", 4)
    llm = ScriptedLLM([
        vote("memo_only", note="想整理一下春天的回忆"),
        vote("memo_only", note="先写成随想"),
    ])
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    monkeypatch.setattr(
        "modules.autonomous.coordinator.save_autonomous_memo",
        lambda reflection, chat_id, session_id, kind="memo": "mem_t1",
    )

    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)
    coordinator._reflect = AsyncMock(return_value={
        "action": "memo_only", "title": "春天的回忆",
        "memo_content": "想起刚建群那会儿的春天。", "work_diary_entry": "", "notebook_pointer": "",
    })
    await coordinator._run(gid, trigger="manual", goal="", mode_arg="group", notify_master=False)

    files = sorted((sandbox_data.transcripts).glob("*.jsonl"))
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    kinds = [r["kind"] for r in records]
    assert kinds[0] == "run_start"
    assert "debate_step" in kinds and "vote" in kinds
    assert "reflection" in kinds and kinds[-1] == "run_finish"
    first_step = next(r for r in records if r["kind"] == "debate_step")
    assert first_step["role"] == "A" and first_step["content"]
    assert records[-1]["outcome"] == "memo_only"


async def test_transcript_records_workshop_steps(sandbox_data, monkeypatch):
    script = [
        {"content": "先翻翻旧日记", "tool_calls": [tool_call("search_diary", keyword="第一章")]},
        {"content": "收尾", "tool_calls": [tool_call(
            "work_finish", status="completed", work_log="写好第一章",
            artifacts=["workspace/a.md"])]},
    ]
    workshop, state, llm = _workshop(script, sandbox_data)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    await workshop.run()

    files = sorted(sandbox_data.transcripts.glob("*.jsonl"))
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    kinds = [r["kind"] for r in records]
    assert kinds[0] == "run_start" and kinds[-1] == "workshop_finish"
    steps = [r for r in records if r["kind"] == "workshop_step"]
    assert any(r.get("calls") and r["calls"][0]["name"] == "search_diary" and r.get("tools")
               for r in steps)
    assert "写好第一章" in records[-1]["work_log"]


async def test_deep_think_refused_when_group_sleeping(monkeypatch):
    """休眠群不该跑自主轮：先提示 /开启。"""
    from modules.QQNapcatListen import listen_main

    gid = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "1057020972"
    coordinator = SimpleNamespace(
        status_text=MagicMock(return_value="状态"),
        start_run=AsyncMock(return_value={"ok": True}),
        force_release=MagicMock(return_value={"ok": True}),
    )
    pipeline = SimpleNamespace(autonomous=coordinator, group_active_state={gid: False})
    gateway = AsyncMock()

    handled = listen_main.handle_autonomous_command(
        pipeline, gateway, gid, gid, cfg.MASTER_QQS[0], "/深思",
    )
    await asyncio.sleep(0)
    assert handled is True
    coordinator.start_run.assert_not_awaited()
    sent = gateway.send.await_args.args[1]
    assert "/开启" in sent


# ==================== P8：创造力引擎与 Yuki's Corner 展柜闭环 ====================

async def test_debate_feeds_tool_findings_to_next_step(sandbox_data, monkeypatch):
    """修复盲查 Bug：debate 中检索工具的真实返回必须传进下一步上下文。"""
    monkeypatch.setattr(cfg.autonomous, "debate_retrieval_steps", 2)

    async def diary_handler(context, **kwargs):
        return ToolResult(success=True, content="查到真实记忆：上周大家在群里约定一起做星光扭蛋机。")

    registry = _main_registry()
    registry.register(ToolSpec(
        name="search_diary", description="查日记",
        parameters={"type": "object", "properties": {"keyword": {"type": "string"}}},
        handler=diary_handler,
    ))
    script = [
        {"content": "先查查上周的约定。", "tool_calls": [tool_call("search_diary", keyword="扭蛋机")]},
        {"content": "看到啦！那就做成网页小玩具。"},
    ]
    llm = ScriptedLLM(script)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    monkeypatch.setattr("modules.autonomous.inner_debate.diary_seed_sampler.sample", lambda cid: [])

    state = SandboxState(run_id="run-findings", chat_id="1057020972")
    debate = InnerDebate(
        chat_id="1057020972", chat_label="测试群", state=state,
        main_registry=registry, yuki=SimpleNamespace(), max_rounds=2,
    )
    await debate.run()

    step2_user = llm.calls[1]["messages"][1]["content"]
    assert "星光扭蛋机" in step2_user
    assert "search_diary 查到的结果" in step2_user


def test_inspiration_bundle_combines_feedback_boredom_and_spark(sandbox_data):
    """多源灵感混合器：融合展柜新纸条、反无聊提醒、剪贴簿灵感与随机创意火花卡。"""
    from modules.autonomous.inspiration import build_inspiration_bundle, render_inspiration_block

    sandbox_data.inspiration_store.add(
        title="WebAudio 雨声合成",
        snippet="用棕色噪声加滤波可以纯前端合成逼真雨声。",
        source_url="https://example.test/rain",
    )
    feedback = {
        "unread_notes": [
            {"author": "月白", "work_title": "《倒计时》", "message": "下次想玩个能点的像素小游戏！"}
        ],
        "recent_works": [
            {"slug": "n1", "title": "倒计时", "kind": "note", "views": 5, "reactions_total": 3, "guestbook_count": 1},
            {"slug": "n2", "title": "随想二", "kind": "note", "views": 2, "reactions_total": 1, "guestbook_count": 0},
        ],
    }
    bundle = build_inspiration_bundle(
        "1057020972",
        corner_feedback=feedback,
        store=sandbox_data.inspiration_store,
        jargon_db_path=str(sandbox_data.root / "missing_jargon.db"),
    )
    text = render_inspiration_block(bundle)
    assert "月白" in text and "像素小游戏" in text
    assert "纯文字手账" in text
    assert "WebAudio 雨声合成" in text
    assert "创意火花卡" in text


async def test_publish_to_corner_and_save_inspiration_tools(sandbox_data, monkeypatch):
    """工坊内可调用 save_inspiration 与 publish_to_corner，并把公网链接写入 artifacts 与 L4 记忆。"""
    from modules.autonomous import corner_client, tools as sb_tools

    local_corner = sandbox_data.root / "corner_local"
    monkeypatch.setattr(corner_client, "CORNER_LOCAL_ROOT", local_corner)
    monkeypatch.setattr(cfg.autonomous, "corner_base_url", "http://corner.test")
    monkeypatch.setattr(cfg.autonomous, "corner_token", "yc_test_token")

    captured = {}

    def fake_http(method, url, *, payload=None, token="", timeout=15.0):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        captured["token"] = token
        return {
            "ok": True,
            "slug": payload["slug"],
            "page_url": f"http://corner.test/w/{payload['slug']}",
            "files": [f["path"] for f in payload["files"]],
        }

    monkeypatch.setattr(corner_client, "_http_request_sync", fake_http)

    script = [
        {"content": "先剪贴一条采风灵感", "tool_calls": [tool_call(
            "save_inspiration", title="会发光的水母算法", snippet="Canvas 贝塞尔触手动画超梦幻",
        )]},
        {"content": "把互动玩具上架展柜", "tool_calls": [tool_call(
            "publish_to_corner",
            slug="star-gacha",
            title="星光扭蛋机",
            kind="toy",
            summary="点一下摇出群友今日运势",
            inline_content="<!doctype html><html><body><h1>Star Gacha</h1></body></html>",
            inline_filename="index.html",
            tags=["扭蛋", "互动"],
        )]},
        {"content": "收尾", "tool_calls": [tool_call(
            "work_finish", status="completed",
            work_log="做好了《星光扭蛋机》互动网页并上架展柜！",
        )]},
    ]
    workshop, state, llm = _workshop(script, sandbox_data)
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)
    outcome = await workshop.run()

    assert outcome.status == "completed"
    assert captured["url"] == "http://corner.test/api/publish"
    assert captured["token"] == "yc_test_token"
    assert captured["payload"]["kind"] == "toy"
    assert "http://corner.test/w/star-gacha" in state.published_urls
    assert "http://corner.test/w/star-gacha" in outcome.artifacts
    assert len(sandbox_data.inspiration_store.list_recent()) == 1

    sb_tools.record_work_memory(state, {"title": "星光扭蛋机"}, status="已完成")
    assert "http://corner.test/w/star-gacha" in sandbox_data.daily_store.text()


async def test_wait_maid_tasks_returns_report_immediately(sandbox_data, monkeypatch):
    """工坊里调用 wait_maid_tasks 会在小女仆汇报到达时立即返回内容。"""
    from core.maid.maid_runtime import MaidRuntime

    runtime = MaidRuntime()
    rec = runtime.register("做个星光扭蛋机网页", chat_id="1057020972")
    runtime.mark(rec.uid, "running")

    script = [
        {"content": "等小女仆干完活", "tool_calls": [tool_call("wait_maid_tasks", timeout_seconds=10)]},
        {"content": "收到汇报，收尾", "tool_calls": [tool_call(
            "work_finish", status="completed", work_log="小女仆写好并验收完毕",
        )]},
    ]
    workshop, state, llm = _workshop(script, sandbox_data)
    workshop.deps.yuki.maid_runtime = runtime
    workshop.context.runtime.yuki_state = workshop.deps.yuki
    monkeypatch.setattr("modules.autonomous.sandbox_loop.llm_chat_raw", llm)

    async def deliver_soon():
        await asyncio.sleep(0.05)
        workshop.queue_inner_event({"content": "小女仆 #1 已把网页写到 workspace/yuki_corner/star/index.html"})
        runtime.remove(rec.uid)

    feeder = asyncio.create_task(deliver_soon())
    outcome = await workshop.run()
    await feeder

    assert outcome.status == "completed"
    second_call = json.dumps(llm.calls[1]["messages"], ensure_ascii=False)
    assert "workspace/yuki_corner/star/index.html" in second_call


def test_ensure_work_session_splits_new_topic_from_old_paused(sandbox_data):
    """全新创意企划不会硬套旧的无关 paused 会话；显式 resume_session_id 可精准续作。"""
    sandbox_data.session_store.save({
        "session_id": "sess_old_01", "title": "旧企划：紧急开关", "kind": "creative",
        "status": "paused", "work_log": "写了一半", "chat_id": "1057020972",
    })
    pipeline = FakePipeline()
    coordinator = AutonomousCoordinator(pipeline)

    new_sess = coordinator._ensure_work_session("1057020972", {"title": "星光扭蛋机网页"})
    assert new_sess["session_id"] != "sess_old_01"
    assert new_sess["title"] == "星光扭蛋机网页"

    resumed = coordinator._ensure_work_session(
        "1057020972", {"title": "继续写紧急开关", "resume_session_id": "sess_old_01"},
    )
    assert resumed["session_id"] == "sess_old_01"
    assert resumed["status"] == "active"
