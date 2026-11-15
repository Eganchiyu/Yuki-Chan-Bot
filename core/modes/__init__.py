# core/modes/__init__.py
"""模式层：每群单一模式 + 全局单活跃非聊天模式。

`chat` 模式即原有 SessionPipeline 流程；debate / workshop 等非聊天模式
由 `modules/autonomous` 提供，并通过本层的路由器接入入站收口。
"""
from core.modes.base import CHAT_CAPABILITIES, Mode, ModeCapabilities  # noqa: F401
from core.modes.pipeline import ModeAwarePipeline  # noqa: F401
from core.modes.router import (  # noqa: F401
    CHAT_MODE,
    ROUTE_CHAT,
    ROUTE_FROZEN,
    ROUTE_MODE,
    FrozenChat,
    ModeBusyError,
    ModeRouter,
    ModeState,
    router,
)

__all__ = [
    "CHAT_CAPABILITIES",
    "CHAT_MODE",
    "FrozenChat",
    "Mode",
    "ModeAwarePipeline",
    "ModeBusyError",
    "ModeCapabilities",
    "ModeRouter",
    "ModeState",
    "ROUTE_CHAT",
    "ROUTE_FROZEN",
    "ROUTE_MODE",
    "router",
]
