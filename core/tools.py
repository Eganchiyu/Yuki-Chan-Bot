# core/tools.py
import asyncio
import datetime
import os
from urllib.parse import quote_plus

import aiohttp

from config import cfg
from core.maid import MaidCapabilityBoundary, build_maid_task, maid_evolution_loop, search_diary_fast
from core.toolchain import ToolResult, ToolSpec
from utils.logger import get_logger

logger = get_logger("tools")

_TIMER_TASKS_KEY = "__timer_tasks__"
_TIMER_HANDLES_KEY = "__timer_handles__"
_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


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


async def search_diary_tool(context, date_str=None, keyword=None):
    """查询 Yuki 日记。"""
    logger.info(
        f"[ToolCall][search_diary] chat_id={context.chat_id} date_str={date_str} keyword={keyword}"
    )
    if not date_str and not keyword:
        return ToolResult(success=False, content="请至少提供日期或关键词。", error="missing_date_or_keyword")
    result = await asyncio.to_thread(search_diary_fast, date_str, keyword)
    return ToolResult(success=True, content=result)


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


async def delegate_to_maid_tool(context, goal, run_inline=False):
    """调用小女仆处理重型任务。"""
    if not goal:
        return ToolResult(success=False, content="缺少任务目标", error="missing_goal")

    boundary = MaidCapabilityBoundary.judge(goal)
    if not boundary["allowed"]:
        return ToolResult(
            success=False,
            content=f"小女仆不建议执行：{boundary['reason']}。{boundary['suggestion']}",
            data=boundary,
            error="capability_boundary_rejected",
        )

    if run_inline:
        result = await maid_evolution_loop(user_goal=goal, chat_id=context.chat_id)
        return ToolResult(
            success=result.get("status") == "finished",
            content=result.get("result", "小女仆未返回结果"),
            data=result,
        )

    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    await context.yuki.maid_task_queue.put(task)
    context.yuki.maid_current_tasks[context.chat_id] = task
    return ToolResult(success=True, content="已交给小女仆后台处理。")


async def send_master_private_tool(context, message):
    """向主人私聊发送私密信息。"""
    if not message:
        return ToolResult(success=False, content="缺少消息内容", error="missing_message")
    await context.sender.send(cfg.TARGET_QQ, message, mode="private")
    return ToolResult(success=True, content="已私聊发送给主人。")


async def browser_search_tool(context, query, max_results=5, search_depth="basic"):
    """调用 Tavily 搜索服务，返回可供 LLM 总结的网页结果。"""
    if not query:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_query")

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        return ToolResult(
            success=False,
            content="未配置 TAVILY_API_KEY，暂时只能返回浏览器搜索地址。",
            data={"url": url},
            error="missing_tavily_api_key",
        )

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": True,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_TAVILY_SEARCH_URL, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return ToolResult(
                    success=False,
                    content="Tavily 搜索请求失败。",
                    data=data,
                    error=f"http_{response.status}",
                )

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        })
    return ToolResult(
        success=True,
        content=data.get("answer") or f"已搜索到 {len(results)} 条结果。",
        data={"query": query, "answer": data.get("answer"), "results": results},
    )


async def send_qq_file_tool(context, file_path, file_type="auto", caption=None):
    """发送本地图片、语音或文件。"""
    if not file_path:
        return ToolResult(success=False, content="缺少文件路径", error="missing_file_path")

    abs_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(abs_path):
        return ToolResult(success=False, content="文件不存在，无法发送。", error="file_not_found")

    suffix = os.path.splitext(abs_path)[1].lower()
    if file_type == "auto":
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            file_type = "image"
        elif suffix in {".wav", ".mp3", ".amr", ".silk", ".m4a", ".ogg"}:
            file_type = "voice"
        else:
            file_type = "file"

    if caption:
        await context.sender.send(context.chat_id, caption, mode=context.mode)
    if file_type == "voice":
        await context.sender.send_local_voice(context.chat_id, abs_path, mode=context.mode)
    elif file_type == "image":
        await context.sender.send_local_image(context.chat_id, abs_path, mode=context.mode)
    elif file_type == "file":
        if hasattr(context.sender, "send_local_file"):
            await context.sender.send_local_file(context.chat_id, abs_path, mode=context.mode)
        else:
            await context.sender.send(context.chat_id, f"[CQ:file,file=file:///{abs_path}]", mode=context.mode)
    else:
        return ToolResult(success=False, content="不支持的文件类型", error="unsupported_file_type")
    return ToolResult(success=True, content="文件已发送。", data={"file_path": abs_path, "file_type": file_type})


TOOL_SPECS = [
    ToolSpec(
        name="search_diary",
        description="查询 Yuki 的日记/记忆，支持按日期和关键词检索。",
        parameters={
            "type": "object",
            "properties": {
                "date_str": {"type": "string", "description": "日期，如 2026-05-20 或 2026-05"},
                "keyword": {"type": "string", "description": "需要匹配的关键词"},
            },
        },
        handler=search_diary_tool,
    ),
    ToolSpec(
        name="manage_timer_task",
        description="为当前群聊/私聊创建、取消或列出精确定时任务；到点后会触发 Yuki 基于提醒内容回复。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题，取消时也可用标题匹配"},
                "due_time": {
                    "type": "string",
                    "description": "到点时间，支持 YYYY-MM-DD HH:MM:SS、YYYY-MM-DD HH:MM 或 ISO 格式",
                },
                "delay_seconds": {"type": "number", "description": "相对延迟秒数，适合很短的提醒"},
                "action": {"type": "string", "enum": ["create", "cancel", "list"]},
                "task_id": {"type": "string", "description": "取消指定任务时使用"},
                "message": {"type": "string", "description": "到点后注入给 Yuki 的提醒内容"},
            },
        },
        handler=manage_timer_task_tool,
    ),
    ToolSpec(
        name="delegate_to_maid",
        description="将重型任务委托给小女仆处理。",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "run_inline": {"type": "boolean"},
            },
            "required": ["goal"],
        },
        handler=delegate_to_maid_tool,
    ),
    ToolSpec(
        name="send_master_private",
        description="向主人私聊发送私密信息。",
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        handler=send_master_private_tool,
    ),
    ToolSpec(
        name="browser_search",
        description="使用 Tavily 搜索实时网页信息，并返回摘要、来源链接和网页片段供 Yuki 作答。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或问题"},
                "max_results": {"type": "integer", "description": "返回结果数量，1 到 10"},
                "search_depth": {"type": "string", "enum": ["basic", "advanced"]},
            },
            "required": ["query"],
        },
        handler=browser_search_tool,
    ),
    ToolSpec(
        name="send_qq_file",
        description="发送本地图片、语音或普通文件；优先用此工具，不要直接在回复中手写 CQ 文件码。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地文件路径"},
                "file_type": {"type": "string", "enum": ["auto", "image", "voice", "file"]},
                "caption": {"type": "string", "description": "发送文件前附带的一句说明，可省略"},
            },
            "required": ["file_path"],
        },
        handler=send_qq_file_tool,
    ),
]

# 兼容旧引用，后续新增工具优先维护 TOOL_SPECS。
TOOL_SCHEMAS = [spec.to_schema() for spec in TOOL_SPECS]
TOOL_HANDLERS = {spec.name: spec.handler for spec in TOOL_SPECS}
