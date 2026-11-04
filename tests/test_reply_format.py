"""回复标记容错、文本工具调用解析清洗、HistoryManager 自修复与 EngineReplyService 收尾测试。"""
import json
from unittest.mock import patch

from core.engine.engine_reply import WORKING_NOTICE, EngineReplyService
from core.history_manager import HistoryManager
from core.reply_format import (
    clean_visible_reply,
    normalize_layout_tags,
    normalize_meme_tags,
    normalize_reply_markup,
    strip_layout_markup,
    strip_meme_tags,
)
from core.session_pipeline import SessionPipeline
from core.tool_markup import extract_text_tool_calls, strip_tool_call_markup

DSML_LEAK = (
    "\n\n<｜｜DSML｜｜ calls>\n"
    '<｜｜DSML｜｜ invoke name="delegate_to_maid">\n'
    '<｜｜DSML｜｜ parameter name="arguments" string="true">{"goal": "补全日记"}</｜｜DSML｜｜ parameter>\n'
    "</｜｜DSML｜｜ invoke>\n"
    "</｜｜DSML｜｜ calls>"
)


# ==================== layout / MEME 归一化与清洗 ====================

def test_layout_and_meme_markup_normalization():
    """<layout> 与 [MEME:] 的错括号/大小写/全角变体归一化，未闭合 layout 整段丢弃防外泄。"""
    for raw, expected in (
        ("[layout]盘算[/layout]", "<layout>盘算</layout>"),
        ("[layout]盘算</layout>", "<layout>盘算</layout>"),
        ("【layout】盘算【/layout】", "<layout>盘算</layout>"),
        ("［LAYOUT］盘算［/LAYOUT］", "<layout>盘算</layout>"),
        ("<layout>盘算</layout>", "<layout>盘算</layout>"),
    ):
        assert normalize_layout_tags(raw) == expected

    assert strip_layout_markup("[layout]等反驳～</layout>正文") == "正文"
    assert strip_layout_markup("[layout]没闭合的盘算，后面全是计划") == ""
    assert strip_layout_markup("<layout>同样藏住") == ""

    assert normalize_meme_tags("【MEME:委屈】语法") == "[MEME:委屈]语法"
    assert normalize_meme_tags("[meme:得意]小写") == "[MEME:得意]小写"
    assert normalize_meme_tags("［MEME：好奇］全角") == "[MEME:好奇]全角"
    assert normalize_meme_tags("[MEME]【MEME:】") == ""
    assert strip_meme_tags("正文【MEME:哼】尾巴[MEME:戳一戳]") == "正文尾巴"

    raw_mixed = "[layout]盘算[/layout]正文【MEME:坏笑】"
    assert clean_visible_reply(raw_mixed) == "正文[MEME:坏笑]"
    assert normalize_reply_markup(raw_mixed) == "<layout>盘算</layout>正文[MEME:坏笑]"

    plain = "没有任何标记的普通文本[MEME:得意]"
    assert clean_visible_reply(plain) == plain and normalize_reply_markup(plain) == plain


# ==================== 文本形式工具调用提取与清洗 ====================

def test_extract_and_strip_text_tool_calls():
    """支持 DSML、<tool_call>、<function=...> 提取，忽略未知工具，且彻底剥离残留或截断标记。"""
    calls, cleaned = extract_text_tool_calls("我先查一下喵" + DSML_LEAK, {"delegate_to_maid"})
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "delegate_to_maid"
    assert json.loads(calls[0]["function"]["arguments"]) == {"goal": "补全日记"}
    assert cleaned == "我先查一下喵"

    dsml_direct = (
        '<|DSML| calls><|DSML| invoke name="ncm_search">'
        '<|DSML| parameter name="keyword" string="true">晴天</|DSML| parameter>'
        "</|DSML| invoke></|DSML| calls>"
    )
    calls2, cleaned2 = extract_text_tool_calls(dsml_direct, {"ncm_search"})
    assert calls2 and json.loads(calls2[0]["function"]["arguments"]) == {"keyword": "晴天"} and cleaned2 == ""

    calls3, cleaned3 = extract_text_tool_calls(
        '好的<tool_call>{"name": "poke", "arguments": {"count": 2}}</tool_call>', {"poke"}
    )
    assert calls3 and json.loads(calls3[0]["function"]["arguments"]) == {"count": 2} and cleaned3 == "好的"

    calls4, cleaned4 = extract_text_tool_calls(
        '<function=send_master_private>{"message": "晚点睡"}</function>', {"send_master_private"}
    )
    assert calls4 and json.loads(calls4[0]["function"]["arguments"]) == {"message": "晚点睡"} and cleaned4 == ""

    # 未注册工具不提取
    unknown = '<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>'
    assert extract_text_tool_calls(unknown, {"poke"}) == ([], unknown)

    # 普通文本不受影响
    for text in ("", None, "今天天气不错喵", '{"goal": "普通 JSON"}'):
        assert extract_text_tool_calls(text, {"poke"}) == ([], text or "")

    assert strip_tool_call_markup("正文" + DSML_LEAK) == "正文"
    assert strip_tool_call_markup('正文<｜｜DSML｜｜ invoke name="poke">{"a": 1') == "正文"
    assert clean_visible_reply("我先查查" + DSML_LEAK) == "我先查查"
    assert normalize_reply_markup(DSML_LEAK) == ""


# ==================== 发送拦截与 HistoryManager 修复 ====================

async def test_send_reply_and_history_manager_markup_hygiene(tmp_path):
    """send_reply 剥离错括号 layout 防外泄；HistoryManager 追加与预载修复 assistant 标记且不动 user 原文。"""
    pipeline = SessionPipeline.__new__(SessionPipeline)
    sent = []

    class _Sender:
        async def send(self, chat_id, message, mode="private"):
            sent.append(message)

    pipeline.sender = _Sender()
    pipeline.yuki = type("Y", (), {"energy": {"10001": 5.0}, "consume_energy": lambda self, cid: None})()
    pipeline.sticker_manager = None

    await pipeline.send_reply({
        "chat_id": "10001", "mode": "group",
        "answer_text": "[layout]等主人上钩～[/layout]正文【MEME:偷笑】", "voice": None,
    })
    joined = "".join(sent)
    assert "等主人上钩" not in joined and "正文" in joined

    history_file = tmp_path / "chat_history.json"
    log_file = tmp_path / "yuki_log.txt"
    history_file.write_text(
        '{"10001":[{"role":"system","content":"sys"},'
        '{"role":"assistant","content":"[layout]计划[/layout]正文【MEME:委屈】"},'
        '{"role":"user","content":"【MEME:原文】不要动"}]}',
        encoding="utf-8",
    )
    manager = HistoryManager(history_file=str(history_file), log_file=str(log_file))
    assert manager.repair_reply_markup() == 1

    reloaded = manager.read_from_disk()
    assert reloaded["10001"][1]["content"] == "<layout>计划</layout>正文[MEME:委屈]"
    assert reloaded["10001"][2]["content"] == "【MEME:原文】不要动"

    manager.append_session_message("10001", "assistant", "[layout]新盘算[/layout]回复【MEME:坏笑】")
    session = manager.get_session("10001")
    assert session[-1]["content"] == "<layout>新盘算</layout>回复[MEME:坏笑]"


# ==================== EngineReplyService 收尾与工具链端到端 ====================

def test_finalize_answer_rules():
    """finalize_answer 区分是否执行过工具：执行过工具但仅剩 layout 时返回 WORKING_NOTICE，未执行工具则保持空。"""
    assert EngineReplyService.finalize_answer("[layout]只有盘算[/layout]", False) == ("<layout>只有盘算</layout>", "")
    assert EngineReplyService.finalize_answer("[layout]只有盘算[/layout]", True) == (
        "<layout>只有盘算</layout>", WORKING_NOTICE
    )
    assert EngineReplyService.finalize_answer("", False)[1] == ""
    for used_tools in (False, True):
        assert EngineReplyService.finalize_answer("[layout]盘算[/layout]正文【MEME:坏笑】", used_tools) == (
            "<layout>盘算</layout>正文[MEME:坏笑]", "正文[MEME:坏笑]"
        )


async def test_chat_with_tools_text_call_and_working_notice():
    """chat_with_tools 能还原执行正文里的 DSML 调用，且工具执行后若最终回复仅剩 layout 则返回 WORKING_NOTICE。"""
    class _ToolManager:
        max_rounds = 3
        def start_session(self, *a, **k): pass
        def finish_session(self, *a, **k): pass

    captured = {}

    class _CallManager:
        def __init__(self, *a, **k):
            self.max_rounds = 3

        async def execute_tool_calls(self, tool_calls, context, finish_reason=""):
            captured["tool_calls"] = tool_calls
            return [
                {"role": "tool", "tool_call_id": c["id"], "name": c["function"]["name"], "content": '{"success": true}'}
                for c in tool_calls
            ]

        def finish_session(self, *a, **k): pass

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
        {"role": "assistant", "content": "[layout]后续盘算[/layout]"},
    ]

    async def fake_raw(**kwargs):
        return responses.pop(0)

    with patch("core.engine.engine_reply.llm_chat_raw", fake_raw), \
            patch("core.engine.engine_reply.ToolCallManager", _CallManager):
        raw, visible = await service.chat_with_tools("10001", "hi", [], "group", [])

    assert captured["tool_calls"][0]["function"]["name"] == "poke"
    assert sender.sent == ["我戳你一下喵"]
    assert raw == "<layout>后续盘算</layout>"
    assert visible == WORKING_NOTICE
