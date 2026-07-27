# core/modes.py
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

logger = get_logger("modes")


@dataclass(frozen=True)
class ModeSpec:
    """Yuki 可进入的模式声明。"""
    mode_id: str
    display_name: str
    session_id: str
    tool_group: str = "default"
    is_focus_mode: bool = False


class QQChatMode:
    """默认 QQ 群聊模式包装。"""
    spec = ModeSpec(
        mode_id="group",
        display_name="QQChatMode",
        session_id="<chat_id>",
        tool_group="default",
        is_focus_mode=False,
    )


class BrowserInteractionMode:
    """浏览器交互聚焦模式包装。"""
    spec = ModeSpec(
        mode_id="browser_interaction",
        display_name="BrowserInteractionMode",
        session_id="mode:browser",
        tool_group="browser_interaction",
        is_focus_mode=True,
    )


@dataclass
class FocusModeState:
    """当前全局聚焦模式状态。"""
    mode: str
    display_name: str
    session_id: str
    origin_chat_id: str
    origin_mode: str
    entered_at: float
    last_active_at: float
    goal: str = ""
    status: str = "running"
    steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: str):
        text = str(step or "").strip()
        if not text:
            return
        self.steps.append(text)
        self.last_active_at = time.time()

    def brief(self, max_steps: int = 4) -> str:
        goal_text = self.goal or "未记录目标"
        recent_steps = self.steps[-max_steps:]
        if recent_steps:
            steps_text = "；".join(recent_steps)
        else:
            steps_text = "尚未执行具体步骤"
        return (
            f"当前处于 {self.display_name}，来源会话 {self.origin_mode}:{self.origin_chat_id}，"
            f"目标：{goal_text}；进展：{steps_text}"
        )


class ModeManager:
    """维护 Yuki 的全局聚焦模式。"""

    def __init__(self):
        self._focus_state: FocusModeState | None = None
        self._lock = asyncio.Lock()
        self._specs = {
            QQChatMode.spec.mode_id: QQChatMode.spec,
            BrowserInteractionMode.spec.mode_id: BrowserInteractionMode.spec,
        }

    def get_spec(self, mode: str) -> ModeSpec:
        return self._specs.get(mode) or QQChatMode.spec

    def current_focus(self) -> FocusModeState | None:
        return self._focus_state

    def is_focus_active(self) -> bool:
        return self._focus_state is not None and self._focus_state.status == "running"

    def active_mode_id(self) -> str:
        return self._focus_state.mode if self.is_focus_active() else "idle"

    async def enter_mode(
        self,
        mode: str,
        origin_chat_id: str,
        origin_mode: str,
        goal: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, FocusModeState | None, str]:
        """进入全局聚焦模式。同一时间只允许一个聚焦模式运行。"""
        async with self._lock:
            if self.is_focus_active():
                assert self._focus_state is not None
                return False, self._focus_state, "focus_mode_busy"

            spec = self.get_spec(mode)
            if not spec.is_focus_mode:
                return False, None, "mode_is_not_focus_mode"

            now = time.time()
            self._focus_state = FocusModeState(
                mode=spec.mode_id,
                display_name=spec.display_name,
                session_id=spec.session_id,
                origin_chat_id=str(origin_chat_id),
                origin_mode=str(origin_mode),
                entered_at=now,
                last_active_at=now,
                goal=str(goal or ""),
                metadata=dict(metadata or {}),
            )
            logger.info(
                f"[Mode] 进入 {spec.display_name}: origin={origin_mode}:{origin_chat_id} goal={goal}"
            )
            return True, self._focus_state, "entered"

    async def record_step(self, step: str) -> FocusModeState | None:
        """记录当前聚焦模式步骤。"""
        async with self._lock:
            if not self.is_focus_active():
                return None
            assert self._focus_state is not None
            self._focus_state.add_step(step)
            return self._focus_state

    async def complete_mode(self, summary: str = "") -> tuple[bool, FocusModeState | None, str]:
        """完成并退出当前聚焦模式，返回退出前的状态快照。"""
        async with self._lock:
            if not self.is_focus_active():
                return False, None, "no_active_focus_mode"
            assert self._focus_state is not None
            state = self._focus_state
            if summary:
                state.add_step(f"完成说明：{summary}")
            state.status = "completed"
            state.last_active_at = time.time()
            self._focus_state = None
            logger.info(f"[Mode] 退出 {state.display_name}: summary={summary}")
            return True, state, "completed"

    async def exit_mode(self, summary: str = "") -> tuple[bool, FocusModeState | None, str]:
        """兼容命名：退出当前聚焦模式。"""
        return await self.complete_mode(summary=summary)

    def render_prompt_status(self, current_chat_id: str | None = None, current_mode: str | None = None) -> str:
        """生成注入到全局 prompt 的模式状态说明。"""
        if not self.is_focus_active():
            return "【全局模式状态】当前没有聚焦模式运行，Yuki 处于 QQChatMode 空闲待命状态。"

        assert self._focus_state is not None
        state = self._focus_state
        source_note = ""
        if current_chat_id and str(current_chat_id) == state.origin_chat_id:
            source_note = "当前会话是该聚焦模式的来源会话；需要时可以询问或接收模式完成后的返回说明。"
        else:
            source_note = "当前会话不是该聚焦模式的来源会话；正常聊天即可，但要知道自己后台正在执行该模式。"

        return f"【全局模式状态】{state.brief()}。{source_note} 同一时间不能重复进入新的聚焦模式。"
