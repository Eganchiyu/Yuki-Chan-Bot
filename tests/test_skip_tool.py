# tests/test_skip_tool.py
"""skip 工具：模型主动跳过本轮回复的单元与管线测试。"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from core.toolchain import (
    SKIP_REPLY_MARKER,
    FunctionRegistry,
    ToolCallManager,
    ToolContext,
    ToolRuntime,
)
from core.tools import TOOL_SPECS


def _registry():
    registry = FunctionRegistry()
    registry.scan_and_register(TOOL_SPECS)
    return registry


def _context(mode="group"):
    return ToolContext(
        chat_id="12345",
        mode=mode,
        session=[],
        combined_text="",
        runtime=ToolRuntime(sender=AsyncMock(), yuki_state=MagicMock()),
    )


def test_skip_tool_registered():
    assert "skip" in _registry().list_functions()


def test_skip_marks_context_and_stops_batch():
    async def run():
        manager = ToolCallManager(_registry())
        context = _context("group")
        messages = await manager.execute_tool_calls(
            [
                {"id": "c1", "function": {"name": "skip", "arguments": json.dumps({"reason": "在聊别的"})}},
                {"id": "c2", "function": {"name": "poke", "arguments": json.dumps({"target": "某人"})}},
            ],
            context,
        )
        assert context.metadata.get("skip_reply") is True
        # skip 生效后同批后面的工具不再执行，避免跳过之后又发出消息
        assert [m["name"] for m in messages] == ["skip"]
        payload = json.loads(messages[0]["content"])
        assert payload["success"] is True
        assert payload["data"]["skip_reply"] is True

    asyncio.run(run())


def test_skip_rejected_outside_group():
    async def run():
        manager = ToolCallManager(_registry())
        context = _context("private")
        messages = await manager.execute_tool_calls(
            [{"id": "c3", "function": {"name": "skip", "arguments": "{}"}}],
            context,
        )
        assert context.metadata.get("skip_reply") is None
        payload = json.loads(messages[0]["content"])
        assert payload["success"] is False
        assert payload["error"] == "skip_not_allowed"

    asyncio.run(run())


def _pipeline():
    from core.session_pipeline import SessionPipeline

    components = {
        "sender": AsyncMock(),
        "meme_processor": MagicMock(),
        "yuki": MagicMock(),
        "history_manager": MagicMock(),
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
    }
    pipeline = SessionPipeline(components, {})
    pipeline.engine.api_reply = AsyncMock(return_value=(SKIP_REPLY_MARKER, SKIP_REPLY_MARKER, ""))
    return pipeline


def test_pipeline_stops_without_sending_on_skip():
    async def run():
        pipeline = _pipeline()
        context = {
            "chat_id": "12345",
            "mode": "group",
            "combined_text": "群友们在聊天",
            "relevant_diaries": [],
            "session": [{"role": "system", "content": "sys"}, {"role": "user", "content": "群友们在聊天"}],
        }
        result = await pipeline.generate_reply(context)

        assert result["stop"] is True
        assert result.get("skip_reply") is True
        assert "answer_text" not in result
        pipeline.sender.send.assert_not_awaited()
        # 用户消息照常留在上下文里，只是没有 assistant 回复
        pipeline.history_manager.replace_session.assert_called_once_with("12345", context["session"])

    asyncio.run(run())
