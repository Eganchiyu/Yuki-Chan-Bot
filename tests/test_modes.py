import asyncio

from core.modes import ModeManager
from modules.memory.rag import MemoryRAG


def test_mode_manager_has_no_focus_mode_registered():
    """Live2D 桌宠与浏览器交互聚焦模式已归档，当前不应还能进入任何聚焦模式。"""
    async def run():
        manager = ModeManager()
        ok, state, reason = await manager.enter_mode(
            "browser_interaction",
            origin_chat_id="10001",
            origin_mode="group",
            goal="归档后不应可进入",
        )
        assert ok is False
        assert state is None
        assert reason == "mode_is_not_focus_mode"
        assert manager.is_focus_active() is False
        assert manager.get_spec("browser_interaction").mode_id == "group"

    asyncio.run(run())


def test_rag_relative_boosts_do_not_dominate_semantic_score():
    local_item = MemoryRAG._calculate_final_item(
        "Alice 和 Yuki 在本群聊讨论浏览器模式",
        {"chat_id": "10001"},
        0.2,
        [],
        chat_id="10001",
        speaker_names=["Alice"],
    )
    other_item = MemoryRAG._calculate_final_item(
        "另一个群聊也讨论浏览器模式",
        {"chat_id": "20002"},
        0.9,
        [],
        chat_id="10001",
        speaker_names=["Alice"],
    )

    # 同群/发言者只按语义分比例提升，不能反超语义高相关其他群回忆
    assert other_item["score"] > local_item["score"]
    assert local_item["score"] < 0.2 * 1.25
    assert local_item["relevance"] == 0.2
    assert other_item["relevance"] == 0.9
