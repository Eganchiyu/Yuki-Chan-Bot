"""日记过滤：轮数统计与总结输入都只算聊天，不含工具调用与工具输出。"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import cfg
from core.engine.engine_diary import EngineDiaryService
from core.history_filter import dialogue_length, dialogue_messages, is_dialogue_message


def _mix_session():
    return [
        {"role": "system", "content": "人设"},
        {"role": "user", "content": "帮我看看手机"},
        {"role": "assistant", "content": "好~人家看看"},
        {"role": "tool", "name": "phone_action", "tool_call_id": "c1",
         "content": json.dumps({"success": True, "content": "[#1] [可点] 外卖 @(540,435)"})},
        {"role": "tool", "name": "bash", "tool_call_id": "c2",
         "content": json.dumps({"success": True, "content": "total 0\ndrwxr-xr-x ..."})},
        {"role": "assistant", "content": "找到外卖啦，要点哪家？"},
        {"role": "user", "content": "第一家"},
        {"role": "assistant", "content": "点好了！"},
    ]


# ---------- 过滤器 ----------

def test_is_dialogue_message_excludes_tool_and_system():
    assert is_dialogue_message({"role": "user"})
    assert is_dialogue_message({"role": "assistant"})
    assert not is_dialogue_message({"role": "tool"})
    assert not is_dialogue_message({"role": "system"})
    assert not is_dialogue_message("不是字典")


def test_dialogue_length_ignores_tools():
    session = _mix_session()
    assert len(session) == 8
    assert dialogue_length(session) == 5
    assert all(m["role"] in ("user", "assistant") for m in dialogue_messages(session))


def test_dialogue_length_handles_empty():
    assert dialogue_length([]) == 0
    assert dialogue_length(None) == 0


# ---------- 总结输入 ----------

async def test_do_summarize_feeds_only_chat_to_model(monkeypatch):
    captured = {}

    async def fake_llm_chat(messages, **kwargs):
        captured["messages"] = messages
        return "今天主人让人家看手机，点了外卖~"

    monkeypatch.setattr("core.engine.engine_diary.llm_chat", fake_llm_chat)

    rag = MagicMock()
    diary = EngineDiaryService(rag, MagicMock())
    result = await diary.do_summarize("12345", _mix_session())

    payload = captured["messages"][-1]["content"]
    # 工具输出与工具消息不进总结输入
    assert "phone_action" not in payload
    assert "tool_call_id" not in payload
    assert "drwxr-xr-x" not in payload
    assert "[#1]" not in payload
    # 聊天内容要完整保留
    assert "帮我看看手机" in payload and "点好了！" in payload

    rag.save_diary.assert_called_once()
    diary_text = rag.save_diary.call_args[0][0]
    assert "【日记(" in diary_text and "点了外卖" in diary_text

    # 回写历史：system 前缀保留，其余只留最近 KEEP_LAST_DIALOGUE 条聊天
    roles = [msg["role"] for msg in result]
    assert roles[0] == "system"
    assert "tool" not in roles
    assert len(result) == 1 + min(cfg.KEEP_LAST_DIALOGUE, 5)


async def test_do_summarize_failure_keeps_history(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("模型挂了")

    monkeypatch.setattr("core.engine.engine_diary.llm_chat", boom)
    original = _mix_session()
    diary = EngineDiaryService(MagicMock(), MagicMock())
    assert await diary.do_summarize("12345", original) == original


# ---------- 触发阈值 ----------

async def test_pipeline_forces_diary_by_chat_count_only(monkeypatch):
    """历史里塞满工具消息也不该提前触发日记。"""
    from tests.test_pipeline import _create_mock_pipeline

    pipeline = _create_mock_pipeline()
    session = [{"role": "system", "content": "人设"}]
    session.append({"role": "user", "content": "开始"})
    session.append({"role": "assistant", "content": "嗯"})
    # 塞入超过阈值的工具消息
    for i in range(cfg.DIARY_MAX_LENGTH + 10):
        session.append({"role": "tool", "name": "bash", "tool_call_id": f"c{i}",
                        "content": "一堆输出"})
    pipeline.history_manager.append_session_message.return_value = session

    created = []
    monkeypatch.setattr("asyncio.create_task", lambda coro: created.append(coro) or coro.close())

    context = {
        "chat_id": "12345",
        "answer_text": "回复",
        "answer_raw": "回复",
        "current_time_str": "2026-11-05 22:00",
    }
    await pipeline.finalize_conversation(context)
    assert created == []  # 聊天只有 2 条，不该写日记


async def test_pipeline_forces_diary_when_chat_exceeds_threshold(monkeypatch):
    from tests.test_pipeline import _create_mock_pipeline

    pipeline = _create_mock_pipeline()
    session = [{"role": "system", "content": "人设"}]
    for i in range(cfg.DIARY_MAX_LENGTH + 2):
        session.append({"role": "user" if i % 2 else "assistant", "content": f"聊天{i}"})
    pipeline.history_manager.append_session_message.return_value = session

    created = []
    monkeypatch.setattr("asyncio.create_task", lambda coro: created.append(coro) or coro.close())

    context = {
        "chat_id": "12345",
        "answer_text": "回复",
        "answer_raw": "回复",
        "current_time_str": "2026-11-05 22:00",
    }
    await pipeline.finalize_conversation(context)
    assert len(created) == 1
