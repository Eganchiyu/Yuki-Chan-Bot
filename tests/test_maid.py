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
