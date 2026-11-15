# modules/autonomous/mode_impl.py
"""把 debate / workshop 包装成模式层可调度的 `Mode` 实现。"""
from __future__ import annotations

import asyncio

from core.modes.base import Mode, ModeCapabilities
from modules.autonomous.sandbox_loop import SandboxDeps
from modules.autonomous.tools import SandboxState
from utils.logger import get_logger

logger = get_logger("autonomous.mode")


class DebateMode(Mode):
    name = "debate"
    title = "独处思考"
    capabilities = ModeCapabilities(
        can_send=False,
        writes_chat_history=False,
        accepts_human_input=False,
        allow_sub_focus=False,
        triggers_diary=False,
        accepts_inner_event=False,
    )

    def __init__(self, *, chat_id, router=None, run_id="", session_id="", goal="",
                 mode_arg="group", deps: SandboxDeps | None = None,
                 state: SandboxState | None = None, chat_label: str = ""):
        super().__init__(chat_id=chat_id, router=router, run_id=run_id,
                         session_id=session_id, goal=goal, mode_arg=mode_arg)
        self.deps = deps
        self.state = state or SandboxState(run_id=run_id, chat_id=self.chat_id)
        self.chat_label = chat_label
        self.debate_result = None

    async def run(self) -> dict:
        from modules.autonomous.inner_debate import InnerDebate

        if self.deps is None:
            raise RuntimeError("debate 模式缺少依赖")
        debate = InnerDebate(
            chat_id=self.chat_id,
            chat_label=self.chat_label,
            state=self.state,
            main_registry=self.deps.main_registry,
            yuki=self.deps.yuki,
            sender=None,          # 用 SilenceSender：思考期间不发群
            image_store=self.deps.image_store,
            stop_check=lambda: self.stop_requested,
        )
        self.debate_result = await debate.run()
        self.result = {"debate": self.debate_result}
        return self.result

    def on_input(self, message: dict) -> None:
        # 独处时被群里叫了：不改主意，只记一笔，由补台在回群时补偿
        logger.debug(f"[Debate] {self.chat_id} 独处期间收到消息（已缓冲）")


class WorkshopMode(Mode):
    name = "workshop"
    title = "自主工坊"
    capabilities = ModeCapabilities(
        can_send=False,
        writes_chat_history=False,
        accepts_human_input=False,
        allow_sub_focus=True,
        triggers_diary=False,
        accepts_inner_event=True,
    )

    def __init__(self, *, chat_id, router=None, run_id="", session_id="", goal="",
                 mode_arg="group", deps: SandboxDeps | None = None,
                 state: SandboxState | None = None, chat_label: str = ""):
        super().__init__(chat_id=chat_id, router=router, run_id=run_id,
                         session_id=session_id, goal=goal, mode_arg=mode_arg)
        self.deps = deps
        self.state = state or SandboxState(run_id=run_id, chat_id=self.chat_id)
        self.chat_label = chat_label
        self.workshop = None
        self._inner_events: list[dict] = []

    async def run(self) -> dict:
        from modules.autonomous.workshop import Workshop

        if self.deps is None:
            raise RuntimeError("workshop 模式缺少依赖")
        self.workshop = Workshop(
            chat_id=self.chat_id,
            chat_label=self.chat_label,
            state=self.state,
            deps=self.deps,
            stop_check=lambda: self.stop_requested,
        )
        outcome = await self.workshop.run()
        self.result = {"workshop": outcome}
        return self.result

    def on_inner_event(self, event: dict) -> bool:
        """小女仆汇报：塞进工坊的下一轮上下文，不写群历史、不发群。"""
        self._inner_events.append(dict(event or {}))
        if self.workshop is not None:
            self.workshop.queue_inner_event(dict(event or {}))
        logger.info(f"[Workshop] {self.chat_id} 收到内部事件（小女仆汇报）")
        return True

    def on_input(self, message: dict) -> None:
        logger.debug(f"[Workshop] {self.chat_id} 工坊期间收到群消息（已缓冲，退出后补台）")


def make_mode_factory(mode_name: str):
    """给 ModeRouter 用的工厂：只声明模式名，真正的依赖在 enter 时注入。"""
    cls = DebateMode if mode_name == "debate" else WorkshopMode

    def _factory():
        return cls(chat_id="", deps=None)

    return _factory


async def cancel_task(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
