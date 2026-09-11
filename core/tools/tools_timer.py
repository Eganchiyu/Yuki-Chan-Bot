# core/tools/tools_timer.py
"""精确定时任务工具。"""
import asyncio
import datetime

from core.toolchain import ToolResult

from .tools_common import logger

_TIMER_TASKS_KEY = "__timer_tasks__"
_TIMER_HANDLES_KEY = "__timer_handles__"


def _timer_store(context):
    return context.yuki.maid_current_tasks.setdefault(_TIMER_TASKS_KEY, {})


def _timer_handles(context):
    return context.yuki.maid_current_tasks.setdefault(_TIMER_HANDLES_KEY, {})


def _parse_due_time(due_time=None, delay_seconds=None):
    """解析绝对或相对时间，返回触发时间与等待秒数。"""
    now = datetime.datetime.now()
    if delay_seconds is not None:
        delay = max(0.0, float(delay_seconds))
        return now + datetime.timedelta(seconds=delay), delay

    if not due_time:
        raise ValueError("missing_due_time")

    text = str(due_time).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            due_at = datetime.datetime.strptime(text, fmt)
            return due_at, max(0.0, (due_at - now).total_seconds())
        except ValueError:
            pass

    due_at = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if due_at.tzinfo is not None:
        due_at = due_at.astimezone().replace(tzinfo=None)
    return due_at, max(0.0, (due_at - now).total_seconds())


async def _timer_wake_worker(context, task_id, delay_seconds):
    """到点后把定时事件写入群聊缓冲，并触发主 LLM 回复流程。"""
    try:
        await asyncio.sleep(delay_seconds)
        tasks = _timer_store(context)
        task = tasks.get(task_id)
        if not task or task.get("status") == "cancelled":
            return

        task["status"] = "triggered"
        task["triggered_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = task["chat_id"]
        reminder = task.get("message") or task["title"]
        message_obj = {
            "content": f"【定时任务到点】{reminder}",
            "time": task["triggered_at"],
            "is_timer_event": True,
        }

        callback = context.metadata.get("process_callback") or getattr(context.yuki, "process_callback", None)
        if callback is None:
            logger.warning(f"[Timer] process_callback 未设置，无法触发回复: {task_id}")
            return
        asyncio.create_task(
            callback(
                chat_id,
                task.get("mode", "group"),
                message_obj=message_obj,
                debounce_flag=False,
                force_reply=True,
            )
        )
        logger.info(f"[Timer] 已经通过主管道触发定时任务: {task_id} chat_id={chat_id}")
    finally:
        _timer_handles(context).pop(task_id, None)


async def manage_timer_task_tool(
    context,
    title=None,
    due_time=None,
    delay_seconds=None,
    action="create",
    task_id=None,
    message=None,
):
    """为当前群聊/私聊创建、取消或列出精确定时任务。"""
    tasks = _timer_store(context)
    handles = _timer_handles(context)
    chat_id = str(context.chat_id)

    if action == "list":
        current_tasks = [task for task in tasks.values() if task.get("chat_id") == chat_id]
        return ToolResult(success=True, content="当前会话定时任务列表", data=current_tasks)

    if action == "cancel":
        key = task_id
        if not key and title:
            key = next((tid for tid, task in tasks.items() if task.get("title") == title), None)
        if not key or key not in tasks:
            return ToolResult(success=False, content="未找到对应定时任务", error="timer_not_found")
        task = tasks[key]
        task["status"] = "cancelled"
        handle = handles.pop(key, None)
        if handle:
            handle.cancel()
        return ToolResult(success=True, content="定时任务已取消", data=task)

    if not title:
        return ToolResult(success=False, content="缺少定时任务标题", error="missing_title")

    try:
        due_at, delay = _parse_due_time(due_time, delay_seconds)
    except (TypeError, ValueError) as e:
        return ToolResult(success=False, content="定时任务时间格式无效", error=str(e))

    new_task_id = f"timer_{chat_id}_{int(datetime.datetime.now().timestamp() * 1000)}"
    task = {
        "id": new_task_id,
        "title": title,
        "message": message or title,
        "chat_id": chat_id,
        "mode": context.mode,
        "due_time": due_at.strftime("%Y-%m-%d %H:%M:%S"),
        "delay_seconds": round(delay, 3),
        "status": "scheduled",
    }
    tasks[new_task_id] = task
    handles[new_task_id] = asyncio.create_task(_timer_wake_worker(context, new_task_id, delay))
    return ToolResult(success=True, content="定时任务已创建，到点后会触发 Yuki 回复。", data=task)
