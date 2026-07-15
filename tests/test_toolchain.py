# tests/test_toolchain.py
import asyncio
import json
import os
import sys
from types import SimpleNamespace

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.toolchain import FunctionRegistry, ToolCallManager, ToolContext, ToolResult, ToolRuntime, ToolSpec


async def sample_tool(context, text=""):
    return ToolResult(success=True, content=f"已处理：{text}", data={"chat_id": context.chat_id})


async def another_tool(context):
    return ToolResult(success=True, content="第二个工具")


async def failing_tool(context):
    raise RuntimeError("secret internal detail")


def build_context():
    runtime = ToolRuntime(
        sender=SimpleNamespace(),
        yuki_state=SimpleNamespace(maid_current_tasks={}, maid_task_queue=asyncio.Queue()),
    )
    return ToolContext(
        chat_id="test_chat",
        mode="group",
        session=[],
        combined_text="测试工具调用",
        runtime=runtime,
        metadata={},
    )


def build_registry():
    registry = FunctionRegistry()
    registry.scan_and_register([
        ToolSpec(
            name="sample",
            description="测试工具",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
            handler=sample_tool,
        ),
        ToolSpec(
            name="another",
            description="第二个测试工具",
            parameters={"type": "object", "properties": {}},
            handler=another_tool,
        ),
    ])
    return registry


def test_tool_spec_to_schema():
    spec = ToolSpec(
        name="sample",
        description="测试工具",
        parameters={"type": "object", "properties": {}},
        handler=sample_tool,
    )
    schema = spec.to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "sample"
    assert schema["function"]["description"] == "测试工具"


def test_registry_registers_tool_specs():
    registry = build_registry()
    assert registry.list_functions() == ["sample", "another"]
    assert registry.get_handler("sample") is sample_tool
    assert registry.get_handler("missing") is None
    assert len(registry.get_tools()) == 2


def test_registry_unregister():
    registry = build_registry()
    registry.unregister("sample")
    assert registry.list_functions() == ["another"]
    assert registry.get_handler("sample") is None


def test_execute_tool_call_success():
    async def run():
        manager = ToolCallManager(build_registry())
        message = await manager.execute_tool_call(
            {
                "id": "call_1",
                "function": {"name": "sample", "arguments": json.dumps({"text": "hello"})},
            },
            build_context(),
        )
        payload = json.loads(message["content"])
        assert message["role"] == "tool"
        assert message["tool_call_id"] == "call_1"
        assert message["name"] == "sample"
        assert payload["success"] is True
        assert payload["content"] == "已处理：hello"
        assert payload["data"]["chat_id"] == "test_chat"

    asyncio.run(run())


def test_execute_tool_call_invalid_json():
    async def run():
        manager = ToolCallManager(build_registry())
        message = await manager.execute_tool_call(
            {"id": "call_bad", "function": {"name": "sample", "arguments": "{"}},
            build_context(),
        )
        payload = json.loads(message["content"])
        assert payload["success"] is False
        assert payload["content"] == "工具参数不是合法 JSON"
        assert payload["error"] == "invalid_json"

    asyncio.run(run())


def test_execute_tool_call_missing_handler():
    async def run():
        manager = ToolCallManager(build_registry())
        message = await manager.execute_tool_call(
            {"id": "call_missing", "function": {"name": "missing", "arguments": "{}"}},
            build_context(),
        )
        payload = json.loads(message["content"])
        assert payload["success"] is False
        assert payload["error"] == "handler_not_found"

    asyncio.run(run())


def test_execute_tool_call_hides_internal_exception():
    async def run():
        registry = build_registry()
        registry.register(
            ToolSpec(
                name="failing",
                description="异常工具",
                parameters={"type": "object", "properties": {}},
                handler=failing_tool,
            )
        )
        manager = ToolCallManager(registry)
        message = await manager.execute_tool_call(
            {"id": "call_error", "function": {"name": "failing", "arguments": "{}"}},
            build_context(),
        )
        payload = json.loads(message["content"])
        assert payload["success"] is False
        assert payload["error"] == "tool_execution_failed"
        assert "secret internal detail" not in payload["content"]
        assert "secret internal detail" not in payload["error"]

    asyncio.run(run())


def test_execute_tool_calls_keep_order():
    async def run():
        manager = ToolCallManager(build_registry())
        messages = await manager.execute_tool_calls(
            [
                {"id": "call_1", "function": {"name": "sample", "arguments": "{}"}},
                {"id": "call_2", "function": {"name": "another", "arguments": "{}"}},
            ],
            build_context(),
        )
        assert [message["tool_call_id"] for message in messages] == ["call_1", "call_2"]
        assert [message["name"] for message in messages] == ["sample", "another"]

    asyncio.run(run())


def test_timer_task_triggers_pipeline_callback():
    async def run():
        from core.tools import manage_timer_task_tool

        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append({"chat_id": chat_id, "mode": mode, **kwargs})

        context = build_context()
        context.metadata["process_callback"] = callback
        result = await manage_timer_task_tool(
            context,
            title="提醒喝水",
            delay_seconds=0,
            message="该喝水了",
        )
        await asyncio.sleep(0.05)

        assert result.success is True
        assert calls
        assert calls[0]["chat_id"] == "test_chat"
        assert calls[0]["message_obj"]["content"] == "【定时任务到点】该喝水了"
        assert calls[0]["debounce_flag"] is False
        assert calls[0]["force_reply"] is True

    asyncio.run(run())


def test_send_qq_file_auto_detects_plain_file(tmp_path):
    async def run():
        from core.tools import send_qq_file_tool

        sent_files = []
        file_path = tmp_path / "report.txt"
        file_path.write_text("hello", encoding="utf-8")

        async def send_local_file(chat_id, local_path, mode="private"):
            sent_files.append((chat_id, local_path, mode))

        context = build_context()
        context.runtime.sender = SimpleNamespace(send_local_file=send_local_file)
        result = await send_qq_file_tool(context, str(file_path))

        assert result.success is True
        assert result.data["file_type"] == "file"
        assert sent_files[0][0] == "test_chat"

    asyncio.run(run())
