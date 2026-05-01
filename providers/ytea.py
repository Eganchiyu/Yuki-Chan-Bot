from typing import Dict, Any

from providers.openai_compatible import OpenAICompatibleProvider
from utils.logger import get_logger

logger = get_logger("provider.ytea")


class YteaProvider(OpenAICompatibleProvider):
    """
    TeaTop (ytea) 平台 Provider。
    基于 OpenAI 兼容格式，针对 TeaTop 代理特性做适配。
    当前 TeaTop 主要代理 DeepSeek 模型，参数支持度与 DeepSeek 基本一致。
    """

    PLATFORM_NAME = "ytea"
    DEFAULT_BASE_URL = "https://api.ytea.top/v1"

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        TeaTop 兼容 OpenAI 标准参数，默认透传。
        如后续发现 TeaTop 特有参数差异，可在此扩展处理。
        """
        logger.debug(f"[YteaProvider/{self.name}] 请求参数: {list(payload.keys())}")
        return payload
