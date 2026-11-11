"""P0 聚焦模式现状快照测试与 B1/B5 缺陷复现测试。"""
from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.engine.engine_reply as er
import core.phone_focus as pf
from core.engine.engine import YukiEngine
from core.engine.engine_reply import EngineReplyService
from core.phone_focus import SUMMARY_PREFIX, PhoneFocusManager
from core.toolchain import (
    SKIP_REPLY_MARKER,
    FunctionRegistry,
    ToolCallManager,
    ToolResult,
    ToolSpec,
)
from core.tools import TOOL_SPECS


class InMemoryHistory:
    """轻量内存 HistoryManager 替身，完整保留 append / get / replace / load 语义。"""

    def __init__(self, sessions: dict[str, list[dict]] | None = None):
        self.data: dict[str, list[dict]] = {
            str(k): [dict(m) for m in v] for k, v in (sessions or {}).items()
        }

    def get_session(self, chat_id: str, system_content: str | None = None) -> list[dict]:
        cid = str(chat_id)
        sess = self.data.setdefault(cid, [])
        if system_content and (not sess or sess[0].get("role") != "system"):
            sess.insert(0, {"role": "system", "content": system_content})
        return [dict(m) for m in sess]

    def replace_session(self, chat_id: str, session: list[dict]) -> list[dict]:
        cid = str(chat_id)
        self.data[cid] = [dict(m) for m in session]
        return [dict(m) for m in self.data[cid]]

    def append_session_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        system_content: str | None = None,
        *,
        save_immediately: bool = True,
        return_snapshot: bool = True,
        **extra,
    ):
        cid = str(chat_id)
        sess = self.data.setdefault(cid, [])
        item = {"role": role, "content": content}
        item.update(extra)
        sess.append(item)
        return [dict(m) for m in sess] if return_snapshot else None

    def load(self, *, copy_result: bool = True) -> dict[str, list[dict]]:
        return {k: [dict(m) for m in v] for k, v in self.data.items()}


def _build_reply_service(history: InMemoryHistory | None = None, max_rounds: int = 4):
    history = history or InMemoryHistory({
        "c1": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "阿澄: 帮我点杯奶茶"},
        ]
    })
    yuki = SimpleNamespace(
        message_buffer=defaultdict(list),
        pop_buffer=lambda cid: yuki.message_buffer.pop(str(cid), []),
        maid_current_tasks={},
    )
    sender = SimpleNamespace(send=AsyncMock(), send_local_file=AsyncMock())

    reg = FunctionRegistry()
    reg.scan_and_register(TOOL_SPECS)

    # 用假 handler 替换 phone_start / phone_action，避免真实触发 ADB
    async def fake_phone_start(context, goal: str = "") -> ToolResult:
        pf.phone_focus_manager.enter(context.chat_id, goal=goal)
        if goal:
            pf.phone_focus_manager.record_step(context.chat_id, f"开始操作手机: {goal}")
        return ToolResult(
            success=True,
            content="【已进入手机聚焦模式】首屏控件树 [#1 外卖]",
            data={"phone_focus": "entered", "goal": goal, "no_persist": False},
            name="phone_start",
        )

    async def fake_phone_action(context, action: str = "inspect", target: str = "", note: str = "", remember: bool = True, **_kw) -> ToolResult:
        pf.phone_focus_manager.record_step(context.chat_id, f"{action} {target}".strip(), note)
        return ToolResult(
            success=True,
            content=f"已执行 {action} {target} -> 控件树 [#2 立即下单]",
            data={"action": action, "steps": [f"{action} {target}".strip()], "note": note, "no_persist": not remember},
            name="phone_action",
        )

    reg.register(ToolSpec(
        name="phone_start",
        description="拿起手机",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}}},
        handler=fake_phone_start,
    ))
    reg.register(ToolSpec(
        name="phone_action",
        description="操作手机",
        parameters={"type": "object", "properties": {"action": {"type": "string"}, "target": {"type": "string"}, "note": {"type": "string"}}},
        handler=fake_phone_action,
    ))

    tool_mgr = ToolCallManager(reg, max_rounds=max_rounds)
    svc = EngineReplyService(
        yuki=yuki,
        history=history,
        sender=sender,
        tool_registry=reg,
        tool_manager=tool_mgr,
        get_process_callback=lambda: None,
        get_image_store=lambda: None,
        get_meme_processor=lambda: None,
    )
    return svc, history, yuki, sender


@pytest.fixture(autouse=True)
def _clean_focus_state(monkeypatch):
    """每个测试独立重置聚焦状态机与调用延迟。"""
    monkeypatch.setattr(er.cfg.timing, "tool_call_delay_seconds", 0.0)
    pf.phone_focus_manager._states.clear()
    yield
    pf.phone_focus_manager._states.clear()


# ==================== 1. 同轮切换 + 4. 禁止同轮重入 ====================

async def test_snapshot_same_turn_view_switch_and_forbid_reentry(monkeypatch):
    """同轮内 phone_start -> 下一轮立即切换聚焦工具集；phone_finish -> 立即切回常态并收起 phone_start 防重入。"""
    svc, history, _, _ = _build_reply_service()
    seen_tool_sets: list[set[str]] = []

    scripted_responses = [
        # Round 1 (常态视图): 调用 phone_start
        {
            "role": "assistant",
            "content": "我拿手机看看~",
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "phone_start", "arguments": '{"goal": "买奶茶"}'},
            }],
        },
        # Round 2 (已切入聚焦视图): 调用 phone_action
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_2",
                "function": {"name": "phone_action", "arguments": '{"action": "tap", "target": "1", "note": "选奶茶"}'},
            }],
        },
        # Round 3 (仍在聚焦视图): 调用 phone_finish
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_3",
                "function": {"name": "phone_finish", "arguments": '{"summary": "帮阿澄买好了珍珠奶茶"}'},
            }],
        },
        # Round 4 (同轮刚退出，恢复常态但收起 phone_start): 输出最终回复
        {
            "role": "assistant",
            "content": "奶茶已经下单好啦~",
        },
    ]

    async def fake_llm_chat_raw(messages, tools=None, **_kwargs):
        names = {t["function"]["name"] for t in (tools or [])}
        seen_tool_sets.append(names)
        return dict(scripted_responses.pop(0))

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm_chat_raw)

    session = history.get_session("c1")
    raw_ans, clean_ans = await svc.chat_with_tools(
        "c1", "阿澄: 帮我点杯奶茶", session, "group", list(session)
    )
    assert clean_ans == "奶茶已经下单好啦~"
    assert len(seen_tool_sets) == 4

    # Round 1: 常态，有 phone_start & search_diary，无 phone_action / phone_finish
    assert "phone_start" in seen_tool_sets[0]
    assert "search_diary" in seen_tool_sets[0]
    assert "phone_action" not in seen_tool_sets[0]
    assert "phone_finish" not in seen_tool_sets[0]

    # Round 2 & 3: 聚焦视图，有 phone_action / phone_macro / phone_finish / skip，无 phone_start / search_diary
    for idx in (1, 2):
        assert {"phone_action", "phone_macro", "phone_finish", "skip"} <= seen_tool_sets[idx]
        assert "phone_start" not in seen_tool_sets[idx]
        assert "search_diary" not in seen_tool_sets[idx]

    # Round 4: 同轮退出后切回常态（search_diary 恢复），但禁止同轮重入（phone_start 被收起）
    assert "search_diary" in seen_tool_sets[3]
    assert "phone_start" not in seen_tool_sets[3]
    assert "phone_action" not in seen_tool_sets[3]
    assert "phone_finish" not in seen_tool_sets[3]

    # 下一轮新对话时，phone_start 重新暴露
    seen_next_turn: list[set[str]] = []

    async def fake_next_turn_llm(messages, tools=None, **_kwargs):
        seen_next_turn.append({t["function"]["name"] for t in (tools or [])})
        return {"role": "assistant", "content": "嗯嗯！"}

    monkeypatch.setattr(er, "llm_chat_raw", fake_next_turn_llm)
    await svc.chat_with_tools("c1", "阿澄: 谢谢", history.get_session("c1"), "group", history.get_session("c1"))
    assert "phone_start" in seen_next_turn[0]


# ==================== 2. 插话保序 ====================

async def test_snapshot_pending_messages_preserved_in_order_across_rewrite(monkeypatch):
    """聚焦期间通过 merge_pending_messages 插入的群友消息，在退出覆写后严格保序留存。"""
    svc, history, yuki, _ = _build_reply_service()
    captured_round3_messages: list[dict] = []

    async def fake_llm_chat_raw(messages, tools=None, **_kwargs):
        round_no = fake_llm_chat_raw.calls
        fake_llm_chat_raw.calls += 1
        if round_no == 0:
            # 执行 phone_start 期间有群友插话进入 buffer
            yuki.message_buffer["c1"].append({"content": "群友B: 顺便帮我带一杯三分糖柠檬水"})
            return {
                "role": "assistant",
                "content": "我先打开手机~",
                "tool_calls": [{
                    "id": "c_start",
                    "function": {"name": "phone_start", "arguments": '{"goal": "买奶茶和柠檬水"}'},
                }],
            }
        if round_no == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "c_fin",
                    "function": {"name": "phone_finish", "arguments": '{"summary": "买了奶茶和三分糖柠檬水"}'},
                }],
            }
        captured_round3_messages.extend(messages)
        return {"role": "assistant", "content": "两杯都买好啦！"}

    fake_llm_chat_raw.calls = 0
    monkeypatch.setattr(er, "llm_chat_raw", fake_llm_chat_raw)

    session = history.get_session("c1")
    await svc.chat_with_tools("c1", "阿澄: 帮我点杯奶茶", session, "group", list(session))

    # 1) 持久化历史：阶段思考与工具消息被抹除，原消息 -> 群友B插话 -> 手机总结 严格保序
    persisted = history.get_session("c1")
    assert [(m["role"], m["content"]) for m in persisted] == [
        ("system", "sys"),
        ("user", "阿澄: 帮我点杯奶茶"),
        ("user", "群友B: 顺便帮我带一杯三分糖柠檬水"),
        ("user", f"{SUMMARY_PREFIX}买了奶茶和三分糖柠檬水"),
    ]

    # 2) 当轮内存 tool_messages（Round 3 喂给模型的上下文）：插话同样排在总结之前，且无残留 tool 消息
    assert all(m.get("role") != "tool" for m in captured_round3_messages)
    user_contents = [m["content"] for m in captured_round3_messages if m.get("role") == "user"]
    assert any("群友B: 顺便帮我带一杯三分糖柠檬水" in c for c in user_contents)
    assert SUMMARY_PREFIX in user_contents[-1]


# ==================== 3. 闲置超过 5 轮自动退出 ====================

async def test_snapshot_idle_more_than_five_turns_auto_exits(monkeypatch):
    """通过主循环连续 5 轮纯聊天不退出，第 6 轮纯聊天结束后自动退出并写入兜底总结。"""
    svc, history, _, _ = _build_reply_service()

    # 先进入聚焦并记录一步
    pf.phone_focus_manager.enter("c1", goal="看物流")
    pf.phone_focus_manager.record_step("c1", "launch 菜鸟", "查快递")
    history.append_session_message(
        "c1", "tool", '{"success": true}', name="phone_action", phone_focus_work=True
    )

    async def fake_llm_chat_raw(messages, tools=None, **_kwargs):
        return {"role": "assistant", "content": "我们在闲聊~"}

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm_chat_raw)

    # 前 5 轮闲置：仍处于聚焦模式
    for _ in range(5):
        sess = history.get_session("c1")
        await svc.chat_with_tools("c1", "闲聊", sess, "group", list(sess))
        assert pf.phone_focus_manager.is_focused("c1") is True

    # 第 6 轮闲置：自动退出并写入兜底总结
    sess = history.get_session("c1")
    await svc.chat_with_tools("c1", "还在闲聊", sess, "group", list(sess))
    assert pf.phone_focus_manager.is_focused("c1") is False

    persisted = history.get_session("c1")
    assert all(m.get("role") != "tool" for m in persisted)
    assert persisted[-1]["role"] == "user"
    assert persisted[-1]["content"].startswith(SUMMARY_PREFIX)
    assert "看物流" in persisted[-1]["content"]


# ==================== 5. 四条返回出口的收尾次数 ====================

@pytest.mark.parametrize("exit_kind", ["reply", "filtered", "skip", "exhausted"])
async def test_snapshot_all_turn_exits_call_after_turn_once(monkeypatch, exit_kind):
    """正常回复 / 内容过滤 / skip / 轮次用尽 四条出口，每轮都恰好触发一次聚焦与折叠收尾。"""
    svc, history, _, _ = _build_reply_service(max_rounds=2)

    focus_after_calls: list[tuple[str, bool]] = []
    prune_after_calls: list[tuple[str, bool]] = []

    from core.focus import focus_manager

    orig_focus_after = focus_manager.after_turn
    orig_prune_after = svc.pruner.after_turn

    def spy_focus_after(cid, used, *, history=None):
        focus_after_calls.append((str(cid), bool(used)))
        return orig_focus_after(cid, used, history=history)

    def spy_prune_after(cid, executed):
        prune_after_calls.append((str(cid), bool(executed)))
        return orig_prune_after(cid, executed)

    monkeypatch.setattr(focus_manager, "after_turn", spy_focus_after)
    monkeypatch.setattr(svc.pruner, "after_turn", spy_prune_after)

    async def fake_llm_chat_raw(messages, tools=None, **_kwargs):
        if exit_kind == "reply":
            return {"role": "assistant", "content": "普通回复"}
        if exit_kind == "filtered":
            return {"role": "assistant", "content": "", "_finish_reason": "content_filter"}
        if exit_kind == "skip":
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c_skip", "function": {"name": "skip", "arguments": '{"reason":"潜水"}'}}],
            }
        # exhausted: 每一轮都请求工具，直到 max_rounds=2 耗尽
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c_act", "function": {"name": "phone_action", "arguments": '{"action":"inspect"}'}}],
        }

    async def fake_llm_chat(messages, **_kwargs):
        return "轮次用尽后的兜底文字"

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm_chat_raw)
    monkeypatch.setattr(er, "llm_chat", fake_llm_chat)

    sess = history.get_session("c1")
    raw_ans, clean_ans = await svc.chat_with_tools("c1", "测试", sess, "group", list(sess))

    if exit_kind == "reply":
        assert clean_ans == "普通回复"
    elif exit_kind == "filtered":
        assert clean_ans == "Filtered"
    elif exit_kind == "skip":
        assert clean_ans == SKIP_REPLY_MARKER
    elif exit_kind == "exhausted":
        assert clean_ans == "轮次用尽后的兜底文字"

    assert len(focus_after_calls) == 1
    assert len(prune_after_calls) == 1


# ==================== B1 修复验证（同批专精工具 + finish 时工作记录不泄漏） ====================

async def test_b1_same_batch_action_and_finish_does_not_leak_work_record(monkeypatch):
    """当模型在同一批 tool_calls 中同时调用 phone_action 与 phone_finish 时，历史中不应残留 phone_action 记录。"""
    svc, history, _, _ = _build_reply_service()
    pf.phone_focus_manager.enter("c1", goal="点咖啡")

    responses = [
        {
            "role": "assistant",
            "content": "点好收工~",
            "tool_calls": [
                {"id": "c_act", "function": {"name": "phone_action", "arguments": '{"action": "tap", "target": "2", "note": "点击下单"}'}},
                {"id": "c_fin", "function": {"name": "phone_finish", "arguments": '{"summary": "已下单美式咖啡"}'}},
            ],
        },
        {
            "role": "assistant",
            "content": "美式咖啡点好啦！",
        },
    ]

    async def fake_llm_chat_raw(messages, tools=None, **_kwargs):
        return dict(responses.pop(0))

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm_chat_raw)

    sess = history.get_session("c1")
    await svc.chat_with_tools("c1", "阿澄: 帮我点杯咖啡", sess, "group", list(sess))

    persisted = history.get_session("c1")
    # 断言历史里没有任何 tool 消息残留，且最后一条是总结
    assert [m for m in persisted if m.get("role") == "tool"] == []
    assert persisted[-1]["role"] == "user"
    assert SUMMARY_PREFIX in persisted[-1]["content"]


# ==================== B5 修复验证（重启后孤儿聚焦记录清扫） ====================

def test_b5_startup_sweeps_orphan_focus_work_records():
    """引擎启动时应清扫历史中没有活跃聚焦状态的孤儿工作记录，原地替换为兜底总结并保留期间群聊。"""
    history = InMemoryHistory({
        "c_orphan": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "阿澄: 帮我看下淘宝物流"},
            {"role": "assistant", "content": "我打开淘宝看看~", "is_tool_thought": True, "phone_focus_work": True},
            {"role": "tool", "name": "phone_start", "content": '{"success":true}', "phone_focus_work": True},
            {"role": "user", "content": "群友B: 顺便看看今晚吃啥"},
            {"role": "tool", "name": "phone_action", "content": '{"success":true}', "phone_focus_work": True},
            {"role": "assistant", "content": "之后普通聊天回复"},
        ]
    })
    yuki_state = SimpleNamespace(
        message_buffer=defaultdict(list),
        maid_current_tasks={},
    )
    YukiEngine(MagicMock(), history, yuki_state, MagicMock())

    cleaned = history.get_session("c_orphan")
    # 孤儿 tool 与 is_tool_thought 工作记录应被清除
    assert [m for m in cleaned if m.get("role") == "tool"] == []
    assert [m for m in cleaned if m.get("is_tool_thought")] == []
    # 群友消息与后续正常回复保留，且插入了重启未正常结束的兜底总结
    contents = [m["content"] for m in cleaned]
    assert "阿澄: 帮我看下淘宝物流" in contents
    assert "群友B: 顺便看看今晚吃啥" in contents
    assert "之后普通聊天回复" in contents
    assert any("重启前未正常结束" in c for c in contents)
