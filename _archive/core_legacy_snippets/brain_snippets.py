# 原位于 core/brain.py 的未挂载/历史遗留代码片段
import datetime
import math
from concurrent.futures.thread import ThreadPoolExecutor


# 1. UserMapping.get_all（原位于 core/brain.py 第 77-80 行，仅供已归档的 resolve_user_tool 调试使用）
def user_mapping_get_all(self, chat_id: str) -> dict:
    """获取指定群聊的所有映射（用于调试）。"""
    cid = str(chat_id)
    return {name: info["user_id"] for name, info in self._map.get(cid, {}).items()}


# 2. YukiState.__init__ 中的线程池属性（原位于 core/brain.py 第 101 行，从未被调用）
def init_maid_executor(self):
    self.maid_executor = ThreadPoolExecutor(max_workers=2)  # 并行执行小女仆


# 3. 初代双峰余弦平滑生物钟模型（原注释保留于 core/brain.py 第 223-251 行）
def get_smooth_time_weight_cosine_v1() -> float:
    """
    使用余弦平滑算法计算生物钟权重
    实现从深夜到饭点的无缝平滑过渡
    """
    now = datetime.datetime.now()
    t = now.hour + now.minute / 60.0

    # --- 构造双峰生物钟模型 ---
    # 基础权重 0.8 (白天平稳期)
    base = 0.8

    # 模拟深夜 (3:00 为最冷清点)
    # 使用 cos( (t-3)*pi/12 )，在3点时为 1，在15点时为 -1
    night_factor = math.cos((t - 3) * math.pi / 12)

    # 模拟饭点 (12:00 和 19:00 为高峰)
    # 使用周期更短的波来模拟两个进食高峰
    lunch_peak = math.exp(-((t - 12.5) ** 2 / 4)) * 0.5  # 12:30 附近
    dinner_peak = math.exp(-((t - 19.5) ** 2 / 4)) * 0.5  # 19:30 附近

    # 融合权重
    # 夜间 night_factor 大，我们减去它；饭点峰值我们加上它
    weight = base - (night_factor * 0.5) + lunch_peak + dinner_peak

    # 最终映射到 [0.2, 1.5] 之间
    return max(0.2, min(weight, 1.5))


# 4. 生物钟测试辅助静态方法（原位于 core/brain.py 第 289-291 行，未被任何测试或业务代码调用）
def get_smooth_time_weight_test(self_cls, t) -> float:
    return self_cls._calculate_smooth_time_weight(t)
