from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseProvider(ABC):
    """AI 模型 Provider 抽象基类，定义所有 Provider 必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 标识名称"""
        pass

    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None, **kwargs) -> str:
        """
        发起对话补全请求，返回模型生成的文本。

        Args:
            messages: OpenAI 格式的消息列表
            model: 指定模型名，为 None 时使用 Provider 默认模型
            **kwargs: 额外参数（temperature, max_tokens, response_format 等）
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭 Provider，释放资源"""
        pass
