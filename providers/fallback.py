import time
from typing import List, Dict, Any, Optional

from providers.base import BaseProvider
from utils.logger import get_logger

logger = get_logger("provider.fallback")


class FallbackProvider(BaseProvider):
    """
    主备故障转移 Provider。
    封装两个子 Provider，主线路失败时自动熔断并切换备用线路，
    支持按配置的时间间隔自动恢复主线路。
    """

    def __init__(
        self,
        name: str,
        primary: BaseProvider,
        backup: BaseProvider,
        recovery_seconds: float = 120.0,
        fallback_message: Optional[str] = None,
    ):
        self._name = name
        self.primary = primary
        self.backup = backup
        self.recovery_seconds = recovery_seconds
        self.fallback_message = fallback_message
        self._is_degraded = False
        self._last_fail_time = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_degraded(self) -> bool:
        """当前是否处于降级状态（主线路不可用）。"""
        return self._is_degraded

    def check_auto_recovery(self) -> None:
        """熔断自动恢复：超过 recovery_seconds 后尝试恢复主线路。"""
        if self._is_degraded and (
            time.time() - self._last_fail_time > self.recovery_seconds
        ):
            self._is_degraded = False
            logger.info(f"[{self.name}] 尝试恢复主线路 {self.primary.name}")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> str:
        self.check_auto_recovery()

        # 策略 1：正常状态下优先尝试主线路
        if not self._is_degraded:
            try:
                return await self.primary.chat(messages, model=model, **kwargs)
            except Exception as e:
                logger.warning(
                    f"[{self.name}] 主线路 {self.primary.name} 失效: {e}，"
                    f"触发熔断并切换备用"
                )
                self._is_degraded = True
                self._last_fail_time = time.time()

        # 策略 2：备用线路
        try:
            return await self.backup.chat(messages, model=model, **kwargs)
        except Exception as e:
            logger.error(f"[{self.name}] 备用线路 {self.backup.name} 也失效: {e}")
            if self.fallback_message:
                return self.fallback_message
            raise

    async def close(self) -> None:
        await self.primary.close()
        await self.backup.close()
