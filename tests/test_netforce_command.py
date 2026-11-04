"""QQ 指令测试：/刷新（手动刷新网络）在群聊与私聊都只在原会话回话。

真实探活由宿主看门狗完成，这里只替换「投递请求 + 等待结果」这一对函数，
校验指令拦截、master 鉴权与回复路由。
"""
import asyncio

import pytest

from config import cfg

from modules.QQNapcatListen import listen_main


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
    """把宿主往返替换成固定结果，并记录投递。"""
    state = {"requests": 0, "result": {"ok": True, "probes": {
        "direct": {"ok": True, "detail": "ok"},
        "proxy": {"ok": True, "detail": "ok"},
    }, "actions": []}}

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


async def test_group_refresh_replies_to_same_group(fake_refresh):
    gateway = _FakeGateway()
    handled = listen_main.handle_group_switch(
        None, gateway, 1057020972, "1057020972", _master_qq(), "/刷新"
    )
    await _drain()

    assert handled is True
    assert fake_refresh["requests"] == 1
    assert [m["chat_id"] for m in gateway.sent] == [1057020972, 1057020972]
    assert all(m["mode"] == "group" for m in gateway.sent)
    assert gateway.sent[-1]["text"].startswith("测试已连通")


async def test_private_refresh_replies_to_same_private_chat(fake_refresh):
    gateway = _FakeGateway()
    handled = listen_main.handle_private_command(gateway, _master_qq(), "/刷新")
    await _drain()

    assert handled is True
    assert [m["chat_id"] for m in gateway.sent] == [_master_qq(), _master_qq()]
    assert all(m["mode"] == "private" for m in gateway.sent)
    assert gateway.sent[-1]["text"].startswith("测试已连通")


async def test_refresh_rejected_for_non_master(fake_refresh):
    gateway = _FakeGateway()
    handled = listen_main.handle_private_command(gateway, 999999, "/刷新")
    await _drain()

    assert handled is True
    assert fake_refresh["requests"] == 0
    assert len(gateway.sent) == 1
    assert "只有哥哥大人" in gateway.sent[0]["text"]


def test_refresh_failure_reports_reason(fake_refresh):
    text = listen_main._format_netforce_reply({
        "ok": False,
        "actions": ["重载 mihomo 配置"],
        "probes": {"direct": {"ok": False}, "proxy": {"ok": True}},
    })
    assert "没连通" in text and "direct 不通" in text and "重载 mihomo 配置" in text


def test_plain_message_not_intercepted(fake_refresh):
    gateway = _FakeGateway()
    assert listen_main.handle_private_command(gateway, _master_qq(), "在吗") is False
    assert listen_main.handle_group_switch(
        None, gateway, 1057020972, "1057020972", _master_qq(), "在吗"
    ) is False
