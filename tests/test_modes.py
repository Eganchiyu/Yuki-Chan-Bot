import asyncio
from types import SimpleNamespace

from core.modes import ModeManager
from core.toolchain import ToolContext, ToolRuntime, ToolRegistryProvider
from core.tools import TOOL_SPECS, enter_browser_interaction_tool
from modules.browser_interaction import BROWSER_TOOL_SPECS
from modules.browser_interaction.tools import browser_complete_tool, browser_scan_placeholder_tool
from modules.memory.rag import MemoryRAG


def test_browser_interaction_tool_thought_does_not_use_qq_sender(monkeypatch):
    async def run():
        from core.engine.engine_reply import EngineReplyService

        broadcasts = []

        async def fake_broadcast(message):
            broadcasts.append(message)

        class Sender:
            async def send(self, chat_id, message, mode="private"):
                raise AssertionError("browser_interaction 不应使用 QQ sender 发送阶段性文本")

        import modules.LiveYukiL2D.server as live2d_server
        monkeypatch.setattr(live2d_server, "broadcast", fake_broadcast)

        service = EngineReplyService(
            yuki=SimpleNamespace(),
            history=SimpleNamespace(),
            sender=Sender(),
            tool_registry=SimpleNamespace(get_registry=lambda mode=None: SimpleNamespace(get_tools=lambda: [])),
            tool_manager=SimpleNamespace(max_rounds=1),
            get_process_callback=lambda: None,
            get_image_store=lambda: None,
        )
        sent = await service.send_tool_thought(
            "mode:browser",
            "browser_interaction",
            "我先看一下页面",
            set(),
            tool_names=["browser_scan_placeholder"],
        )

        assert sent == "我先看一下页面"
        assert broadcasts == [{"type": "say", "text": "我先看一下页面"}]

    asyncio.run(run())


class FakeHistoryManager:
    def __init__(self):
        self.sessions = {}
        self.appended = []

    def get_session(self, chat_id, system_content=None):
        session = self.sessions.setdefault(str(chat_id), [])
        if system_content and not session:
            session.append({"role": "system", "content": system_content})
        return list(session)

    def append_session_message(self, chat_id, role, content, **extra):
        item = {"role": role, "content": content, **extra}
        self.appended.append((str(chat_id), item))
        self.sessions.setdefault(str(chat_id), []).append(item)
        return list(self.sessions[str(chat_id)])


class FakeSender:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, message, mode="private"):
        self.sent.append((str(chat_id), message, mode))


def build_context(callback=None):
    yuki = SimpleNamespace(
        mode_manager=ModeManager(),
        get_setting=lambda mode: f"system:{mode}",
        maid_current_tasks={},
        maid_task_queue=asyncio.Queue(),
    )
    history = FakeHistoryManager()
    sender = FakeSender()
    runtime = ToolRuntime(sender=sender, yuki_state=yuki)
    return ToolContext(
        chat_id="10001",
        mode="group",
        session=[],
        combined_text="帮我看一下浏览器",
        runtime=runtime,
        metadata={"history_manager": history, "process_callback": callback},
    )


def test_mode_manager_allows_single_focus_mode():
    async def run():
        manager = ModeManager()
        ok, state, reason = await manager.enter_mode(
            "browser_interaction",
            origin_chat_id="10001",
            origin_mode="group",
            goal="测试浏览器模式",
        )
        assert ok is True
        assert state.session_id == "mode:browser"
        assert manager.is_focus_active() is True

        ok2, state2, reason2 = await manager.enter_mode(
            "browser_interaction",
            origin_chat_id="10002",
            origin_mode="group",
            goal="重复进入",
        )
        assert ok2 is False
        assert reason2 == "focus_mode_busy"
        assert state2.origin_chat_id == "10001"

    asyncio.run(run())


def test_enter_browser_interaction_creates_mode_session_and_callback():
    async def run():
        calls = []

        async def callback(chat_id, mode, **kwargs):
            calls.append((chat_id, mode, kwargs))

        context = build_context(callback=callback)
        result = await enter_browser_interaction_tool(context, goal="观察网页")
        await asyncio.sleep(0.05)

        assert result.success is True
        assert context.yuki.mode_manager.is_focus_active() is True
        assert result.data["session_id"] == "mode:browser"
        assert calls[0][0] == "mode:browser"
        assert calls[0][1] == "browser_interaction"
        assert context.metadata["history_manager"].sessions["mode:browser"][0]["role"] == "system"

    asyncio.run(run())


def test_browser_placeholder_tools_complete_and_return_to_origin():
    async def run():
        context = build_context()
        await context.yuki.mode_manager.enter_mode(
            "browser_interaction",
            origin_chat_id="10001",
            origin_mode="group",
            goal="验证返回",
        )
        context.chat_id = "mode:browser"
        context.mode = "browser_interaction"

        scan_result = await browser_scan_placeholder_tool(context)
        assert scan_result.success is True
        assert scan_result.data["origin_chat_id"] == "10001"

        complete_result = await browser_complete_tool(context, summary="占位验证完成")
        assert complete_result.success is True
        assert context.yuki.mode_manager.is_focus_active() is False
        assert context.sender.sent == [("10001", "【浏览器模式完成】占位验证完成", "group")]

    asyncio.run(run())


def test_tool_registry_provider_uses_browser_tool_group_only_in_browser_mode():
    provider = ToolRegistryProvider(
        TOOL_SPECS,
        mode_specs={"browser_interaction": BROWSER_TOOL_SPECS},
    )
    default_tools = provider.list_functions("group")
    browser_tools = provider.list_functions("browser_interaction")

    assert "enter_browser_interaction" in default_tools
    assert "browser_scan_placeholder" not in default_tools
    assert "browser_scan_placeholder" in browser_tools
    assert "enter_browser_interaction" not in browser_tools


def test_rag_current_chat_and_speaker_boosts_are_applied():
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

    assert local_item["score"] > other_item["score"]
    assert "当前群聊:10.00" in local_item["debug"]
    assert "发言者:0.15" in local_item["debug"]
