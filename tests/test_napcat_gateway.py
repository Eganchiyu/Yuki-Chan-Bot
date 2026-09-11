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
    """连上就推一条心跳事件，之后把收到的动作原样确认回去。"""
    await ws.send(json.dumps({
        "post_type": "meta_event", "meta_event_type": "heartbeat",
        "status": {"online": True}, "time": 1, "self_id": 10000,
    }))
    async for raw in ws:
        frame = json.loads(raw)
        if frame.get("action") == "close_me":
            await ws.close()
            return
        await ws.send(json.dumps({
            "status": "ok", "retcode": 0, "echo": frame.get("echo"),
            "data": {"action": frame.get("action")},
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
