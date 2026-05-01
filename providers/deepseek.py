from typing import Dict, Any

from providers.openai_compatible import OpenAICompatibleProvider
from utils.logger import get_logger

logger = get_logger("provider.deepseek")


class DeepSeekProvider(OpenAICompatibleProvider):
    """
    DeepSeek 平台 Provider。
    在 OpenAI 兼容格式基础上做参数适配：
    - 完整支持 response_format、frequency_penalty 等标准参数
    - 预留 reasoning_content（推理内容）解析扩展点
    """

    PLATFORM_NAME = "deepseek"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        DeepSeek 几乎完整兼容 OpenAI 参数，默认透传。
        如后续发现特定参数差异，可在此扩展处理。
        """
        logger.debug(f"[DeepSeekProvider/{self.name}] 请求参数: {list(payload.keys())}")
        return payload
