from typing import Dict, Any

from providers.openai_compatible import OpenAICompatibleProvider
from utils.logger import get_logger

logger = get_logger("provider.dashscope")


class DashScopeProvider(OpenAICompatibleProvider):
    """
    阿里云 DashScope 兼容模式 Provider。
    在 OpenAI 兼容格式基础上做平台差异适配：
    - 自动兼容 /compatible-mode/v1 路径
    - 对不支持或行为有差异的参数进行过滤/修正
    """

    PLATFORM_NAME = "dashscope"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # DashScope 兼容模式已支持大部分 OpenAI 标准参数。
    # 若后续发现某模型不支持特定字段，可在此扩展过滤逻辑。
    _KNOWN_UNSUPPORTED_FOR_VL = {"response_format"}

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        model = payload.get("model", "")
        is_vl_model = "vl" in str(model).lower()

        if is_vl_model:
            # 视觉模型在部分场景下对 response_format 支持不稳定，过滤掉
            for key in self._KNOWN_UNSUPPORTED_FOR_VL:
                if key in payload:
                    logger.debug(f"[DashScopeProvider/{self.name}] VL模型过滤参数: {key}")
                    del payload[key]

        logger.debug(f"[DashScopeProvider/{self.name}] 请求参数: {list(payload.keys())}")
        return payload
