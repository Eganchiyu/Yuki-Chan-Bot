# core/tools.py
import asyncio
import datetime
from urllib.parse import quote_plus

from config import cfg
from core.maid import MaidCapabilityBoundary, build_maid_task, maid_evolution_loop, search_diary_fast
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")


async def search_diary_tool(context, date_str=None, keyword=None):
    """查询 Yuki 日记。"""
    if not date_str and not keyword:
        return ToolResult(
            name="search_diary",
            success=False,
            content="请至少提供日期或关键词。",
            error="missing_date_or_keyword",
        )
    result = await asyncio.to_thread(search_diary_fast, date_str, keyword)
    return ToolResult(name="search_diary", success=True, content=result)


async def manage_timer_task_tool(context, title, due_time=None, action="create"):
    """轻量定时任务管理，先提供可扩展的状态入口。"""
    tasks = context.engine.yuki.maid_current_tasks.setdefault("__timers__", {})
    task_id = f"timer_{len(tasks) + 1}"
    if action == "list":
        return ToolResult(name="manage_timer_task", success=True, content="当前定时任务列表", data=tasks)
    if action == "cancel":
        removed = tasks.pop(title, None)
        return ToolResult(
            name="manage_timer_task",
            success=removed is not None,
            content="定时任务已取消" if removed else "未找到对应定时任务",
            data=removed,
        )
    tasks[title] = {"id": task_id, "title": title, "due_time": due_time, "chat_id": context.chat_id}
    return ToolResult(name="manage_timer_task", success=True, content="定时任务已记录", data=tasks[title])


async def delegate_to_maid_tool(context, goal, run_inline=False):
    """调用小女仆处理重型任务。"""
    if not goal:
        return ToolResult(name="delegate_to_maid", success=False, content="缺少任务目标", error="missing_goal")

    boundary = MaidCapabilityBoundary.judge(goal)
    if not boundary["allowed"]:
        return ToolResult(
            name="delegate_to_maid",
            success=False,
            content=f"小女仆不建议执行：{boundary['reason']}。{boundary['suggestion']}",
            data=boundary,
            error="capability_boundary_rejected",
        )

    if run_inline:
        result = await maid_evolution_loop(user_goal=goal, chat_id=context.chat_id)
        return ToolResult(
            name="delegate_to_maid",
            success=result.get("status") == "finished",
            content=result.get("result", "小女仆未返回结果"),
            data=result,
        )

    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    await context.engine.yuki.maid_task_queue.put(task)
    context.engine.yuki.maid_current_tasks[context.chat_id] = task
    return ToolResult(name="delegate_to_maid", success=True, content="已交给小女仆后台处理。")


async def send_master_private_tool(context, message):
    """向主人私聊发送私密信息。"""
    if not message:
        return ToolResult(name="send_master_private", success=False, content="缺少消息内容", error="missing_message")
    await context.engine.sender.send(cfg.TARGET_QQ, message, mode="private")
    return ToolResult(name="send_master_private", success=True, content="已私聊发送给主人。")


async def browser_search_tool(context, query):
    """提供网络搜索入口，当前返回可打开的搜索地址。"""
    if not query:
        return ToolResult(name="browser_search", success=False, content="缺少搜索关键词", error="missing_query")
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    return ToolResult(name="browser_search", success=True, content=f"可通过浏览器继续搜索：{url}", data={"url": url})


async def send_qq_file_tool(context, file_path, file_type="image"):
    """发送图片或语音文件，保留 QQ 文件发送扩展入口。"""
    if not file_path:
        return ToolResult(name="send_qq_file", success=False, content="缺少文件路径", error="missing_file_path")
    if file_type == "voice":
        await context.engine.sender.send_local_voice(context.chat_id, file_path, mode=context.mode)
    else:
        await context.engine.sender.send_local_image(context.chat_id, file_path, mode=context.mode)
    return ToolResult(name="send_qq_file", success=True, content="文件已发送。")


async def inject_external_content_tool(context, content, source="external"):
    """外部内容注入入口，用于 WebUI 或多渠道输入适配。"""
    if not content:
        return ToolResult(name="inject_external_content", success=False, content="缺少注入内容", error="missing_content")
    current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
    context.history_dict.setdefault(context.chat_id, [])
    context.history_dict[context.chat_id].append({
        "role": "user",
        "content": f"【{source} 内容注入】{content}",
        "time": current_time_str,
    })
    return ToolResult(name="inject_external_content", success=True, content="外部内容已注入当前上下文。")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_diary",
            "description": "查询 Yuki 的日记/记忆，支持按日期和关键词检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "日期，如 2026-05-20 或 2026-05"},
                    "keyword": {"type": "string", "description": "需要匹配的关键词"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_timer_task",
            "description": "创建、取消或列出定时任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_time": {"type": "string"},
                    "action": {"type": "string", "enum": ["create", "cancel", "list"]},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_maid",
            "description": "将重型任务委托给小女仆处理。",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "run_inline": {"type": "boolean"},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_master_private",
            "description": "向主人私聊发送私密信息。",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "生成网络搜索入口。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_qq_file",
            "description": "发送图片或语音文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "file_type": {"type": "string", "enum": ["image", "voice"]},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inject_external_content",
            "description": "向当前对话注入外部系统提供的动态内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["content"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "search_diary": search_diary_tool,
    "manage_timer_task": manage_timer_task_tool,
    "delegate_to_maid": delegate_to_maid_tool,
    "send_master_private": send_master_private_tool,
    "browser_search": browser_search_tool,
    "send_qq_file": send_qq_file_tool,
    "inject_external_content": inject_external_content_tool,
}
