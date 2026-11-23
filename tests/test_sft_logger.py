"""SFT 全量训练轨迹落盘（Phase 1）单元测试。"""
import asyncio
import datetime
import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.engine import YukiEngine
from core.session_pipeline import SessionPipeline
from core.sft_logger import SFTTraceLogger, classify_emoji_label, strip_media_and_sanitize
from core.toolchain import SKIP_REPLY_MARKER


def test_negative_feedback_emojis_are_bad():
    assert classify_emoji_label("❔") == "bad"
    assert classify_emoji_label("10068") == "bad"
    assert classify_emoji_label("💦") == "bad"
    assert classify_emoji_label("128166") == "bad"


def test_strip_media_and_sanitize_redacts_secrets_and_base64():
    payload = [
        {"role": "system", "content": "key=sk-secret1234567890abcdef"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看图 Bearer tok_abcdef123456"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "A" * 1024}},
            ],
        },
    ]
    cleaned = strip_media_and_sanitize(payload)
    assert "<REDACTED>" in cleaned[0]["content"]
    assert "sk-secret" not in cleaned[0]["content"]
    assert "tok_abcdef" not in cleaned[1]["content"][0]["text"]
    assert cleaned[1]["content"][1]["image_url"]["url"] == "<image_omitted>"


def test_archive_images_writes_metadata(tmp_path):
    from modules.vision.image_store import ImageStore

    store = ImageStore(str(tmp_path / "source"))
    idx = store.register(b"image-bytes", ext=".png")
    attachment = store.attachment(idx)
    logger = SFTTraceLogger(base_dir=str(tmp_path / "sft"))
    assets = logger.archive_images("turn-image", [attachment], store)

    assert len(assets) == 1
    asset = assets[0]
    assert asset["path"].startswith("images/turn-image/")
    assert asset["bytes"] == 11
    assert len(asset["sha256"]) == 64
    assert asset["mime"] == "image/png"
    assert (tmp_path / "sft" / asset["path"]).read_bytes() == b"image-bytes"


def test_sft_logger_writes_monthly_jsonl_and_handles_errors(tmp_path):
    sft = SFTTraceLogger(base_dir=str(tmp_path))
    dt = datetime.datetime(2026, 11, 16, 21, 30, 0)
    record = sft.record_turn({
        "turn_id": "snap-001",
        "chat_id": "1057020972",
        "mode": "group",
        "model": "gemini-3.1-flash-lite",
        "outcome": "reply",
        "senders": ["池宇健"],
        "combined_text": '【"池宇健"】说: 晚安',
        "relevant_diaries": [{"content": "昨天聊得很开心", "score": 0.91}],
        "input_messages": [{"role": "system", "content": "人设"}, {"role": "user", "content": "晚安"}],
        "turn_messages": [],
        "tools_used": ["poke"],
        "tool_trace": [{"round": 1, "calls": [{"name": "poke", "args": "{}"}]}],
        "answer_raw": "<layout>先轻轻戳一下哥哥。</layout>晚安喵～[MEME:晚安]",
        "answer_text": "晚安喵～[MEME:晚安]",
        "sent_message_ids": [1001, 1002],
    }, now=dt)

    assert record is not None
    expected_file = tmp_path / "traces_2026-11.jsonl"
    assert expected_file.exists()
    lines = expected_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["turn_id"] == "snap-001"
    assert parsed["answer_raw"].startswith("<layout>先轻轻戳一下哥哥。</layout>")
    assert parsed["sent_message_ids"] == ["1001", "1002"]
    assert parsed["relevant_diaries"][0]["score"] == 0.91

    # 写入失败不应抛异常阻断主流程
    bad_file = tmp_path / "not_a_dir"
    bad_file.write_text("x", encoding="utf-8")
    bad_sft = SFTTraceLogger(base_dir=str(bad_file))
    assert bad_sft.record_turn({"chat_id": "1"}, now=dt) is None


async def test_engine_and_pipeline_capture_full_sft_block_with_layout_and_tools(tmp_path, monkeypatch):
    import core.engine.engine_reply as engine_reply_mod

    rag = MagicMock()
    history = MagicMock()
    history.get_session.return_value = [{"role": "system", "content": "测试人设"}]
    history.append_session_message = MagicMock(return_value=[{"role": "system", "content": "测试人设"}])
    history.append_to_log = MagicMock()

    yuki = MagicMock()
    yuki.lock = asyncio.Lock()
    yuki.mode_manager = None
    yuki.energy = {"1057020972": 80.0}
    yuki.group_activity = {"1057020972": 1.0}
    yuki.ice_break_fail_count = {}
    yuki.last_sent_meme = {}
    yuki.message_buffer = defaultdict(list)
    yuki.user_mapping = SimpleNamespace(resolve=lambda cid, name: 123456, tick=lambda cid: None)
    yuki.get_setting = MagicMock(return_value="测试人设")
    yuki.consume_energy = MagicMock()

    sender = AsyncMock()
    sender.send = AsyncMock(return_value="9001")
    sender.send_poke = AsyncMock(return_value={"status": "ok"})

    engine = YukiEngine(rag, history, yuki, sender)

    # 模拟第 1 轮调用 poke 工具，第 2 轮返回带 <layout> 的最终回复
    llm_responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_poke_1",
                "type": "function",
                "function": {"name": "poke", "arguments": '{"target": "池宇健"}'},
            }],
        },
        {
            "role": "assistant",
            "content": "<layout>戳完再撒个娇。</layout>才没有偷懒呢喵～[MEME:害羞]",
        },
    ]
    monkeypatch.setattr(engine_reply_mod, "llm_chat_raw", AsyncMock(side_effect=llm_responses))

    sft = SFTTraceLogger(base_dir=str(tmp_path))
    pipeline = SessionPipeline({
        "sender": sender,
        "meme_processor": MagicMock(),
        "yuki": yuki,
        "history_manager": history,
        "memory_rag": rag,
        "engine": engine,
        "sft_logger": sft,
    }, {"1057020972": True})

    context = {
        "chat_id": "1057020972",
        "mode": "group",
        "combined_text": '【"池宇健"】说: yuki 在干嘛',
        "session": [{"role": "system", "content": "测试人设"}],
        "relevant_diaries": [{"content": "之前哥哥总熬夜", "score": 0.88, "debug": "semantic=0.88"}],
        "message_objs": [{"name": "池宇健", "user_id": 123456}],
        "ice_break": False,
        "current_time_str": "2026年11月16日21:30",
        "debug_snapshot_id": "turn-xyz",
    }

    context = await pipeline.generate_reply(context)
    assert context["answer_raw"] == "<layout>戳完再撒个娇。</layout>才没有偷懒呢喵～[MEME:害羞]"
    assert context["answer_text"] == "才没有偷懒呢喵～[MEME:害羞]"

    context["sent_message_ids"] = ["55501"]
    await pipeline.finalize_conversation(context)

    files = list(tmp_path.glob("traces_*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert row["turn_id"] == "turn-xyz"
    assert row["outcome"] == "reply"
    assert row["tools_used"] == ["poke"]
    assert row["answer_raw"].startswith("<layout>戳完再撒个娇。</layout>")
    assert row["answer_text"] == "才没有偷懒呢喵～[MEME:害羞]"
    assert row["sent_message_ids"] == ["55501"]
    assert len(row["input_messages"]) >= 2
    assert any(m.get("role") == "tool" and m.get("name") == "poke" for m in row["turn_messages"])


async def test_pipeline_records_skip_turn_in_sft_logger(tmp_path):
    sft = SFTTraceLogger(base_dir=str(tmp_path))
    components = {
        "sender": AsyncMock(),
        "meme_processor": MagicMock(),
        "yuki": MagicMock(),
        "history_manager": MagicMock(),
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
        "sft_logger": sft,
    }
    components["history_manager"].get_session.return_value = [{"role": "system", "content": "系统"}]
    components["engine"].api_reply = AsyncMock(return_value=(SKIP_REPLY_MARKER, SKIP_REPLY_MARKER, ""))
    components["engine"].pop_sft_capture = MagicMock(return_value={
        "input_messages": [{"role": "system", "content": "系统"}, {"role": "user", "content": "别人的聊天"}],
        "turn_messages": [{"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "skip"}}]}],
        "tools_used": ["skip"],
        "tool_trace": [{"round": 1, "calls": [{"name": "skip", "args": "{}"}]}],
        "outcome": "skip",
        "llm_rounds": 1,
    })

    pipeline = SessionPipeline(components, {})
    ctx = await pipeline.generate_reply({
        "chat_id": "1057020972",
        "mode": "group",
        "combined_text": '【"路人"】说: 自言自语',
        "session": [{"role": "system", "content": "系统"}],
        "relevant_diaries": [],
        "message_objs": [{"name": "路人", "user_id": 999}],
        "debug_snapshot_id": "skip-001",
    })
    assert ctx["skip_reply"] is True

    files = list(tmp_path.glob("traces_*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert row["turn_id"] == "skip-001"
    assert row["outcome"] == "skip"
    assert row["tools_used"] == ["skip"]
    assert row["answer_raw"] == ""


async def test_send_reply_indexes_message_ids_and_emoji_like_labels(tmp_path, monkeypatch):
    from config import cfg
    from modules.QQNapcatListen.listen_main import handle_emoji_like_event, handle_sft_quote_label

    sft_writer = SFTTraceLogger(base_dir=str(tmp_path))
    sticker_mgr = MagicMock()
    sticker_mgr.get_suitable_sticker = AsyncMock(return_value={
        "id": "st-1",
        "image_ref": "data/stickers/happy.png",
    })

    sender = AsyncMock()
    sender.send = AsyncMock(side_effect=[70001, 70002])

    yuki = MagicMock()
    yuki.lock = asyncio.Lock()
    yuki.energy = {"1057020972": 90.0}
    yuki.last_sent_meme = {}
    yuki.ice_break_fail_count = {}
    yuki.user_mapping = SimpleNamespace(tick=lambda cid: None)
    yuki.consume_energy = MagicMock()

    history = MagicMock()
    history.append_to_log = MagicMock()
    history.append_session_message = MagicMock(return_value=[{"role": "system", "content": "人设"}])

    pipeline = SessionPipeline({
        "sender": sender,
        "meme_processor": MagicMock(),
        "yuki": yuki,
        "history_manager": history,
        "memory_rag": MagicMock(),
        "engine": MagicMock(),
        "sticker_manager": sticker_mgr,
        "sft_logger": sft_writer,
    }, {"1057020972": True})

    ctx = {
        "chat_id": "1057020972",
        "mode": "group",
        "combined_text": '【"池宇健"】说: 摸摸头',
        "answer_raw": "<layout>哥哥摸头了好开心。</layout>嘿嘿～[MEME:开心]",
        "answer_text": "嘿嘿～[MEME:开心]",
        "current_time_str": "2026年11月16日21:40",
        "debug_snapshot_id": "turn-react-01",
        "sft_capture": {
            "input_messages": [{"role": "user", "content": "摸摸头"}],
            "turn_messages": [],
            "tools_used": [],
            "tool_trace": [],
            "outcome": "reply",
            "llm_rounds": 1,
        },
    }
    monkeypatch.setattr("core.outbound_sender._TEXT_SENT_SLEEP", 0)
    monkeypatch.setattr("core.outbound_sender._MEME_SENT_SLEEP", 0)

    await pipeline.send_reply(ctx)
    assert ctx["sent_message_ids"] == ["70001", "70002"]
    await pipeline.finalize_conversation(ctx)

    # 模拟重启后的新 SFTTraceLogger 实例，验证能从 msg_index.jsonl 反查 turn_id
    sft_reloaded = SFTTraceLogger(base_dir=str(tmp_path))
    pipeline_reloaded = SimpleNamespace(sft_logger=sft_reloaded)
    monkeypatch.setattr(cfg, "is_master_qq", lambda uid: str(uid) == "10001")

    # 1) 非主人贴表情：忽略
    assert handle_emoji_like_event(pipeline_reloaded, {
        "post_type": "notice",
        "notice_type": "group_msg_emoji_like",
        "group_id": 1057020972,
        "user_id": 99999,
        "message_id": 70002,
        "likes": [{"emoji_id": "76", "count": 1}],
        "is_add": True,
    }) == []

    # 2) 主人贴点赞表情 (76) -> perfect；点踩 (77) -> bad；取消 -> removed
    res_pos = handle_emoji_like_event(pipeline_reloaded, {
        "post_type": "notice",
        "notice_type": "group_msg_emoji_like",
        "group_id": 1057020972,
        "user_id": 10001,
        "message_id": 70002,
        "likes": [{"emoji_id": "76", "count": 1}],
        "is_add": True,
    })
    assert len(res_pos) == 1
    assert res_pos[0]["turn_id"] == "turn-react-01"
    assert res_pos[0]["label"] == "perfect"

    res_neg = handle_emoji_like_event(pipeline_reloaded, {
        "post_type": "notice",
        "notice_type": "group_msg_emoji_like",
        "group_id": 1057020972,
        "user_id": 10001,
        "message_id": 70001,
        "likes": [{"emoji_id": "77", "count": 1}],
        "is_add": True,
    })
    assert len(res_neg) == 1 and res_neg[0]["label"] == "bad"

    res_rm = handle_emoji_like_event(pipeline_reloaded, {
        "post_type": "notice",
        "notice_type": "group_msg_emoji_like",
        "group_id": 1057020972,
        "user_id": 10001,
        "message_id": 70002,
        "likes": [{"emoji_id": "76", "count": 1}],
        "is_add": False,
    })
    assert len(res_rm) == 1 and res_rm[0]["label"] == "removed"

    # 3) 未跟踪的别人消息 ID：忽略
    assert handle_emoji_like_event(pipeline_reloaded, {
        "post_type": "notice",
        "notice_type": "group_msg_emoji_like",
        "group_id": 1057020972,
        "user_id": 10001,
        "message_id": 888888,
        "likes": [{"emoji_id": "76", "count": 1}],
        "is_add": True,
    }) == []

    # 4) 私聊/群聊引用指令兜底 /good
    assert handle_sft_quote_label(
        pipeline_reloaded, 10001, 10001, "[CQ:reply,id=70001] /good",
        segments=[{"type": "reply", "data": {"id": "70001"}}],
    ) is True
    assert handle_sft_quote_label(
        pipeline_reloaded, 10001, 10001, "[CQ:reply,id=70001] 正常聊天",
        segments=[{"type": "reply", "data": {"id": "70001"}}],
    ) is False

    labels_lines = (tmp_path / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(labels_lines) == 4
