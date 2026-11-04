"""小女仆子系统 (core/maid/) 单元测试：读文件防爆、墙钟预算、任务快照与续跑、终端审批与看图。"""
import asyncio
import json
import os

import pytest

from core.maid import maid_approval, maid_common, maid_loop, maid_memory, maid_runtime
from core.maid.maid_tools import read_file_content


@pytest.fixture
def maid_tmp_env(tmp_path, monkeypatch):
    """将小女仆的所有状态、索引与日志目录重定向到 pytest tmp_path。"""
    state_dir = tmp_path / "state"
    index_file = tmp_path / "task_index.jsonl"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(maid_memory, "TASK_STATE_DIR", str(state_dir))
    monkeypatch.setattr(maid_memory, "TASK_INDEX_FILE", str(index_file))
    monkeypatch.setattr(maid_loop, "LOGS_DIR", str(logs_dir))
    return state_dir, index_file


# ==================== read_file 防爆与分页 ====================

def test_read_file_truncation_pagination_and_guards(tmp_path):
    """单行超长截断、按行 offset 分页，以及拒绝目录和二进制文件。"""
    b64_file = tmp_path / "b64.txt"
    b64_file.write_text("A" * (900 * 1024), encoding="utf-8")
    res_long = read_file_content(str(b64_file))
    assert len(res_long) < 6000 and "截断" in res_long

    lines_file = tmp_path / "lines.txt"
    lines_file.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")
    first = read_file_content(str(lines_file), max_lines=5)
    assert "line4" in first and "line5" not in first and "offset=5" in first
    second = read_file_content(str(lines_file), max_lines=5, offset=95)
    assert "line95" in second and "line99" in second

    assert "目录" in read_file_content("core/maid")
    assert "二进制" in read_file_content("yuki_help.png")


# ==================== 预算、错误轮、快照与续跑 ====================

async def test_wall_clock_budget_and_parse_error_tolerance(maid_tmp_env, monkeypatch):
    """墙钟预算超时立即中止循环；JSON 解析错误不消耗有效轮次。"""
    calls = {"n": 0}

    async def slow_spin(messages):
        calls["n"] += 1
        await asyncio.sleep(0.08)
        return '{"thought":"spin","tool":"list_skills","args":{}}'

    monkeypatch.setattr(maid_common, "MAID_MAX_WALL_SECONDS", 0.12)
    monkeypatch.setattr(maid_loop, "call_cloud_maid_robust", slow_spin)
    timeout_res = await maid_loop.maid_evolution_loop("预算测试")
    assert timeout_res["status"] == "timeout" and calls["n"] <= 2 and "墙钟" in timeout_res["result"]

    monkeypatch.setattr(maid_common, "MAID_MAX_WALL_SECONDS", 60.0)
    replies = iter(["不是JSON", "还不是JSON", '{"thought":"done","tool":"finish","args":{"reason":"ok"}}'])
    monkeypatch.setattr(maid_loop, "call_cloud_maid_robust", lambda messages: asyncio.sleep(0, result=next(replies)))
    ok_res = await maid_loop.maid_evolution_loop("错误轮测试")
    assert ok_res["status"] == "finished" and ok_res["rounds"] == 1


async def test_snapshot_index_finish_and_resume(maid_tmp_env, monkeypatch):
    """任务快照读写、未完成列表、finish 自动清理快照写索引，以及 resume_task 恢复上下文续跑。"""
    state_dir, index_file = maid_tmp_env

    await maid_memory.save_task_state(
        task_id="t1", goal="写周报", messages=[{"role": "user", "content": "hi"}],
        round_no=2, last_step={"tool": "read_file"}, status="interrupted",
    )
    state = await maid_memory.load_task_state("t1")
    assert state["goal"] == "写周报" and state["round"] == 2
    assert [i["task_id"] for i in await maid_memory.list_unfinished_states()] == ["t1"]

    await maid_memory.append_task_index("t1", "写周报", "finished", "完成", rounds=3, elapsed=4.2)
    startup_ctx = await maid_memory.build_startup_context()
    assert "最近任务" in startup_ctx and "写周报" in startup_ctx and "未完成任务" in startup_ctx

    # finish 清理当前任务快照
    os.unlink(state_dir / "t1.json")
    index_file.unlink()

    async def fake_finish(messages):
        return '{"thought":"done","tool":"finish","args":{"reason":"完成"}}'

    monkeypatch.setattr(maid_loop, "call_cloud_maid_robust", fake_finish)
    fin_res = await maid_loop.maid_evolution_loop("结束清理测试", chat_id="42")
    assert fin_res["status"] == "finished" and fin_res["rounds"] == 1
    assert not list(state_dir.glob("*.json"))
    assert json.loads(index_file.read_text(encoding="utf-8").splitlines()[0])["status"] == "finished"

    # resume_task 恢复旧任务上下文并延续轮次
    await maid_memory.save_task_state(
        task_id="t_prev", goal="旧任务",
        messages=[{"role": "user", "content": "上半段进度"}, {"role": "assistant", "content": "已做完 A"}],
        round_no=4, status="interrupted",
    )

    async def fake_resume(messages):
        joined = " ".join(str(m.get("content")) for m in messages)
        if "已从任务 t_prev" not in joined:
            return '{"thought":"续跑","tool":"resume_task","args":{"task_id":"t_prev"}}'
        return '{"thought":"done","tool":"finish","args":{"reason":"续跑完成"}}'

    monkeypatch.setattr(maid_loop, "call_cloud_maid_robust", fake_resume)
    res_resume = await maid_loop.maid_evolution_loop("继续旧任务")
    assert res_resume["status"] == "finished" and res_resume["rounds"] == 5


# ==================== 终端命令分级授权与看图 ====================

async def test_terminal_approval_and_vision_helpers(tmp_path, monkeypatch):
    """命令分级 (allow/ask/block)、审批拒绝不执行、Yuki 审批解析失败默认拒绝，以及图片消息构建与降级。"""
    assert maid_approval.classify_command("echo hi")[0] == "allow"
    assert maid_approval.classify_command("pip list --format=json")[0] == "allow"
    assert maid_approval.classify_command("rm -rf /tmp/x")[0] == "ask"
    assert maid_approval.classify_command("pip install requests")[0] == "ask"
    assert maid_approval.classify_command("rm -rf /")[0] == "block"
    assert maid_approval.classify_command("sudo apt install x")[0] == "block"

    target = tmp_path / "keep.txt"
    target.write_text("keep", encoding="utf-8")

    async def deny(cmd, cwd, thought):
        return False, "测试拒绝"

    denied = json.loads(await maid_runtime.terminal_command_maid(f"rm -rf {target}", approver=deny))
    assert denied["ok"] is False and denied["approval"] == "denied" and target.exists()

    async def allow(cmd, cwd, thought):
        return True, "测试同意"

    allowed = json.loads(await maid_runtime.terminal_command_maid(f"rm -f {target}", approver=allow))
    assert allowed["ok"] is True and not target.exists()

    async def unparsable_llm(**kwargs):
        return "我觉得可以"

    monkeypatch.setattr(maid_approval, "llm_chat", unparsable_llm)
    approved, reason = await maid_approval.judge_by_yuki("pip install x", "装依赖")
    assert approved is False and "解析" in reason

    # 看图与降级
    result_text, message = await maid_runtime.prepare_image_message("yuki_help.png", "图里写了什么")
    assert "图片" in result_text
    assert [b["type"] for b in message["content"]] == ["text", "image_url"]
    assert message["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    maid_loop._degrade_image_message(message)
    assert isinstance(message["content"], str) and "图片" in message["content"]

    miss_text, miss_msg = await maid_runtime.prepare_image_message("nope_not_here.png")
    assert miss_msg is None and "不存在" in miss_text
