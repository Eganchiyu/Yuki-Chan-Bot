# core/engine_monitor.py
import asyncio
import random
import time
from typing import Callable

from config import cfg
from core.focus import focus_manager
from core.history_filter import dialogue_length
from utils.logger import get_logger

logger = get_logger("engine")


class EngineMonitorService:
    """负责引擎后台巡检任务。"""

    def __init__(self, yuki, history, diary_service, get_napcat_online: Callable[[], bool],
                 get_process_callback, get_autonomous: Callable[[], object] | None = None,
                 get_group_active_state: Callable[[], dict | None] | None = None):
        self.yuki = yuki
        self.history = history
        self.diary_service = diary_service
        self.get_napcat_online = get_napcat_online
        self.get_process_callback = get_process_callback
        self.get_autonomous = get_autonomous or (lambda: None)
        self.get_group_active_state = get_group_active_state or (lambda: None)

    def _is_group_sleeping(self, cid: str) -> bool:
        state = self.get_group_active_state()
        return isinstance(state, dict) and state.get(str(cid)) is False

    def _autonomous_busy(self) -> bool:
        """非聊天模式进行中：冻结期不写日记、不触发破冰。"""
        coordinator = self.get_autonomous()
        if coordinator is None:
            return False
        try:
            return bool(coordinator.is_running())
        except Exception:
            return False

    async def idle_diary_checker(self):
        """后台任务，每30秒检查一次空闲群聊。"""
        while True:
            await asyncio.sleep(30)
            if not self.get_napcat_online():
                continue
            now = time.time()
            logger.debug("[Engine] 后台空闲检查开始")
            if self._autonomous_busy():
                logger.debug("[Engine] 自主轮进行中，跳过日记巡检")
                continue
            # 冷场自动触发自主轮（白名单 + 精力/深夜/冷却/日配额判定都在 coordinator 内）
            coordinator = self.get_autonomous()
            if coordinator is not None:
                try:
                    await coordinator.auto_trigger_check()
                except Exception as exc:
                    logger.warning(f"[Engine] 自主轮自动触发检查失败: {exc}")
            for cid, last_msg in list(self.yuki.last_message_time.items()):
                if cid in self.yuki.writing_diary:
                    continue
                if focus_manager.is_focused(cid):
                    continue

                idle_seconds = now - last_msg
                if idle_seconds < cfg.DIARY_IDLE_SECONDS:
                    continue

                session = (
                    self.history.get_session(cid)
                    if hasattr(self.history, "get_session")
                    else (self.history.load().get(cid) or [])
                )
                if not session:
                    continue
                # 轮数只算聊天，工具调用与工具输出不算（否则连着用几次工具就触发日记）
                dialogue_count = dialogue_length(session)
                if dialogue_count < cfg.DIARY_MIN_TURNS:
                    continue

                logger.info(f"[Engine] 群 {cid} 空闲 {idle_seconds:.0f}s，聊天轮数 {dialogue_count}，触发日记")
                self.yuki.writing_diary.add(cid)
                try:
                    await self.diary_service.summarize_idle_session(cid, session)
                finally:
                    self.yuki.writing_diary.discard(cid)

    async def ice_break_monitor(self):
        """后台任务，检查冷场群聊并触发破冰流程。"""
        while True:
            await asyncio.sleep(random.randint(600, 1800))
            if not self.get_napcat_online():
                continue
            if self._autonomous_busy():
                logger.debug("[Engine] 自主轮进行中，跳过破冰巡检")
                continue
            target_list = [str(gid) for gid in cfg.TARGET_GROUPS]
            logger.debug(f"[Engine] 已加载 {len(target_list)} 个目标群组")
            pending_ice_break = []

            async with self.yuki.lock:
                for cid in target_list:
                    if self._is_group_sleeping(cid):
                        continue
                    self.yuki.update_energy(chat_id=cid)
                    self.yuki.update_desire_to_reply(cid)
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    logger.debug(f"[Engine] 群 {cid} 活跃度={activity:.2f} 欲望={desire:.1f}%")

                    fail_count = self.yuki.ice_break_fail_count.get(cid, 0)
                    logger.debug(f"[Engine] {cid} 破冰失败次数: {fail_count}")

                    if activity < 0.5 and desire > 75 and fail_count < 2:
                        if random.random() < 0.8:
                            pending_ice_break.append(cid)
                    elif fail_count >= 2:
                        logger.info(f"[Engine] {cid} 连续破冰无果，进入自闭模式，等待群友先开口")

            for cid in pending_ice_break:
                logger.info(f"[IceBreak] 群 {cid} 触发冷场唤醒，走主管道")
                process_callback = self.get_process_callback()
                if process_callback is not None:
                    asyncio.create_task(
                        process_callback(
                            cid,
                            "group",
                            debounce_flag=False,
                            force_reply=True,
                            ice_break=True,
                        )
                    )
                else:
                    logger.warning(f"[IceBreak] process_callback 未设置，无法触发破冰")
