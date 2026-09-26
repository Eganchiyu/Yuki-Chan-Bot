# tests/test_reply_format.py
"""回复标记格式容错回归测试。

覆盖模型把 `<layout>`/`[MEME:]` 括号写错时的三重防护：
1. 发送前清洗（布局不外泄、表情包仍能检索）；
2. 写入 history 前归一化（避免错误示例被模型学走）；
3. 启动预载时批量修复历史里的既有错格式。
"""
import asyncio
import os
import shutil
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.history_manager import HistoryManager
from core.reply_format import (
    clean_visible_reply,
    normalize_layout_tags,
    normalize_meme_tags,
    normalize_reply_markup,
    strip_layout_markup,
    strip_meme_tags,
)


# ==================== 归一化单元测试 ====================

def test_layout_variants_normalize_to_angle_brackets():
    """方括号、全角尖括号等 layout 变体统一为规范标签。"""
    cases = [
        ("[layout]盘算[/layout]", "<layout>盘算</layout>"),
        ("[layout]盘算</layout>", "<layout>盘算</layout>"),
        ("【layout】盘算【/layout】", "<layout>盘算</layout>"),
        ("［LAYOUT］盘算［/LAYOUT］", "<layout>盘算</layout>"),
        ("<layout>盘算</layout>", "<layout>盘算</layout>"),
    ]
    for raw, expected in cases:
        assert normalize_layout_tags(raw) == expected, raw


def test_strip_layout_markup_removes_mismatched_bracket_pairs():
    """混用括号的布局块整体剥离，不把盘算当正文。"""
    assert strip_layout_markup("[layout]等lito反驳～</layout>正文") == "正文"
    assert strip_layout_markup("[layout]先扎一刀[/layout]正文") == "正文"
    assert strip_layout_markup("<layout>正常盘算</layout>正文") == "正文"


def test_strip_layout_markup_drops_unclosed_layout():
    """未闭合的开标签按内部思考处理，宁可少发也不外泄。"""
    assert strip_layout_markup("[layout]没闭合的盘算，后面全是计划") == ""
    assert strip_layout_markup("<layout>同样藏住") == ""


def test_meme_variants_normalize_and_bare_tag_dropped():
    """表情包标记括号/大小写归一化，空标记丢弃。"""
    assert normalize_meme_tags("【MEME:委屈】语法") == "[MEME:委屈]语法"
    assert normalize_meme_tags("[meme:得意]小写") == "[MEME:得意]小写"
    assert normalize_meme_tags("［MEME：好奇］全角") == "[MEME:好奇]全角"
    assert normalize_meme_tags("[MEME]【MEME:】") == ""


def test_strip_meme_tags_removes_all_variants():
    assert strip_meme_tags("正文【MEME:哼】尾巴[MEME:戳一戳]") == "正文尾巴"


def test_clean_visible_reply_keeps_canonical_meme_for_sending():
    """发送前清洗保留规范 MEME（后续还要按它检索表情包），但剥离布局。"""
    raw = "[layout]先埋个雷～</layout>正文【MEME:偷笑】"
    assert clean_visible_reply(raw) == "正文[MEME:偷笑]"


def test_normalize_reply_markup_keeps_layout_but_fixes_brackets():
    """写回历史：保留规范 layout（模型记忆需要），只修括号。"""
    raw = "[layout]盘算[/layout]正文【MEME:坏笑】"
    assert normalize_reply_markup(raw) == "<layout>盘算</layout>正文[MEME:坏笑]"


def test_plain_text_untouched():
    raw = "没有任何标记的普通文本[MEME:得意]"
    assert clean_visible_reply(raw) == raw
    assert normalize_reply_markup(raw) == raw


# ==================== 发送阶段测试 ====================

def test_send_reply_strips_malformed_layout_before_sending():
    """send_reply 必须拦住写错括号的 layout，不能把它当正文发出去。"""
    from core.session_pipeline import SessionPipeline

    pipeline = SessionPipeline.__new__(SessionPipeline)
    sent = []

    class Sender:
        async def send(self, chat_id, message, mode="private"):
            sent.append(message)

    class Yuki:
        energy = {"10001": 5.0}

        def consume_energy(self, chat_id):
            return None

    pipeline.sender = Sender()
    pipeline.yuki = Yuki()
    pipeline.sticker_manager = None

    context = {
        "chat_id": "10001",
        "mode": "group",
        "answer_text": "[layout]等主人上钩～[/layout]正文【MEME:偷笑】",
        "voice": None,
    }
    asyncio.run(pipeline.send_reply(context))

    joined = "".join(sent)
    assert "等主人上钩" not in joined, "布局内容不得外泄"
    assert "正文" in joined


# ==================== 历史写回测试 ====================

def test_history_manager_normalizes_markup_on_append():
    """追加消息时归一化 assistant 回复，不污染历史。"""
    tmp_dir = "data/_test_reply_format_append"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    manager = HistoryManager(
        history_file=os.path.join(tmp_dir, "chat_history.json"),
        log_file=os.path.join(tmp_dir, "yuki_log.txt"),
    )
    try:
        manager.append_session_message(
            "10001", "assistant", "[layout]盘算[/layout]正文【MEME:坏笑】"
        )
        session = manager.get_session("10001")
        stored = [m for m in session if m["role"] == "assistant"][0]["content"]
        assert stored == "<layout>盘算</layout>正文[MEME:坏笑]"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_history_manager_repairs_existing_messages_on_preload():
    """预载历史时批量修复已落盘的错格式，并写回磁盘。"""
    tmp_dir = "data/_test_reply_format_repair"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    history_file = os.path.join(tmp_dir, "chat_history.json")
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            f.write(
                '{"10001":[{"role":"system","content":"sys"},'
                '{"role":"assistant","content":"[layout]计划[/layout]正文【MEME:委屈】"},'
                '{"role":"user","content":"【MEME:原文】不要动"}]}'
            )

        manager = HistoryManager(
            history_file=history_file,
            log_file=os.path.join(tmp_dir, "yuki_log.txt"),
        )
        fixed = manager.repair_reply_markup()
        assert fixed == 1, "只应修复 assistant 消息"

        data = manager.load()
        assistant_msg = data["10001"][1]["content"]
        assert assistant_msg == "<layout>计划</layout>正文[MEME:委屈]"
        # 用户原文不属于生成标记，保持原样
        assert data["10001"][2]["content"] == "【MEME:原文】不要动"

        # 已写回磁盘，重启后不会回退
        with open(history_file, "r", encoding="utf-8") as f:
            reloaded = manager.read_from_disk()
        assert reloaded["10001"][1]["content"] == "<layout>计划</layout>正文[MEME:委屈]"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==================== 工具链回复归一化测试 ====================

def test_engine_normalizes_raw_answer_for_history():
    """chat_with_tools 返回的原始回复（写历史）应已归一化。"""
    from unittest.mock import patch

    from core.engine.engine_reply import EngineReplyService

    class _ToolManager:
        max_rounds = 1

        def start_session(self, *args, **kwargs):
            return None

        def finish_session(self, *args, **kwargs):
            return None

    service = EngineReplyService(
        yuki=None,
        history=None,
        sender=None,
        tool_registry=type("R", (), {"get_tools": lambda self: []})(),
        tool_manager=_ToolManager(),
        get_process_callback=lambda: None,
        get_image_store=lambda: None,
    )

    async def fake_raw(**kwargs):
        return {"role": "assistant", "content": "[layout]盘算[/layout]正文【MEME:坏笑】"}

    with patch("core.engine.engine_reply.llm_chat_raw", fake_raw):
        raw, visible = asyncio.run(
            service.chat_with_tools("10001", "hi", [], "group", [])
        )

    assert raw == "<layout>盘算</layout>正文[MEME:坏笑]"
    assert visible == "正文[MEME:坏笑]"
