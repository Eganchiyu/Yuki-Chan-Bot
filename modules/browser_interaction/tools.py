# modules/browser_interaction/tools.py
from core.toolchain import ToolResult, ToolSpec


async def browser_scan_placeholder_tool(context):
    """浏览器扫描占位工具，用于验证浏览器模式工具链通路。"""
    focus = context.yuki.mode_manager.current_focus()
    if not focus or focus.mode != "browser_interaction":
        return ToolResult.failure("当前不在浏览器交互模式。", "not_in_browser_mode")

    await context.yuki.mode_manager.record_step("完成一次浏览器页面扫描验证")
    return ToolResult(
        success=True,
        content="浏览器扫描占位成功：当前尚未接入真实浏览器驱动。",
        data={
            "mode": focus.mode,
            "session_id": focus.session_id,
            "origin_chat_id": focus.origin_chat_id,
            "origin_mode": focus.origin_mode,
            "mock_page": {
                "url": "about:blank",
                "title": "浏览器交互模式占位页",
                "elements": [],
            },
        },
    )


async def browser_record_step_tool(context, step):
    """记录浏览器模式当前步骤，用于验证任务进展摘要。"""
    if not step:
        return ToolResult.failure("缺少步骤说明。", "missing_step")
    focus = await context.yuki.mode_manager.record_step(step)
    if not focus or focus.mode != "browser_interaction":
        return ToolResult.failure("当前不在浏览器交互模式。", "not_in_browser_mode")
    return ToolResult(success=True, content="已记录浏览器模式步骤。", data={"brief": focus.brief()})


async def browser_complete_tool(context, summary):
    """完成浏览器模式，并把返回说明发送到来源会话。"""
    if not summary:
        return ToolResult.failure("缺少完成说明。", "missing_summary")

    ok, state, reason = await context.yuki.mode_manager.complete_mode(summary)
    if not ok or not state:
        return ToolResult.failure("当前没有可完成的浏览器模式。", reason)

    return_message = f"【浏览器模式完成】{summary}"
    if state.origin_mode in {"group", "private", "master_private"}:
        send_mode = "private" if state.origin_mode == "master_private" else state.origin_mode
        await context.sender.send(state.origin_chat_id, return_message, mode=send_mode)

    history_manager = context.metadata.get("history_manager")
    if history_manager:
        history_manager.append_session_message(
            state.origin_chat_id,
            "assistant",
            return_message,
            source_mode=state.mode,
            mode_return=True,
        )

    return ToolResult(
        success=True,
        content="浏览器模式已完成，并已向来源会话提交返回说明。",
        data={
            "origin_chat_id": state.origin_chat_id,
            "origin_mode": state.origin_mode,
            "brief": state.brief(),
        },
    )


BROWSER_TOOL_SPECS = [
    ToolSpec(
        name="browser_scan_placeholder",
        description="扫描当前浏览器页面的占位工具。当前仅用于验证浏览器模式工具链，尚未执行真实浏览器操作。",
        parameters={"type": "object", "properties": {}},
        handler=browser_scan_placeholder_tool,
    ),
    ToolSpec(
        name="browser_record_step",
        description="记录浏览器交互模式的一条步骤进展，用于后续生成当前任务摘要。",
        parameters={
            "type": "object",
            "properties": {
                "step": {"type": "string", "description": "已经完成或正在进行的步骤说明"},
            },
            "required": ["step"],
        },
        handler=browser_record_step_tool,
    ),
    ToolSpec(
        name="browser_complete",
        description="完成浏览器交互模式，并向来源 QQ 群聊或私聊提交返回说明。",
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "浏览器模式完成后的返回说明"},
            },
            "required": ["summary"],
        },
        handler=browser_complete_tool,
    ),
]
