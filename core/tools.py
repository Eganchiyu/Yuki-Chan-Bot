# core/tools.py
import asyncio
import datetime
from urllib.parse import quote_plus

from config import cfg
from core.maid import MaidCapabilityBoundary, build_maid_task, maid_evolution_loop, search_diary_fast
from core.toolchain import ToolResult, ToolSpec
from utils.logger import get_logger

logger = get_logger("tools")


async def search_diary_tool(context, date_str=None, keyword=None):
    """查询 Yuki 日记。"""
    logger.info(
        f"[ToolCall][search_diary] chat_id={context.chat_id} date_str={date_str} keyword={keyword}"
    )
    if not date_str and not keyword:
        return ToolResult(success=False, content="请至少提供日期或关键词。", error="missing_date_or_keyword")
    result = await asyncio.to_thread(search_diary_fast, date_str, keyword)
    return ToolResult(success=True, content=result)


async def manage_timer_task_tool(context, title, due_time=None, action="create"):
    """轻量定时任务管理，先提供可扩展的状态入口。"""
    tasks = context.yuki.maid_current_tasks.setdefault("__timers__", {})
    task_id = f"timer_{len(tasks) + 1}"
    if action == "list":
        return ToolResult(success=True, content="当前定时任务列表", data=tasks)
    if action == "cancel":
        removed = tasks.pop(title, None)
        return ToolResult(
            success=removed is not None,
            content="定时任务已取消" if removed else "未找到对应定时任务",
            data=removed,
        )
    tasks[title] = {"id": task_id, "title": title, "due_time": due_time, "chat_id": context.chat_id}
    return ToolResult(success=True, content="定时任务已记录", data=tasks[title])


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


async def browser_search_tool(context, query):
    """提供网络搜索入口，当前返回可打开的搜索地址。"""
    if not query:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_query")
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    return ToolResult(success=True, content=f"可通过浏览器继续搜索：{url}", data={"url": url})


async def send_qq_file_tool(context, file_path, file_type="image"):
    """发送图片或语音文件，保留 QQ 文件发送扩展入口。"""
    if not file_path:
        return ToolResult(success=False, content="缺少文件路径", error="missing_file_path")
    if file_type == "voice":
        await context.sender.send_local_voice(context.chat_id, file_path, mode=context.mode)
    else:
        await context.sender.send_local_image(context.chat_id, file_path, mode=context.mode)
    return ToolResult(success=True, content="文件已发送。")


async def inject_external_content_tool(context, content, source="external"):
    """外部内容注入入口，用于 WebUI 或多渠道输入适配。"""
    if not content:
        return ToolResult(success=False, content="缺少注入内容", error="missing_content")
    current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
    context.history_dict.setdefault(context.chat_id, [])
    context.history_dict[context.chat_id].append({
        "role": "user",
        "content": f"【{source} 内容注入】{content}",
        "time": current_time_str,
    })
    return ToolResult(success=True, content="外部内容已注入当前上下文。")


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
        description="创建、取消或列出定时任务。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due_time": {"type": "string"},
                "action": {"type": "string", "enum": ["create", "cancel", "list"]},
            },
            "required": ["title"],
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
        description="生成网络搜索入口。",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=browser_search_tool,
    ),
    ToolSpec(
        name="send_qq_file",
        description="发送图片或语音文件。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "file_type": {"type": "string", "enum": ["image", "voice"]},
            },
            "required": ["file_path"],
        },
        handler=send_qq_file_tool,
    ),
    ToolSpec(
        name="inject_external_content",
        description="向当前对话注入外部系统提供的动态内容。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["content"],
        },
        handler=inject_external_content_tool,
    ),
]

# 兼容旧引用，后续新增工具优先维护 TOOL_SPECS。
TOOL_SCHEMAS = [spec.to_schema() for spec in TOOL_SPECS]
TOOL_HANDLERS = {spec.name: spec.handler for spec in TOOL_SPECS}
