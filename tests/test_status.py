# tests/test_status.py
"""/查询 状态简报与 /强制关闭 指令的离线测试。"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import cfg
from core import status as status_mod
from modules.QQNapcatListen import listen_main


MASTER_QQ = cfg.MASTER_QQS[0] if cfg.MASTER_QQS else 1
GROUP_ID = "1057020972"


class FakeYuki:
    def __init__(self):
        self.energy = {GROUP_ID: 63.4}
        self.group_activity = {GROUP_ID: 1.2}
        self.desire_to_start_topic = {GROUP_ID: 71.5}
        self.last_message_time = {GROUP_ID: time.time() - 754}
        self.maid_task_queue = None
        self.maid_current_tasks = {}
        self.message_buffer = {GROUP_ID: [{"content": "hi"}]}
        self.buffer_tasks = {}


def _pipeline():
    yuki = FakeYuki()
    pipeline = MagicMock()
    pipeline.yuki = yuki
    pipeline.group_active_state = {GROUP_ID: True}
    return pipeline


def _gateway():
    gateway = MagicMock()
    gateway.send = AsyncMock()
    return gateway


@pytest.fixture(autouse=True)
def _clean_state():
    status_mod.reset_force_close_state()
    status_mod.reset_mode_providers()
    yield
    status_mod.reset_force_close_state()
    status_mod.reset_mode_providers()


# ---------------- 状态简报 ----------------

def test_member_view_hides_model_and_route():
    text = status_mod.build_status_text(FakeYuki(), GROUP_ID, is_master=False)
    assert "模式" in text and "精力" in text and "静默" in text
    assert cfg.LLM_MODEL not in text
    assert "主线" not in text and "备用线路" not in text


def test_master_view_shows_route_model_and_maid():
    text = status_mod.build_status_text(FakeYuki(), GROUP_ID, is_master=True)
    assert cfg.LLM_MODEL in text
    assert "主线" in text
    assert "小女仆" in text
    assert "欲" in text and "活跃" in text


def test_dormant_group_reports_dormant_mode():
    text = status_mod.build_status_text(FakeYuki(), GROUP_ID, group_active=False)
    assert "模式 休眠" in text


def test_short_output_single_line():
    """关键词式简报：不允许出现换行，长度受控。"""
    text = status_mod.build_status_text(FakeYuki(), GROUP_ID, is_master=True)
    assert "\n" not in text
    assert len(text) < 160


def test_mode_provider_override():
    status_mod.register_mode_provider(lambda cid: "辩论中 · 第12轮" if cid == GROUP_ID else None)
    text = status_mod.build_status_text(FakeYuki(), GROUP_ID)
    assert "辩论中 · 第12轮" in text


# ---------------- 指令正则 ----------------

@pytest.mark.parametrize("text", ["/查询", " /状态 ", "/status", "/STATUS"])
def test_status_regex_matches(text):
    assert status_mod.match_status_command(text)


@pytest.mark.parametrize("text", ["/查询 模式", "/查", "查询", "/关闭", ""])
def test_status_regex_rejects(text):
    assert not status_mod.match_status_command(text)


@pytest.mark.parametrize("text", ["/强制关闭", "/强制关", "/强制关闭 确认", "/强制关闭确认"])
def test_force_close_regex_matches(text):
    assert status_mod.match_force_close_command(text)


@pytest.mark.parametrize("text", ["/关闭", "/强制", "/强制开启"])
def test_force_close_regex_rejects(text):
    assert not status_mod.match_force_close_command(text)


# ---------------- 指令处理 ----------------

async def test_status_command_sends_one_line():
    pipeline, gateway = _pipeline(), _gateway()
    handled = listen_main.handle_status_command(
        gateway, pipeline, GROUP_ID, GROUP_ID, MASTER_QQ, "/查询"
    )
    assert handled is True
    await __import__("asyncio").sleep(0)
    gateway.send.assert_awaited_once()
    text = gateway.send.await_args.args[1]
    assert "模式" in text and "\n" not in text


async def test_non_command_not_handled():
    pipeline, gateway = _pipeline(), _gateway()
    assert listen_main.handle_status_command(gateway, pipeline, GROUP_ID, GROUP_ID, MASTER_QQ, "查询一下") is False
    assert listen_main.handle_force_close_command(gateway, pipeline, GROUP_ID, GROUP_ID, "/关闭") is False


async def test_force_close_needs_two_sends():
    pipeline, gateway = _pipeline(), _gateway()
    import asyncio

    # 第一次：只提示确认，群状态不变
    assert listen_main.handle_force_close_command(gateway, pipeline, GROUP_ID, GROUP_ID, "/强制关闭") is True
    await asyncio.sleep(0)
    assert pipeline.group_active_state[GROUP_ID] is True
    assert "再发一次" in gateway.send.await_args.args[1]
    assert pipeline.group_active_state is not None

    # 第二次：真正休眠，并清空缓冲
    assert listen_main.handle_force_close_command(gateway, pipeline, GROUP_ID, GROUP_ID, "/强制关闭") is True
    await asyncio.sleep(0)
    assert pipeline.group_active_state[GROUP_ID] is False
    assert pipeline.yuki.message_buffer[GROUP_ID] == []
    assert status_mod.is_force_close_confirmed(GROUP_ID) is False


async def test_force_close_confirmation_expires():
    status_mod.mark_force_close_pending(GROUP_ID, now=time.time() - status_mod.FORCE_CLOSE_CONFIRM_SECONDS - 1)
    assert status_mod.is_force_close_confirmed(GROUP_ID) is False


async def test_force_close_anyone_can_use():
    """非主人也能触发（这是设计选择），但同样要两次。"""
    pipeline, gateway = _pipeline(), _gateway()
    import asyncio

    listen_main.handle_force_close_command(gateway, pipeline, GROUP_ID, GROUP_ID, "/强制关闭")
    await asyncio.sleep(0)
    listen_main.handle_force_close_command(gateway, pipeline, GROUP_ID, GROUP_ID, "/强制关闭")
    await asyncio.sleep(0)
    assert pipeline.group_active_state[GROUP_ID] is False
