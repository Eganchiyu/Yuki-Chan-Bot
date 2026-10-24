"""小女仆的 harness 后端：把执行交给宿主侧的 DeepSeek Harness。

为什么换掉原来的内置循环：
    原来的 core/maid/maid_loop.py 自己实现了 LLM 循环、JSON function-call 协议、
    14 个工具的人肉分派、轮次上限和 messages 快照。这些都是 harness 的现成能力，
    自己维护只会越来越长，而且工具质量、上下文压缩、沙箱都远不如 harness。

现在的分工：
    容器内（本文件）只做三件事——写任务、盯事件流、把结果翻译成 Yuki 认识的格式。
    宿主侧 deploy/maid_runner.py 负责真正拉起 dsh 子进程。

协议见 deploy/maid_runner.py 的模块注释。这里不引入任何新依赖。
"""
import asyncio
import json
import os
import time
from datetime import datetime

from core.maid import maid_memory
from core.maid.maid_common import (
    LOGS_DIR,
    MAID_MAX_WALL_SECONDS,
    TASK_STATE_DIR,
    logger,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DSH_TASKS_DIR = os.path.join(PROJECT_ROOT, "tasks", "dsh")
POLL_SECONDS = float(os.environ.get("YUKI_MAID_POLL", "1.0"))
# 执行器（宿主侧的 maid_runner）没起来时的识别窗口：这么久了连 lock/events 都没有，就别干等
STARTUP_GRACE = float(os.environ.get("YUKI_MAID_STARTUP_GRACE", "90"))
# 结果文本要进 Yuki 的记忆流，别让一次超长输出把上下文淹了
RESULT_MAX_CHARS = 12000
TRACE_STEP_CHARS = 2500


def _dsh_task_dir(task_id):
    return os.path.join(DSH_TASKS_DIR, task_id)


def _write_json_atomic(path, payload):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _new_task_id():
    # 带毫秒和 pid 后缀：同一秒内连派两个任务也不会撞目录
    return f"{datetime.now():%Y%m%d_%H%M%S}_{os.getpid() % 1000:03d}"


def _step_markdown(step_no, thought, tool, args, result):
    thought = (thought or "").strip()
    args_text = json.dumps(args, ensure_ascii=False) if isinstance(args, (dict, list)) else str(args)
    result_text = str(result or "")
    if len(result_text) > TRACE_STEP_CHARS:
        result_text = result_text[:TRACE_STEP_CHARS] + "\n... [已截断] ..."
    return (
        f"### 步骤 {step_no}\n**思考**: {thought or '（无）'}\n\n"
        f"**动作**: `{tool}`({args_text})\n\n**结果**: \n{result_text}\n\n"
    )


def _resume_session_for(task_id):
    """从历史快照里找可续做的 harness session id。"""
    if not task_id:
        return ""
    state = _read_json(os.path.join(TASK_STATE_DIR, f"{task_id}.json"))
    return str((state or {}).get("session_id") or "")


def _save_session_state(task_id, goal, session_id, status, steps, chat_id):
    """轻量快照：只存续做需要的 session id，不复制 harness 自己的会话历史。"""
    if not session_id:
        return ""
    os.makedirs(TASK_STATE_DIR, exist_ok=True)
    path = os.path.join(TASK_STATE_DIR, f"{task_id}.json")
    _write_json_atomic(path, {
        "task_id": task_id,
        "goal": goal,
        "session_id": session_id,
        "status": status,
        "round": steps,
        "chat_id": chat_id,
        "backend": "harness",
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return path


async def harness_evolution_loop(user_goal: str, chat_id: str = None, approver=None, resume_task_id=None):
    """执行一个小女仆任务。返回值结构与原 maid_evolution_loop 保持一致。"""
    del approver  # harness 自带沙箱与审批策略，容器侧不再二次拦截
    task_id = _new_task_id()
    task_dir = _dsh_task_dir(task_id)
    events_path = os.path.join(task_dir, "events.jsonl")
    result_path = os.path.join(task_dir, "result.json")
    trace_path = os.path.join(LOGS_DIR, f"trace_{task_id}.md")

    os.makedirs(task_dir, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    resume_session = _resume_session_for(resume_task_id) if resume_task_id else ""
    request = {
        "goal": user_goal,
        "chat_id": str(chat_id) if chat_id is not None else "",
        "timeout_s": int(MAID_MAX_WALL_SECONDS),
    }
    if resume_session:
        request["session_id"] = resume_session
    _write_json_atomic(os.path.join(task_dir, "request.json"), request)

    logger.info(f"[Maid/Harness] 任务已派发: {task_id}（{user_goal[:80]}）"
                + (f" 续做 session={resume_session}" if resume_session else ""))
    with open(trace_path, "w", encoding="utf-8") as f:
        f.write(f"# 小女仆任务追踪: {task_id}\n\n"
                f"**后端**: deepseek-harness（宿主 maid_runner）\n\n"
                f"**任务目标**: {user_goal}\n\n---\n")

    started = time.monotonic()
    deadline = started + int(MAID_MAX_WALL_SECONDS) + 120  # 比 runner 的上限多留收尾时间
    events_seen = 0
    events_offset = 0
    steps = 0
    tools = []
    pending_thoughts = []
    open_calls = {}
    seen_any_life = False

    while True:
        # ---- 读增量事件：用于写 trace 和打印进度 ----
        if os.path.exists(events_path):
            seen_any_life = True
            try:
                with open(events_path, encoding="utf-8", errors="replace") as f:
                    f.seek(events_offset)
                    chunk = f.read()
                    events_offset = f.tell()
            except OSError:
                chunk = ""
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                events_seen += 1
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "status" and ev.get("phase") == "step_start":
                    steps = max(steps, int(ev.get("step") or 0))
                elif kind == "thinking":
                    pending_thoughts.append(ev.get("text") or "")
                elif kind == "text":
                    pending_thoughts.append(ev.get("text") or "")
                elif kind == "tool_call":
                    open_calls[ev.get("callId")] = {
                        "tool": ev.get("tool"),
                        "input": ev.get("input"),
                        "step": steps,
                    }
                    tools.append(ev.get("tool"))
                    logger.info(f"[Maid/Harness] {task_id} 第 {steps} 步: {ev.get('tool')}")
                elif kind == "tool_result":
                    call = open_calls.pop(ev.get("callId"), None) or {"tool": ev.get("tool"), "input": {}}
                    thought = "\n".join(t for t in pending_thoughts if t).strip()
                    pending_thoughts = []
                    with open(trace_path, "a", encoding="utf-8") as tf:
                        tf.write(_step_markdown(
                            call.get("step") or steps, thought,
                            call.get("tool") or ev.get("tool"),
                            call.get("input"), ev.get("result"),
                        ))

        # ---- 结果文件 ----
        result = _read_json(result_path)
        if result is not None:
            return await _finish(result, user_goal, task_id, chat_id, trace_path, started, steps, tools)

        # ---- 兜底：执行器根本没起来 ----
        elapsed = time.monotonic() - started
        if not seen_any_life and elapsed > STARTUP_GRACE:
            reason = (f"小女仆执行器无响应：{int(elapsed)}s 内宿主侧没有任何动静。"
                      f"检查 `systemctl status yuki-maid-runner` 与 logs/maid_runner.log。")
            logger.error(f"[Maid/Harness] {task_id} {reason}")
            await maid_memory.append_task_index(
                task_id=task_id, goal=user_goal, status="runner_unavailable",
                result=reason, rounds=0, elapsed=elapsed, chat_id=chat_id,
            )
            return {
                "status": "error", "result": reason, "goal": user_goal,
                "task_id": task_id, "rounds": 0, "elapsed": round(elapsed, 1),
                "trace": trace_path, "state": "",
            }

        # ---- 兜底：自己等太久（runner 挂了 / 结果丢失）----
        if elapsed > (deadline - started):
            reason = f"等待 harness 结果超时（{int(elapsed)}s），已放弃等待。"
            logger.error(f"[Maid/Harness] {task_id} {reason}")
            await maid_memory.append_task_index(
                task_id=task_id, goal=user_goal, status="timeout",
                result=reason, rounds=steps, elapsed=elapsed, chat_id=chat_id,
            )
            return {
                "status": "timeout", "result": reason, "goal": user_goal,
                "task_id": task_id, "rounds": steps, "elapsed": round(elapsed, 1),
                "trace": trace_path, "state": "",
            }

        await asyncio.sleep(POLL_SECONDS)


async def _finish(result, user_goal, task_id, chat_id, trace_path, started, steps, tools):
    """把 runner 的 result.json 翻译成 Yuki 侧统一的任务结果。"""
    raw_status = str(result.get("status") or "failed")
    text = str(result.get("result") or "").strip()
    if len(text) > RESULT_MAX_CHARS:
        text = text[:RESULT_MAX_CHARS] + "\n... [结果过长，已截断] ..."
    session_id = str(result.get("session_id") or "")
    elapsed = float(result.get("elapsed") or (time.monotonic() - started))
    steps = max(steps, int(result.get("steps") or 0))

    status_map = {"finished": "finished", "timeout": "timeout"}
    status = status_map.get(raw_status, "error")
    if status != "finished" and not text:
        text = str(result.get("detail") or f"harness 返回 {raw_status}")[:2000]

    state_path = _save_session_state(
        task_id, user_goal, session_id, status, steps, chat_id
    ) if status != "finished" else ""

    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(f"### 任务结束（{status}）\n**结果**: {text[:4000]}\n\n"
                f"**统计**: {steps} 步 / {elapsed:.1f}s / 工具 {tools[-8:]}\n\n"
                f"**session**: `{session_id or '-'}`\n")

    await maid_memory.append_task_index(
        task_id=task_id,
        goal=user_goal,
        status=status,
        result=text,
        rounds=steps,
        elapsed=elapsed,
        chat_id=chat_id,
        state_path=state_path,
    )
    if status == "finished":
        await maid_memory.delete_task_state(task_id)

    logger.info(f"[Maid/Harness] {task_id} {status}: {steps} 步 / {elapsed:.1f}s")
    return {
        "status": status,
        "result": text,
        "goal": user_goal,
        "task_id": task_id,
        "rounds": steps,
        "elapsed": round(elapsed, 1),
        "trace": trace_path,
        "state": state_path,
        "session_id": session_id,
        "tools": tools[-20:],
    }
