# tests/test_tool_markup.py
"""文本形式工具调用的解析与清洗。"""
import asyncio
import json

from core.reply_format import clean_visible_reply, normalize_reply_markup
from core.tool_markup import extract_text_tool_calls, strip_tool_call_markup

# 线上事故原样复现：模型把 delegate_to_maid 调用写成了 DSML 标记正文
DSML_LEAK = (
    "\n\n<｜｜DSML｜｜ calls>\n"
    '<｜｜DSML｜｜ invoke name="delegate_to_maid">\n'
    '<｜｜DSML｜｜ parameter name="arguments" string="true">{"goal": "补全日记"}</｜｜DSML｜｜ parameter>\n'
    "</｜｜DSML｜｜ invoke>\n"
    "</｜｜DSML｜｜ calls>"
)


def test_extract_dsml_call():
    calls, cleaned = extract_text_tool_calls(DSML_LEAK, {"delegate_to_maid"})
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "delegate_to_maid"
    assert json.loads(calls[0]["function"]["arguments"]) == {"goal": "补全日记"}
    assert cleaned == ""


def test_extract_dsml_call_keeps_visible_text():
    content = "我先让小女仆查一下喵" + DSML_LEAK
    calls, cleaned = extract_text_tool_calls(content, {"delegate_to_maid"})
    assert len(calls) == 1
    assert cleaned == "我先让小女仆查一下喵"


def test_extract_dsml_direct_parameters():
    """parameter 直接按参数名写，而不是一整包 arguments。"""
    content = (
        "<|DSML| calls><|DSML| invoke name=\"ncm_search\">"
        '<|DSML| parameter name="keyword" string="true">晴天</|DSML| parameter>'
        "</|DSML| invoke></|DSML| calls>"
    )
    calls, cleaned = extract_text_tool_calls(content, {"ncm_search"})
    assert calls and calls[0]["function"]["name"] == "ncm_search"
    assert json.loads(calls[0]["function"]["arguments"]) == {"keyword": "晴天"}
    assert cleaned == ""


def test_extract_tool_call_json_block():
    content = '好的<tool_call>{"name": "poke", "arguments": {"count": 2}}</tool_call>'
    calls, cleaned = extract_text_tool_calls(content, {"poke"})
    assert calls and calls[0]["function"]["name"] == "poke"
    assert json.loads(calls[0]["function"]["arguments"]) == {"count": 2}
    assert cleaned == "好的"


def test_extract_function_block():
    content = '<function=send_master_private>{"message": "晚点睡"}</function>'
    calls, cleaned = extract_text_tool_calls(content, {"send_master_private"})
    assert calls and json.loads(calls[0]["function"]["arguments"]) == {"message": "晚点睡"}
    assert cleaned == ""


def test_extract_ignores_unknown_tool_names():
    """未注册的工具名不执行（防止模型凭空调用）。"""
    content = '<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>'
    calls, cleaned = extract_text_tool_calls(content, {"poke"})
    assert calls == []
    assert cleaned == content


def test_extract_plain_text_untouched():
    for text in ("", None, "今天天气不错喵", '{"goal": "普通 JSON 不是工具调用"}'):
        calls, cleaned = extract_text_tool_calls(text, {"poke"})
        assert calls == []
        assert cleaned == (text or "")


def test_strip_tool_call_markup_removes_leaked_blocks():
    cleaned = strip_tool_call_markup("正文" + DSML_LEAK)
    assert cleaned == "正文"
    # 标记不完整（被截断）时，从标记起整段丢弃
    assert strip_tool_call_markup('正文<｜｜DSML｜｜ invoke name="poke">{"a": 1') == "正文"


def test_clean_visible_reply_drops_tool_markup():
    """发送前兜底：即使没被解析执行，标记也不能外泄。"""
    assert clean_visible_reply(DSML_LEAK) == ""
    assert clean_visible_reply("我先查查" + DSML_LEAK) == "我先查查"
    assert normalize_reply_markup(DSML_LEAK) == ""


# ==================== 工具链端到端：文本调用被解析并真正执行 ====================

def test_chat_with_tools_executes_text_form_call():
    """模型把调用写成正文文本时，应还原成真实调用执行，且不外泄标记。"""
    from unittest.mock import patch

    from core.engine.engine_reply import EngineReplyService

    class _ToolManager:
        max_rounds = 3

        def start_session(self, *args, **kwargs):
            return None

        def finish_session(self, *args, **kwargs):
            return None

    captured = {}

    class _CallManager:
        def __init__(self, *args, **kwargs):
            self.max_rounds = 3

        async def execute_tool_calls(self, tool_calls, context, finish_reason=""):
            captured["tool_calls"] = tool_calls
            captured["finish_reason"] = finish_reason
            return [
                {"role": "tool", "tool_call_id": call["id"], "name": call["function"]["name"],
                 "content": '{"success": true, "content": "ok"}'}
                for call in tool_calls
            ]

        def finish_session(self, *args, **kwargs):
            return None

    class _Sender:
        def __init__(self):
            self.sent = []

        async def send(self, chat_id, message, mode="private"):
            self.sent.append(message)

    sender = _Sender()
    service = EngineReplyService(
        yuki=type("Y", (), {"message_buffer": {}})(),
        history=type("H", (), {"append_session_message": staticmethod(lambda *a, **k: None)})(),
        sender=sender,
        tool_registry=type("R", (), {
            "get_tools": lambda self: [],
            "list_functions": lambda self: ["poke"],
            "get_spec": lambda self, name: None,
        })(),
        tool_manager=_ToolManager(),
        get_process_callback=lambda: None,
        get_image_store=lambda: None,
    )

    responses = [
        {"role": "assistant", "content": "我戳你一下喵" + DSML_LEAK.replace("delegate_to_maid", "poke")},
        {"role": "assistant", "content": "戳完啦"},
    ]

    async def fake_raw(**kwargs):
        return responses.pop(0)

    with patch("core.engine.engine_reply.llm_chat_raw", fake_raw), \
            patch("core.engine.engine_reply.ToolCallManager", _CallManager):
        raw, visible = asyncio.run(
            service.chat_with_tools("10001", "hi", [], "group", [])
        )

    assert visible == "戳完啦"
    assert captured["tool_calls"], "文本形式的调用必须被真正执行"
    assert captured["tool_calls"][0]["function"]["name"] == "poke"
    assert json.loads(captured["tool_calls"][0]["function"]["arguments"]) == {"goal": "补全日记"}
    assert sender.sent == ["我戳你一下喵"], "阶段性文本里不能带标记"
