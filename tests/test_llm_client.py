# tests/test_llm_client.py
"""utils/llm_client.py 纯函数单元测试（不联网）。"""
from utils.llm_client import (
    _sanitize_payload,
    _normalize_url,
    _get_fallback_message,
    close_global_session,
)
from config import cfg


# ==================== 单元测试（纯函数，无需 LLM） ====================

def test_normalize_url():
    """测试 URL 规范化"""
    print("\n[测试 1] URL 规范化")

    assert _normalize_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"
    assert _normalize_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    assert _normalize_url("https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com/v1"
    assert _normalize_url("") == ""
    assert _normalize_url(None) == ""

    print("  [PASS] URL 规范化正确")


def test_sanitize_payload_no_thinking_injection():
    """测试 _sanitize_payload 不再自动注入 reasoning_effort"""
    print("\n[测试 2] 思考参数不再自动注入")

    payload = {"model": "o1-preview", "messages": []}
    result = _sanitize_payload("o1-preview", payload)
    assert "reasoning_effort" not in result

    payload2 = {"model": "deepseek-chat", "messages": []}
    assert "reasoning_effort" not in _sanitize_payload("deepseek-chat", payload2)

    print("  [PASS] 思考参数由配置/调用方决定，_sanitize_payload 不注入")


def test_sanitize_payload_vl_model():
    """测试视觉模型过滤 response_format"""
    print("\n[测试 3] 视觉模型 response_format 过滤")

    payload = {
        "model": "qwen-vl-plus",
        "messages": [],
        "response_format": {"type": "json_object"}
    }
    result = _sanitize_payload("qwen-vl-plus", payload)
    assert "response_format" not in result

    print("  [PASS] 视觉模型正确过滤 response_format")


def test_sanitize_payload_normal_model():
    """测试普通模型保留 response_format"""
    print("\n[测试 4] 普通模型保留 response_format")

    payload = {
        "model": "deepseek-chat",
        "messages": [],
        "response_format": {"type": "json_object"}
    }
    result = _sanitize_payload("deepseek-chat", payload)
    assert "response_format" in result
    assert result["response_format"] == {"type": "json_object"}

    print("  [PASS] 普通模型正确保留 response_format")


def test_sanitize_payload_gemini_penalties():
    """Gemini 兼容层需去掉 frequency/presence_penalty，否则会 400。"""
    print("\n[测试 4b] Gemini 不兼容采样参数过滤")

    payload = {
        "model": "gemini-3.1-flash-lite",
        "messages": [],
        "temperature": 1.1,
        "top_p": 0.9,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.4,
        "max_tokens": 520,
    }
    result = _sanitize_payload(
        "gemini-3.1-flash-lite",
        payload,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    assert "frequency_penalty" not in result
    assert "presence_penalty" not in result
    assert result["temperature"] == 1.1
    assert result["top_p"] == 0.9
    assert result["max_tokens"] == 520

    deepseek_payload = {
        "model": "deepseek-v4-flash",
        "frequency_penalty": 0.5,
        "presence_penalty": 0.4,
    }
    deepseek_result = _sanitize_payload("deepseek-v4-flash", deepseek_payload)
    assert deepseek_result["frequency_penalty"] == 0.5
    assert deepseek_result["presence_penalty"] == 0.4

    print("  [PASS] Gemini 过滤 penalty，DeepSeek 保留 penalty")


def test_get_fallback_message():
    """测试降级提示消息格式：按失败原因区分文案"""
    print("\n[测试 5] 降级提示消息格式")

    network_msg = _get_fallback_message("network")
    assert isinstance(network_msg, str)
    assert "好像有点不舒服" in network_msg
    assert "暂时连接不上网络" in network_msg
    assert cfg.MASTER_NAME in network_msg

    empty_msg = _get_fallback_message("empty")
    assert "输出了空字符" in empty_msg

    # 未知原因回退到网络文案
    assert "暂时连接不上网络" in _get_fallback_message("unknown")

    print(f"  [PASS] 网络降级: {network_msg}")
    print(f"  [PASS] 空回复降级: {empty_msg}")


def test_config_urls():
    """测试配置中的 URL 不为空"""
    print("\n[测试 6] 配置 URL 检查")

    assert cfg.LLM_BASE_URL, "LLM_BASE_URL 不能为空"
    assert cfg.BACKUP_BASE_URL, "BACKUP_BASE_URL 不能为空"
    assert cfg.IMAGE_PROCESS_API_URL, "IMAGE_PROCESS_API_URL 不能为空"

    print(f"  [PASS] LLM_BASE_URL: {cfg.LLM_BASE_URL}")
    print(f"  [PASS] BACKUP_BASE_URL: {cfg.BACKUP_BASE_URL}")
    print(f"  [PASS] IMAGE_PROCESS_API_URL: {cfg.IMAGE_PROCESS_API_URL}")


async def test_close_global_session():
    """测试全局 Session 关闭"""
    print("\n[测试 9] close_global_session 测试")

    from utils.llm_client import _get_global_session

    # 先获取一个 session
    session = await _get_global_session()
    assert session is not None
    assert not session.closed
    print("  [PASS] 全局 Session 已创建")

    # 关闭 session
    await close_global_session()

    from utils.llm_client import _global_session as session_after
    assert session_after is None
    print("  [PASS] 全局 Session 已关闭")
