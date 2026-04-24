from typing import List, Dict, Any, Optional

import aiohttp

from providers.base import BaseProvider
from utils.logger import get_logger

logger = get_logger("provider.openai")


class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI 兼容格式的 API Provider。
    支持标准 /chat/completions 端点，可处理文本和视觉消息。
    全局共享 aiohttp ClientSession 以复用 TCP 连接。
    """

    _global_session: Optional[aiohttp.ClientSession] = None

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self._name = name
        base_url = (base_url or "").rstrip("/")
        # 兼容配置中写的是完整端点路径的情况
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        self.base_url = base_url
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=10)

    @property
    def name(self) -> str:
        return self._name

    @classmethod
    async def get_global_session(cls) -> aiohttp.ClientSession:
        """获取全局共享的 aiohttp Session，用于 TCP 连接复用。"""
        if cls._global_session is None or cls._global_session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,
                use_dns_cache=True,
                ttl_dns_cache=300,
            )
            base_timeout = aiohttp.ClientTimeout(total=60, connect=10)
            cls._global_session = aiohttp.ClientSession(
                connector=connector, timeout=base_timeout
            )
        return cls._global_session

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> str:
        session = await self.get_global_session()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            **kwargs,
        }
        payload = self.sanitize_payload(payload)

        endpoint = f"{self.base_url}/chat/completions"

        try:
            async with session.post(
                endpoint, json=payload, headers=headers, timeout=self.timeout
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    err_info = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {err_info}")
        except Exception as e:
            logger.error(f"[{self.name}] API 调用失败: {e}")
            raise

    def _apply_disable_thinking(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认减少模型的 thinking/reasoning 输出。
        对 OpenAI o1/o3 系列生效（reasoning_effort: low）。
        其他平台若忽略未知参数则无害；若报错可在 config 关闭 disable_thinking。
        """
        if "reasoning_effort" not in payload:
            payload["reasoning_effort"] = "low"
        return payload

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        平台参数适配钩子。
        子类可覆盖此方法以针对特定平台过滤/转换不兼容参数。
        """
        from config import cfg
        if cfg.DISABLE_THINKING:
            payload = self._apply_disable_thinking(payload)
        return payload

    async def close(self) -> None:
        """不直接关闭全局 Session，由 close_global_session 统一管理。"""
        pass

    @classmethod
    async def close_global_session(cls) -> None:
        """关闭全局 Session，应在程序退出时调用。"""
        if cls._global_session and not cls._global_session.closed:
            await cls._global_session.close()
            cls._global_session = None
            logger.info("[OpenAICompatibleProvider] 全局 Session 已关闭")
