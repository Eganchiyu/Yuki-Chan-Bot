# core/focus/tools.py
"""通用聚焦入口/退出工具工厂（focus_start_spec / focus_finish_spec）。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from core.focus.domain import FocusDomain
from core.focus.manager import FocusManager, focus_manager
from core.toolchain import ToolResult, ToolSpec


def make_focus_start_handler(
    domain: FocusDomain,
    overview_handler: Callable[..., Awaitable[ToolResult]],
    *,
    manager_getter: Callable[[], Any] = lambda: focus_manager,
) -> Callable[..., Awaitable[ToolResult]]:
    """包装聚焦入口工具：先进入聚焦状态，若 overview_handler 返回 aborted 则自动回滚状态。"""

    async def _handler(context, goal: str = "", **kwargs) -> ToolResult:
        mgr = manager_getter()
        history = (context.metadata or {}).get("history_manager") if isinstance(context.metadata, dict) else None
        if hasattr(mgr, "enter"):
            try:
                mgr.enter(context.chat_id, domain.name, goal=goal, history=history)
            except TypeError:
                mgr.enter(context.chat_id, goal=goal)

        res = await overview_handler(context, goal=goal, **kwargs)
        data = res.data if isinstance(res.data, dict) else {}
        if data.get("focus") == "aborted" or data.get(f"{domain.name}_focus") == "aborted":
            if hasattr(mgr, "abort"):
                mgr.abort(context.chat_id, domain.name)
            elif hasattr(mgr, "_states"):
                mgr._states.pop(str(context.chat_id), None)
        return res

    return _handler


def make_focus_finish_handler(
    domain: FocusDomain,
    *,
    manager_getter: Callable[[], Any] = lambda: focus_manager,
) -> Callable[..., Awaitable[ToolResult]]:
    """生成通用聚焦退出 handler：调用 manager.exit 并登记待内存覆写的退出记录。"""

    async def _finish_tool(context, summary: str = "") -> ToolResult:
        mgr = manager_getter()
        history_manager = (
            (context.metadata or {}).get("history_manager")
            if isinstance(context.metadata, dict)
            else None
        )
        if hasattr(mgr, "exit") and isinstance(mgr, FocusManager):
            exit_info = mgr.exit(
                context.chat_id,
                history=history_manager,
                summary=summary,
                reason="finish",
                domain=domain.name,
            )
            final_summary = exit_info.summary if exit_info else mgr.build_fallback_summary(None, summary, domain=domain.name)
        else:
            # 兼容 PhoneFocusManager 实例
            final_summary = mgr.exit_and_summarize(
                context.chat_id,
                history_manager=history_manager,
                summary=summary,
            )
            from core.focus.manager import FocusExit
            exit_info = FocusExit(
                chat_id=str(context.chat_id),
                domain=domain.name,
                summary=final_summary,
                reason="finish",
            )

        if isinstance(context.metadata, dict):
            exits = context.metadata.setdefault("focus_exits", [])
            if exit_info is not None:
                exits.append(exit_info)
            context.metadata[f"{domain.name}_finish_summary"] = final_summary

        return ToolResult(
            success=True,
            content=(
                f"【已退出{domain.title}聚焦模式】已恢复常规工具空间，刚才的{domain.title}工作过程已压缩为上下文总结："
                f"{domain.effective_summary_prefix}{final_summary}"
            ),
            data={
                "focus": "exited",
                f"{domain.name}_focus": "exited",
                "domain": domain.name,
                "summary": final_summary,
                "no_persist": True,
            },
            name=domain.exit_tool,
        )

    return _finish_tool


def focus_start_spec(
    domain: FocusDomain,
    *,
    description: str,
    handler: Callable[..., Awaitable[ToolResult]],
    goal_description: str = "",
    parameters: dict | None = None,
    wrap_enter: bool = False,
    manager_getter: Callable[[], Any] = lambda: focus_manager,
) -> ToolSpec:
    """构建标准聚焦入口 ToolSpec。"""
    params = parameters or {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": goal_description or f"这次进入{domain.title}模式要做什么（可选）",
            },
        },
    }
    final_handler = (
        make_focus_start_handler(domain, handler, manager_getter=manager_getter)
        if wrap_enter
        else handler
    )
    return ToolSpec(
        name=domain.entry_tool,
        description=description,
        parameters=params,
        handler=final_handler,
    )


def focus_finish_spec(
    domain: FocusDomain,
    *,
    description: str = "",
    summary_description: str = "",
    handler: Callable[..., Awaitable[ToolResult]] | None = None,
    manager_getter: Callable[[], Any] = lambda: focus_manager,
) -> ToolSpec:
    """构建标准聚焦退出 ToolSpec。"""
    desc = description or (
        f"结束{domain.title}操作并退出聚焦模式，恢复常规工具空间。"
        f"请传入一句简短的 summary 总结刚才在{domain.title}模式下做了什么及结果，"
        "它会覆盖工作模式中的繁琐操作记录保留在上下文里。"
    )
    sum_desc = summary_description or f"简短总结刚才在{domain.title}模式下做了什么与结果（会以 USER 总结的形式写入上下文）"
    return ToolSpec(
        name=domain.exit_tool,
        description=desc,
        parameters={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": sum_desc,
                },
            },
            "required": ["summary"],
        },
        handler=handler or make_focus_finish_handler(domain, manager_getter=manager_getter),
    )
