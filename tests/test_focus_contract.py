"""聚焦模式通用契约测试 (tests/test_focus_contract.py)。

对所有已注册的 FocusDomain 参数化执行 9 项核心契约校验；
未来新增聚焦模式（如 art）只需在 REGISTERED_DOMAIN_NAMES 中加入域名（或自动从 focus_manager 发现），
跑通本文件即可证明新模式完整符合聚焦架构规范。
"""
from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.engine.engine_reply as er
from core.engine.engine_reply import EngineReplyService
from core.focus import (
    FocusDomain,
    ToolView,
    focus_finish_spec,
    focus_manager,
    focus_start_spec,
)
from core.toolchain import FunctionRegistry, ToolCallManager, ToolResult, ToolSpec
from core.tools import TOOL_SPECS

REGISTERED_DOMAIN_NAMES = [d.name for d in focus_manager.domains()]


class ContractHistory:
    """契约测试专用内存 HistoryManager。"""

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


def _build_contract_harness(domain: FocusDomain, *, abort_entry: bool = False):
    """为任意给定的 FocusDomain 构造离线可执行的注册表与 EngineReplyService。"""
    history = ContractHistory({
        "c_contract": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": f"用户: 请进入{domain.title}模式处理任务"},
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

    # 为目标域挂载离线确定性的入口、专精与退出 handler（不依赖真实外设/网络）
    async def _entry_overview(context, goal: str = "") -> ToolResult:
        if abort_entry:
            return ToolResult(
                success=False,
                content=f"{domain.title}设备未就绪",
                data={"focus": "aborted", f"{domain.name}_focus": "aborted", "no_persist": True},
                error="device_unavailable",
                name=domain.entry_tool,
            )
        if goal:
            focus_manager.record_step(context.chat_id, f"开始{domain.title}: {goal}", domain=domain.name)
        return ToolResult(
            success=True,
            content=f"【已进入{domain.title}聚焦模式】首屏概览就绪",
            data={"focus": "entered", f"{domain.name}_focus": "entered", "goal": goal, "no_persist": False},
            name=domain.entry_tool,
        )

    reg.register(focus_start_spec(
        domain,
        description=f"进入{domain.title}模式",
        handler=_entry_overview,
        wrap_enter=True,
    ))
    for d_tool in sorted(domain.domain_tools):
        async def _domain_action(context, note: str = "执行步骤", _tname=d_tool, **_kw) -> ToolResult:
            focus_manager.record_step(context.chat_id, f"执行 {_tname}", note, domain=domain.name)
            return ToolResult(
                success=True,
                content=f"{_tname} 输出结果",
                data={"note": note, "no_persist": False},
                name=_tname,
            )

        reg.register(ToolSpec(
            name=d_tool,
            description=f"{domain.title}专精工具 {d_tool}",
            parameters={"type": "object", "properties": {"note": {"type": "string"}}},
            handler=_domain_action,
        ))
    reg.register(focus_finish_spec(domain))

    tool_mgr = ToolCallManager(reg, max_rounds=4)
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
    return svc, reg, history, yuki


@pytest.fixture(autouse=True)
def _reset_focus_state(monkeypatch):
    monkeypatch.setattr(er.cfg.timing, "tool_call_delay_seconds", 0.0)
    focus_manager._states.clear()
    yield
    focus_manager._states.clear()


# ==================== 1 & 2. 常态视图与聚焦视图契约 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
def test_contract_default_and_focus_views(domain_name: str):
    """契约 1 & 2：常态视图只见 entry_tool 不见专精与 exit_tool；聚焦视图等于 focus_allowed ∩ 已注册工具。"""
    domain = focus_manager.domain(domain_name)
    _, reg, _, _ = _build_contract_harness(domain)
    all_registered = set(reg.list_functions())

    # 常态视图
    default_view = ToolView.resolve(reg, focus_manager, "c_contract")
    assert domain.entry_tool in default_view.visible
    assert domain.exit_tool not in default_view.visible
    assert domain.domain_tools.isdisjoint(default_view.visible)

    # 聚焦视图
    focus_manager.enter("c_contract", domain.name, goal="契约测试")
    focused_view = ToolView.resolve(reg, focus_manager, "c_contract")
    assert focused_view.visible == (all_registered & domain.focus_allowed)
    assert domain.entry_tool not in focused_view.visible
    assert domain.exit_tool in focused_view.visible
    assert domain.domain_tools <= focused_view.visible


# ==================== 3 & 7. 同轮切换视图 + 本轮退出后禁止同轮重入 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
async def test_contract_same_turn_switch_and_no_same_turn_reentry(monkeypatch, domain_name: str):
    """契约 3 & 7：同轮调用 entry_tool 后下一轮 LLM 视图立即切换；同轮调用 exit_tool 后收起 entry_tool 防重入。"""
    domain = focus_manager.domain(domain_name)
    svc, _, history, _ = _build_contract_harness(domain)
    sample_domain_tool = sorted(domain.domain_tools)[0]
    seen_views: list[set[str]] = []

    script = [
        {
            "role": "assistant",
            "content": "进入模式~",
            "tool_calls": [{"id": "c1", "function": {"name": domain.entry_tool, "arguments": '{"goal":"测试目标"}'}}],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c2", "function": {"name": sample_domain_tool, "arguments": '{"note":"第一步"}'}}],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c3", "function": {"name": domain.exit_tool, "arguments": '{"summary":"顺利完成任务"}'}}],
        },
        {
            "role": "assistant",
            "content": "任务完成啦~",
        },
    ]

    async def fake_llm(messages, tools=None, **_kw):
        seen_views.append({t["function"]["name"] for t in (tools or [])})
        return dict(script.pop(0))

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm)
    sess = history.get_session("c_contract")
    await svc.chat_with_tools("c_contract", "开始", sess, "group", list(sess))

    assert len(seen_views) == 4
    # 第 1 步常态：有 entry_tool
    assert domain.entry_tool in seen_views[0]
    assert sample_domain_tool not in seen_views[0]
    # 第 2、3 步聚焦：有专精工具和 exit_tool，无 entry_tool
    assert sample_domain_tool in seen_views[1] and domain.exit_tool in seen_views[1]
    assert domain.entry_tool not in seen_views[1]
    # 第 4 步同轮刚退出：恢复常态工具（如 search_diary），但禁止同轮重入（无 entry_tool）
    assert "search_diary" in seen_views[3]
    assert domain.entry_tool not in seen_views[3]
    assert sample_domain_tool not in seen_views[3]


# ==================== 4 & 5. 同批专精+退出不泄漏(B1) + 插话保序 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
async def test_contract_same_batch_finish_gate_and_pending_message_order(monkeypatch, domain_name: str):
    """契约 4 & 5：聚焦期间插话严格保序，且同批执行专精工具 + exit_tool 后历史只剩群聊与总结（B1）。"""
    domain = focus_manager.domain(domain_name)
    svc, _, history, yuki = _build_contract_harness(domain)
    sample_domain_tool = sorted(domain.domain_tools)[0]

    script = [
        {
            "role": "assistant",
            "content": "准备开始~",
            "tool_calls": [{"id": "c1", "function": {"name": domain.entry_tool, "arguments": '{"goal":"批量任务"}'}}],
        },
        {
            "role": "assistant",
            "content": "最后一步并收工~",
            "tool_calls": [
                {"id": "c2", "function": {"name": sample_domain_tool, "arguments": '{"note":"收尾操作"}'}},
                {"id": "c3", "function": {"name": domain.exit_tool, "arguments": '{"summary":"完成全部操作"}'}},
            ],
        },
        {
            "role": "assistant",
            "content": "全部搞定啦！",
        },
    ]

    async def fake_llm(messages, tools=None, **_kw):
        step = fake_llm.step
        fake_llm.step += 1
        if step == 0:
            yuki.message_buffer["c_contract"].append({"content": "群友插话: 顺便帮我看一眼"})
        return dict(script.pop(0))

    fake_llm.step = 0
    monkeypatch.setattr(er, "llm_chat_raw", fake_llm)

    sess = history.get_session("c_contract")
    await svc.chat_with_tools("c_contract", "开始", sess, "group", list(sess))

    persisted = history.get_session("c_contract")
    assert [m for m in persisted if m.get("role") == "tool"] == []
    assert [m for m in persisted if m.get("is_tool_thought")] == []
    assert [(m["role"], m["content"]) for m in persisted] == [
        ("system", "sys"),
        ("user", f"用户: 请进入{domain.title}模式处理任务"),
        ("user", "群友插话: 顺便帮我看一眼"),
        ("user", f"{domain.effective_summary_prefix}完成全部操作"),
    ]
    assert persisted[-1].get("is_focus_summary") is True
    assert persisted[-1].get("focus_domain") == domain.name


# ==================== 6. 闲置超过阈值自动退出并写兜底总结 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
def test_contract_idle_timeout_auto_exits(domain_name: str):
    """契约 6：连续闲置超过阈值后自动退出聚焦模式并生成包含目标与轨迹的兜底总结。"""
    domain = focus_manager.domain(domain_name)
    _, _, history, _ = _build_contract_harness(domain)

    focus_manager.enter("c_contract", domain.name, goal="长期目标")
    focus_manager.record_step("c_contract", "step_1", "步骤一", domain=domain.name)
    history.append_session_message(
        "c_contract",
        "tool",
        '{"success":true}',
        name=sorted(domain.domain_tools)[0],
        focus_work=domain.name,
    )

    limit = focus_manager._idle_limit_for(domain)
    for _ in range(limit):
        assert focus_manager.after_turn("c_contract", set(), history=history) is None
        assert focus_manager.is_focused("c_contract", domain.name) is True

    exit_res = focus_manager.after_turn("c_contract", set(), history=history)
    assert exit_res is not None and exit_res.reason == "idle"
    assert focus_manager.is_focused("c_contract") is False

    persisted = history.get_session("c_contract")
    assert [m for m in persisted if m.get("role") == "tool"] == []
    assert persisted[-1]["content"].startswith(domain.effective_summary_prefix)
    assert "长期目标" in persisted[-1]["content"]


# ==================== 8. 重启后孤儿记录被清扫 (B5) ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
def test_contract_startup_sweeps_orphan_records(domain_name: str):
    """契约 8：无活跃状态时，sweep_orphans 原地清扫该域残留的 focus_work 片段并保留期间群聊。"""
    domain = focus_manager.domain(domain_name)
    sample_tool = sorted(domain.domain_tools)[0]
    history = ContractHistory({
        "c_orphan": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "用户提问"},
            {"role": "assistant", "content": "阶段思考", "is_tool_thought": True, "focus_work": domain.name},
            {"role": "tool", "name": domain.entry_tool, "content": "{}", "focus_work": domain.name},
            {"role": "user", "content": "期间群友插话"},
            {"role": "tool", "name": sample_tool, "content": "{}", "focus_work": domain.name},
        ]
    })

    swept = focus_manager.sweep_orphans(history)
    assert swept == 3
    cleaned = history.get_session("c_orphan")
    assert [m for m in cleaned if m.get("role") == "tool"] == []
    assert [m for m in cleaned if m.get("is_tool_thought")] == []
    assert [m["content"] for m in cleaned[:3]] == ["sys", "用户提问", "期间群友插话"]
    assert cleaned[3]["content"].startswith(f"{domain.effective_summary_prefix}（重启前未正常结束）")
    assert cleaned[3].get("is_focus_summary") is True
    assert cleaned[3].get("focus_domain") == domain.name


# ==================== 9. 入口返回 aborted 时自动回滚状态 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
async def test_contract_entry_aborted_rolls_back_state(monkeypatch, domain_name: str):
    """契约 9：当入口工具返回 data={'focus': 'aborted'} 时，框架自动回滚聚焦状态。"""
    domain = focus_manager.domain(domain_name)
    svc, _, history, _ = _build_contract_harness(domain, abort_entry=True)

    script = [
        {
            "role": "assistant",
            "content": "试试看~",
            "tool_calls": [{"id": "c1", "function": {"name": domain.entry_tool, "arguments": '{"goal":"尝试连接"}'}}],
        },
        {
            "role": "assistant",
            "content": "设备没连上呢~",
        },
    ]

    async def fake_llm(messages, tools=None, **_kw):
        return dict(script.pop(0))

    monkeypatch.setattr(er, "llm_chat_raw", fake_llm)
    sess = history.get_session("c_contract")
    await svc.chat_with_tools("c_contract", "开始", sess, "group", list(sess))

    assert focus_manager.is_focused("c_contract") is False


# ==================== 10. 聚焦期间暂停日记总结 ====================

@pytest.mark.parametrize("domain_name", REGISTERED_DOMAIN_NAMES)
async def test_contract_diary_summarization_paused_while_focused(monkeypatch, domain_name: str):
    """契约 10：处于任意聚焦域期间，超长日记与空闲日记均暂停触发，避免半途总结工作过程。"""
    from config import cfg
    from core.engine.engine_diary import EngineDiaryService
    from tests.test_pipeline import _create_mock_pipeline

    pipeline = _create_mock_pipeline()
    session = [{"role": "system", "content": "sys"}] + [
        {"role": "user" if i % 2 else "assistant", "content": f"msg-{i}"}
        for i in range(cfg.DIARY_MAX_LENGTH + 3)
    ]
    pipeline.history_manager.append_session_message.return_value = session

    created = []
    monkeypatch.setattr("asyncio.create_task", lambda coro: created.append(coro) or coro.close())

    focus_manager.enter("c_contract", domain_name, goal="防日记截断测试")
    await pipeline.finalize_conversation({
        "chat_id": "c_contract",
        "answer_text": "回复",
        "answer_raw": "回复",
        "current_time_str": "2026-11-09 22:00",
    })
    assert created == []
    pipeline.history_manager.replace_session.assert_not_called()

    diary = EngineDiaryService(
        SimpleNamespace(save_diary=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not save"))),
        pipeline.history_manager,
    )
    await diary.summarize_idle_session("c_contract", session)
    pipeline.history_manager.replace_session.assert_not_called()

