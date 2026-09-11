# core/tools/tools_browser.py
"""浏览器交互聚焦模式入口工具。"""
import asyncio

from core.toolchain import ToolResult


async def enter_browser_interaction_tool(context, goal=None):
    """进入浏览器交互聚焦模式，并触发浏览器模式会话。"""
    goal_text = str(goal or context.combined_text or "浏览器交互任务").strip()
    ok, state, reason = await context.yuki.mode_manager.enter_mode(
        "browser_interaction",
        origin_chat_id=context.chat_id,
        origin_mode=context.mode,
        goal=goal_text,
    )
    if not ok or not state:
        current = context.yuki.mode_manager.current_focus()
        busy_text = current.brief() if current else "已有聚焦模式正在运行"
        return ToolResult.failure(
            f"暂时不能进入浏览器交互模式：{busy_text}",
            reason,
            data={"active_mode": current.mode if current else None},
        )

    history_manager = context.metadata.get("history_manager")
    if history_manager:
        browser_prompt = context.yuki.get_setting("browser_interaction")
        history_manager.get_session(state.session_id, browser_prompt)
        history_manager.append_session_message(
            state.session_id,
            "user",
            f"【进入浏览器模式】来源={context.mode}:{context.chat_id}；目标={goal_text}",
            origin_chat_id=context.chat_id,
            origin_mode=context.mode,
        )

    callback = context.metadata.get("process_callback") or getattr(context.yuki, "process_callback", None)
    if callback:
        message_obj = {
            "name": "ModeManager",
            "content": f"【浏览器交互模式启动】目标：{goal_text}",
            "raw_text": goal_text,
            "source": "mode_manager",
            "owner_id": state.session_id,
        }
        asyncio.create_task(
            callback(
                state.session_id,
                "browser_interaction",
                message_obj=message_obj,
                debounce_flag=False,
                force_reply=True,
            )
        )

    return ToolResult(
        success=True,
        content="已进入浏览器交互模式，并创建独立模式会话。",
        data={
            "mode": state.mode,
            "session_id": state.session_id,
            "origin_chat_id": state.origin_chat_id,
            "origin_mode": state.origin_mode,
            "goal": state.goal,
        },
    )
