import datetime
import time
import asyncio
import aiohttp
import json
from config import BACKUP_API_KEY, DEEPSEEK_BASE_URL, BACKUP_MODEL
from utils.logger import get_logger

logger = get_logger("api_request")


class ApiCall:
    # 类级别变量，确保整个进程生命周期内只存在一个 Session
    # 这样可以复用 TCP 连接（Keep-Alive），达到测试脚本中 0.1s 的响应速度
    _session = None

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        # 统一处理 URL：确保没有末尾斜杠
        self.base_url = base_url.rstrip('/')
        self.is_degraded = False
        self.last_fail_time = 0

    @classmethod
    async def get_session(cls):
        """获取异步 Session。这是非阻塞的关键。"""
        if cls._session is None or cls._session.closed:
            # 限制连接池大小，防止瞬间请求过多导致网络抖动
            connector = aiohttp.TCPConnector(
                limit=10,
                use_dns_cache=True,
                ttl_dns_cache=300
            )
            # 设置全局超时参考
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            cls._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return cls._session

    def check_auto_recovery(self):
        """熔断自动恢复逻辑"""
        # 如果降级超过 120 秒，尝试给主线路一个机会
        if self.is_degraded and (time.time() - self.last_fail_time > 120):
            self.is_degraded = False
            logger.info("[System] 尝试恢复 TeaTop 主线路...")

    async def _raw_post(self, url, key, model, messages, timeout, **kwargs):
        """底层 HTTP 请求，完全模拟你测试脚本的 fetch_test"""
        session = await self.get_session()
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            **kwargs
        }

        # 兼容性处理：有些 base_url 包含 /v1，有些不包含
        endpoint = f"{url}/chat/completions"

        try:
            # 异步非阻塞调用
            async with session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=timeout
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return True, data["choices"][0]["message"]["content"]
                else:
                    err_info = await resp.text()
                    return False, f"HTTP {resp.status}: {err_info}"
        except Exception as e:
            return False, str(e)

    async def robust_api_call(self, messages, model="deepseek-chat", **kwargs):
        """
        全异步稳健调用逻辑：
        1. 优先尝试主线 (TeaTop) -> 2. 失败立即切备用 (DeepSeek官方)
        """
        self.check_auto_recovery()

        # 策略 1: 正常状态下尝试主线
        if not self.is_degraded:
            # 给主线 15 秒窗口，超过不回就认为不可用
            success, result = await self._raw_post(
                self.base_url, self.api_key, model, messages, 15, **kwargs
            )

            if success:
                return result

            # 主线一旦出任何错，记录降级并立刻转向备用
            logger.warning(f"[API] 主线路失效: {result}。触发熔断，切换官方线路。")
            self.is_degraded = True
            self.last_fail_time = time.time()

        # 策略 2: 备用线路 (官方)
        # 官方线路极稳，给 40 秒长超时确保能拿到回复
        # 修正 URL 拼接：官方 Base 一般是 https://api.deepseek.com/v1
        official_url = DEEPSEEK_BASE_URL.rstrip('/')

        success, result = await self._raw_post(
            official_url, BACKUP_API_KEY, BACKUP_MODEL, messages, 40, **kwargs
        )

        if success:
            return result
        else:
            # 官方也报错，返回兜底话术
            logger.error(f"[Critical] 全线不可用: {result}")
            return "（Yuki 好像有点不舒服，暂时连接不上大脑...哥哥等会再找我好吗？）"

    @classmethod
    async def close(cls):
        """程序关闭时销毁 Session"""
        if cls._session:
            await cls._session.close()