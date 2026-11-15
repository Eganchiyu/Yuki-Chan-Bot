# core/modes/pipeline.py
"""模式感知管线：只在 enqueue_message 一处做路由，chat 模式原样透传父类。"""
from __future__ import annotations

import time

from config import cfg
from core.modes.router import (
    CHAT_MODE,
    ROUTE_CHAT,
    ROUTE_FROZEN,
    ROUTE_MODE,
    ModeRouter,
)
from core.session_pipeline import IncomingMessage, SessionPipeline
from utils.logger import get_logger

logger = get_logger("modes.pipeline")


class ModeAwarePipeline(SessionPipeline):
    """SessionPipeline 的子类：入站统一先问路由，非聊天模式只入缓冲。

    约束（docs/autonomous-sandbox-plan.md §3.4）：router 空闲时 `route()` 必然返回
    `ROUTE_CHAT`，此时调用序列与父类完全一致，不额外建任务、不加锁。
    """

    def __init__(self, components: dict, group_active_state: dict, mode_router: ModeRouter | None = None):
        self.mode_router = mode_router or ModeRouter()
        super().__init__(components, group_active_state)
        try:
            self.mode_router.set_catchup_handler(self.handle_catchup)
        except Exception as exc:  # pragma: no cover - 防御
            logger.warning(f"[Modes] 绑定补台处理器失败: {exc}")

    # ------------------------------------------------------------ 入站路由
    async def enqueue_message(self, chat_id, mode, message_obj=None, debounce_flag=True,
                              force_reply=None, ice_break=False):
        router = getattr(self, "mode_router", None)
        if router is None or router.is_idle():
            return await super().enqueue_message(
                chat_id, mode, message_obj=message_obj,
                debounce_flag=debounce_flag, force_reply=force_reply, ice_break=ice_break,
            )

        action, state = router.route(chat_id, mode)
        if action == ROUTE_CHAT:
            return await super().enqueue_message(
                chat_id, mode, message_obj=message_obj,
                debounce_flag=debounce_flag, force_reply=force_reply, ice_break=ice_break,
            )

        cid = str(chat_id)
        incoming = IncomingMessage.from_mapping(message_obj) if message_obj else None
        payload = incoming.to_dict() if incoming else None

        if action == ROUTE_MODE:
            # 内部事件（小女仆汇报）直接投给主循环，不入缓冲、不补台
            if incoming is not None and incoming.is_system_injected:
                if self.mode_router.deliver_inner_event(cid, payload):
                    logger.info(f"[Modes] {cid} 内部事件已被 {state.mode if state else '?'} 模式消费")
                    return None
            elif incoming is None and force_reply:
                # maid_worker 只把汇报写进历史、不传 message_obj，这里从历史里捡回来
                event = self._inner_event_from_history(cid)
                if event is not None and self.mode_router.deliver_inner_event(cid, event):
                    logger.info(f"[Modes] {cid} 小女仆汇报已投递给运行中的模式")
                    return None

            # 真人消息：只入缓冲并登记缺席（退出后统一补台）
            self._buffer_incoming(cid, message_obj)
            if payload is not None:
                self.mode_router.mark_frozen(cid, payload)
                self.mode_router.deliver_input(cid, payload)
            logger.debug(f"[Modes] {cid} 处于 {state.mode if state else '?'} 模式，消息入缓冲")
            return None

        # ROUTE_FROZEN：别的群占着模式，这里一律冻结（唯一体性）：只入缓冲，等退出后补台
        self._buffer_incoming(cid, message_obj)
        if payload is not None:
            self.mode_router.mark_frozen(cid, payload)
        logger.debug(f"[Modes] {cid} 因全局 {state.mode if state else '?'} 占用而冻结")
        return None

    # ------------------------------------------------------------ 补台
    async def handle_catchup(self, chat_id) -> None:
        """冻结期结束后，把「你不在的时候群里发生了什么」补回该群。"""
        if not cfg.autonomous.catchup_enabled:
            self.mode_router.clear_catchup(chat_id)
            return
        from modules.autonomous.catchup import build_catchup_event

        cid = str(chat_id)
        event = await build_catchup_event(self, cid)
        if event is None:
            self.mode_router.clear_catchup(cid)
            return
        await super().enqueue_message(
            cid, "group", message_obj=event, debounce_flag=False, force_reply=True,
        )

    def _inner_event_from_history(self, chat_id: str) -> dict | None:
        """小女仆汇报只写进了历史（不带 message_obj），这里把它读出来当内部事件。"""
        try:
            session = self.history_manager.get_session(chat_id)
        except Exception:
            return None
        if not session:
            return None
        last = session[-1]
        if not isinstance(last, dict) or not last.get("is_maid_report"):
            return None
        return {
            "name": "小女仆",
            "content": last.get("content", ""),
            "raw_text": "",
            "source": "yuki.maid_report",
            "is_maid_report": True,
            "tags": ["maid_report"],
        }
