# core/phone_focus.py
"""手机聚焦模式兼容层：委托给通用 core.focus，保留全部旧符号与单测接口。"""
from __future__ import annotations

from typing import Any

from core.focus import (
    DEFAULT_MAX_IDLE_TURNS,
    FocusManager,
    FocusState,
    focus_manager,
    is_domain_work_message,
    rewrite_in_memory_messages,
)
from core.focus.domains.phone import PHONE, phone_finish_tool, phone_start_tool

# 兼容旧集合常量（轉为 set 保持旧类型契约）
PHONE_HIDDEN_IN_DEFAULT = set(PHONE.hidden_in_default)
PHONE_FOCUS_ALLOWED_TOOLS = set(PHONE.focus_allowed)
PHONE_WORK_TOOL_NAMES = set(PHONE.work_tools)
SUMMARY_PREFIX = PHONE.effective_summary_prefix

# 兼容旧状态类名
PhoneFocusState = FocusState


class PhoneFocusManager:
    """兼容旧单域接口的薄适配器，底层委托给 FocusManager。"""

    def __init__(
        self,
        max_idle_turns: int = DEFAULT_MAX_IDLE_TURNS,
        *,
        _delegate: FocusManager | None = None,
    ):
        if _delegate is not None:
            self._mgr = _delegate
            self.max_idle_turns = _delegate.max_idle_turns
        else:
            self._mgr = FocusManager(max_idle_turns=max_idle_turns)
            self._mgr.register(PHONE)
            self.max_idle_turns = self._mgr.max_idle_turns

    @property
    def _states(self) -> dict[str, FocusState]:
        return self._mgr._states

    def is_focused(self, chat_id: str) -> bool:
        return self._mgr.is_focused(chat_id, "phone")

    def get_state(self, chat_id: str) -> FocusState | None:
        state = self._mgr.active(chat_id)
        if state and state.domain == "phone":
            return state
        return None

    def enter(self, chat_id: str, goal: str = "") -> FocusState:
        return self._mgr.enter(chat_id, "phone", goal=goal)

    def record_step(self, chat_id: str, step_desc: str, note: str = "") -> None:
        self._mgr.record_step(chat_id, step_desc, note, domain="phone")

    def build_fallback_summary(self, state: FocusState | None, custom_summary: str = "") -> str:
        return self._mgr.build_fallback_summary(state, custom_summary, domain="phone")

    @staticmethod
    def _is_work_session_message(msg: dict) -> bool:
        return is_domain_work_message(msg, PHONE)

    @staticmethod
    def rewrite_in_memory_tool_messages(tool_messages: list[dict], summary_text: str) -> None:
        rewrite_in_memory_messages(tool_messages, PHONE, summary_text)

    def exit_and_summarize(
        self,
        chat_id: str,
        history_manager: Any = None,
        summary: str = "",
        tool_messages: list[dict] | None = None,
    ) -> str:
        exit_res = self._mgr.exit(
            chat_id,
            history=history_manager,
            summary=summary,
            reason="finish",
            domain="phone",
            tool_messages=tool_messages,
        )
        return exit_res.summary if exit_res else self.build_fallback_summary(None, summary)

    def after_turn(self, chat_id: str, phone_tools_used: bool, history_manager: Any = None) -> bool:
        self._mgr.max_idle_turns = self.max_idle_turns
        used = {"phone"} if phone_tools_used else set()
        exit_res = self._mgr.after_turn(chat_id, used, history=history_manager)
        return exit_res is not None


phone_focus_manager = PhoneFocusManager(_delegate=focus_manager)

__all__ = [
    "PHONE_HIDDEN_IN_DEFAULT",
    "PHONE_FOCUS_ALLOWED_TOOLS",
    "PHONE_WORK_TOOL_NAMES",
    "SUMMARY_PREFIX",
    "DEFAULT_MAX_IDLE_TURNS",
    "PhoneFocusState",
    "PhoneFocusManager",
    "phone_focus_manager",
    "phone_start_tool",
    "phone_finish_tool",
]
