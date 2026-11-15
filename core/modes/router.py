# core/modes/router.py
"""模式路由：每群单一模式 + 全局单活跃非聊天模式 + 冻结与内部事件投递。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.modes.base import CHAT_CAPABILITIES, Mode, ModeCapabilities
from utils.logger import get_logger

logger = get_logger("modes")

CHAT_MODE = "chat"

# route() 的三种去向
ROUTE_CHAT = "chat"       # 交给父类 SessionPipeline 正常处理
ROUTE_MODE = "mode"       # 交给该群当前的非聊天模式
ROUTE_FROZEN = "frozen"   # 全局被别的群占用：只入缓冲并登记冻结


class ModeBusyError(RuntimeError):
    """全局已经有一个非聊天模式在跑（唯一体性约束）。"""


@dataclass
class ModeState:
    chat_id: str
    mode: str
    run_id: str
    started_at: float
    session_id: str = ""
    instance: Any = None
    task: Any = None

    @property
    def is_chat(self) -> bool:
        return self.mode == CHAT_MODE

    def as_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "mode": self.mode,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "elapsed": max(0.0, time.time() - self.started_at),
        }


@dataclass
class FrozenChat:
    """冻结期间的群登记：谁在被冻、期间来了多少真人消息。"""

    chat_id: str
    since: float = field(default_factory=time.time)
    messages: int = 0
    last_at: float = 0.0


class ModeRouter:
    """模式路由与唯一体性守卫（纯内存状态，不跑 LLM）。"""

    def __init__(self):
        self._modes: dict[str, Callable[[], Mode]] = {}
        self._states: dict[str, ModeState] = {}
        self._global_run: ModeState | None = None
        self._frozen: dict[str, FrozenChat] = {}
        self._catchup_handler: Callable[[str], Any] | None = None

    # ------------------------------------------------------------ 注册
    def register_mode(self, name: str, factory: Callable[[], Mode]) -> None:
        self._modes[str(name)] = factory

    def has_mode(self, name: str) -> bool:
        return str(name) in self._modes

    def create_mode(self, name: str) -> Mode | None:
        factory = self._modes.get(str(name))
        if factory is None:
            return None
        return factory()

    def set_catchup_handler(self, handler: Callable[[str], Any] | None) -> None:
        self._catchup_handler = handler

    # ------------------------------------------------------------ 查询
    @property
    def global_run(self) -> ModeState | None:
        return self._global_run

    def is_idle(self) -> bool:
        """没有任何非聊天模式在跑（chat 模式不算）。"""
        return self._global_run is None

    def current_mode(self, chat_id: Any) -> str:
        state = self._states.get(str(chat_id))
        return state.mode if state else CHAT_MODE

    def active_state(self, chat_id: Any) -> ModeState | None:
        state = self._states.get(str(chat_id))
        if state is None or state.is_chat:
            return None
        return state

    def capabilities(self, chat_id: Any) -> ModeCapabilities:
        state = self.active_state(chat_id)
        if state is None or state.instance is None:
            return CHAT_CAPABILITIES
        return getattr(state.instance, "capabilities", CHAT_CAPABILITIES)

    def states(self) -> dict[str, ModeState]:
        return dict(self._states)

    # ------------------------------------------------------------ 路由
    def route(self, chat_id: Any, mode: str | None = None) -> tuple[str, ModeState | None]:
        """决定一条入站消息的去向，返回 (action, 相关 ModeState)。"""
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is not None and not state.is_chat:
            # 本群正在跑非聊天模式
            return ROUTE_MODE, state
        if self._global_run is not None:
            # 唯一体性：全局只有一个非聊天模式，其它群一律冻结
            return ROUTE_FROZEN, self._global_run
        return ROUTE_CHAT, None

    # ------------------------------------------------------------ 生命周期
    def enter(
        self,
        chat_id: Any,
        mode: str,
        *,
        run_id: str | None = None,
        session_id: str = "",
        instance: Mode | None = None,
    ) -> ModeState:
        """进入非聊天模式；全局已被别的群占用时抛 ModeBusyError。"""
        cid = str(chat_id)
        mode = str(mode)
        if mode == CHAT_MODE:
            raise ValueError("chat 模式不经 router.enter 进入")
        current = self._states.get(cid)
        if current is not None and not current.is_chat:
            if current.mode == mode:
                return current
            raise ModeBusyError(f"chat {cid} 已有模式 {current.mode} 在跑")
        if self._global_run is not None and self._global_run.chat_id != cid:
            raise ModeBusyError(
                f"全局已有 {self._global_run.mode} 在跑（chat {self._global_run.chat_id}）"
            )
        state = ModeState(
            chat_id=cid,
            mode=mode,
            run_id=str(run_id or f"{mode}-{int(time.time() * 1000)}"),
            started_at=time.time(),
            session_id=str(session_id or ""),
            instance=instance,
        )
        self._states[cid] = state
        self._global_run = state
        self._frozen.setdefault(cid, FrozenChat(chat_id=cid))
        logger.warning(f"[Modes] {cid} 进入 {mode} 模式 run={state.run_id}")
        return state

    def exit(self, chat_id: Any = None, *, run_id: str | None = None) -> ModeState | None:
        """退出非聊天模式；不传 chat_id 时退出当前全局 run。"""
        cid = str(chat_id) if chat_id is not None else (
            self._global_run.chat_id if self._global_run else None
        )
        if cid is None:
            return None
        state = self._states.get(cid)
        if state is None or state.is_chat:
            return None
        if run_id and state.run_id != str(run_id):
            logger.warning(f"[Modes] 忽略过期退出 cid={cid} run={run_id}（当前 {state.run_id}）")
            return None
        self._states.pop(cid, None)
        if self._global_run is state:
            self._global_run = None
        logger.warning(f"[Modes] {cid} 退出 {state.mode} 模式 run={state.run_id}")
        return state

    def force_release(self, reason: str = "force_release") -> ModeState | None:
        """逃生阀：中断当前非聊天模式，请求它尽快收尾。"""
        state = self._global_run
        if state is None:
            return None
        instance = state.instance
        if instance is not None:
            try:
                instance.request_stop(reason)
            except Exception as exc:  # pragma: no cover - 防御
                logger.warning(f"[Modes] 请求停止模式失败: {exc}")
        logger.warning(f"[Modes] 强制放行 {state.chat_id}（{reason}）")
        return state

    # ------------------------------------------------------------ 冻结与补台
    def mark_frozen(self, chat_id: Any, message: dict | None = None) -> FrozenChat:
        """登记某个群在非聊天模式期间的缺席；真人消息才计数。"""
        cid = str(chat_id)
        frozen = self._frozen.get(cid)
        if frozen is None:
            frozen = FrozenChat(chat_id=cid)
            self._frozen[cid] = frozen
        if message is not None and _counts_as_missed(message):
            frozen.messages += 1
            frozen.last_at = time.time()
        return frozen

    def is_frozen(self, chat_id: Any) -> bool:
        return str(chat_id) in self._frozen

    def frozen_chats(self) -> dict[str, FrozenChat]:
        return dict(self._frozen)

    def pending_catchups(self) -> dict[str, FrozenChat]:
        """需要补台的群：期间确实有新消息。"""
        return {cid: f for cid, f in self._frozen.items() if f.messages > 0}

    def clear_catchup(self, chat_id: Any) -> None:
        self._frozen.pop(str(chat_id), None)

    def clear_all_catchups(self) -> None:
        self._frozen.clear()

    async def dispatch_catchups(self) -> list[str]:
        """对每个冻结期有新消息的群执行补台，返回已处理的 chat_id 列表。"""
        pending = self.pending_catchups()
        self.clear_all_catchups()
        if not pending or self._catchup_handler is None:
            return []
        done: list[str] = []
        for cid in pending:
            try:
                result = self._catchup_handler(cid)
                if hasattr(result, "__await__"):
                    await result
                done.append(cid)
            except Exception as exc:
                logger.error(f"[Modes] {cid} 补台失败: {exc}")
        return done

    # ------------------------------------------------------------ 内部事件
    def deliver_inner_event(self, chat_id: Any, event: dict) -> bool:
        """把小女仆汇报 / 定时注入投给运行中的模式主循环。"""
        state = self.active_state(chat_id)
        if state is None or state.instance is None:
            return False
        try:
            return bool(state.instance.on_inner_event(dict(event or {})))
        except Exception as exc:
            logger.error(f"[Modes] 内部事件投递失败 {chat_id}: {exc}")
            return False

    def deliver_input(self, chat_id: Any, message: dict) -> None:
        """把该群的非聊天模式期间入站消息告诉主循环（默认由循环忽略）。"""
        state = self.active_state(chat_id)
        if state is None or state.instance is None:
            return
        try:
            state.instance.on_input(dict(message or {}))
        except Exception as exc:
            logger.debug(f"[Modes] on_input 异常 {chat_id}: {exc}")


IGNORED_INBOUND_SOURCES = ("yuki.reply_watch", "yuki.timer", "yuki.catchup")


def _counts_as_missed(message: dict) -> bool:
    """冻结期间真正需要补台的消息：真人发言，不包含计时器/订阅/补台自身。"""
    if not isinstance(message, dict):
        return False
    if message.get("is_catchup") or message.get("is_reply_watch_event") or message.get("is_timer_event"):
        return False
    if message.get("is_maid_report"):
        return False
    source = str(message.get("source") or "")
    if source in IGNORED_INBOUND_SOURCES:
        return False
    return not bool(message.get("is_bot"))


router = ModeRouter()
