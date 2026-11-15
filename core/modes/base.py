# core/modes/base.py
"""模式层基类：模式能力声明 + 生命周期钩子。

范式（docs/autonomous-architecture.md §1）：
- 每群同一时刻只有一种模式；`chat` 模式仍是原来的 `SessionPipeline`。
- 非聊天模式（debate / workshop）有自己的主循环，不发消息、不写群历史。
- `focus`(phone/art) 不是模式，而是模式内的子状态。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModeCapabilities:
    """一个模式允许做什么，由路由层与循环层共同遵守。"""

    can_send: bool = True               # 能否往真实会话发消息
    writes_chat_history: bool = True    # 是否写 data/chat_history.json
    accepts_human_input: bool = True    # 是否消费真人入站消息
    allow_sub_focus: bool = False       # 是否允许进入 phone/art 子聚焦
    triggers_diary: bool = True         # 是否触发超长历史日记总结
    accepts_inner_event: bool = False   # 是否接收内部事件（小女仆汇报等）

    def as_dict(self) -> dict[str, bool]:
        return {
            "can_send": self.can_send,
            "writes_chat_history": self.writes_chat_history,
            "accepts_human_input": self.accepts_human_input,
            "allow_sub_focus": self.allow_sub_focus,
            "triggers_diary": self.triggers_diary,
            "accepts_inner_event": self.accepts_inner_event,
        }


CHAT_CAPABILITIES = ModeCapabilities()


class Mode:
    """非聊天模式基类。子类只需实现 `run()`。"""

    name: str = "mode"
    title: str = ""
    capabilities: ModeCapabilities = ModeCapabilities(
        can_send=False,
        writes_chat_history=False,
        accepts_human_input=False,
        allow_sub_focus=False,
        triggers_diary=False,
        accepts_inner_event=True,
    )

    def __init__(self, *, chat_id, router=None, run_id: str = "", session_id: str = "",
                 goal: str = "", mode_arg: str = "group"):
        self.chat_id = str(chat_id)
        self.router = router
        self.run_id = str(run_id or "")
        self.session_id = str(session_id or "")
        self.goal = str(goal or "")
        self.mode_arg = str(mode_arg or "group")
        self._stop_reason = ""
        self.result: dict[str, Any] = {}

    # -------- 生命周期（默认空实现）--------
    async def run(self) -> dict[str, Any]:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def on_input(self, message: dict) -> None:
        """真人消息到达（当前群处于本模式）。默认忽略。"""
        return None

    def on_inner_event(self, event: dict) -> bool:
        """内部事件（小女仆汇报 / 定时注入）。返回 True 表示已消费，不再入缓冲。"""
        return False

    async def on_exit(self, result: dict[str, Any]) -> None:
        return None

    # -------- 停止请求 --------
    def request_stop(self, reason: str = "force_release") -> None:
        self._stop_reason = str(reason or "force_release")

    @property
    def stop_requested(self) -> bool:
        return bool(self._stop_reason)

    @property
    def stop_reason(self) -> str:
        return self._stop_reason
