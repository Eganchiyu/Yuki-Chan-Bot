# 原位于 core/engine/engine.py 的旧私有兼容包装方法（第 77-99 行）与未使用的 self.maid 属性
from core.engine.engine_diary import EngineDiaryService
from core.engine.engine_reply import EngineReplyService


class YukiEngineLegacyCompatMixin:
    """YukiEngine 拆分出 EngineReplyService / EngineDiaryService 时保留的旧私有方法兼容层。"""

    @staticmethod
    def _clean_visible_reply(content):
        """兼容旧私有入口。"""
        return EngineReplyService.clean_visible_reply(content)

    async def _merge_pending_messages(self, chat_id, tool_messages):
        """兼容旧私有入口。"""
        return await self.reply_service.merge_pending_messages(chat_id, tool_messages)

    async def _send_tool_thought(self, *args, **kwargs):
        """兼容旧私有入口。"""
        return await self.reply_service.send_tool_thought(*args, **kwargs)

    async def _chat_with_tools(self, *args, **kwargs):
        """兼容旧私有入口。"""
        return await self.reply_service.chat_with_tools(*args, **kwargs)

    async def _summarize_idle_session(self, chat_id, session):
        """兼容旧私有入口。"""
        if hasattr(self, "diary_service"):
            return await self.diary_service.summarize_idle_session(chat_id, session)
        new_session = await self.do_summarize(int(chat_id), session)
        self.history.replace_session(chat_id, new_session)
