# utils/llm_client.py
# 简化版 LLM 客户端 —— 直接通过配置文件管理 API 参数
"""
替代原 providers 模块，内联所有 provider 逻辑。
- 平台 URL 解析
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

# 平台名称 -> 默认 API 基地址
_PLATFORM_URLS: Dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ytea": "https://api.ytea.top/v1",
    "openai": "https://api.openai.com/v1",
}

# 可用平台列表（供 WebUI 等外部模块使用）
AVAILABLE_PLATFORMS = sorted(set(list(_PLATFORM_URLS.keys()) + ["custom"]))

# 全局 aiohttp Session（TCP 连接复用）
_global_session: Optional[aiohttp.ClientSession] = None

# 主备故障转移状态
_fallback_state: Dict[str, Any] = {
    "is_degraded": False,
    "last_fail_time": 0,
    "recovery_seconds": 120.0,
}


def _resolve_base_url(platform: str, override_url: str = "") -> str:
    """根据平台名称解析 API 基地址。custom 平台使用 override_url。"""
    p = (platform or "").lower().strip()
    if p == "custom":
        return (override_url or "").rstrip("/")
    url = _PLATFORM_URLS.get(p, "")
    return url.rstrip("/") if url else ""


def _sanitize_payload(model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """平台参数适配：清理/转换不兼容参数。"""
    if cfg.DISABLE_THINKING and "reasoning_effort" not in payload:
        payload["reasoning_effort"] = "low"
    # DashScope 视觉模型不支持 response_format
    if model and "vl" in model.lower() and "response_format" in payload:
        del payload["response_format"]
    return payload


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

    # 处理 base_url 末尾可能带的 /chat/completions
    url = (base_url or "").rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    endpoint = f"{url}/chat/completions"

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
    自动使用配置中的首选/备选平台和密钥。

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
            base_url = _resolve_base_url(cfg.LLM_PLATFORM, cfg.LLM_BASE_URL)
            return await chat_completion(
                base_url=base_url,
                api_key=cfg.LLM_API_KEY,
                messages=messages,
                model=model or cfg.LLM_MODEL,
                timeout=60.0,
                **kwargs,
            )
        except Exception as e:
            logger.warning(
                f"[LLM] 主线路 ({cfg.LLM_PLATFORM}) 失效: {e}，"
                f"触发熔断并切换备用"
            )
            state["is_degraded"] = True
            state["last_fail_time"] = time.time()

    # 策略 2：备用线路
    try:
        backup_key = cfg.BACKUP_API_KEY
        if not backup_key and cfg.BACKUP_PLATFORM == cfg.LLM_PLATFORM:
            backup_key = cfg.LLM_API_KEY
        base_url = _resolve_base_url(cfg.BACKUP_PLATFORM, cfg.BACKUP_BASE_URL)
        return await chat_completion(
            base_url=base_url,
            api_key=backup_key,
            messages=messages,
            model=model or cfg.BACKUP_MODEL,
            timeout=60.0,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"[LLM] 备用线路 ({cfg.BACKUP_PLATFORM}) 也失效: {e}")
        return _get_fallback_message()


async def vision_chat(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """
    视觉模型对话接口。
    使用配置中的视觉平台和密钥。

    Args:
        messages: OpenAI 格式的消息列表
        model: 指定模型名，为 None 时使用配置中的视觉模型
        **kwargs: 额外参数

    Returns:
        模型生成的文本
    """
    base_url = _resolve_base_url(cfg.VISION_PLATFORM, cfg.IMAGE_PROCESS_API_URL)
    return await chat_completion(
        base_url=base_url,
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
