"""NapCat 网关传输契约、入站唤醒策略与 QQ 指令测试。"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

from config import cfg
from modules.QQNapcatListen import listen_main
from network.napcat import NapCatGateway, mentions_self


# ==================== 本地假 OneBot WebSocket 服务 ====================

async def _fake_napcat(ws):
    await ws.send(json.dumps({
        "post_type": "meta_event", "meta_event_type": "heartbeat",
        "status": {"online": True}, "time": 1, "self_id": 10000,
    }))
    async for raw in ws:
        frame = json.loads(raw)
        action = frame.get("action")
        if action == "close_me":
            await ws.close()
            return
        if action == "get_msg":
            data = {"sender": {"nickname": "小明"}, "raw_message": "被引用的内容"}
        elif action == "get_group_member_info":
            data = {"card": "群名片", "nickname": "昵称"}
        elif action in ("get_group_detail_info", "get_group_info"):
            data = {"group_name": "测试群", "group_remark": "备注"}
        else:
            data = {"action": action}
        await ws.send(json.dumps({
            "status": "ok", "retcode": 0, "echo": frame.get("echo"), "data": data,
        }))


@pytest.fixture
async def napcat_url():
    async with websockets.serve(_fake_napcat, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


# ==================== NapCatGateway 传输契约与 CQ 解析 ====================

async def test_gateway_call_and_event_isolation(napcat_url):
    """无消费者时 call() 仍能拿到响应，且 API 响应绝不混入 listen() 事件流。"""
    gateway = NapCatGateway(napcat_url, "")
    try:
        resp = await gateway.call("get_login_info", {}, timeout=3)
        assert resp is not None and resp["status"] == "ok"

        event = await asyncio.wait_for(gateway.listen().__anext__(), timeout=5)
        assert event["post_type"] == "meta_event" and "echo" not in event
    finally:
        await gateway.close()


async def test_gateway_reconnects_after_disconnect(napcat_url, monkeypatch):
    """对端断开后自动重连，API 恢复可用。"""
    import network.napcat as napcat_mod
    monkeypatch.setattr(napcat_mod, "RECONNECT_DELAY", 0.1)

    gateway = NapCatGateway(napcat_url, "")
    try:
        await gateway.call("close_me", {}, timeout=1)
        await asyncio.sleep(0.3)
        resp = await gateway.call("get_login_info", {}, timeout=3)
        assert resp is not None and resp["status"] == "ok"
        assert gateway.stats["reconnects"] >= 1
    finally:
        await gateway.close()


async def test_gateway_cq_parsing_and_member_cache(napcat_url):
    """CQ 码解析（引用、@群名片、图片）以及群信息/成员名缓存复用。"""
    gateway = NapCatGateway(napcat_url, "")
    try:
        text = "[CQ:reply,id=7] [CQ:at,qq=123] 你好 [CQ:image,file=a.jpg]"
        out = await gateway.parse_cq_codes(text, "1057020972")
        assert "【引用小明的消息: 被引用的内容】" in out
        assert "@群名片" in out
        assert "[图片]" in out and "[CQ:" not in out

        meta = await gateway.get_group_meta("1057020972")
        assert meta["group_name"] == "测试群"
        assert await gateway.get_member_name("1057020972", "123") == "群名片"
        assert await gateway.get_member_name("1057020972", "all") == "全体成员"

        calls_before = gateway.stats["calls"]
        await gateway.get_member_name("1057020972", "123")
        assert gateway.stats["calls"] == calls_before
    finally:
        await gateway.close()


# ==================== 入站策略：@检测、快速唤醒、BOT过滤、戳一戳 ====================

def _make_pipeline():
    enqueued = []

    async def enqueue_message(chat_id, mode, message_obj=None, **kwargs):
        enqueued.append({"chat_id": chat_id, "mode": mode, "obj": message_obj, **kwargs})

    pipeline = MagicMock()
    pipeline.yuki.last_sent_meme = {}
    pipeline.yuki.ice_break_fail_count = {}
    pipeline.yuki.last_message_time = {}
    pipeline.group_active_state = {}
    pipeline.history_manager = MagicMock()
    pipeline.enqueue_message = AsyncMock(side_effect=enqueue_message)
    return pipeline, enqueued


def _at_seg(qq):
    return {"type": "at", "data": {"qq": str(qq)}}


def test_mentions_self_detection():
    """mentions_self 优先读 segments，缺失时回退 raw_text 并容忍带附加参数的 CQ 码。"""
    assert mentions_self([_at_seg(cfg.SELF_QQ)], "", cfg.SELF_QQ)
    assert not mentions_self([_at_seg("all")], "", cfg.SELF_QQ)
    assert not mentions_self([_at_seg(123456)], "", cfg.SELF_QQ)
    assert mentions_self(None, f"[CQ:at,qq={cfg.SELF_QQ},name=Yuki] 在吗", cfg.SELF_QQ)
    assert not mentions_self(None, "[CQ:at,qq=all] 大家好", cfg.SELF_QQ)
    assert not mentions_self(None, f"[CQ:at,qq=9{cfg.SELF_QQ}] 在吗", cfg.SELF_QQ)


async def test_inbound_debounce_and_wake_policy():
    """叫名字或 @自己跳过防抖并强制回复；@全体/@他人与普通消息保持防抖。"""
    pipeline, enqueued = _make_pipeline()

    async def feed(content, segments=None):
        await listen_main.feed_message(
            pipeline, AsyncMock(), "10000", content, "group",
            raw_message=content,
            message_obj={
                "name": "路人", "content": content, "raw_text": content,
                "user_id": 123456, "segments": list(segments or []), "tags": {"group"},
            },
        )

    await feed(f"{cfg.ROBOT_NAME} 在吗")
    assert enqueued[-1]["debounce_flag"] is False and enqueued[-1]["force_reply"] is True

    await feed(f"[CQ:at,qq={cfg.SELF_QQ}] 在吗", segments=[_at_seg(cfg.SELF_QQ)])
    assert enqueued[-1]["debounce_flag"] is False and enqueued[-1]["force_reply"] is True

    await feed("[CQ:at,qq=all] 大家好", segments=[_at_seg("all")])
    assert enqueued[-1]["debounce_flag"] is True and enqueued[-1]["force_reply"] is None

    await feed("今天天气不错")
    assert enqueued[-1]["debounce_flag"] is True and enqueued[-1]["force_reply"] is None


async def test_feed_message_filters_bot_unless_whitelisted(monkeypatch):
    """非白名单 BOT 拦截，白名单 BOT 允许入队并标记 is_bot=True。"""
    monkeypatch.setattr(listen_main.cfg.target, "whitelist", [1390249127])
    monkeypatch.setattr(listen_main.cfg, "max_message_length", 500)
    pipeline, enqueued = _make_pipeline()
    gateway = AsyncMock()

    await listen_main.feed_message(
        pipeline, gateway, "10000", "普通机器人消息", "group",
        raw_message="普通机器人消息", sender_name="测试BOT", user_id=123456,
    )
    assert not enqueued

    await listen_main.feed_message(
        pipeline, gateway, "10000", "白名单机器人消息", "group",
        raw_message="白名单机器人消息", sender_name="测试BOT", user_id=1390249127,
    )
    assert len(enqueued) == 1 and enqueued[0]["obj"].is_bot is True


async def test_poke_enqueues_only_when_target_is_self():
    """戳一戳事件仅在目标是 Yuki 且发起人不是自己时入队。"""
    group_id = cfg.TARGET_GROUPS[0] if cfg.TARGET_GROUPS else 10000
    gateway = AsyncMock()
    gateway.get_member_info = AsyncMock(return_value={"card": "小明"})
    pipeline, enqueued = _make_pipeline()

    await listen_main.handle_poke_event(
        gateway, pipeline, {"group_id": group_id, "user_id": 123456, "target_id": cfg.SELF_QQ}, "mixed"
    )
    assert len(enqueued) == 1 and enqueued[0]["obj"].source == "napcat.notice.poke"

    await listen_main.handle_poke_event(
        gateway, pipeline, {"group_id": group_id, "user_id": 123456, "target_id": 999999}, "mixed"
    )
    await listen_main.handle_poke_event(
        gateway, pipeline, {"group_id": group_id, "user_id": cfg.SELF_QQ, "target_id": cfg.SELF_QQ}, "mixed"
    )
    assert len(enqueued) == 1


# ==================== /刷新 手动网络探活指令 ====================

class _FakeGateway:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text, mode="group", **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "mode": mode})


def _master_qq():
    masters = getattr(cfg, "MASTER_QQS", None) or []
    return masters[0] if masters else cfg.MASTER_QQ


@pytest.fixture
def fake_refresh(monkeypatch):
    state = {
        "requests": 0,
        "result": {
            "ok": True,
            "probes": {"direct": {"ok": True, "detail": "ok"}, "proxy": {"ok": True, "detail": "ok"}},
            "actions": [],
        },
    }

    def _write():
        state["requests"] += 1
        return "req-1"

    async def _wait(req_id, timeout=0):
        return state["result"]

    monkeypatch.setattr(listen_main, "_write_netforce_request", _write)
    monkeypatch.setattr(listen_main, "_wait_netforce_result", _wait)
    return state


async def _drain():
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def test_netforce_command_routing_and_auth(fake_refresh):
    """/刷新 在群聊与私聊均回原会话，非 master 拒绝，普通消息不拦截，失败原因可读。"""
    master = _master_qq()

    # 群聊原群回复
    gw_group = _FakeGateway()
    assert listen_main.handle_group_switch(None, gw_group, 1057020972, "1057020972", master, "/刷新") is True
    await _drain()
    assert fake_refresh["requests"] == 1
    assert [m["chat_id"] for m in gw_group.sent] == [1057020972, 1057020972]
    assert all(m["mode"] == "group" for m in gw_group.sent)
    assert gw_group.sent[-1]["text"].startswith("测试已连通")

    # 私聊原会话回复
    gw_priv = _FakeGateway()
    assert listen_main.handle_private_command(gw_priv, master, "/刷新") is True
    await _drain()
    assert [m["chat_id"] for m in gw_priv.sent] == [master, master]
    assert all(m["mode"] == "private" for m in gw_priv.sent)

    # 非 master 拒绝
    gw_unauth = _FakeGateway()
    assert listen_main.handle_private_command(gw_unauth, 999999, "/刷新") is True
    await _drain()
    assert fake_refresh["requests"] == 2
    assert "只有哥哥大人" in gw_unauth.sent[0]["text"]

    # 普通消息不拦截
    assert listen_main.handle_private_command(gw_priv, master, "在吗") is False
    assert listen_main.handle_group_switch(None, gw_group, 1057020972, "1057020972", master, "在吗") is False

    # 失败原因格式化
    fail_text = listen_main._format_netforce_reply({
        "ok": False,
        "actions": ["重载 mihomo 配置"],
        "probes": {"direct": {"ok": False}, "proxy": {"ok": True}},
    })
    assert "没连通" in fail_text and "direct 不通" in fail_text and "重载 mihomo 配置" in fail_text


# ==================== /切换 主备模型线路对调指令 ====================

async def test_switch_command_swaps_route_and_auth(monkeypatch):
    """/切换 在主备线路间对调（模型/地址/Key），群聊私聊都回原会话，非 master 拒绝。"""
    api, model = cfg.api, cfg.model
    monkeypatch.setattr(api, "llm_base_url", "http://main/v1")
    monkeypatch.setattr(api, "backup_base_url", "http://backup/v1")
    monkeypatch.setattr(api, "llm_api_key", "key-main")
    monkeypatch.setattr(api, "backup_api_key", "key-backup")
    monkeypatch.setattr(model, "llm", "model-main")
    monkeypatch.setattr(model, "backup", "model-backup")
    monkeypatch.setattr(model, "llm_native_vision_enabled", True)
    monkeypatch.setattr(model, "backup_native_vision_enabled", False)

    master = _master_qq()
    gw = _FakeGateway()

    assert listen_main.handle_group_switch(None, gw, 1057020972, "1057020972", master, "/切换") is True
    await _drain()
    assert cfg.LLM_BASE_URL == "http://backup/v1" and cfg.BACKUP_BASE_URL == "http://main/v1"
    assert cfg.LLM_API_KEY == "key-backup" and cfg.BACKUP_API_KEY == "key-main"
    assert cfg.LLM_MODEL == "model-backup" and cfg.BACKUP_MODEL == "model-main"
    assert cfg.LLM_NATIVE_VISION_ENABLED is False and cfg.BACKUP_NATIVE_VISION_ENABLED is True
    assert [m["chat_id"] for m in gw.sent] == [1057020972]
    assert "备用模型" in gw.sent[0]["text"] and "model-backup" in gw.sent[0]["text"]

    # 私聊再切一次：回到主模型
    gw_priv = _FakeGateway()
    assert listen_main.handle_private_command(gw_priv, master, "/切换") is True
    await _drain()
    assert cfg.LLM_MODEL == "model-main" and cfg.BACKUP_MODEL == "model-backup"
    assert cfg.LLM_BASE_URL == "http://main/v1" and cfg.LLM_API_KEY == "key-main"
    assert "主模型" in gw_priv.sent[0]["text"] and gw_priv.sent[0]["mode"] == "private"

    # 非 master 拒绝且不改线路
    gw_unauth = _FakeGateway()
    assert listen_main.handle_private_command(gw_unauth, 999999, "/切换") is True
    await _drain()
    assert cfg.LLM_MODEL == "model-main"
    assert "只有哥哥大人" in gw_unauth.sent[0]["text"]
