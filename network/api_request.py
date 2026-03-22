import datetime
import time
from openai import AsyncOpenAI  # 必须换成这个
import asyncio
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL


class ApiCall:
    def __init__(self, api_key, base_url):
        self.fail_count = 0
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.last_fail_time = 0
        self.is_degraded = False

    def check_auto_recovery(self):
        """检查并尝试恢复熔断状态"""
        if self.is_degraded and (time.time() - self.last_fail_time > 600):
            self.is_degraded = False
            self.fail_count = 0
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [System] 尝试恢复 TEATOP 主线路...")

    async def robust_api_call(self, messages, model="deepseek-chat", max_retries=3, **kwargs):
        """全异步化的稳健 API 调用 - 已修复逻辑污染问题"""
        self.check_auto_recovery()
        last_exception = None

        for attempt in range(max_retries):
            # 1. 确定当前尝试使用的客户端和模型（不修改 self.model 变量）
            current_client = self.client
            current_model = model

            # 如果处于熔断状态，或者这不是第一次尝试（说明主线路可能抖动）
            if self.is_degraded or attempt > 0:
                current_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
                current_model = "deepseek-chat"

                # 仅在第一次从主线路切换到备用线路时打印提示
                if not self.is_degraded and attempt > 0:
                    self.is_degraded = True
                    self.last_fail_time = time.time()
                    print(f"[Critical] 主线路异常，本次请求切换至官方线路 (尝试 {attempt + 1})")

            try:
                # 2. 使用确定的参数进行调用
                response = await current_client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    **kwargs
                )

                # 请求成功，如果是降级状态下的成功，说明线路可能回暖（可选：此处不重置 is_degraded，交给 check_auto_recovery）
                self.fail_count = 0
                return response.choices[0].message.content

            except Exception as e:
                last_exception = e
                print(f"[API Error] 第 {attempt + 1} 次尝试失败 ({current_model}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

        raise last_exception