"""入站策略测试：被叫到（名字 / @）跳过防抖，戳一戳只认戳 Yuki。

listen_main 现在只依赖 (gateway, pipeline)，所以这里用两个轻量替身即可，
无需真实连接、也无需改模块全局。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from config import cfg

from modules.QQNapcatListen import listen_main
from network.napcat import mentions_self


def _make_pipeline():
    """记录入队参数的最小替身。"""
    enqueued = []

    async def enqueue_message(chat_id, mode, message_obj=None, **kwargs):
        enqueued.append({"chat_id": chat_id, "mode": mode, "obj": message_obj, **kwargs})

    pipeline = MagicMock()
    pipeline.yuki.last_sent_meme = {}
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.last_message_time = {}
    pipeline.history_manager = MagicMock()
    pipeline.enqueue_message = AsyncMock(side_effect=enqueue_message)
    return pipeline, enqueued


def _at_segment(qq):
    return {"type": "at", "data": {"qq": str(qq)}}


# ==================== mentions_self ====================

def test_mentions_self_from_segments():
    assert mentions_self([_at_segment(cfg.SELF_QQ)], "", cfg.SELF_QQ)
    assert not mentions_self([_at_segment("all")], "", cfg.SELF_QQ)
    assert not mentions_self([_at_segment(123456)], "", cfg.SELF_QQ)
    assert not mentions_self([{"type": "text", "data": {"text": "hi"}}], "hi", cfg.SELF_QQ)


def test_mentions_self_falls_back_to_raw_text():
    """segments 缺失时看 raw_text，且要容忍带附加参数的 CQ 码。"""
    assert mentions_self(None, f"[CQ:at,qq={cfg.SELF_QQ}] 在吗", cfg.SELF_QQ)
    assert mentions_self(None, f"[CQ:at,qq={cfg.SELF_QQ},name=Yuki] 在吗", cfg.SELF_QQ)
    assert not mentions_self(None, "[CQ:at,qq=all] 大家好", cfg.SELF_QQ)
    assert not mentions_self(None, f"[CQ:at,qq=9{cfg.SELF_QQ}] 在吗", cfg.SELF_QQ)


# ==================== feed_message 的快速唤醒 ====================

async def _feed(pipeline, content, raw_text=None, segments=None):
    await listen_main.feed_message(
        pipeline,
        AsyncMock(),
        "10000",
        content,
        "group",
        raw_message=raw_text if raw_text is not None else content,
        message_obj={
            "name": "路人",
            "content": content,
            "raw_text": raw_text if raw_text is not None else content,
            "user_id": 123456,
            "segments": list(segments or []),
            "tags": {"group"},
        },
    )


async def test_called_by_name_skips_debounce():
    pipeline, enqueued = _make_pipeline()
    await _feed(pipeline, f"{cfg.ROBOT_NAME} 在吗")
    assert enqueued[-1]["debounce_flag"] is False
    assert enqueued[-1]["force_reply"] is True


async def test_called_by_at_self_skips_debounce():
    pipeline, enqueued = _make_pipeline()
    await _feed(pipeline, "[CQ:at,qq=%d] 在吗" % cfg.SELF_QQ, segments=[_at_segment(cfg.SELF_QQ)])
    assert enqueued[-1]["debounce_flag"] is False
    assert enqueued[-1]["force_reply"] is True


async def test_at_all_or_others_does_not_skip_debounce():
    pipeline, enqueued = _make_pipeline()
    await _feed(pipeline, "[CQ:at,qq=all] 大家好", segments=[_at_segment("all")])
    assert enqueued[-1]["debounce_flag"] is True
    assert enqueued[-1]["force_reply"] is None

    await _feed(pipeline, "[CQ:at,qq=999999] 你好", segments=[_at_segment(999999)])
    assert enqueued[-1]["debounce_flag"] is True
    assert enqueued[-1]["force_reply"] is None


async def test_plain_message_keeps_debounce():
    pipeline, enqueued = _make_pipeline()
    await _feed(pipeline, "今天天气不错")
    assert enqueued[-1]["debounce_flag"] is True
    assert enqueued[-1]["force_reply"] is None


# ==================== 戳一戳过滤 ====================

def _poke_pipeline():
    pipeline, enqueued = _make_pipeline()
    pipeline.group_active_state = {}
    return pipeline, enqueued


async def test_poke_enqueues_only_when_target_is_self():
    group_id = cfg.TARGET_GROUPS[0] if cfg.TARGET_GROUPS else 10000
    gateway = AsyncMock()
    gateway.get_member_info = AsyncMock(return_value={"card": "小明"})

    pipeline, enqueued = _poke_pipeline()
    await listen_main.handle_poke_event(
        gateway, pipeline,
        {"group_id": group_id, "user_id": 123456, "target_id": cfg.SELF_QQ},
        "mixed",
    )
    assert len(enqueued) == 1, "戳 Yuki 应入队"
    assert enqueued[0]["obj"].source == "napcat.notice.poke"
    # 按普通消息入队：不插队、不强制回复
    assert enqueued[0].get("force_reply") is None
    assert "debounce_flag" not in enqueued[0] or enqueued[0]["debounce_flag"] is True

    pipeline, enqueued = _poke_pipeline()
    await listen_main.handle_poke_event(
        gateway, pipeline,
        {"group_id": group_id, "user_id": 123456, "target_id": 999999},
        "mixed",
    )
    assert not enqueued, "戳别人不应入队"

    pipeline, enqueued = _poke_pipeline()
    await listen_main.handle_poke_event(
        gateway, pipeline,
        {"group_id": group_id, "user_id": cfg.SELF_QQ, "target_id": cfg.SELF_QQ},
        "mixed",
    )
    assert not enqueued, "机器人自己发出的戳不应回灌"
