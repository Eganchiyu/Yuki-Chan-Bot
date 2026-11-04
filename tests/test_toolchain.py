"""工具链核心契约 (core/toolchain.py) 与内置工具 (core/tools/) 单元测试。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core.session_pipeline import SessionPipeline
from core.toolchain import (
    SKIP_REPLY_MARKER,
    FunctionRegistry,
    ToolCallManager,
    ToolContext,
    ToolResult,
    ToolRuntime,
    ToolSpec,
)
from core.tools import TOOL_SPECS, parse_rich_message_tool, send_qq_file_tool


async def _sample_tool(context, text=""):
    return ToolResult(success=True, content=f"已处理：{text}", data={"chat_id": context.chat_id})


async def _another_tool(context):
    return ToolResult(success=True, content="第二个工具")


async def _failing_tool(context):
    raise RuntimeError("secret internal detail")


def _build_context(mode="group"):
    runtime = ToolRuntime(
        sender=AsyncMock(),
        yuki_state=SimpleNamespace(maid_current_tasks={}, maid_task_queue=asyncio.Queue()),
    )
    return ToolContext(
        chat_id="test_chat", mode=mode, session=[], combined_text="测试", runtime=runtime, metadata={}
    )


def _build_sample_registry():
    reg = FunctionRegistry()
    reg.scan_and_register([
        ToolSpec(
            name="sample",
            description="测试工具",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            handler=_sample_tool,
        ),
        ToolSpec(
            name="another",
            description="第二个工具",
            parameters={"type": "object", "properties": {}},
            handler=_another_tool,
        ),
    ])
    return reg


# ==================== ToolSpec 与 FunctionRegistry ====================

def test_tool_specs_and_registry_contracts():
    """ToolSpec schema 结构、delegate_to_maid 专属字数提示、已归档工具不暴露，以及注册表增删查。"""
    spec = ToolSpec(name="sample", description="测试工具", parameters={"type": "object", "properties": {}}, handler=_sample_tool)
    schema = spec.to_schema()
    assert schema["type"] == "function" and schema["function"]["name"] == "sample"

    descriptions = {s.name: s.description for s in TOOL_SPECS}
    assert "500 字以内" in descriptions["delegate_to_maid"]
    assert all("500 字以内" not in d for n, d in descriptions.items() if n != "delegate_to_maid")
    assert "skip" in descriptions
    assert "get_master_status" not in descriptions

    reg = _build_sample_registry()
    assert reg.list_functions() == ["sample", "another"]
    assert reg.get_handler("sample") is _sample_tool and reg.get_handler("missing") is None
    reg.unregister("sample")
    assert reg.list_functions() == ["another"] and reg.get_handler("sample") is None


# ==================== ToolCallManager 执行与容错 ====================

async def test_tool_call_manager_execution_and_error_handling():
    """顺序执行、JSON 损坏自纠提示、length 截断诊断、缺失 handler 与内部异常脱敏。"""
    reg = _build_sample_registry()
    reg.register(ToolSpec(name="failing", description="err", parameters={}, handler=_failing_tool))
    manager = ToolCallManager(reg)

    # 正常批量保序执行
    msgs = await manager.execute_tool_calls([
        {"id": "c1", "function": {"name": "sample", "arguments": json.dumps({"text": "hi"})}},
        {"id": "c2", "function": {"name": "another", "arguments": "{}"}},
    ], _build_context())
    assert [m["tool_call_id"] for m in msgs] == ["c1", "c2"]
    p1 = json.loads(msgs[0]["content"])
    assert p1["success"] is True and p1["content"] == "已处理：hi"

    # 非法 JSON 与 length 截断提示
    bad_msg = await manager.execute_tool_call(
        {"id": "c_bad", "function": {"name": "sample", "arguments": '{"text": "很长的任务'}},
        _build_context(),
        finish_reason="length",
    )
    bad_payload = json.loads(bad_msg["content"])
    assert bad_payload["error"] == "invalid_json"
    assert "截断" in bad_payload["content"] and "500 字以内" in bad_payload["content"]

    # 未注册工具
    miss_msg = await manager.execute_tool_call(
        {"id": "c_miss", "function": {"name": "missing", "arguments": "{}"}}, _build_context()
    )
    assert json.loads(miss_msg["content"])["error"] == "handler_not_found"

    # 内部异常不外泄敏感细节
    err_msg = await manager.execute_tool_call(
        {"id": "c_err", "function": {"name": "failing", "arguments": "{}"}}, _build_context()
    )
    err_payload = json.loads(err_msg["content"])
    assert err_payload["error"] == "tool_execution_failed"
    assert "secret internal detail" not in err_msg["content"]


# ==================== skip 工具与管线静默抹痕 ====================

async def test_skip_tool_and_pipeline_pruning():
    """skip 仅在群聊生效并中断同批后续工具；管线收到 SKIP_REPLY_MARKER 不发消息且抹去本轮工具痕迹。"""
    full_reg = FunctionRegistry()
    full_reg.scan_and_register(TOOL_SPECS)
    manager = ToolCallManager(full_reg)

    # 群聊 skip 成功并中断同批后续工具
    grp_ctx = _build_context("group")
    msgs = await manager.execute_tool_calls([
        {"id": "c1", "function": {"name": "skip", "arguments": json.dumps({"reason": "在聊别的"})}},
        {"id": "c2", "function": {"name": "poke", "arguments": json.dumps({"target": "某人"})}},
    ], grp_ctx)
    assert grp_ctx.metadata.get("skip_reply") is True
    assert [m["name"] for m in msgs] == ["skip"]

    # 私聊拒绝 skip
    priv_ctx = _build_context("private")
    priv_msgs = await manager.execute_tool_calls(
        [{"id": "c3", "function": {"name": "skip", "arguments": "{}"}}], priv_ctx
    )
    assert priv_ctx.metadata.get("skip_reply") is None
    assert json.loads(priv_msgs[0]["content"])["error"] == "skip_not_allowed"

    # 管线收到 SKIP_REPLY_MARKER 停止发送并清理工具痕迹，只保留期间新到的用户消息
    components = {
        "sender": AsyncMock(), "meme_processor": MagicMock(), "yuki": MagicMock(),
        "history_manager": MagicMock(), "memory_rag": MagicMock(), "engine": MagicMock(),
    }
    pipeline = SessionPipeline(components, {})
    pipeline.engine.api_reply = AsyncMock(return_value=(SKIP_REPLY_MARKER, SKIP_REPLY_MARKER, ""))

    snapshot = [{"role": "system", "content": "sys"}, {"role": "user", "content": "群友聊天"}]
    pipeline.history_manager.get_session.return_value = snapshot + [
        {"role": "assistant", "content": "…", "is_tool_thought": True},
        {"role": "tool", "content": '{"success": true}', "name": "skip"},
        {"role": "user", "content": "【工具调用期间新增消息】还有人吗"},
    ]
    res = await pipeline.generate_reply({
        "chat_id": "12345", "mode": "group", "combined_text": "群友聊天",
        "relevant_diaries": [], "session": list(snapshot),
    })
    assert res["stop"] is True and res.get("skip_reply") is True and "answer_text" not in res
    pipeline.sender.send.assert_not_awaited()
    saved = pipeline.history_manager.replace_session.call_args[0][1]
    assert saved == snapshot + [{"role": "user", "content": "【工具调用期间新增消息】还有人吗"}]


# ==================== 内置工具：发文件与富文本解析 ====================

async def test_send_qq_file_and_parse_rich_message(tmp_path):
    """send_qq_file 自动识别普通文件并调用发送器；parse_rich_message 支持解析 NapCat JSON 小程序段。"""
    sent_files = []
    file_path = tmp_path / "report.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def send_local_file(chat_id, local_path, mode="private"):
        sent_files.append((chat_id, local_path, mode))

    ctx = _build_context()
    ctx.runtime.sender = SimpleNamespace(send_local_file=send_local_file)
    file_res = await send_qq_file_tool(ctx, str(file_path))
    assert file_res.success is True and file_res.data["file_type"] == "file"
    assert sent_files[0][0] == "test_chat"

    ctx.metadata["message_objs"] = [{
        "name": "测试群友",
        "message_id": 1376986332,
        "segments": [{
            "type": "json",
            "data": {
                "data": json.dumps({
                    "prompt": "[QQ小程序]捷克狼犬",
                    "meta": {"detail_1": {"title": "哔哩哔哩", "desc": "捷克狼犬", "qqdocurl": "https://b23.tv/CxLmUuP"}},
                }, ensure_ascii=False)
            },
        }],
    }]
    rich_res = await parse_rich_message_tool(ctx, rich_type="miniapp")
    assert rich_res.success is True and rich_res.data["type"] == "miniapp"
    assert "捷克狼犬" in rich_res.content and "https://b23.tv/CxLmUuP" in rich_res.content
