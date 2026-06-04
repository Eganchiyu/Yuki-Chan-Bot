# utils/llm_client.py
# 简化版 LLM 客户端 —— 直接通过配置文件管理 API 参数
"""
替代原 providers 模块，内联所有 provider 逻辑。
- 主备故障转移
- 全局 aiohttp Session 复用
- 平台参数适配（sanitize_payload）
"""
import time
from typing import List, Dict, Any, Optional

import aiohttp

from config import cfg
from utils.logger import get_logger

logger = get_logger("llm_client")

# 全局 aiohttp Session（TCP 连接复用）
_global_session: Optional[aiohttp.ClientSession] = None

# 主备故障转移状态
_fallback_state: Dict[str, Any] = {
    "is_degraded": False,
    "last_fail_time": 0,
    "recovery_seconds": 120.0,
}


def _sanitize_payload(model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """平台参数适配：清理/转换不兼容参数。"""
    # 仅对 OpenAI 推理模型（o1/o3）添加 reasoning_effort
    if cfg.DISABLE_THINKING and "reasoning_effort" not in payload:
        model_lower = (model or "").lower()
        if model_lower.startswith("o1") or model_lower.startswith("o3"):
            payload["reasoning_effort"] = "low"
    # DashScope 视觉模型不支持 response_format
    if model and "vl" in model.lower() and "response_format" in payload:
        del payload["response_format"]
    return payload


def _normalize_url(url: str) -> str:
    """规范化 URL：移除末尾斜杠和可能的 /chat/completions 后缀。"""
    url = (url or "").rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


async def _get_global_session() -> aiohttp.ClientSession:
    """获取全局共享的 aiohttp Session，复用 TCP 连接。"""
    global _global_session
    if _global_session is None or _global_session.closed:
        connector = aiohttp.TCPConnector(
            limit=10,
            use_dns_cache=True,
            ttl_dns_cache=300,
        )
        _global_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=60, connect=10),
        )
    return _global_session


async def chat_completion(
    base_url: str,
    api_key: str,
    messages: List[Dict[str, Any]],
    model: str,
    timeout: float = 60.0,
    **kwargs,
) -> str:
    """
    发送 OpenAI 兼容格式的对话补全请求。

    Args:
        base_url: API 基地址（不含 /chat/completions）
        api_key: API 密钥
        messages: OpenAI 格式的消息列表
        model: 模型名称
        timeout: 请求超时时间（秒）
        **kwargs: 额外参数（temperature, max_tokens, response_format 等）

    Returns:
        模型生成的文本
    """
    session = await _get_global_session()

    endpoint = f"{_normalize_url(base_url)}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, **kwargs}
    payload = _sanitize_payload(model, payload)

    client_timeout = aiohttp.ClientTimeout(total=timeout, connect=10)
    async with session.post(
        endpoint, json=payload, headers=headers, timeout=client_timeout
    ) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            err_info = await resp.text()
            raise Exception(f"HTTP {resp.status}: {err_info}")


def _get_fallback_message() -> str:
    """获取故障转移降级提示消息。"""
    return (
        f"（{cfg.ROBOT_NAME.title()} 好像有点不舒服，"
        f"暂时连接不上大脑...{cfg.MASTER_NAME}等会再找我好吗？）"
    )


async def llm_chat(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """
    默认 LLM 对话接口（含主备故障转移）。
    自动使用配置中的首选/备选 API 参数。

    Args:
        messages: OpenAI 格式的消息列表
        model: 指定模型名，为 None 时使用配置中的默认模型
        **kwargs: 额外参数（temperature, max_tokens, response_format 等）

    Returns:
        模型生成的文本；全部失败时返回降级提示消息
    """
    state = _fallback_state

    # 自动恢复检查：超过 recovery_seconds 后尝试恢复主线路
    if state["is_degraded"] and (
        time.time() - state["last_fail_time"] > state["recovery_seconds"]
    ):
        state["is_degraded"] = False
        logger.info("[LLM] 尝试恢复主线路")

    # 策略 1：正常状态下优先尝试主线路
    if not state["is_degraded"]:
        try:
            return await chat_completion(
                base_url=cfg.LLM_BASE_URL,
                api_key=cfg.LLM_API_KEY,
                messages=messages,
                model=model or cfg.LLM_MODEL,
                timeout=60.0,
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"[LLM] 主线路失效: {e}，触发熔断并切换备用")
            state["is_degraded"] = True
            state["last_fail_time"] = time.time()

    # 策略 2：备用线路
    try:
        backup_key = cfg.BACKUP_API_KEY or cfg.LLM_API_KEY
        return await chat_completion(
            base_url=cfg.BACKUP_BASE_URL,
            api_key=backup_key,
            messages=messages,
            model=model or cfg.BACKUP_MODEL,
            timeout=60.0,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"[LLM] 备用线路也失效: {e}")
        return _get_fallback_message()


async def vision_chat(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """
    视觉模型对话接口。
    使用配置中的视觉 API 参数。

    Args:
        messages: OpenAI 格式的消息列表
        model: 指定模型名，为 None 时使用配置中的视觉模型
        **kwargs: 额外参数

    Returns:
        模型生成的文本
    """
    return await chat_completion(
        base_url=cfg.IMAGE_PROCESS_API_URL,
        api_key=cfg.IMAGE_PROCESS_API_KEY,
        messages=messages,
        model=model or cfg.VISION_MODEL,
        timeout=40.0,
        **kwargs,
    )


async def close_global_session() -> None:
    """关闭全局 aiohttp Session，在程序退出时调用。"""
    global _global_session
    if _global_session and not _global_session.closed:
        await _global_session.close()
        _global_session = None
        logger.info("[LLM] 全局 Session 已关闭")
