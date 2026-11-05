# core/phone_focus.py
"""手机聚焦模式管理器：按会话动态切换 ToolSpec 视图、记录操作轨迹、退出时抹除工作过程并注入 USER 总结。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config import cfg
from core import phone_macro as pm
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")

# 常态下隐藏的复杂手机工具（仅在进入聚焦模式后暴露）
PHONE_HIDDEN_IN_DEFAULT = {"phone_action", "phone_macro", "phone_finish"}

# 聚焦模式下允许暴露的工具集合（收起日记、小本本、画图、小女仆等无关工具，保留群聊基础互动）
PHONE_FOCUS_ALLOWED_TOOLS = {
    "phone_action",
    "phone_macro",
    "phone_finish",
    "skip",
    "send_master_private",
    "send_qq_file",
}

# 属于手机工作过程的工具名
PHONE_WORK_TOOL_NAMES = {"phone_start", "phone_action", "phone_macro", "phone_finish"}

SUMMARY_PREFIX = "【手机操作总结】"
DEFAULT_MAX_IDLE_TURNS = 5  # 连续闲置大于 5 轮（即第 6 轮闲置结束）自动退出


@dataclass
class PhoneFocusState:
    """单个会话的手机聚焦状态。"""
    chat_id: str
    goal: str = ""
    started_at: float = field(default_factory=time.time)
    idle_turns: int = 0
    trace: list[str] = field(default_factory=list)


class PhoneFocusManager:
    """管理各 chat_id 的手机聚焦模式生命周期与上下文覆写。"""

    def __init__(self, max_idle_turns: int = DEFAULT_MAX_IDLE_TURNS):
        self.max_idle_turns = max(1, int(max_idle_turns or DEFAULT_MAX_IDLE_TURNS))
        self._states: dict[str, PhoneFocusState] = {}

    def is_focused(self, chat_id: str) -> bool:
        return str(chat_id) in self._states

    def get_state(self, chat_id: str) -> PhoneFocusState | None:
        return self._states.get(str(chat_id))

    def enter(self, chat_id: str, goal: str = "") -> PhoneFocusState:
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is None:
            state = PhoneFocusState(chat_id=cid, goal=(goal or "").strip())
            self._states[cid] = state
            logger.info(f"[PhoneFocus] {cid} 进入手机聚焦模式 goal={state.goal or '无'}")
        else:
            if goal and not state.goal:
                state.goal = goal.strip()
            state.idle_turns = 0
        return state

    def record_step(self, chat_id: str, step_desc: str, note: str = "") -> None:
        """记录聚焦期间的一步操作，并将闲置轮数清零。"""
        cid = str(chat_id)
        state = self.enter(cid)
        state.idle_turns = 0
        desc = (step_desc or "").strip()
        note_str = (note or "").strip()
        entry = f"{desc} ({note_str})" if (desc and note_str) else (desc or note_str)
        if entry:
            state.trace.append(entry[:80])
            if len(state.trace) > 20:
                del state.trace[:-20]

    def build_fallback_summary(self, state: PhoneFocusState | None, custom_summary: str = "") -> str:
        text = (custom_summary or "").strip()
        if text:
            return text
        if state is None:
            return "已完成手机操作。"
        parts: list[str] = []
        if state.goal:
            parts.append(f"目标：{state.goal}")
        if state.trace:
            parts.append("执行步骤：" + " → ".join(state.trace[-8:]))
        if not parts:
            return "已拿起手机查看并完成操作。"
        return "；".join(parts)

    @staticmethod
    def _is_work_session_message(msg: dict) -> bool:
        """判断持久化 session 中的一条消息是否属于需要被总结覆盖的手机工作记录。"""
        if not isinstance(msg, dict):
            return False
        role = msg.get("role")
        if role == "tool":
            if msg.get("phone_focus_work") or msg.get("name") in PHONE_WORK_TOOL_NAMES:
                return True
        if role == "assistant":
            if msg.get("is_tool_thought") and msg.get("phone_focus_work"):
                return True
        return False

    @staticmethod
    def rewrite_in_memory_tool_messages(tool_messages: list[dict], summary_text: str) -> None:
        """原地清理当轮 tool_messages 中的手机工具调用链，保留期间插入的普通用户消息并追加 USER 总结。"""
        if not isinstance(tool_messages, list):
            return

        cleaned: list[dict] = []
        phone_call_ids: set[str] = set()

        for msg in tool_messages:
            if not isinstance(msg, dict):
                cleaned.append(msg)
                continue
            role = msg.get("role")

            # 1) assistant 发起的 tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                calls = msg.get("tool_calls") or []
                remaining_calls = []
                for call in calls:
                    fn_name = (call.get("function") or {}).get("name") or ""
                    call_id = call.get("id") or ""
                    if fn_name in PHONE_WORK_TOOL_NAMES:
                        if call_id:
                            phone_call_ids.add(call_id)
                    else:
                        remaining_calls.append(call)
                if remaining_calls:
                    new_msg = dict(msg)
                    new_msg["tool_calls"] = remaining_calls
                    cleaned.append(new_msg)
                continue

            # 2) tool 结果消息
            if role == "tool":
                if (
                    msg.get("name") in PHONE_WORK_TOOL_NAMES
                    or msg.get("tool_call_id") in phone_call_ids
                    or msg.get("phone_focus_work")
                ):
                    continue
                cleaned.append(msg)
                continue

            # 3) 工具截图临时 user 消息
            if role == "user":
                content = msg.get("content")
                if isinstance(content, str) and content.startswith("【工具截图】"):
                    continue
                if isinstance(content, list) and any(
                    isinstance(b, dict) and str(b.get("text") or "").startswith("【工具截图】")
                    for b in content
                ):
                    continue

            cleaned.append(msg)

        cleaned.append({
            "role": "user",
            "content": (
                f"{SUMMARY_PREFIX}{summary_text}\n"
                "（你已结束本轮手机操作并收起手机，请直接根据上述操作结果回复用户。）"
            ),
        })
        tool_messages[:] = cleaned

    def exit_and_summarize(
        self,
        chat_id: str,
        history_manager: Any = None,
        summary: str = "",
        tool_messages: list[dict] | None = None,
    ) -> str:
        """退出手机聚焦模式，清除工作过程记录，保留期间群聊消息并以 USER 身份注入简短总结。"""
        cid = str(chat_id)
        state = self._states.pop(cid, None)
        final_summary = self.build_fallback_summary(state, summary)
        summary_msg = {
            "role": "user",
            "content": f"{SUMMARY_PREFIX}{final_summary}",
            "is_phone_summary": True,
        }

        if history_manager is not None:
            try:
                session = history_manager.get_session(cid)
                filtered = [msg for msg in session if not self._is_work_session_message(msg)]
                filtered.append(summary_msg)
                history_manager.replace_session(cid, filtered)
            except Exception as exc:
                logger.warning(f"[PhoneFocus] 覆写会话历史失败 {cid}: {exc}")

        if tool_messages is not None:
            self.rewrite_in_memory_tool_messages(tool_messages, final_summary)

        logger.info(f"[PhoneFocus] {cid} 已退出手机聚焦模式，注入总结: {final_summary[:80]}")
        return final_summary

    def after_turn(self, chat_id: str, phone_tools_used: bool, history_manager: Any = None) -> bool:
        """每轮对话结束时更新闲置计数；连续闲置 > max_idle_turns (5轮) 时自动退出并总结。"""
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is None:
            return False

        if phone_tools_used:
            state.idle_turns = 0
            return False

        state.idle_turns += 1
        limit = int(
            getattr(getattr(cfg, "tools", None), "phone_focus_idle_turns", self.max_idle_turns)
            or self.max_idle_turns
        )
        if state.idle_turns > limit:
            auto_note = self.build_fallback_summary(state)
            logger.info(
                f"[PhoneFocus] {cid} 连续 {state.idle_turns} 轮未操作手机（>{limit}轮），自动退出聚焦模式"
            )
            self.exit_and_summarize(cid, history_manager=history_manager, summary=auto_note)
            return True
        return False


phone_focus_manager = PhoneFocusManager()


async def phone_start_tool(context, goal: str = "") -> ToolResult:
    """进入手机聚焦模式，返回当前手机界面与已存组合技列表。"""
    from core.phone_driver import driver
    from core.tools.tools_phone import phone_action_tool

    phone_focus_manager.enter(context.chat_id, goal=goal)
    if goal:
        phone_focus_manager.record_step(context.chat_id, f"开始操作手机: {goal}")

    # 进入聚焦：先点亮屏幕并解除锁屏（本机无锁屏密码，上滑即可）。
    # 对模型完全无感：只记日志，不进工具输出。
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
        # 手机未连接时直接回退到常态，避免模型还得再调一次 phone_finish 退出
        phone_focus_manager._states.pop(str(context.chat_id), None)
        return ToolResult(
            success=False,
            content=inspect_res.content,
            data={"phone_focus": "aborted", "no_persist": True},
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


async def phone_finish_tool(context, summary: str = "") -> ToolResult:
    """结束操作手机，退出聚焦模式，用一句 USER 总结覆盖工作过程记录。"""
    history_manager = (context.metadata or {}).get("history_manager")
    final_summary = phone_focus_manager.exit_and_summarize(
        context.chat_id,
        history_manager=history_manager,
        summary=summary,
    )
    if isinstance(context.metadata, dict):
        context.metadata["phone_finish_summary"] = final_summary

    return ToolResult(
        success=True,
        content=(
            f"【已退出手机聚焦模式】已恢复常规工具空间，刚才的手机工作过程已压缩为上下文总结："
            f"{SUMMARY_PREFIX}{final_summary}"
        ),
        data={
            "phone_focus": "exited",
            "summary": final_summary,
            "no_persist": True,
        },
        name="phone_finish",
    )
