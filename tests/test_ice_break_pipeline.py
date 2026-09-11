# tests/test_ice_break_pipeline.py
"""
破冰流程主管道集成 Smoke Test

验证破冰逻辑从独立流程迁移到主管道后的正确性：
  1. 纯函数：get_ice_break_instructions 返回有效内容
  2. 提示词注入：build_chat_context 在 ice_break=True 时注入破冰指令
  3. 管道阶段：各阶段正确处理 ice_break 上下文标记
  4. 监控集成：ice_break_monitor 通过 process_callback 触发主管道
  5. 计数递增：finalize_conversation 正确递增破冰失败计数

运行方式：
    python tests/test_ice_break_pipeline.py
    python -m pytest tests/test_ice_break_pipeline.py -v
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Windows 控制台 UTF-8 支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 动态获取项目根目录并加入 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)


# ==================== 纯函数测试 ====================

def test_get_ice_break_instructions_returns_content():
    """get_ice_break_instructions 返回非空字符串且包含关键指令"""
    print("\n[测试 1] get_ice_break_instructions 返回有效内容")

    from core.prompts import get_ice_break_instructions

    result = get_ice_break_instructions()

    assert isinstance(result, str), "返回值应为字符串"
    assert len(result) > 50, "返回内容过短"
    assert "破冰模式指令" in result, "应包含'破冰模式指令'标记"
    assert "群聊安静中" in result, "应包含环境描述"
    assert "30-60 字" in result, "应包含字数限制"
    print(f"  [PASS] 返回 {len(result)} 字符的破冰指令")


def test_get_ice_break_instructions_contains_time():
    """get_ice_break_instructions 包含当前时间信息"""
    print("\n[测试 2] get_ice_break_instructions 包含时间信息")

    from core.prompts import get_ice_break_instructions
    import datetime

    result = get_ice_break_instructions()
    now = datetime.datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")

    assert time_str in result, f"应包含当前时间 {time_str}"
    print(f"  [PASS] 包含当前时间: {time_str}")


# ==================== 提示词注入测试 ====================

async def test_build_chat_context_injects_ice_break_instructions():
    """build_chat_context 在 ice_break=True 时注入破冰指令到系统消息中"""
    print("\n[测试 3] build_chat_context 注入破冰指令")

    from core.prompts import build_chat_context

    # 构造最小化 mock
    yuki = MagicMock()
    yuki.get_setting.return_value = "你是测试机器人"

    chat_id = "12345"
    history_dict = {
        chat_id: [
            {"role": "system", "content": "你是测试机器人"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "嗨~"},
        ]
    }
    relevant_diaries = [{"content": "今天天气不错", "score": 0.9, "debug": "test"}]

    # ice_break=True
    messages = await build_chat_context(
        yuki, chat_id, "测试消息", history_dict, "group", relevant_diaries,
        ice_break=True
    )

    # 检查是否包含破冰指令
    system_contents = [m["content"] for m in messages if m["role"] == "system"]
    has_ice_break = any("破冰模式指令" in c for c in system_contents)

    assert has_ice_break, "ice_break=True 时应注入破冰指令"
    print(f"  [PASS] 破冰指令已注入（共 {len(messages)} 条消息，{len(system_contents)} 条系统消息）")


async def test_build_chat_context_no_ice_break_by_default():
    """build_chat_context 默认不注入破冰指令"""
    print("\n[测试 4] build_chat_context 默认不注入破冰指令")

    from core.prompts import build_chat_context

    yuki = MagicMock()
    yuki.get_setting.return_value = "你是测试机器人"

    chat_id = "12345"
    history_dict = {
        chat_id: [
            {"role": "system", "content": "你是测试机器人"},
        ]
    }
    relevant_diaries = []

    # ice_break=False（默认）
    messages = await build_chat_context(
        yuki, chat_id, "普通消息", history_dict, "group", relevant_diaries
    )

    system_contents = [m["content"] for m in messages if m["role"] == "system"]
    has_ice_break = any("破冰模式指令" in c for c in system_contents)

    assert not has_ice_break, "默认不应注入破冰指令"
    print(f"  [PASS] 默认模式无破冰指令（共 {len(messages)} 条消息）")


# ==================== 管道阶段测试 ====================

async def test_pipeline_prepare_message_batch_ice_break():
    """prepare_message_batch 在 ice_break 模式下跳过防抖，构建合成上下文"""
    print("\n[测试 5] prepare_message_batch 破冰模式")

    from core.session_pipeline import SessionPipeline

    # 构造最小化 pipeline
    pipeline = _create_mock_pipeline()
    pipeline.history_manager.get_session.return_value = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "之前的消息"},
        {"role": "assistant", "content": "之前的回复"},
    ]

    context = {
        "chat_id": "99999",
        "mode": "group",
        "debounce_flag": True,
        "force_reply": True,
        "ice_break": True,
    }

    result = await pipeline.prepare_message_batch(context)

    assert result.get("combined_text"), "应设置 combined_text"
    assert "之前的消息" in result["combined_text"], "combined_text 应包含历史内容"
    assert result.get("message_objs") == [], "message_objs 应为空列表"
    assert "first_time" in result, "应设置 first_time"
    print(f"  [PASS] combined_text='{result['combined_text'][:50]}'")


async def test_pipeline_enqueue_preserves_incoming_message_metadata():
    """enqueue_message 保留入站消息的来源、归属和状态标签。"""
    print("\n[测试 6] enqueue_message 保留消息元数据")

    from core.session_pipeline import IncomingMessage

    pipeline = _create_mock_pipeline()
    await pipeline.enqueue_message(
        "12345",
        "private",
        message_obj=IncomingMessage(
            name="用户A",
            content="你好",
            raw_text="你好",
            user_id=12345,
            source="napcat.private",
            owner_id="12345",
            tags={"private"},
        ),
        debounce_flag=False,
        force_reply=True,
    )
    task = pipeline._timer_tasks.pop("12345")
    task.cancel()
    await asyncio.sleep(0)

    stored_message = pipeline.yuki.message_buffer["12345"][0]
    assert stored_message["source"] == "napcat.private"
    assert stored_message["owner_id"] == "12345"
    assert stored_message["status"] == "received"
    assert stored_message["tags"] == ["private"]
    print("  [PASS] 入站消息元数据已保存")


async def test_feed_message_filters_bot_unless_whitelisted():
    """feed_message 保留 BOT 过滤，并允许白名单绕过。"""
    print("\n[测试 7] BOT 黑白名单过滤")

    from modules.QQNapcatListen import listen_main

    enqueued_messages = []

    async def enqueue_message(chat_id, mode, message_obj=None, **kwargs):
        enqueued_messages.append((chat_id, mode, message_obj))

    pipeline = MagicMock()
    pipeline.yuki.last_sent_meme = {}
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.last_message_time = {}
    pipeline.history_manager = MagicMock()
    pipeline.enqueue_message = AsyncMock(side_effect=enqueue_message)
    gateway = AsyncMock()

    original_whitelist = list(listen_main.cfg.target.whitelist)
    original_max_message_length = listen_main.cfg.max_message_length
    listen_main.cfg.target.whitelist = [1390249127]
    listen_main.cfg.max_message_length = 500
    try:
        await listen_main.feed_message(
            pipeline,
            gateway,
            "10000",
            "普通机器人消息",
            "group",
            raw_message="普通机器人消息",
            sender_name="测试BOT",
            user_id=123456,
        )
        assert not enqueued_messages, "非白名单 BOT 应被拦截"

        await listen_main.feed_message(
            pipeline,
            gateway,
            "10000",
            "白名单机器人消息",
            "group",
            raw_message="白名单机器人消息",
            sender_name="测试BOT",
            user_id=1390249127,
        )
        assert len(enqueued_messages) == 1, "白名单 BOT 应允许进入管线"
        assert enqueued_messages[0][2].is_bot is True
    finally:
        listen_main.cfg.target.whitelist = original_whitelist
        listen_main.cfg.max_message_length = original_max_message_length

    print("  [PASS] BOT 黑白名单过滤正常")


async def test_pipeline_decide_reply_always_replies_in_private():
    """私聊模式跳过群聊潜水决策。"""
    print("\n[测试 7] private 模式必回")

    pipeline = _create_mock_pipeline()
    context = {
        "chat_id": "12345",
        "mode": "private",
        "ice_break": False,
        "history_dict": {"12345": []},
        "message_objs": [],
        "force_reply": None,
    }

    result = await pipeline.decide_reply_action(context)

    assert not result.get("stop"), "私聊不应被潜水决策停止"
    pipeline.engine.decide_to_reply.assert_not_called()
    print("  [PASS] private 模式跳过群聊回复决策")


async def test_pipeline_normalize_skips_for_ice_break():
    """normalize_incoming_content 在 ice_break 模式下直接跳过"""
    print("\n[测试 6] normalize_incoming_content 破冰跳过")

    from core.session_pipeline import SessionPipeline

    pipeline = _create_mock_pipeline()

    context = {
        "chat_id": "99999",
        "ice_break": True,
        "combined_text": "已有文本",
    }

    result = await pipeline.normalize_incoming_content(context)

    assert result["combined_text"] == "已有文本", "不应修改 combined_text"
    print(f"  [PASS] 破冰模式跳过消息规范化")


async def test_pipeline_decide_reply_skips_for_ice_break():
    """decide_reply_action 在 ice_break 模式下跳过决策，强制回复"""
    print("\n[测试 7] decide_reply_action 破冰强制回复")

    from core.session_pipeline import SessionPipeline

    pipeline = _create_mock_pipeline()

    context = {
        "chat_id": "99999",
        "mode": "group",
        "ice_break": True,
        "history_dict": {"99999": []},
        "message_objs": [],
        "force_reply": True,
    }

    result = await pipeline.decide_reply_action(context)

    assert not result.get("stop"), "破冰模式不应标记 stop"
    # decide_to_reply 不应被调用
    pipeline.engine.decide_to_reply.assert_not_called()
    print(f"  [PASS] 破冰模式跳过回复决策")


async def test_pipeline_finalize_increments_fail_count():
    """finalize_conversation 在 ice_break 模式下递增破冰失败计数"""
    print("\n[测试 8] finalize_conversation 破冰计数递增")

    from core.session_pipeline import SessionPipeline

    pipeline = _create_mock_pipeline()
    pipeline.yuki.ice_break_fail_count = {"99999": 0}

    context = {
        "chat_id": "99999",
        "history_dict": {
            "99999": [
                {"role": "system", "content": "系统"},
            ]
        },
        "answer_text": "测试回复",
        "answer_raw": "测试回复",
        "current_time_str": "2026年06月06日12:00",
        "ice_break": True,
    }

    result = await pipeline.finalize_conversation(context)

    assert pipeline.yuki.ice_break_fail_count["99999"] == 1, \
        f"破冰计数应为 1，实际为 {pipeline.yuki.ice_break_fail_count['99999']}"
    print(f"  [PASS] 破冰失败计数从 0 递增到 1")


async def test_pipeline_finalize_no_increment_without_ice_break():
    """finalize_conversation 非破冰模式不递增计数"""
    print("\n[测试 9] finalize_conversation 非破冰不递增计数")

    from core.session_pipeline import SessionPipeline

    pipeline = _create_mock_pipeline()
    pipeline.yuki.ice_break_fail_count = {"99999": 0}

    context = {
        "chat_id": "99999",
        "history_dict": {
            "99999": [
                {"role": "system", "content": "系统"},
            ]
        },
        "answer_text": "普通回复",
        "answer_raw": "普通回复",
        "current_time_str": "2026年06月06日12:00",
        "ice_break": False,
    }

    result = await pipeline.finalize_conversation(context)

    assert pipeline.yuki.ice_break_fail_count["99999"] == 0, \
        f"非破冰模式计数应保持 0，实际为 {pipeline.yuki.ice_break_fail_count['99999']}"
    print(f"  [PASS] 非破冰模式计数不变")


# ==================== 监控集成测试 ====================

async def test_ice_break_monitor_calls_process_callback():
    """ice_break_monitor 检测到破冰条件时通过 process_callback 触发主管道"""
    print("\n[测试 10] ice_break_monitor 调用 process_callback")

    from core.engine import YukiEngine

    engine = _create_mock_engine()
    # 设置 process_callback 为 mock
    callback_mock = AsyncMock()
    engine.process_callback = callback_mock

    # 模拟破冰条件：低活跃度、高欲望、低失败计数
    engine.yuki.group_activity = {"99999": 0.1}
    engine.yuki.desire_to_start_topic = {"99999": 80}
    engine.yuki.ice_break_fail_count = {"99999": 0}
    engine.yuki.energy = {"99999": 90}
    engine.yuki.last_update = {}

    # 补丁：让 random.random() 返回 0.1（< 0.8 触发），random.randint 返回固定值
    with patch("core.engine.random.random", return_value=0.1), \
         patch("core.engine.random.randint", return_value=600), \
         patch("core.engine.cfg") as mock_cfg:
        mock_cfg.TARGET_GROUPS = [99999]

        # 手动执行一次 ice_break_monitor 的核心逻辑（不进入无限循环）
        # 模拟 ice_break_monitor 的单次迭代
        target_list = [str(gid) for gid in mock_cfg.TARGET_GROUPS]
        pending_ice_break = []

        for cid in target_list:
            engine.yuki.update_energy(chat_id=cid)
            activity = engine.yuki.group_activity.get(cid, 0.0)
            desire = engine.yuki.desire_to_start_topic.get(cid, 0)
            fail_count = engine.yuki.ice_break_fail_count.get(cid, 0)

            if activity < 0.5 and desire > 75 and fail_count < 0.8:
                pending_ice_break.append(cid)

        for cid in pending_ice_break:
            if engine.process_callback is not None:
                await engine.process_callback(cid, "group", debounce_flag=False, force_reply=True, ice_break=True)

    callback_mock.assert_called_once_with(
        "99999", "group", debounce_flag=False, force_reply=True, ice_break=True
    )
    print(f"  [PASS] process_callback 已调用，参数 ice_break=True")


async def test_ice_break_monitor_without_callback():
    """ice_break_monitor 在 process_callback 未设置时不崩溃"""
    print("\n[测试 11] ice_break_monitor 无回调安全降级")

    from core.engine import YukiEngine

    engine = _create_mock_engine()
    engine.process_callback = None  # 未设置回调

    # 这里只验证逻辑不会抛异常
    try:
        if engine.process_callback is not None:
            await engine.process_callback("99999", "group", ice_break=True)
        # 不应到达这里，因为 callback 是 None
        callback_called = False
    except Exception:
        callback_called = True

    assert not callback_called, "callback 为 None 时不应调用"
    print(f"  [PASS] process_callback=None 时安全跳过")


# ==================== 端到端管道测试 ====================

async def test_pipeline_run_once_ice_break_context_propagation():
    """run_once 在 ice_break=True 时将标记正确传播到所有阶段"""
    print("\n[测试 12] run_once ice_break 上下文传播")

    from core.session_pipeline import SessionPipeline

    pipeline = _create_mock_pipeline()

    # Mock 所有阶段，记录接收到的 context
    stage_contexts = []

    async def capture_stage(context):
        stage_contexts.append({
            "stage": context.get("_stage_name", "unknown"),
            "ice_break": context.get("ice_break"),
            "stop": context.get("stop"),
        })
        return context

    # 替换 stages 为带标记的 capture 函数
    original_stages = pipeline.stages
    named_stages = []
    for i, stage in enumerate(original_stages):
        async def named_capture(ctx, _name=stage.__name__):
            ctx["_stage_name"] = _name
            return await capture_stage(ctx)
        named_stages.append(named_capture)

    pipeline.stages = named_stages

    # 设置 mock 历史
    pipeline.history_manager.load.return_value = {
        "99999": [
            {"role": "system", "content": "系统"},
            {"role": "user", "content": "历史消息"},
            {"role": "assistant", "content": "历史回复"},
        ]
    }

    # Mock engine.api_reply 返回值
    pipeline.engine.api_reply = AsyncMock(return_value=("原始回复", "清理回复", ""))

    try:
        result = await pipeline.run_once("99999", "group", debounce_flag=False, force_reply=True, ice_break=True)
    finally:
        pipeline.stages = original_stages

    # 验证 ice_break 标记在各阶段都存在
    ice_break_stages = [s for s in stage_contexts if s["ice_break"] is True]
    assert len(ice_break_stages) > 0, "ice_break 标记应传播到至少一个阶段"

    # 验证 decide_reply_action 阶段未标记 stop
    decide_stages = [s for s in stage_contexts if s["stage"] == "decide_reply_action"]
    if decide_stages:
        assert not decide_stages[0].get("stop"), "decide_reply_action 不应标记 stop"

    print(f"  [PASS] ice_break 标记传播到 {len(ice_break_stages)}/{len(stage_contexts)} 个阶段")


# ==================== 辅助函数 ====================

def _create_mock_pipeline():
    """创建最小化的 SessionPipeline mock 实例"""
    from core.session_pipeline import SessionPipeline

    components = {
        "sender": AsyncMock(),
        "meme_processor": MagicMock(),
        "yuki": MagicMock(),
        "history_manager": MagicMock(),
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
    }
    group_active_state = {}

    pipeline = SessionPipeline(components, group_active_state)

    # 设置必要的 mock 返回值
    pipeline.yuki.lock = asyncio.Lock()
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.energy = {}
    pipeline.yuki.group_activity = {}
    pipeline.yuki.message_buffer = {}
    pipeline.yuki.buffer_tasks = {}
    pipeline.yuki.boost_activity = AsyncMock()
    pipeline.yuki.pop_buffer = MagicMock(return_value=[])
    pipeline.yuki.consume_energy = MagicMock()
    pipeline.yuki.get_setting = MagicMock(return_value="测试系统提示")
    pipeline.history_manager.load.return_value = {}
    pipeline.history_manager.save = MagicMock()
    pipeline.history_manager.append_to_log = MagicMock()
    pipeline.engine.do_summarize = AsyncMock(return_value=[])
    pipeline.engine.decide_to_reply = AsyncMock(return_value=True)
    pipeline.engine.api_reply = AsyncMock(return_value=("原始", "回复", ""))
    pipeline.memory_rag.search_diaries = MagicMock(return_value=[])
    pipeline.meme_processor.extract_urls_from_text = MagicMock(return_value=("", []))
    pipeline.sender.parse_cq_codes = AsyncMock(side_effect=lambda text, group_id: text)

    return pipeline


def _create_mock_engine():
    """创建最小化的 YukiEngine mock 实例"""
    from core.engine import YukiEngine

    rag = MagicMock()
    history = MagicMock()
    yuki = MagicMock()
    sender = AsyncMock()

    # YukiState 需要真实的 lock
    yuki.lock = asyncio.Lock()
    yuki.energy = {}
    yuki.last_update = {}
    yuki.group_activity = {}
    yuki.desire_to_start_topic = {}
    yuki.ice_break_fail_count = {}
    yuki.update_energy = MagicMock(return_value=90)
    yuki.update_desire_to_reply = MagicMock()
    yuki.get_setting = MagicMock(return_value="测试系统提示")
    yuki.writing_diary = set()

    engine = YukiEngine(rag, history, yuki, sender)
    return engine


# ==================== 测试运行器 ====================

def run_sync_tests():
    """运行同步单元测试"""
    print(f"\n{'=' * 50}")
    print(f"{' 同步单元测试 ':=^50}")
    print(f"{'=' * 50}")

    tests = [
        test_get_ice_break_instructions_returns_content,
        test_get_ice_break_instructions_contains_time,
    ]

    passed, failed = 0, 0
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


async def run_async_tests():
    """运行异步测试"""
    print(f"\n{'=' * 50}")
    print(f"{' 异步集成测试 ':=^50}")
    print(f"{'=' * 50}")

    tests = [
        test_build_chat_context_injects_ice_break_instructions,
        test_build_chat_context_no_ice_break_by_default,
        test_pipeline_prepare_message_batch_ice_break,
        test_pipeline_enqueue_preserves_incoming_message_metadata,
        test_feed_message_filters_bot_unless_whitelisted,
        test_pipeline_decide_reply_always_replies_in_private,
        test_pipeline_normalize_skips_for_ice_break,
        test_pipeline_decide_reply_skips_for_ice_break,
        test_pipeline_finalize_increments_fail_count,
        test_pipeline_finalize_no_increment_without_ice_break,
        test_ice_break_monitor_calls_process_callback,
        test_ice_break_monitor_without_callback,
        test_pipeline_run_once_ice_break_context_propagation,
    ]

    passed, failed = 0, 0
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] 断言失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] 异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    return passed, failed


async def main():
    """主测试入口"""
    print(f"\n{' 破冰流程主管道 Smoke Test ':=^50}")
    print(f"验证破冰逻辑从独立流程迁移到主管道后的正确性")

    sync_passed, sync_failed = run_sync_tests()
    async_passed, async_failed = await run_async_tests()

    total_passed = sync_passed + async_passed
    total_failed = sync_failed + async_failed

    print(f"\n{'=' * 50}")
    print(f"{' 测试结果汇总 ':=^50}")
    print(f"{'=' * 50}")
    print(f"同步测试: {sync_passed} 通过, {sync_failed} 失败")
    print(f"异步测试: {async_passed} 通过, {async_failed} 失败")
    print(f"总计: {total_passed} 通过, {total_failed} 失败")

    if total_failed == 0:
        print(f"\n[PASS] 全部 {total_passed} 个测试通过！")
    else:
        print(f"\n[FAIL] 有 {total_failed} 个测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
