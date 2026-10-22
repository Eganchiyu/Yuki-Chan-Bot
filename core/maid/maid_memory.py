"""小女仆任务状态与历史索引的持久化层。

- `tasks/state/<task_id>.json`：每轮覆盖写一次，供超时/崩溃后用 `resume_task` 续跑。
- `logs/task_index.jsonl`：每个任务结束后追加一行，用于下次任务开头的摘要注入。
所有磁盘 IO 都走 asyncio.to_thread，调用方（maid_loop）仍跑在 Yuki 的事件循环里。
"""
import asyncio
import json
import os
from datetime import datetime

from core.maid.maid_common import TASK_INDEX_FILE, TASK_STATE_DIR, logger

MAX_SNAPSHOT_MESSAGE_CHARS = 3000
MAX_INDEX_RESULT_CHARS = 500
MAX_SUMMARY_GOAL_CHARS = 120

_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_path(task_id: str) -> str:
    safe_id = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in "_-")
    return os.path.join(TASK_STATE_DIR, f"{safe_id}.json")


def _text_of(content) -> str:
    """把消息内容压成纯文本；图块等非文本内容替换为占位符。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "image_url":
                parts.append("[图片]")
        return " ".join(parts)
    return "" if content is None else str(content)


def _trim_messages(messages) -> list:
    """落盘前裁剪：去掉图块、单条内容截断，避免快照无限膨胀。"""
    trimmed = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        text = _text_of(message.get("content"))
        if len(text) > MAX_SNAPSHOT_MESSAGE_CHARS:
            text = text[:MAX_SNAPSHOT_MESSAGE_CHARS] + "…[快照截断]"
        trimmed.append({"role": message.get("role", "user"), "content": text})
    return trimmed


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


async def save_task_state(
    task_id: str,
    goal: str,
    messages,
    round_no: int = 0,
    last_step: dict = None,
    chat_id=None,
    status: str = "running",
    created_at: str = None,
) -> str:
    """覆盖写当前任务快照，返回快照路径；失败只记日志不抛出。"""
    payload = {
        "task_id": str(task_id),
        "goal": goal,
        "chat_id": str(chat_id) if chat_id is not None else None,
        "round": int(round_no or 0),
        "last_step": last_step or {},
        "messages": _trim_messages(messages),
        "created_at": created_at or _now(),
        "updated_at": _now(),
        "status": status,
    }
    path = _state_path(task_id)
    try:
        async with _lock:
            await asyncio.to_thread(_write_json_atomic, path, payload)
    except Exception as e:
        logger.warning(f"[Maid] 写任务快照失败: {e}")
    return path


async def load_task_state(task_id: str = None) -> dict:
    """读取指定任务快照；task_id 为空时取最近更新的那个未完成快照。"""
    if not task_id:
        states = await list_unfinished_states(include_running=True)
        return states[0] if states else {}
    path = _state_path(task_id)
    if not os.path.exists(path):
        return {}
    try:
        return await asyncio.to_thread(_read_json, path)
    except Exception as e:
        logger.warning(f"[Maid] 读任务快照失败: {e}")
        return {}


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def list_unfinished_states(include_running: bool = False) -> list:
    """按更新时间倒序列出未完成任务快照（status=running）。"""
    def _scan():
        if not os.path.isdir(TASK_STATE_DIR):
            return []
        items = []
        for name in os.listdir(TASK_STATE_DIR):
            if not name.endswith(".json"):
                continue
            try:
                data = _read_json(os.path.join(TASK_STATE_DIR, name))
            except Exception:
                continue
            if include_running or data.get("status") == "running":
                items.append(data)
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items

    try:
        return await asyncio.to_thread(_scan)
    except Exception as e:
        logger.warning(f"[Maid] 扫描任务快照失败: {e}")
        return []


async def delete_task_state(task_id: str) -> None:
    path = _state_path(task_id)
    try:
        if os.path.exists(path):
            await asyncio.to_thread(os.remove, path)
    except Exception as e:
        logger.warning(f"[Maid] 删除任务快照失败: {e}")


def _append_line(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


async def append_task_index(
    task_id: str,
    goal: str,
    status: str,
    result: str,
    rounds: int = 0,
    elapsed: float = 0.0,
    chat_id=None,
    state_path: str = "",
) -> None:
    """任务结束追加一行历史索引。"""
    payload = {
        "task_id": str(task_id),
        "goal": goal,
        "status": status,
        "result": (result or "")[:MAX_INDEX_RESULT_CHARS],
        "rounds": int(rounds or 0),
        "elapsed": round(float(elapsed or 0), 1),
        "chat_id": str(chat_id) if chat_id is not None else None,
        "finished_at": _now(),
    }
    if state_path:
        payload["state"] = state_path
    try:
        async with _lock:
            await asyncio.to_thread(_append_line, TASK_INDEX_FILE, payload)
    except Exception as e:
        logger.warning(f"[Maid] 写任务索引失败: {e}")


def _read_recent_index(limit: int = 3) -> list:
    if not os.path.exists(TASK_INDEX_FILE):
        return []
    try:
        with open(TASK_INDEX_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-max(limit * 4, 20):]
    except Exception:
        return []
    items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items[-limit:]


def _one_line(text, limit: int) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


async def build_startup_context(limit: int = 3) -> str:
    """任务开始时注入的上下文：最近任务摘要 + 未完成快照提示。没有内容时返回空串。"""
    recent = await asyncio.to_thread(_read_recent_index, limit)
    unfinished = await list_unfinished_states(include_running=True)

    lines = []
    for item in recent:
        lines.append(
            f"[最近任务] {item.get('finished_at', '?')} | {item.get('status', '?')} | "
            f"目标：{_one_line(item.get('goal'), MAX_SUMMARY_GOAL_CHARS)} | "
            f"结果：{_one_line(item.get('result'), MAX_SUMMARY_GOAL_CHARS)}"
        )
    for item in unfinished[:1]:
        lines.append(
            f"[未完成任务] task_id={item.get('task_id')} | "
            f"目标：{_one_line(item.get('goal'), MAX_SUMMARY_GOAL_CHARS)} | "
            f"第 {item.get('round', 0)} 轮中断，可用 resume_task 继续"
        )
    return "\n".join(lines)


async def resume_state(task_id: str = None) -> dict:
    """取可续跑的快照：给了 task_id 就取对应快照，否则取最近一个未完成快照。"""
    return await load_task_state(task_id)


def build_resumed_messages(state: dict, system_prompt: str, goal: str) -> list:
    """用快照重建消息列表：换成本次的 system prompt，其余历史保留（已截断）。"""
    messages = [{"role": "system", "content": system_prompt}]
    for message in state.get("messages") or []:
        if message.get("role") == "system":
            continue
        messages.append({"role": message.get("role", "user"), "content": message.get("content", "")})
    messages.append({
        "role": "user",
        "content": (
            f"[系统] 已从任务 {state.get('task_id')} 的快照恢复（原目标：{state.get('goal')}）。"
            f"当前新目标：{goal}。请从上次中断处继续，不要重复已经完成的动作。"
        ),
    })
    return messages
