# core/engine_monitor.py
import asyncio
import random
import time
from typing import Callable

from config import cfg
from utils.logger import get_logger

logger = get_logger("engine")


class EngineMonitorService:
    """负责引擎后台巡检任务。"""

    def __init__(self, yuki, history, diary_service, get_napcat_online: Callable[[], bool], get_process_callback):
        self.yuki = yuki
        self.history = history
        self.diary_service = diary_service
        self.get_napcat_online = get_napcat_online
        self.get_process_callback = get_process_callback

    async def idle_diary_checker(self):
        """后台任务，每30秒检查一次空闲群聊。"""
        while True:
            await asyncio.sleep(30)
            if not self.get_napcat_online():
                continue
            now = time.time()
            logger.debug(f"[Engine] 后台检查中... {now}")
            history_dict = self.history.load()
            for cid, last_msg in list(self.yuki.last_message_time.items()):
                if cid in self.yuki.writing_diary:
                    continue

                idle_seconds = now - last_msg
                if idle_seconds < cfg.DIARY_IDLE_SECONDS:
                    continue

                if cid not in history_dict:
                    continue
                non_system_msgs = [msg for msg in history_dict[cid] if msg["role"] != "system"]
                non_system_count = len(non_system_msgs)
                if non_system_count < cfg.DIARY_MIN_TURNS:
                    continue

                logger.info(f"[Engine] 群 {cid} 空闲 {idle_seconds:.0f}s，轮数 {non_system_count}，触发日记")
                self.yuki.writing_diary.add(cid)
                try:
                    await self.diary_service.summarize_idle_session(cid, history_dict[cid])
                finally:
                    self.yuki.writing_diary.discard(cid)

    async def ice_break_monitor(self):
        """后台任务，检查冷场群聊并触发破冰流程。"""
        while True:
            await asyncio.sleep(random.randint(600, 1800))
            if not self.get_napcat_online():
                continue
            target_list = [str(gid) for gid in cfg.TARGET_GROUPS]
            logger.info(f"[Engine] 已加载 {len(target_list)} 个目标群组")
            pending_ice_break = []

            async with self.yuki.lock:
                for cid in target_list:
                    self.yuki.update_energy(chat_id=cid)
                    self.yuki.update_desire_to_reply(cid)
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    logger.info(f"[Engine] 群 {cid} 活跃度={activity:.2f} 欲望={desire:.1f}%")

                    fail_count = self.yuki.ice_break_fail_count.get(cid, 0)
                    logger.info(f"[Engine] {cid} 破冰失败次数: {fail_count}")

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
