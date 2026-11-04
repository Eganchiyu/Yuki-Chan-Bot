# core/engine.py

from core.engine.engine_decision import EngineDecisionService
from core.engine.engine_diary import EngineDiaryService
from core.engine.engine_monitor import EngineMonitorService
from core.engine.engine_reply import EngineReplyService
from core.toolchain import FunctionRegistry, ToolCallManager
from core.tools import TOOL_SPECS
from modules.stickers.manager import StickerManager
from modules.vision.image_store import ImageStore
from modules.vision.processor import MemeProcessor


class YukiEngine:
    """Yuki 核心引擎门面，负责装配子服务并保持外部调用兼容。"""

    def __init__(self, rag, history_manager, yuki_state, sender):
        self.rag = rag
        self.history = history_manager
        self.yuki = yuki_state
        self.sender = sender
        self.process_callback = None
        self.sticker_manager: StickerManager | None = None
        self.image_store: ImageStore | None = None
        self.meme_processor: MemeProcessor | None = None
        self.tool_registry = FunctionRegistry()
        self.tool_registry.scan_and_register(TOOL_SPECS)
        self.tool_manager = ToolCallManager(self.tool_registry)
        self.napcat_online = True

        self.diary_service = EngineDiaryService(self.rag, self.history)
        self.reply_service = EngineReplyService(
            self.yuki,
            self.history,
            self.sender,
            self.tool_registry,
            self.tool_manager,
            get_process_callback=lambda: self.process_callback,
            get_image_store=lambda: getattr(self, "image_store", None),
            get_meme_processor=lambda: getattr(self, "meme_processor", None),
        )
        self.decision_service = EngineDecisionService(self.yuki)
        self.monitor_service = EngineMonitorService(
            self.yuki,
            self.history,
            self.diary_service,
            get_napcat_online=lambda: getattr(self, "napcat_online", True),
            get_process_callback=lambda: self.process_callback,
        )

    async def api_reply(self, *args, **kwargs):
        """生成回复，保留原 YukiEngine 调用入口。"""
        return await self.reply_service.api_reply(*args, **kwargs)

    async def decide_to_reply(self, *args, **kwargs):
        """判断群聊是否回复，保留原 YukiEngine 调用入口。"""
        return await self.decision_service.decide_to_reply(*args, **kwargs)

    async def do_summarize(self, *args, **kwargs):
        """总结会话，保留原 YukiEngine 调用入口。"""
        if hasattr(self, "diary_service"):
            return await self.diary_service.do_summarize(*args, **kwargs)
        return await EngineDiaryService(self.rag, self.history).do_summarize(*args, **kwargs)

    async def idle_diary_checker(self):
        """启动空闲日记后台检查，保留原 YukiEngine 调用入口。"""
        return await self.monitor_service.idle_diary_checker()

    async def ice_break_monitor(self):
        """启动破冰后台检查，保留原 YukiEngine 调用入口。"""
        return await self.monitor_service.ice_break_monitor()
