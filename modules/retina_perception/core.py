import asyncio
from utils.logger import get_logger
from modules.retina_perception.prefrontal import local_prefrontal_loop
from modules.retina_perception.attention import dynamic_attention_loop
from config import cfg

logger = get_logger("retina_core")

class RetinaPerceptionSystem:
    def __init__(self):
        self.tasks = []

    async def start(self, engine, history_manager, default_chat_id: str = str(cfg.TARGET_QQ)):
        """
        启动视网膜感知系统的两个核心子循环。
        """
        logger.info("[Retina System] Starting Retina Perception System...")

        # 启动前额叶生产者循环
        # 注意：这里我们让 prefrontal_loop 每次循环读取 dynamic_sleep_interval 的逻辑最好放在内部，
        # 为了演示，我们将直接启动原始循环。理想情况是修改 prefrontal_loop 从 attention 获取间隔。
        # 我们会在稍后对 prefrontal.py 进行微调。

        prefrontal_task = asyncio.create_task(
            local_prefrontal_loop()
        )
        self.tasks.append(prefrontal_task)

        # 启动注意力消费者循环
        attention_task = asyncio.create_task(
            dynamic_attention_loop(
                engine=engine,
                history_manager=history_manager,
                default_chat_id=default_chat_id
            )
        )
        self.tasks.append(attention_task)

        logger.info("[Retina System] System started successfully.")

    async def stop(self):
        """
        停止子循环
        """
        logger.info("[Retina System] Stopping Retina Perception System...")
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info("[Retina System] System stopped.")
