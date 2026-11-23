# utils/background_tasks.py
"""后台异步任务托管：维护 Task 强引用防止被 GC 提前回收，并统一记录未捕获异常。"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional, Set

from utils.logger import get_logger

logger = get_logger("bg_tasks")

_ACTIVE_TASKS: Set[asyncio.Task[Any]] = set()


def _on_task_done(task: asyncio.Task[Any], label: str) -> None:
    _ACTIVE_TASKS.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except Exception:
        return
    if exc is not None:
        logger.error(f"[BgTask] 后台任务异常 ({label}): {exc}")


def spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: Optional[str] = None,
) -> Any:
    """启动并托管一个 fire-and-forget 后台协程。

    内部委托给 `asyncio.create_task`，兼容单测对其的 monkeypatch。
    """
    label = name or getattr(coro, "__qualname__", None) or "background_task"
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        coro.close()
        return None
    if hasattr(task, "add_done_callback"):
        _ACTIVE_TASKS.add(task)
        task.add_done_callback(lambda t: _on_task_done(t, label))
    return task


def active_background_task_count() -> int:
    """返回当前托管中的活跃后台任务数量。"""
    return len(_ACTIVE_TASKS)
