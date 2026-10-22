"""小女仆本轮升级的功能测试：读文件防爆、预算、快照、授权、看图。

runner 只收集模块级 test_* 函数，async def 会被自动 asyncio.run。
"""
import asyncio
import json
import os
import tempfile

from core.maid import maid_approval, maid_common, maid_loop, maid_memory, maid_runtime


def _tmp_paths():
    root = tempfile.mkdtemp(prefix="maid_test_")
    state_dir = os.path.join(root, "state")
    index_file = os.path.join(root, "task_index.jsonl")
    maid_memory.TASK_STATE_DIR = state_dir
    maid_memory.TASK_INDEX_FILE = index_file
    return state_dir, index_file


def _restore_paths(state_dir, index_file):
    maid_memory.TASK_STATE_DIR = state_dir
    maid_memory.TASK_INDEX_FILE = index_file


# --- read_file 防爆 ---

def test_read_file_truncates_long_single_line():
    path = os.path.join(tempfile.mkdtemp(prefix="maid_test_"), "b64.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("A" * (900 * 1024))

    result = maid_tools_read(path)
    assert len(result) < 6000, f"单行超长文件仍然返回了 {len(result)} 字符"
    assert "截断" in result


def maid_tools_read(path, **kwargs):
    from core.maid.maid_tools import read_file_content
    return read_file_content(path, **kwargs)


def test_read_file_offset_continues():
    path = os.path.join(tempfile.mkdtemp(prefix="maid_test_"), "lines.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(f"line{i}" for i in range(100)))

    first = maid_tools_read(path, max_lines=5)
    assert "line4" in first and "line5" not in first
    assert "offset=5" in first

    second = maid_tools_read(path, max_lines=5, offset=95)
    assert "line95" in second and "line99" in second


def test_read_file_rejects_directory_and_binary():
    assert "目录" in maid_tools_read("core/maid")
    assert "二进制" in maid_tools_read("yuki_help.png")


# --- 预算与错误轮 ---

async def test_wall_clock_budget_stops_task():
    saved_budget = maid_common.MAID_MAX_WALL_SECONDS
    saved_call = maid_loop.call_cloud_maid_robust
    calls = {"n": 0}

    async def fake(messages):
        calls["n"] += 1
        await asyncio.sleep(0.1)
        return '{"thought":"spin","tool":"list_skills","args":{}}'

    try:
        maid_common.MAID_MAX_WALL_SECONDS = 0.15
        maid_loop.call_cloud_maid_robust = fake
        result = await maid_loop.maid_evolution_loop("预算测试")
    finally:
        maid_common.MAID_MAX_WALL_SECONDS = saved_budget
        maid_loop.call_cloud_maid_robust = saved_call

    assert result["status"] == "timeout"
    assert calls["n"] <= 2, f"墙钟超时后仍调用了 {calls['n']} 次 LLM"
    assert "墙钟" in result["result"]


async def test_parse_error_does_not_consume_rounds():
    saved_call = maid_loop.call_cloud_maid_robust
    replies = iter(["不是JSON", "还不是JSON"] + ['{"thought":"done","tool":"finish","args":{"reason":"ok"}}'])

    async def fake(messages):
        return next(replies)

    try:
        maid_loop.call_cloud_maid_robust = fake
        result = await maid_loop.maid_evolution_loop("错误轮测试")
    finally:
        maid_loop.call_cloud_maid_robust = saved_call

    assert result["status"] == "finished"
    assert result["rounds"] == 1, f"解析失败被算进了有效轮：{result['rounds']}"


# --- 快照 / 索引 / 续跑 ---

async def test_snapshot_and_index_roundtrip():
    saved = (maid_memory.TASK_STATE_DIR, maid_memory.TASK_INDEX_FILE)
    state_dir, index_file = _tmp_paths()
    try:
        await maid_memory.save_task_state(
            task_id="t1", goal="写周报", messages=[{"role": "user", "content": "hi"}],
            round_no=2, last_step={"tool": "read_file"}, status="interrupted",
        )
        state = await maid_memory.load_task_state("t1")
        assert state["goal"] == "写周报" and state["round"] == 2
        assert os.path.exists(os.path.join(state_dir, "t1.json"))

        unfinished = await maid_memory.list_unfinished_states()
        assert [item["task_id"] for item in unfinished] == ["t1"]

        await maid_memory.append_task_index("t1", "写周报", "finished", "完成", rounds=3, elapsed=4.2)
        with open(index_file, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["rounds"] == 3 and entry["status"] == "finished"

        context = await maid_memory.build_startup_context()
        assert "最近任务" in context and "写周报" in context
        assert "未完成任务" in context and "t1" in context
    finally:
        _restore_paths(*saved)


async def test_finish_deletes_snapshot_and_writes_index():
    saved = (maid_memory.TASK_STATE_DIR, maid_memory.TASK_INDEX_FILE)
    saved_call = maid_loop.call_cloud_maid_robust
    state_dir, index_file = _tmp_paths()

    async def fake(messages):
        return '{"thought":"done","tool":"finish","args":{"reason":"完成"}}'

    try:
        maid_loop.call_cloud_maid_robust = fake
        result = await maid_loop.maid_evolution_loop("结束清理测试", chat_id="42")
        assert result["status"] == "finished"
        assert result["rounds"] == 1 and result["trace"].startswith("logs/")
        assert os.listdir(state_dir) == [] if os.path.isdir(state_dir) else True
        with open(index_file, encoding="utf-8") as f:
            assert json.loads(f.readline())["status"] == "finished"
    finally:
        maid_loop.call_cloud_maid_robust = saved_call
        _restore_paths(*saved)


async def test_resume_task_restores_context_once():
    saved = (maid_memory.TASK_STATE_DIR, maid_memory.TASK_INDEX_FILE)
    saved_call = maid_loop.call_cloud_maid_robust
    _tmp_paths()
    seen = {"rounds_at_finish": None}

    async def fake(messages):
        joined = " ".join(str(m.get("content")) for m in messages)
        if "已从任务 t_prev" not in joined:
            return '{"thought":"续跑","tool":"resume_task","args":{"task_id":"t_prev"}}'
        seen["rounds_at_finish"] = len(messages)
        return '{"thought":"done","tool":"finish","args":{"reason":"续跑完成"}}'

    try:
        await maid_memory.save_task_state(
            task_id="t_prev", goal="旧任务",
            messages=[{"role": "user", "content": "上半段进度"}, {"role": "assistant", "content": "已做完 A"}],
            round_no=4, status="interrupted",
        )
        maid_loop.call_cloud_maid_robust = fake
        result = await maid_loop.maid_evolution_loop("继续旧任务")
        assert result["status"] == "finished"
        assert result["rounds"] == 5, f"续跑轮次不对：{result['rounds']}"
        assert seen["rounds_at_finish"] is not None
    finally:
        maid_loop.call_cloud_maid_robust = saved_call
        _restore_paths(*saved)


# --- 终端授权 ---

def test_classify_command_split():
    assert maid_approval.classify_command("rm -rf /tmp/x")[0] == "ask"
    assert maid_approval.classify_command("rm -rf /")[0] == "block"
    assert maid_approval.classify_command("echo hi")[0] == "allow"
    assert maid_approval.classify_command("pip list --format=json")[0] == "allow"
    assert maid_approval.classify_command("sudo apt install x")[0] == "block"
    assert maid_approval.classify_command("pip install requests")[0] == "ask"


async def test_terminal_denied_by_approver_is_not_executed():
    target = os.path.join(tempfile.mkdtemp(prefix="maid_test_"), "keep.txt")
    with open(target, "w", encoding="utf-8") as f:
        f.write("keep")

    async def deny(command, cwd, thought):
        return False, "测试拒绝"

    result = json.loads(await maid_runtime.terminal_command_maid(f"rm -rf {target}", approver=deny))
    assert result["ok"] is False and result["approval"] == "denied"
    assert os.path.exists(target), "被拒绝的命令仍然执行了"


async def test_terminal_approved_by_approver_runs():
    target = os.path.join(tempfile.mkdtemp(prefix="maid_test_"), "keep.txt")
    with open(target, "w", encoding="utf-8") as f:
        f.write("keep")

    async def allow(command, cwd, thought):
        return True, "测试同意"

    result = json.loads(await maid_runtime.terminal_command_maid(f"rm -f {target}", approver=allow))
    assert result["ok"] is True
    assert not os.path.exists(target)


async def test_judge_by_yuki_denies_unparsable():
    saved = maid_approval.llm_chat

    async def fake(**kwargs):
        return "我觉得可以"

    try:
        maid_approval.llm_chat = fake
        approved, reason = await maid_approval.judge_by_yuki("pip install x", "装依赖")
    finally:
        maid_approval.llm_chat = saved

    assert approved is False
    assert "解析" in reason


# --- 看图 ---

async def test_image_message_builds_block_and_degrades():
    result_text, message = await maid_runtime.prepare_image_message("yuki_help.png", "图里写了什么")
    assert "图片" in result_text
    kinds = [block["type"] for block in message["content"]]
    assert kinds == ["text", "image_url"]
    assert message["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    maid_loop._degrade_image_message(message)
    assert isinstance(message["content"], str)
    assert "图片" in message["content"]


async def test_prepare_image_rejects_missing_file():
    text, message = await maid_runtime.prepare_image_message("nope_not_here.png")
    assert message is None and "不存在" in text
