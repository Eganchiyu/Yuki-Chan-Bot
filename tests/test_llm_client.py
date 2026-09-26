# tests/test_llm_client.py
"""
utils/llm_client.py 测试文件
包含单元测试（纯函数）和集成测试（LLM 调用）。

运行方式：
    python tests/test_llm_client.py          # 直接运行
    python -m pytest tests/test_llm_client.py  # pytest 运行
"""
import asyncio
import os
import sys

# Windows 控制台 UTF-8 支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 动态获取项目根目录并加入 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.llm_client import (
    _sanitize_payload,
    _normalize_url,
    _get_fallback_message,
    chat_completion,
    llm_chat,
    vision_chat,
    close_global_session,
    _fallback_state,
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


def test_sanitize_payload_disable_thinking():
    """测试 DISABLE_THINKING 参数注入（仅对 o1/o3 模型）"""
    print("\n[测试 2] DISABLE_THINKING 参数注入")

    original_value = cfg.DISABLE_THINKING

    try:
        # 模拟 DISABLE_THINKING = True
        cfg._raw.setdefault("model", {})["disable_thinking"] = True
        cfg._content_hash = ""  # 强制重新加载

        # 普通模型不添加 reasoning_effort
        payload1 = {"model": "deepseek-chat", "messages": []}
        result1 = _sanitize_payload("deepseek-chat", payload1)
        assert "reasoning_effort" not in result1

        # o1/o3 模型添加 reasoning_effort
        payload2 = {"model": "o1-preview", "messages": []}
        result2 = _sanitize_payload("o1-preview", payload2)
        assert "reasoning_effort" in result2
        assert result2["reasoning_effort"] == "low"

        payload3 = {"model": "o3-mini", "messages": []}
        result3 = _sanitize_payload("o3-mini", payload3)
        assert "reasoning_effort" in result3

        print("  [PASS] DISABLE_THINKING=True 时仅对 o1/o3 模型注入 reasoning_effort")

        payload4 = {"model": "gemini-3.1-flash-lite", "messages": []}
        result4 = _sanitize_payload("gemini-3.1-flash-lite", payload4)
        assert result4.get("reasoning_effort") == "none"
        print("  [PASS] Gemini 在 DISABLE_THINKING=True 时注入 reasoning_effort=none")
    finally:
        # 恢复原始值
        cfg._raw.setdefault("model", {})["disable_thinking"] = original_value
        cfg._content_hash = ""


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


# ==================== 集成测试（需要 LLM） ====================

async def test_chat_completion_integration():
    """集成测试：直接调用 chat_completion"""
    print("\n[测试 7] chat_completion 集成测试（调用 LLM）")

    if not cfg.LLM_API_KEY:
        print("  [SKIP] 未配置 LLM_API_KEY")
        return

    print(f"  URL: {cfg.LLM_BASE_URL}")
    print(f"  模型: {cfg.LLM_MODEL}")

    try:
        result = await chat_completion(
            base_url=cfg.LLM_BASE_URL,
            api_key=cfg.LLM_API_KEY,
            messages=[{"role": "user", "content": "请用一句话介绍你自己，不超过20字。"}],
            model=cfg.LLM_MODEL,
            max_tokens=50,
            temperature=0.7,
        )
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"  [PASS] LLM 回复: {result[:80]}...")
    except Exception as e:
        print(f"  [FAIL] 调用失败: {e}")
        raise


async def test_llm_chat_integration():
    """集成测试：llm_chat 接口（含主备故障转移）"""
    print("\n[测试 8] llm_chat 集成测试（调用 LLM）")

    if not cfg.LLM_API_KEY:
        print("  [SKIP] 未配置 LLM_API_KEY")
        return

    # 重置故障转移状态
    _fallback_state["is_degraded"] = False
    _fallback_state["last_fail_time"] = 0

    print(f"  主线路: {cfg.LLM_BASE_URL} / {cfg.LLM_MODEL}")
    print(f"  备用线路: {cfg.BACKUP_BASE_URL} / {cfg.BACKUP_MODEL}")

    try:
        result = await llm_chat(
            messages=[{"role": "user", "content": "回复'测试成功'四个字即可。"}],
            max_tokens=20,
            temperature=0.1,
        )
        assert isinstance(result, str)
        assert len(result) > 0

        # 检查是否是降级消息
        if "好像有点不舒服" in result:
            print(f"  [WARN] 返回了降级消息（主备线路均失败）")
        else:
            print(f"  [PASS] LLM 回复: {result}")

        # 检查故障转移状态
        print(f"  当前降级状态: {_fallback_state['is_degraded']}")
    except Exception as e:
        print(f"  [FAIL] 调用失败: {e}")
        raise


async def test_close_global_session():
    """测试全局 Session 关闭"""
    print("\n[测试 9] close_global_session 测试")

    from utils.llm_client import _global_session, _get_global_session

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


# ==================== 测试运行器 ====================

def run_unit_tests():
    """运行所有单元测试"""
    print(f"\n{'=' * 50}")
    print(f"{' 单元测试（纯函数） ':=^50}")
    print(f"{'=' * 50}")

    tests = [
        test_normalize_url,
        test_sanitize_payload_disable_thinking,
        test_sanitize_payload_vl_model,
        test_sanitize_payload_normal_model,
        test_get_fallback_message,
        test_config_urls,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] 断言失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] 异常: {e}")
            failed += 1

    return passed, failed


async def run_integration_tests():
    """运行所有集成测试"""
    print(f"\n{'=' * 50}")
    print(f"{' 集成测试（LLM 调用） ':=^50}")
    print(f"{'=' * 50}")

    tests = [
        test_chat_completion_integration,
        test_llm_chat_integration,
        test_close_global_session,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] 断言失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] 异常: {e}")
            failed += 1

    return passed, failed


async def main():
    """主测试入口"""
    print(f"\n{' Yuki LLM Client 测试 ':=^50}")
    print(f"LLM URL: {cfg.LLM_BASE_URL}")
    print(f"LLM 模型: {cfg.LLM_MODEL}")
    print(f"API Key: {'已配置' if cfg.LLM_API_KEY else '未配置'}")

    # 运行单元测试
    unit_passed, unit_failed = run_unit_tests()

    # 运行集成测试
    int_passed, int_failed = await run_integration_tests()

    # 汇总结果
    total_passed = unit_passed + int_passed
    total_failed = unit_failed + int_failed

    print(f"\n{'=' * 50}")
    print(f"{' 测试结果汇总 ':=^50}")
    print(f"{'=' * 50}")
    print(f"单元测试: {unit_passed} 通过, {unit_failed} 失败")
    print(f"集成测试: {int_passed} 通过, {int_failed} 失败")
    print(f"总计: {total_passed} 通过, {total_failed} 失败")

    if total_failed == 0:
        print(f"\n[PASS] 全部测试通过！")
    else:
        print(f"\n[FAIL] 有 {total_failed} 个测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
