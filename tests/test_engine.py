import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_summarize_idle_session_replaces_only_target_session():
    async def run():
        from core.engine import YukiEngine

        engine = YukiEngine.__new__(YukiEngine)
        engine.history = MagicMock()
        engine.history.replace_session = MagicMock()
        engine.history.save = MagicMock()
        engine.do_summarize = AsyncMock(return_value=[
            {"role": "system", "content": "系统"},
        ])

        source_session = [
            {"role": "system", "content": "系统"},
            {"role": "user", "content": "旧消息"},
        ]
        await engine._summarize_idle_session("12345", source_session)

        engine.do_summarize.assert_awaited_once_with(12345, source_session)
        engine.history.replace_session.assert_called_once_with(
            "12345",
            [{"role": "system", "content": "系统"}],
        )
        engine.history.save.assert_not_called()

    asyncio.run(run())
