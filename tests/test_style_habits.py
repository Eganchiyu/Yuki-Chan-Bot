# tests/test_style_habits.py
"""群聊情境表达习惯（StyleHabit）存储、抽取与选择单元测试。"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from modules.memory.style_learner import extract_styles_from_dialogue
from modules.memory.style_selector import format_style_habits_hint, select_style_habits
from modules.memory.style_store import StyleStore


def test_style_store_records_and_increments(tmp_path):
    store = StyleStore(str(tmp_path / "style.db"))
    first = store.record_habits(
        "10001",
        [("对某件事表示十分惊叹", "使用 我嘞个xxxx"), ("表示敷衍赞同", "使用 对对对")],
    )
    assert len(first) == 2
    assert first[0].count == 1

    second = store.record_habits("10001", [("对某件事表示十分惊叹", "使用 我嘞个xxxx")])
    assert second[0].count == 2
    active = store.get_active_habits("10001")
    assert active[0].situation == "对某件事表示十分惊叹"
    assert active[0].count == 2


def test_style_selector_matches_context_and_respects_cooldown(tmp_path):
    store = StyleStore(str(tmp_path / "style.db"))
    store.record_habits(
        "10001",
        [
            ("游戏操作非常厉害惊叹", "使用 这么强！"),
            ("表示加班痛苦难受", "使用 真是坐牢啊"),
            ("早上打招呼", "使用 早安喵"),
        ],
    )

    picked = select_style_habits(
        "10001",
        "刚才那把游戏操作真的太厉害了",
        store=store,
        limit=2,
        cooldown_seconds=180.0,
        now=1000.0,
    )
    assert len(picked) == 2
    assert picked[0].situation == "游戏操作非常厉害惊叹"
    first_ids = {h.id for h in picked}

    # 冷却期内再次选择，刚用过的两条被跳过，只剩未冷却的第 3 条
    picked_again = select_style_habits(
        "10001",
        "游戏操作厉害",
        store=store,
        limit=2,
        cooldown_seconds=180.0,
        now=1060.0,
    )
    assert len(picked_again) == 1
    assert picked_again[0].id not in first_ids

    hint = format_style_habits_hint(picked)
    assert "本群常用表达参考" in hint
    assert "这么强" in hint


def test_extract_styles_from_dialogue_ignores_short_and_assistant(tmp_path):
    store = StyleStore(str(tmp_path / "style.db"))
    dialogue = [
        {"role": "user", "content": "群友A: 我嘞个豆这也太强了"},
        {"role": "assistant", "content": "确实厉害呀"},
        {"role": "user", "content": "群友B: 对对对，真的离谱"},
        {"role": "user", "content": "群友C: 我嘞个豆，羡慕哭了"},
        {"role": "user", "content": "群友D: 狠狠支持了"},
    ]
    mock_resp = json.dumps(
        [{"situation": "对某事表示惊叹", "style": "使用 我嘞个豆"}],
        ensure_ascii=False,
    )
    with patch("modules.memory.style_learner._call_style_llm", new_callable=AsyncMock, return_value=mock_resp):
        saved = asyncio.run(extract_styles_from_dialogue("20002", dialogue, store=store))
    assert len(saved) == 1
    assert saved[0].style == "使用 我嘞个豆"
