# core/engine/turn.py
"""TurnState：单轮工具链对话的状态容器。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.focus import FocusExit
from core.toolchain import ToolContext


@dataclass
class PersistDecision:
    """单条消息的持久化判定结果。"""

    action: str = "write"          # "write" | "drop"
    focus_work: str | None = None  # 若属于聚焦域工作过程，记下域名


@dataclass
class TurnState:
    """封装 chat_with_tools 单轮对话期间的全部运行状态。"""

    chat_id: str
    mode: str
    context: ToolContext
    tool_messages: list[dict]
    active_registry: Any
    active_tool_manager: Any
    valid_tool_names: set[str] | None = None
    fallback_factory: Callable[[], Awaitable[list[dict]]] | None = None
    round_idx: int = 0
    max_rounds: int = 4
    base_max_rounds: int = 4
    tools_executed: bool = False
    used_domains: set[str] = field(default_factory=set)
    exited_this_turn: set[str] = field(default_factory=set)
    pending_exits: list[FocusExit] = field(default_factory=list)
    batch_exited_domains: set[str] = field(default_factory=set)
    tool_trace: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    sent_thoughts: set[str] = field(default_factory=set)
    pending_thought: str = ""
    batch_focus_domain: str | None = None
    debug_snap_id: str | None = None
    outcome: str = ""              # "reply" | "skip" | "filtered" | "exhausted"
    final: tuple[str, str] | None = None
