# core/brain.py
import datetime
import math
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor

from core.prompts import get_yuki_setting_private, get_yuki_setting_group
from config import cfg
import asyncio
from utils.logger import get_logger

logger = get_logger("brain")

class YukiState:
    def __init__(self):
        self.lock = asyncio.Lock()  # 进程锁，保护数值计算
        self.energy = {}  # {chat_id: current_energy}
        self.last_update = {}
        self.message_buffer = defaultdict(list)
        self.buffer_tasks = {}    # chat_id: task
        self.last_message_time = {} # chat_id: timestamp
        self.writing_diary = set()  # chat_id
        self.desire_to_start_topic = {} # chat_id
        self.ice_break_fail_count = {}  # {chat_id: count} 新增：破冰无人理睬计数
        # --- 新增：记录刚才发了什么表情包，用于正反馈捕捉 ---
        self.last_sent_meme = {}  # {chat_id: doc_id}
        # 在 __init__ 里添加
        self.maid_task_queue = asyncio.Queue()
        self.maid_current_tasks = {}  # chat_id -> 当前任务描述（让Yuki知道她在干什么）
        self.maid_executor = ThreadPoolExecutor(max_workers=2)  # 并行执行小女仆

        # --- 新增：活跃度感知 ---
        # chat_id: float (0.0 ~ 10.0, 10 代表极度刷屏)

        self.group_activity = {}
        # # 记录每个群上一次“升温”的时间，用于计算自然冷却
        # self.last_activity_update = {}

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
            logger.info(f"[Activity] {cid} 活跃度波动: {current:.2f} -> {self.group_activity[cid]:.2f}")
        return

    async def decay_heartbeat(self, decay_level = cfg.DECAY_LEVEL) -> None:
        """核心：每5分钟执行一次的恒定半衰降温"""
        while True:
            await asyncio.sleep(600)  # 恒定 5 分钟 (300秒)
            async with self.lock:
                if not self.group_activity:
                    continue

                logger.info("[Activity] 执行周期性半衰降温...")
                for cid in list(self.group_activity.keys()):
                    # 半衰计算：每次心跳热度减半
                    self.group_activity[cid] *= decay_level

                    # 清理机制：如果热度已经低到忽略不计，直接从内存移除
                    if self.group_activity[cid] < 0.1:
                        del self.group_activity[cid]
                        logger.info(f"[Activity] {cid} 已完全冷却，从监控中移除")
        return


    @staticmethod
    def get_setting(mode):
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
        # 假设热度 5.0 是我们定义的“非常活跃”基准
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
        logger.info(f"[Brain] 群组:{cid} | 模式:{mode} | 最终欲望:{self.desire_to_start_topic[cid]}%")

    def pop_buffer(self, chat_id):
        """原子化取出并清空缓冲区"""
        msgs = self.message_buffer.get(chat_id, [])
        self.message_buffer[chat_id] = []
        if chat_id in self.buffer_tasks:
            del self.buffer_tasks[chat_id]
        return msgs

    # @staticmethod
    # def get_smooth_time_weight() -> float:
    #     """
    #     使用余弦平滑算法计算生物钟权重
    #     实现从深夜到饭点的无缝平滑过渡
    #     """
    #     # 获取当前时间（带分钟，保证秒级平滑）
    #     now = datetime.datetime.now()
    #     t = now.hour + now.minute / 60.0
    #
    #     # --- 构造双峰生物钟模型 ---
    #     # 基础权重 0.8 (白天平稳期)
    #     base = 0.8
    #
    #     # 模拟深夜 (3:00 为最冷清点)
    #     # 使用 cos( (t-3)*pi/12 )，在3点时为 1，在15点时为 -1
    #     night_factor = math.cos((t - 3) * math.pi / 12)
    #
    #     # 模拟饭点 (12:00 和 19:00 为高峰)
    #     # 使用周期更短的波来模拟两个进食高峰
    #     lunch_peak = math.exp(-((t - 12.5) ** 2 / 4)) * 0.5  # 12:30 附近
    #     dinner_peak = math.exp(-((t - 19.5) ** 2 / 4)) * 0.5  # 19:30 附近
    #
    #     # 融合权重
    #     # 夜间 night_factor 大，我们减去它；饭点峰值我们加上它
    #     weight = base - (night_factor * 0.5) + lunch_peak + dinner_peak
    #
    #     # 最终映射到 [0.2, 1.5] 之间
    #     return max(0.2, min(weight, 1.5))
    @staticmethod
    def get_smooth_time_weight() -> float:
        """
        优化后的生物钟模型：分段基准 + 高斯活跃峰
        解决清晨不醒、下午太累、深夜早退的问题
        """

        now = datetime.datetime.now()
        t = now.hour + now.minute / 60.0

        # 1. 定义基础背景 (Base Line) - 优化后的睡眠模型
        if 0 <= t < 7.8:
            if t < 1.0:
                # 快速入睡：0点到2点迅速下滑
                base = 0.7 - (t / 1.0) * 0.45
            elif 1.0 <= t < 7.0:
                # 深睡稳态：维持极低权重 (0.25)
                base = 0.25
            else:
                # 黎明回升：5点到7.2点从小幅回升，准备迎接晨间高峰
                base = 0.25 + ((t - 7.0) / 0.8) * 0.45
        elif t >= 23.8:
            # 23点后快速收尾入睡
            base = 0.9 - (t - 23.8) * 0.8
        else:
            # 白天标准基准
            base = 0.9

        # 2. 活跃峰值函数 (Gaussian Peaks)
        def peak(time, mu, sig, amp):
            return amp * math.exp(-((time - mu) ** 2) / (2 * sig ** 2))

        # --- 活跃点注入 ---
        # 晨间苏醒: 8点峰值，sigma缩窄到0.4让爆发力更集中
        morning = peak(t, 8.0, 0.6, 0.5)
        # 午后高峰: 12.8点
        lunch = peak(t, 12.8, 0.8, 0.4)
        # 晚间活跃: 20.0点，sigma较宽(1.0)模拟长夜畅谈
        evening = peak(t, 20.0, 1.5, 0.4)

        # 3. 融合结果并限幅
        weight = base + morning + lunch + evening
        return max(0.2, min(weight, 1.5))

    @staticmethod
    def get_smooth_time_weight_test(t) -> float:
        # 1. 定义基础背景 (Base Line) - 优化后的睡眠模型
        if 0 <= t < 7.8:
            if t < 1.0:
                # 快速入睡：0点到2点迅速下滑
                base = 0.7 - (t / 1.0) * 0.45
            elif 1.0 <= t < 7.0:
                # 深睡稳态：维持极低权重 (0.25)
                base = 0.25
            else:
                # 黎明回升：5点到7.2点从小幅回升，准备迎接晨间高峰
                base = 0.25 + ((t - 7.0) / 0.8) * 0.45
        elif t >= 23.8:
            # 23点后快速收尾入睡
            base = 0.9 - (t - 23.8) * 0.8
        else:
            # 白天标准基准
            base = 0.9

        # 2. 活跃峰值函数 (Gaussian Peaks)
        def peak(time, mu, sig, amp):
            return amp * math.exp(-((time - mu) ** 2) / (2 * sig ** 2))

        # --- 活跃点注入 ---
        # 晨间苏醒: 8点峰值，sigma缩窄到0.4让爆发力更集中
        morning = peak(t, 8.0, 0.6, 0.5)
        # 午后高峰: 12.8点
        lunch = peak(t, 12.8, 0.8, 0.4)
        # 晚间活跃: 20.0点，sigma较宽(1.0)模拟长夜畅谈
        evening = peak(t, 20.0, 1.5, 0.4)

        # 3. 融合结果并限幅
        weight = base + morning + lunch + evening
        return max(0.2, min(weight, 1.5))