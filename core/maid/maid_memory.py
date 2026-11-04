"""小女仆任务状态清理与历史索引持久化（Harness 后端精简版）。"""
import asyncio
import json
import os
import threading
from datetime import datetime

from core.maid.maid_common import TASK_INDEX_FILE, TASK_STATE_DIR, logger

MAX_INDEX_RESULT_CHARS = 500

_io_lock = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_path(task_id: str) -> str:
    safe_id = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in "_-")
    return os.path.join(TASK_STATE_DIR, f"{safe_id}.json")


async def delete_task_state(task_id: str) -> None:
    path = _state_path(task_id)
    try:
        if os.path.exists(path):
            await asyncio.to_thread(os.remove, path)
    except Exception as e:
        logger.warning(f"[Maid] 删除任务快照失败: {e}")


def _append_line(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _io_lock:
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
        await asyncio.to_thread(_append_line, TASK_INDEX_FILE, payload)
    except Exception as e:
        logger.warning(f"[Maid] 写任务索引失败: {e}")
