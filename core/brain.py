# core/brain.py
import asyncio
import datetime
import math
import time
from collections import defaultdict

from config import cfg
from core.maid.maid_runtime import MaidRuntime
from core.prompts import (
    get_yuki_setting_group,
    get_yuki_setting_master_private,
    get_yuki_setting_private,
)
from utils.logger import get_logger

logger = get_logger("brain")


class UserMapping:
    """用户昵称到QQ号的临时映射表，支持多轮管线持久化。"""

    def __init__(self, ttl_rounds=10):
        # {chat_id: {sender_name: {"user_id": int, "ttl": int}}}
        self._map = defaultdict(dict)
        self.ttl_rounds = ttl_rounds

    def update(self, chat_id: str, sender_name: str, user_id: int):
        """更新或新增映射。"""
        if not sender_name or not user_id:
            return
        cid = str(chat_id)
        self._map[cid][sender_name] = {
            "user_id": user_id,
            "ttl": self.ttl_rounds,
        }
        logger.debug(f"[UserMapping] {cid} 更新映射: {sender_name} -> {user_id}")

    def resolve(self, chat_id: str, name: str) -> int | None:
        """根据昵称解析 QQ 号，支持精确匹配和模糊匹配。"""
        cid = str(chat_id)
        user_map = self._map.get(cid, {})
        if not user_map:
            return None

        # 精确匹配
        if name in user_map:
            return user_map[name]["user_id"]

        # 模糊匹配：目标包含在昵称中，或昵称包含在目标中
        for nick, info in user_map.items():
            if name in nick or nick in name:
                return info["user_id"]

        return None

    def tick(self, chat_id: str):
        """管线轮次递减，清理过期映射。"""
        cid = str(chat_id)
        if cid not in self._map:
            return

        expired_keys = []
        for name, info in self._map[cid].items():
            info["ttl"] -= 1
            if info["ttl"] <= 0:
                expired_keys.append(name)

        for key in expired_keys:
            del self._map[cid][key]
            logger.debug(f"[UserMapping] {cid} 过期移除: {key}")

        # 如果该群聊映射为空，清理整个条目
        if not self._map[cid]:
            del self._map[cid]


class YukiState:
    def __init__(self):
        self.lock = asyncio.Lock()  # 进程锁，保护数值计算
        self.energy = {}  # {chat_id: current_energy}
        self.last_update = {}
        self.message_buffer = defaultdict(list)
        self.last_message_time = {} # chat_id: timestamp
        self.writing_diary = set()  # chat_id
        self.desire_to_start_topic = {} # chat_id
        self.ice_break_fail_count = {}  # {chat_id: count} 新增：破冰无人理睬计数
        self.topic_hormone = {}
        # --- 新增：记录刚才发了什么表情包，用于正反馈捕捉 ---
        self.last_sent_meme = {}  # {chat_id: doc_id}
        # 在 __init__ 里添加
        self.maid_task_queue = asyncio.Queue()
        # 小女仆任务运行时登记表：会话内编号、并行执行、叫停都走它（唯一事实源）
        self.maid_runtime = MaidRuntime()
        self.maid_current_tasks = {}  # chat_id -> 当前任务描述（让Yuki知道她在干什么）

        # --- 新增：用户昵称到QQ号的映射 ---
        self.user_mapping = UserMapping(ttl_rounds=10)

        # --- 新增：活跃度感知 ---
        # chat_id: float (0.0 ~ 10.0, 10 代表极度刷屏)

        self.group_activity = {}

        # --- 新增：自主轮回群后的「心情高涨」社交反哺状态（按 chat_id 记账）---
        self.high_spirits_until = {}          # chat_id -> 截止时间戳
        self.high_spirits_remaining_turns = {}  # chat_id -> 剩余主动补发配额
        # 连发护栏：回群后最多连发「1 + high_spirits_turns」条，两条之间要留出空隙，
        # 避免独处结束后一口气刷屏（真主接话会把连发链重置）。
        self.high_spirits_burst_limit = {}    # chat_id -> 本轮连发上限（含回群第一句）
        self.high_spirits_burst_left = {}     # chat_id -> 本轮还能连发几条
        self.high_spirits_last_send_at = {}   # chat_id -> 上一条发出时间

    def mark_high_spirits(self, chat_id, turns=None, minutes=None):
        """自主轮结束回到群聊：拉高回复欲望，并给一小段「最多 2 连发」的分享窗口。"""
        cid = str(chat_id)
        turns = max(
            0,
            int(turns if turns is not None else getattr(cfg.autonomous, "high_spirits_turns", 1) or 1),
        )
        minutes = float(
            minutes if minutes is not None else getattr(cfg.autonomous, "high_spirits_minutes", 25) or 25
        )
        burst_limit = turns + 1  # 回群第一句也算一次连发
        self.high_spirits_until[cid] = time.time() + max(0.0, minutes) * 60
        self.high_spirits_remaining_turns[cid] = turns
        self.high_spirits_burst_limit[cid] = burst_limit
        self.high_spirits_burst_left[cid] = burst_limit
        self.high_spirits_last_send_at[cid] = 0.0
        logger.info(
            f"[Brain] {cid} 进入心情高涨：最多连发 {burst_limit} 条，持续 {minutes:.0f} 分钟"
        )

    def high_spirits_active(self, chat_id) -> bool:
        cid = str(chat_id)
        until = float(self.high_spirits_until.get(cid, 0.0) or 0.0)
        return bool(until) and time.time() < until

    def high_spirits_turns_left(self, chat_id) -> int:
        if not self.high_spirits_active(chat_id):
            return 0
        return max(0, int(self.high_spirits_remaining_turns.get(str(chat_id), 0) or 0))

    def consume_high_spirits_turn(self, chat_id) -> int:
        cid = str(chat_id)
        left = max(0, self.high_spirits_turns_left(cid) - 1)
        self.high_spirits_remaining_turns[cid] = left
        # 配额用完只代表不再额外补发，心情高涨本身仍按 high_spirits_minutes 持续
        return left

    # ------------------------------------------------------------ 连发护栏
    def high_spirits_burst_remaining(self, chat_id) -> int:
        """高涨期内本轮还能连发几条（不在高涨期返回 0）。"""
        if not self.high_spirits_active(chat_id):
            return 0
        return max(0, int(self.high_spirits_burst_left.get(str(chat_id), 0) or 0))

    def note_high_spirits_send(self, chat_id) -> int:
        """回复真正发出后记账：消耗一条连发额度并记录发送时刻。"""
        cid = str(chat_id)
        if not self.high_spirits_active(chat_id):
            return 0
        left = max(0, self.high_spirits_burst_remaining(cid) - 1)
        self.high_spirits_burst_left[cid] = left
        self.high_spirits_last_send_at[cid] = time.time()
        return left

    def reset_high_spirits_burst(self, chat_id) -> None:
        """真人接话：连发链被打断，回群连发额度回满（只在高涨期内生效）。"""
        cid = str(chat_id)
        if not self.high_spirits_active(chat_id):
            return
        limit = int(self.high_spirits_burst_limit.get(cid, 0) or 0)
        if limit:
            self.high_spirits_burst_left[cid] = limit

    def high_spirits_gap_elapsed(self, chat_id, seconds) -> bool:
        """距离上一条发出是否已经够得上「连发空隙」。"""
        last = float(self.high_spirits_last_send_at.get(str(chat_id), 0.0) or 0.0)
        return last <= 0 or (time.time() - last) >= max(0.0, float(seconds))

    async def boost_activity(self, chat_id, sensitivity = cfg.SENSITIVITY) -> None:
        """
        非线性提升活跃度：
        距离上限越近，单条消息提供的增量越小。
        """
        async with self.lock:
            cid = str(chat_id)
            current = self.group_activity.get(cid, 0.0)

            # 计算增量：(上限 - 当前值) * 灵敏度
            # 这样永远不会超过 10.0，且越往后加得越慢
            increment = (10.0 - current) * sensitivity

            self.group_activity[cid] = current + increment
            logger.debug(f"[Activity] {cid} 活跃度波动: {current:.2f} -> {self.group_activity[cid]:.2f}")
        return

    async def decay_heartbeat(self, decay_level = cfg.DECAY_LEVEL) -> None:
        """核心：每10分钟执行一次的恒定半衰降温"""
        while True:
            await asyncio.sleep(600)  # 恒定 10 分钟
            async with self.lock:
                if not self.group_activity:
                    continue

                logger.debug("[Activity] 执行周期性半衰降温...")
                for cid in list(self.group_activity.keys()):
                    # 半衰计算：每次心跳热度减半
                    self.group_activity[cid] *= decay_level

                    # 清理机制：如果热度已经低到忽略不计，直接从内存移除
                    if self.group_activity[cid] < 0.1:
                        del self.group_activity[cid]
                        logger.debug(f"[Activity] {cid} 已完全冷却，从监控中移除")
        return


    @staticmethod
    def get_setting(mode):
        if mode == "master_private":
            return get_yuki_setting_master_private()
        return get_yuki_setting_private() if mode == "private" else get_yuki_setting_group()

    def update_energy(self, chat_id):
        """计算并更新当前精力值"""
        now = datetime.datetime.now()
        # 初始化该群精力
        if chat_id not in self.energy:
            self.energy[chat_id] = cfg.INITIAL_ENERGY
            self.last_update[chat_id] = now
            return self.energy[chat_id]
        duration_mins = (now - self.last_update[chat_id]).total_seconds() / 60
        self.energy[chat_id] = min(cfg.MAX_ENERGY, self.energy[chat_id] + (duration_mins * cfg.RECOVERY_PER_MIN))
        self.last_update[chat_id] = now
        return self.energy[chat_id]

    def consume_energy(self, chat_id):
        """消耗精力值"""

        if chat_id in self.energy:
            self.energy[chat_id] = max(0.0, self.energy[chat_id] - cfg.COST_PER_REPLY)

    def update_desire_to_reply(self, chat_id):
        """
        不再从外部传 activity，而是内部实时从感知池(group_activity)获取
        """
        cid = str(chat_id)

        # 2. 获取该群的实时活跃度，并归一化到 0.0~1.0
        # 假设热度 5.0 是我们定义的"非常活跃"基准
        raw_activity = self.group_activity.get(cid, 0.0)
        recent_activity_level = min(raw_activity / 5.0, 1.0)

        # --- 计算逻辑保持不变 ---
        # 模式 A: 跟风 (0.0~1.0 比例)
        follow_desire = recent_activity_level * 80 * (self.energy[chat_id] / 100)

        # 模式 B: 破冰
        ice_break_desire = (1.0 - recent_activity_level) * 60 * max(0, (self.energy[chat_id] - 60) / 40)

        # 融合平滑时间权重
        total_desire = max(follow_desire, ice_break_desire) * self.get_smooth_time_weight()

        # 3. Sigmoid 非线性归一化
        normalized = 100 / (1 + math.exp(-cfg.SIGMOID_ALPHA * (total_desire - cfg.SIGMOID_CENTRE)))

        # 4. 隔离存储：只更新当前 chat_id 的欲望值
        self.desire_to_start_topic[cid] = round(normalized, 2)

        # [Debug]
        mode = "跟风" if follow_desire > ice_break_desire else "破冰"
        logger.debug(f"[Brain] 群组:{cid} | 模式:{mode} | 最终欲望:{self.desire_to_start_topic[cid]}%")

    def pop_buffer(self, chat_id):
        """原子化取出并清空缓冲区"""
        cid = str(chat_id)
        msgs = self.message_buffer.get(chat_id) or self.message_buffer.get(cid, [])
        self.message_buffer[chat_id] = []
        self.message_buffer[cid] = self.message_buffer[chat_id]
        return msgs

    @staticmethod
    def _calculate_smooth_time_weight(t) -> float:
        """按给定小时计算生物钟权重。"""
        if 0 <= t < 7.8:
            if t < 1.0:
                # 0:00 到 1:00 快速入睡
                base = 0.7 - (t / 1.0) * 0.45
            elif 1.0 <= t < 7.0:
                # 1:00 到 7:00 深睡稳态
                base = 0.25
            else:
                # 7:00 到 7:48 黎明回升
                base = 0.25 + ((t - 7.0) / 0.8) * 0.45
        elif t >= 23.8:
            # 23:48 后快速收尾入睡
            base = 0.9 - (t - 23.8) * 0.8
        else:
            # 白天标准基准
            base = 0.9

        def peak(time, mu, sig, amp):
            return amp * math.exp(-((time - mu) ** 2) / (2 * sig ** 2))

        morning = peak(t, 8.0, 0.6, 0.5)
        lunch = peak(t, 12.8, 0.8, 0.4)
        evening = peak(t, 20.0, 1.5, 0.4)

        weight = base + morning + lunch + evening
        return max(0.2, min(weight, 1.5))

    @staticmethod
    def get_smooth_time_weight() -> float:
        """生物钟模型：分段基准 + 高斯活跃峰。"""
        now = datetime.datetime.now()
        t = now.hour + now.minute / 60.0
        return YukiState._calculate_smooth_time_weight(t)

