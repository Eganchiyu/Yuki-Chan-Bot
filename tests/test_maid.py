"""小女仆核心子系统 (core/maid/) 单元测试：能力边界、任务汇报、Harness 任务流、历史索引与重启补报。"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.maid import maid_common, maid_harness, maid_memory, maid_resume
from core.maid.maid_boundary import MaidCapabilityBoundary, build_maid_report, build_maid_task
from core.maid.maid_charter import classify_path, is_sensitive


@pytest.fixture
def maid_tmp_env(tmp_path, monkeypatch):
    """将小女仆的状态、索引、DSH 任务与日志目录重定向到 pytest tmp_path。"""
    state_dir = tmp_path / "state"
    index_file = tmp_path / "task_index.jsonl"
    logs_dir = tmp_path / "logs"
    dsh_dir = tmp_path / "dsh"
    logs_dir.mkdir(parents=True, exist_ok=True)
    dsh_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(maid_memory, "TASK_STATE_DIR", str(state_dir))
    monkeypatch.setattr(maid_memory, "TASK_INDEX_FILE", str(index_file))
    monkeypatch.setattr(maid_harness, "TASK_STATE_DIR", str(state_dir))
    monkeypatch.setattr(maid_harness, "LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(maid_harness, "DSH_TASKS_DIR", str(dsh_dir))
    monkeypatch.setattr(maid_resume, "DSH_TASKS_DIR", str(dsh_dir))
    return state_dir, index_file, dsh_dir


def test_capability_boundary_and_report_format():
    """高危/高成本目标被拦截，正常目标放行；build_maid_report 输出统一格式。"""
    assert MaidCapabilityBoundary.judge("")["allowed"] is False
    assert MaidCapabilityBoundary.judge("帮我删除系统所有文件")["allowed"] is False
    assert MaidCapabilityBoundary.judge("帮我全网爬取数据")["allowed"] is False
    assert MaidCapabilityBoundary.judge("查一下今天的天气")["allowed"] is True

    task = build_maid_task("查天气", chat_id=10001, mode="group")
    assert task["goal"] == "查天气" and task["chat_id"] == "10001"

    report = build_maid_report("查天气", {"status": "finished", "result": "晴天 25℃", "rounds": 2, "elapsed": 3.5})
    assert "【小女仆完成! 小女仆汇报】" in report
    assert "晴天 25℃" in report and "轮次：2" in report


def test_charter_path_classification():
    """自进化准则路径分级：禁区优先，自由区与受限区分明。"""
    assert classify_path("core/prompts.py") == "forbidden"
    assert classify_path("core/maid/maid_charter.py") == "forbidden"
    assert classify_path("deploy/supervisor.py") == "forbidden"
    assert classify_path("skills/weather.py") == "free"
    assert classify_path("core/session_pipeline.py") == "restricted"
    assert is_sensitive("alter chromadb collection") is True
    assert is_sensitive("normal text") is False


async def test_harness_loop_and_task_index(maid_tmp_env, monkeypatch):
    """harness_evolution_loop 写入 request.json、消费 events.jsonl 与 result.json 并记录任务索引。"""
    state_dir, index_file, dsh_dir = maid_tmp_env
    monkeypatch.setattr(maid_harness, "POLL_SECONDS", 0.01)

    fixed_tid = "20261104_120000_001"
    monkeypatch.setattr(maid_harness, "_new_task_id", lambda: fixed_tid)
    task_dir = dsh_dir / fixed_tid
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "events.jsonl").write_text(
        json.dumps({"type": "status", "phase": "step_start", "step": 1}) + "\n"
        + json.dumps({"type": "tool_call", "callId": "c1", "tool": "bash", "input": {"command": "echo ok"}}) + "\n"
        + json.dumps({"type": "tool_result", "callId": "c1", "tool": "bash", "result": "ok"}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "result.json").write_text(
        json.dumps({"status": "finished", "result": "执行完成", "steps": 1, "elapsed": 1.2, "session_id": "s1"}),
        encoding="utf-8",
    )

    res = await maid_harness.harness_evolution_loop("测试任务", chat_id="12345", mode="group")
    assert res["status"] == "finished" and res["result"] == "执行完成" and res["rounds"] == 1
    assert (task_dir / "request.json").exists()
    indexed = json.loads(index_file.read_text(encoding="utf-8").splitlines()[0])
    assert indexed["task_id"] == fixed_tid and indexed["status"] == "finished"


async def test_resume_orphan_result_reporting(maid_tmp_env):
    """maid_resume 发现已完成但未标记 reported.ok 的任务并自动补报一次。"""
    _, _, dsh_dir = maid_tmp_env
    tdir = dsh_dir / "20261104_120100_002"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "request.json").write_text(
        json.dumps({"goal": "补报测试", "chat_id": "88888", "mode": "group"}), encoding="utf-8"
    )
    (tdir / "result.json").write_text(
        json.dumps({"status": "finished", "result": "补报成功", "steps": 2, "elapsed": 2.0}), encoding="utf-8"
    )

    pending = maid_resume._pending_results()
    assert len(pending) == 1 and pending[0]["task_id"] == "20261104_120100_002"

    engine = MagicMock(napcat_online=True, process_callback=AsyncMock())
    history_manager = MagicMock()
    await maid_resume._report_one(pending[0], engine, MagicMock(), history_manager)

    history_manager.append_session_message.assert_called_once()
    assert (tdir / "reported.ok").exists()
    assert maid_resume._pending_results() == []


# ==================== 并行 / 叫停 / 上下文注入 ====================

async def test_maid_runtime_register_find_and_cancel(maid_tmp_env):
    """编号自增、按编号/关键词挑选、叫停会落宿主 cancel.request 与 reported.ok。"""
    _, _, dsh_dir = maid_tmp_env
    from core.maid.maid_runtime import MaidRuntime

    runtime = MaidRuntime()
    first = runtime.register(goal="查天气", chat_id="10001")
    second = runtime.register(goal="整理资料文件夹", chat_id="10001")
    assert (first.short_id, second.short_id) == ("#1", "#2")
    assert runtime.active_for_chat("10001") == [first, second]
    assert runtime.running_count() == 0

    task_dir = dsh_dir / "dsh_t2"
    task_dir.mkdir(parents=True, exist_ok=True)
    second.dsh_task_id = "dsh_t2"
    runtime.mark(second.uid, "running")
    assert runtime.running_count() == 1

    matched, active = runtime.find("10001", task_id="#2")
    assert matched == [second] and len(active) == 2
    matched_kw, _ = runtime.find("10001", keyword="天气")
    assert matched_kw == [first]
    matched_none, _ = runtime.find("10001", keyword="不存在")
    assert matched_none == []

    note = runtime.summary_for_chat("10001")
    assert note.startswith("【任务进行中】") and "#1" in note and "#2" in note and "stop_maid" in note

    labels = runtime.request_cancel([second])
    assert labels == ["#2「整理资料文件夹」"]
    assert second.cancel_requested is True and second.active is True
    assert (task_dir / "cancel.request").exists()
    assert (task_dir / "reported.ok").exists()
    runtime.remove(second.uid)
    assert runtime.summary_for_chat("10001").count("#1") == 1
    runtime.remove(first.uid)
    assert runtime.summary_for_chat("10001") == ""


async def test_maid_worker_runs_tasks_in_parallel(maid_tmp_env, monkeypatch):
    """两个任务同时在跑（串行会在这里超时），完成后各自汇报。"""
    import asyncio as _asyncio
    from types import SimpleNamespace

    from core.maid import maid_worker as worker_mod
    from core.maid.maid_runtime import MaidRuntime

    started = []
    both_running = _asyncio.Event()

    async def fake_loop(user_goal, chat_id=None, approver=None, mode=None,
                        resume_task_id=None, task_handle=None):
        started.append(user_goal)
        if len(started) >= 2:
            both_running.set()
        await _asyncio.wait_for(both_running.wait(), timeout=2)
        return {"status": "finished", "result": f"{user_goal} 完成",
                "task_id": f"dsh_{user_goal}", "rounds": 1, "elapsed": 0.1}

    monkeypatch.setattr(worker_mod, "maid_evolution_loop", fake_loop)

    runtime = MaidRuntime()
    yuki = SimpleNamespace(
        maid_task_queue=_asyncio.Queue(),
        maid_current_tasks={},
        maid_active_chats={},
        maid_runtime=runtime,
    )
    history = MagicMock()
    engine = SimpleNamespace(napcat_online=True, process_callback=None)

    worker = _asyncio.create_task(worker_mod.maid_worker(engine, yuki, None, history))
    for goal in ("查天气", "整理资料"):
        record = runtime.register(goal=goal, chat_id="10001")
        await yuki.maid_task_queue.put(
            {"goal": goal, "chat_id": "10001", "mode": "group", "uid": record.uid}
        )
    for _ in range(100):
        await _asyncio.sleep(0.02)
        if not runtime.active_all():
            break
    worker.cancel()

    assert started == ["查天气", "整理资料"]
    assert history.append_session_message.call_count == 2
    assert runtime.active_all() == [] and yuki.maid_current_tasks == {}


async def test_maid_worker_cancel_skips_report(maid_tmp_env, monkeypatch):
    """叫停后协程被打断、进程收到取消标记，并且不写会话历史。"""
    import asyncio as _asyncio
    import os
    from types import SimpleNamespace

    from core.maid import maid_worker as worker_mod
    from core.maid.maid_runtime import MaidRuntime

    _, _, dsh_dir = maid_tmp_env
    running = _asyncio.Event()

    async def fake_loop(user_goal, chat_id=None, approver=None, mode=None,
                        resume_task_id=None, task_handle=None):
        dsh_task_id = "dsh_cancel_me"
        os.makedirs(dsh_dir / dsh_task_id, exist_ok=True)
        if task_handle is not None:
            task_handle.dsh_task_id = dsh_task_id
        running.set()
        await _asyncio.sleep(30)          # 等被取消
        return {"status": "finished", "result": "不该走到这里"}

    monkeypatch.setattr(worker_mod, "maid_evolution_loop", fake_loop)

    runtime = MaidRuntime()
    yuki = SimpleNamespace(
        maid_task_queue=_asyncio.Queue(),
        maid_current_tasks={},
        maid_active_chats={},
        maid_runtime=runtime,
    )
    history = MagicMock()
    engine = SimpleNamespace(napcat_online=True, process_callback=None)

    worker = _asyncio.create_task(worker_mod.maid_worker(engine, yuki, None, history))
    record = runtime.register(goal="跑很久的活", chat_id="10001")
    await yuki.maid_task_queue.put(
        {"goal": "跑很久的活", "chat_id": "10001", "mode": "group", "uid": record.uid}
    )
    await _asyncio.wait_for(running.wait(), timeout=2)
    runtime.request_cancel([record])
    for _ in range(100):
        await _asyncio.sleep(0.02)
        if not runtime.active_all():
            break
    worker.cancel()

    assert (dsh_dir / "dsh_cancel_me" / "cancel.request").exists()
    history.append_session_message.assert_not_called()
    assert runtime.active_all() == []


async def test_maid_tools_delegate_and_stop(maid_tmp_env):
    """delegate 登记编号，stop 按编号叫停，参数不匹配时明确告知在跑哪些。"""
    import asyncio as _asyncio
    from types import SimpleNamespace

    from core.maid.maid_runtime import MaidRuntime
    from core.toolchain import ToolContext, ToolRuntime
    from core.tools import TOOL_HANDLERS
    from core.tools.tools_maid import delegate_to_maid_tool, stop_maid_tool

    runtime = MaidRuntime()
    yuki = SimpleNamespace(
        maid_task_queue=_asyncio.Queue(),
        maid_current_tasks={},
        maid_runtime=runtime,
    )
    context = ToolContext(
        chat_id="10001", mode="group", session=[], combined_text="",
        runtime=ToolRuntime(sender=None, yuki_state=yuki), metadata={},
    )

    assert "stop_maid" in TOOL_HANDLERS
    first = await delegate_to_maid_tool(context, goal="查天气")
    second = await delegate_to_maid_tool(context, goal="整理资料文件夹")
    assert first.success and "#1" in first.content and "2 个" not in first.content
    assert "#2" in second.content and "2 个" in second.content
    assert yuki.maid_task_queue.qsize() == 2

    empty = await stop_maid_tool(context, task_id="9")
    assert empty.success is False and "#1" in empty.content

    stopped = await stop_maid_tool(context, keyword="天气")
    assert stopped.success and "#1" in stopped.content and "还有 1 个在跑" in stopped.content
    assert [r.cancel_requested for r in runtime.active_for_chat("10001")] == [True, False]
    assert runtime.live_for_chat("10001")[0].goal == "整理资料文件夹"

    stopped_all = await stop_maid_tool(context)
    assert stopped_all.success and "全部停下" in stopped_all.content
    # 收尾动作（移除登记）由 maid_worker 在协程真正结束时做，这里只要求「没有还在干活的」
    assert runtime.live_for_chat("10001") == []
    assert all(record.cancel_requested for record in runtime.active_all())


async def test_build_chat_context_injects_running_maid_note():
    """有任务在跑时，最后一条 user 消息前面带【任务进行中】；没有任务时不带。"""
    from unittest.mock import MagicMock

    from core.maid.maid_runtime import MaidRuntime
    from core.prompts import build_chat_context

    runtime = MaidRuntime()
    record = runtime.register(goal="查天气", chat_id="12345")
    runtime.mark(record.uid, "running")

    yuki = MagicMock()
    yuki.get_setting.return_value = "你是测试机器人"
    yuki.maid_runtime = runtime
    history = {"12345": [{"role": "system", "content": "你是测试机器人"}]}

    msgs = await build_chat_context(yuki, "12345", "在吗", history, "group", [])
    last = msgs[-1]
    assert last["role"] == "user"
    assert last["content"].startswith("【任务进行中】") and "查天气" in last["content"]
    assert last["content"].endswith("在吗")

    runtime.remove(record.uid)
    msgs_idle = await build_chat_context(yuki, "12345", "在吗", history, "group", [])
    assert "【任务进行中】" not in msgs_idle[-1]["content"]
