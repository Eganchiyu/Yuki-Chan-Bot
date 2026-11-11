# core/focus/domains/phone.py
"""手机聚焦域声明与入口/退出工具实现。"""
from __future__ import annotations

from core import phone_macro as pm
from core.focus.domain import BASE_KEEP_TOOLS, FocusDomain
from core.focus.manager import register_domain
from core.focus.tools import make_focus_finish_handler
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")


def _trace_start(chat_id: str, goal: str) -> None:
    try:
        from modules.debug.phone_trace import phone_trace_store
        phone_trace_store.start_session(chat_id, goal=goal)
    except Exception as exc:
        logger.debug(f"[PhoneFocus] 启动轨迹会话失败: {exc}")


def _trace_finish(chat_id: str, summary: str, _reason: str = "finish") -> None:
    try:
        from modules.debug.phone_trace import phone_trace_store
        phone_trace_store.finish_session(chat_id, summary=summary, status="finished")
    except Exception as exc:
        logger.debug(f"[PhoneFocus] 结束轨迹会话失败: {exc}")


def _trace_model_call(chat_id: str, thought: str, tool_calls: list) -> None:
    try:
        from modules.debug.phone_trace import phone_trace_store
        phone_trace_store.set_pending_model_call(str(chat_id), thought or "", tool_calls)
    except Exception:
        pass


def _trace_final_reply(chat_id: str, raw_ans: str, clean_ans: str) -> None:
    try:
        from modules.debug.phone_trace import phone_trace_store
        phone_trace_store.record_turn_final_reply(str(chat_id), raw_ans, clean_ans)
    except Exception:
        pass


def _trace_incoming(chat_id: str, text: str) -> None:
    try:
        from modules.debug.phone_trace import phone_trace_store
        phone_trace_store.set_turn_incoming(str(chat_id), text)
    except Exception:
        pass


def _phone_stub(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    text = f"phone_action {data.get('action', '?')}"
    steps = data.get("steps") or []
    if steps:
        text += f" ({' / '.join(str(s) for s in steps[:3])})"
    return text


PHONE = FocusDomain(
    name="phone",
    title="手机",
    entry_tool="phone_start",
    exit_tool="phone_finish",
    domain_tools=frozenset({"phone_action", "phone_macro"}),
    keep_tools=BASE_KEEP_TOOLS,
    summary_prefix="【手机操作总结】",
    exit_hint="（你已结束本轮手机操作并收起手机，请直接根据上述操作结果回复用户。）",
    idle_turns_key="phone_focus_idle_turns",
    max_rounds_key="phone_focus_max_rounds",
    default_fallback="已完成手机操作。",
    empty_trace_fallback="已拿起手机查看并完成操作。",
    on_enter=_trace_start,
    on_exit=_trace_finish,
    on_model_call=_trace_model_call,
    on_final_reply=_trace_final_reply,
    on_incoming=_trace_incoming,
    stub=_phone_stub,
)

register_domain(PHONE)


def _active_phone_manager():
    """优先读取 core.phone_focus.phone_focus_manager 以兼容单元测试的 monkeypatch。"""
    from core import phone_focus as pf
    return pf.phone_focus_manager


async def phone_start_tool(context, goal: str = "") -> ToolResult:
    """进入手机聚焦模式，返回当前手机界面与已存组合技列表。"""
    from core.phone_driver import driver
    from core.tools.tools_phone import phone_action_tool

    mgr = _active_phone_manager()
    mgr.enter(context.chat_id, goal=goal)
    if goal:
        mgr.record_step(context.chat_id, f"开始操作手机: {goal}")

    unlocked, unlock_note = await driver.wake_and_unlock()
    if not unlocked:
        logger.warning(f"[PhoneFocus] {context.chat_id} 唤醒/解锁未完成: {unlock_note}")

    macros = pm.macro_store.list()
    if macros:
        macro_brief = "、".join(f"{m['name']}({m['steps']}步)" for m in macros[:12])
        macro_line = f"可用组合技: {macro_brief}"
    else:
        macro_line = "可用组合技: 暂无（摸熟流程后可用 phone_macro save 存下来）"

    inspect_res = await phone_action_tool(
        context,
        action="inspect",
        note=goal or "拿起手机查看当前屏幕",
        remember=False,
    )
    if not inspect_res.success and inspect_res.error == "device_unavailable":
        mgr._states.pop(str(context.chat_id), None)
        return ToolResult(
            success=False,
            content=inspect_res.content,
            data={"focus": "aborted", "phone_focus": "aborted", "no_persist": True},
            error=inspect_res.error,
            name="phone_start",
        )

    header = (
        "【已进入手机聚焦模式】已展开 phone_action / phone_macro / phone_finish 工具，并收起其他无关工具。\n"
        "你在聚焦期间仍处于群聊/会话中，可随时正常发言互动；"
        "操作全部结束后请调用 phone_finish(summary=\"...\") 收起手机并写一句简短总结。\n"
        f"{macro_line}"
    )
    content = f"{header}\n\n{inspect_res.content}"
    data = dict(inspect_res.data or {})
    data.update({
        "focus": "entered",
        "phone_focus": "entered",
        "goal": goal or "",
        "no_persist": False,
    })
    return ToolResult(
        success=inspect_res.success,
        content=content,
        data=data,
        error=inspect_res.error,
        name="phone_start",
    )


phone_finish_tool = make_focus_finish_handler(PHONE, manager_getter=_active_phone_manager)
