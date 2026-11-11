# core/focus/view.py
"""ToolView：由当前会话聚焦状态唯一推导出的可见工具集合。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.focus.manager import FocusManager


@dataclass(frozen=True)
class ToolView:
    """不可变工具可见性视图。"""

    visible: frozenset[str]

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self.visible

    @classmethod
    def resolve(
        cls,
        registry: Any,
        manager: FocusManager,
        chat_id: Any,
        exited_this_turn: set[str] | None = None,
    ) -> "ToolView":
        """根据会话当前聚焦状态与本轮已退出域推导可见工具集合。"""
        names = set(registry.list_functions()) if hasattr(registry, "list_functions") else set()
        exited = exited_this_turn or set()
        state = manager.active(chat_id)
        if state is not None:
            domain = manager.get_domain(state.domain)
            if domain is not None and domain.entry_tool in names:
                return cls(frozenset(names & domain.focus_allowed))

        for domain in manager.domains():
            if domain.entry_tool in names:
                names -= domain.hidden_in_default
                if domain.name in exited:
                    names.discard(domain.entry_tool)
        return cls(frozenset(names))

    @classmethod
    def from_legacy_kwargs(
        cls,
        registry: Any,
        manager: FocusManager,
        legacy_kwargs: dict[str, Any] | None = None,
    ) -> "ToolView":
        """兼容 get_tools(<domain>_focus=bool) 旧调用方式，构造等价的 ToolView。"""
        names = set(registry.list_functions()) if hasattr(registry, "list_functions") else set()
        kwargs = legacy_kwargs or {}
        for domain in manager.domains():
            if kwargs.get(f"{domain.name}_focus") and domain.entry_tool in names:
                return cls(frozenset(names & domain.focus_allowed))

        for domain in manager.domains():
            if domain.entry_tool in names:
                names -= domain.hidden_in_default
        return cls(frozenset(names))
