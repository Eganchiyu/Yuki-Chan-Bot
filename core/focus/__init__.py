# core/focus/__init__.py
"""通用聚焦模式架构导出入口。"""
from core.focus.domain import BASE_KEEP_TOOLS, FocusDomain
from core.focus.manager import (
    DEFAULT_MAX_IDLE_TURNS,
    FocusExit,
    FocusManager,
    FocusState,
    focus_manager,
    register_domain,
)
from core.focus.rewrite import (
    build_summary_message,
    is_domain_work_message,
    is_focus_summary_message,
    message_focus_domain,
    rewrite_in_memory_messages,
    rewrite_persistent_session,
)
from core.focus.tools import (
    focus_finish_spec,
    focus_start_spec,
    make_focus_finish_handler,
    make_focus_start_handler,
)
from core.focus.view import ToolView

# 导入内置域完成自动注册
from core.focus import domains as _domains  # noqa: F401

__all__ = [
    "BASE_KEEP_TOOLS",
    "DEFAULT_MAX_IDLE_TURNS",
    "FocusDomain",
    "FocusExit",
    "FocusManager",
    "FocusState",
    "ToolView",
    "focus_manager",
    "register_domain",
    "build_summary_message",
    "is_domain_work_message",
    "is_focus_summary_message",
    "message_focus_domain",
    "rewrite_in_memory_messages",
    "rewrite_persistent_session",
    "focus_start_spec",
    "focus_finish_spec",
    "make_focus_start_handler",
    "make_focus_finish_handler",
]
