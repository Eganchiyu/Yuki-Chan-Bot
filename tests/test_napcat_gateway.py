"""NapCatGateway 的传输契约测试。

用本地假 OneBot 服务器验证三条契约：
1. 没有消费者迭代 listen() 时，call() 依然能拿到响应（旧实现必然超时）
2. API 响应永不混进事件流
3. 对端断开后自动重连，API 恢复可用
"""
import asyncio
import json

import pytest
import websockets

from network.napcat import NapCatGateway


async def _fake_napcat(ws):
    """连上就推一条心跳事件，之后按动作返回可预期的假数据。"""
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


async def test_api_call_works_without_event_consumer(napcat_url):
    gateway = NapCatGateway(napcat_url, "")
    try:
        resp = await gateway.call("get_login_info", {}, timeout=3)
        assert resp is not None, "无人消费 listen() 时 call() 不应超时"
        assert resp["status"] == "ok"
    finally:
        await gateway.close()


async def test_responses_never_leak_into_event_stream(napcat_url):
    gateway = NapCatGateway(napcat_url, "")
    try:
        await gateway.call("get_login_info", {}, timeout=3)
        event = await asyncio.wait_for(gateway.listen().__anext__(), timeout=5)
        assert event["post_type"] == "meta_event"
        assert "echo" not in event
    finally:
        await gateway.close()


async def test_gateway_reconnects_after_disconnect(napcat_url):
    gateway = NapCatGateway(napcat_url, "")
    try:
        await gateway.call("close_me", {}, timeout=1)   # 服务端主动断开
        await asyncio.sleep(4)                          # 等待 RECONNECT_DELAY 后的重连
        resp = await gateway.call("get_login_info", {}, timeout=3)
        assert resp is not None and resp["status"] == "ok"
        assert gateway.stats["reconnects"] >= 1
    finally:
        await gateway.close()


async def test_parse_cq_codes_replaces_at_reply_and_media(napcat_url):
    """原 modules/message 的三个文件合并到这里后，行为必须保持一致。"""
    gateway = NapCatGateway(napcat_url, "")
    try:
        text = "[CQ:reply,id=7] [CQ:at,qq=123] 你好 [CQ:image,file=a.jpg]"
        out = await gateway.parse_cq_codes(text, "1057020972")
        assert "【引用小明的消息: 被引用的内容】" in out
        assert "@群名片" in out                       # 群名片优先于昵称
        assert "[图片]" in out
        assert "[CQ:" not in out
    finally:
        await gateway.close()


async def test_get_group_meta_and_member_name(napcat_url):
    gateway = NapCatGateway(napcat_url, "")
    try:
        meta = await gateway.get_group_meta("1057020972")
        assert meta["group_name"] == "测试群"

        assert await gateway.get_member_name("1057020972", "123") == "群名片"
        assert await gateway.get_member_name("1057020972", "all") == "全体成员"
        # 成员信息走缓存，第二次不再发请求
        calls_before = gateway.stats["calls"]
        await gateway.get_member_name("1057020972", "123")
        assert gateway.stats["calls"] == calls_before
    finally:
        await gateway.close()
