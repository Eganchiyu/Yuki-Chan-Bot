# tests/test_vision_prefetch.py
"""入站图片预取回归：消息一到即后台下载理解，主路径复用结果、不重复下载。"""
import asyncio
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import cfg
from modules.vision.prefetch import prefetch_images, resolve_image


class _FakeProcessor:
    """记录下载/理解调用次数，替代真实 MemeProcessor。"""

    def __init__(self, native=False):
        self.image_store = object() if native else None
        self._prefetch = {}
        self.register_calls = 0
        self.understand_calls = 0

    async def register_from_url(self, url):
        self.register_calls += 1
        return {"index": "001", "attachment": {"index": "001", "id": "x"}, "native": True}

    async def understand_from_url(self, url, is_meme=False):
        self.understand_calls += 1
        return {"description": f"描述:{url}", "index": None}


def _images(*specs):
    return [{"url": url, "is_meme": is_meme} for url, is_meme in specs]


async def test_prefetch_result_is_reused_without_second_download():
    """预取完成后，主路径取用结果，不应再次下载。"""
    processor = _FakeProcessor()
    original = cfg.model.image_prefetch_enabled
    cfg.model.image_prefetch_enabled = True
    try:
        scheduled = prefetch_images(processor, _images(("http://img/a", False)))
        assert scheduled == 1, "首次应调度一个预取任务"

        await asyncio.sleep(0)  # 让预取任务跑完
        result = await resolve_image(processor, "http://img/a", False)

        assert result["description"] == "描述:http://img/a"
        assert processor.understand_calls == 1, "下载/理解应只发生一次"
    finally:
        cfg.model.image_prefetch_enabled = original


async def test_same_url_in_batch_scheduled_once():
    """同一批次里重复出现的同一 URL 只调度一次。"""
    processor = _FakeProcessor()
    original = cfg.model.image_prefetch_enabled
    cfg.model.image_prefetch_enabled = True
    try:
        scheduled = prefetch_images(
            processor,
            _images(("http://img/dup", False), ("http://img/dup", False)),
        )
        assert scheduled == 1, "重复 URL 不应重复调度"
        await asyncio.sleep(0)
        assert processor.understand_calls == 1
    finally:
        cfg.model.image_prefetch_enabled = original


async def test_meme_and_plain_image_use_distinct_cache_keys():
    """同一 URL 分别作为表情包与普通图片时，走各自的理解路径。"""
    processor = _FakeProcessor()
    original = cfg.model.image_prefetch_enabled
    cfg.model.image_prefetch_enabled = True
    try:
        scheduled = prefetch_images(
            processor,
            _images(("http://img/same", False), ("http://img/same", True)),
        )
        assert scheduled == 2, "普通图片与表情包是两条路径，应各调度一次"
        await asyncio.sleep(0)
        assert processor.understand_calls == 2
    finally:
        cfg.model.image_prefetch_enabled = original


async def test_disabled_switch_falls_back_to_sync_processing():
    """开关关闭时不调度后台任务，resolve 退回同步处理。"""
    processor = _FakeProcessor()
    original = cfg.model.image_prefetch_enabled
    cfg.model.image_prefetch_enabled = False
    try:
        assert prefetch_images(processor, _images(("http://img/b", False))) == 0
        assert processor._prefetch == {}, "关闭时不应写入预取缓存"

        result = await resolve_image(processor, "http://img/b", False)
        assert result["description"] == "描述:http://img/b"
        assert processor.understand_calls == 1, "退回同步处理仍应完成一次理解"
    finally:
        cfg.model.image_prefetch_enabled = original


async def test_native_vision_prefetch_registers_attachment():
    """开启原生视觉时，普通图片预取走登记并带 native 标记。"""
    processor = _FakeProcessor(native=True)
    original_enabled = cfg.model.image_prefetch_enabled
    original_native = cfg.model.llm_native_vision_enabled
    cfg.model.image_prefetch_enabled = True
    cfg.model.llm_native_vision_enabled = True
    try:
        prefetch_images(processor, _images(("http://img/c", False)))
        await asyncio.sleep(0)
        result = await resolve_image(processor, "http://img/c", False)

        assert result.get("native") is True
        assert result.get("attachment")
        assert processor.register_calls == 1
        assert processor.understand_calls == 0
    finally:
        cfg.model.image_prefetch_enabled = original_enabled
        cfg.model.llm_native_vision_enabled = original_native


async def test_expired_cache_entries_are_evicted():
    """超过 TTL 的缓存条目应被清理，不再复用。"""
    processor = _FakeProcessor()
    original_enabled = cfg.model.image_prefetch_enabled
    original_ttl = cfg.model.image_prefetch_ttl
    cfg.model.image_prefetch_enabled = True
    cfg.model.image_prefetch_ttl = 0.01
    try:
        prefetch_images(processor, _images(("http://img/old", False)))
        await asyncio.sleep(0.05)
        assert processor.understand_calls == 1

        # 再次调度时会先按 TTL 清理旧条目，因此重新下载
        prefetch_images(processor, _images(("http://img/old", False)))
        await asyncio.sleep(0)
        assert processor.understand_calls == 2, "过期条目应被重新预取"
    finally:
        cfg.model.image_prefetch_enabled = original_enabled
        cfg.model.image_prefetch_ttl = original_ttl


async def test_pipeline_enqueue_schedules_prefetch_immediately():
    """enqueue_message 收到图片时立即调度预取，不必等到管线处理阶段。"""
    from core.session_pipeline import IncomingMessage, SessionPipeline

    processor = _FakeProcessor()
    processor.extract_urls_from_text = lambda text: (
        text.replace("[CQ:image,sub_type=0]", "[图片占位符]"),
        _images(("http://img/queue", False)),
    )

    pipeline = SessionPipeline.__new__(SessionPipeline)
    pipeline.meme_processor = processor
    pipeline._timer_tasks = {}
    pipeline._skip_debounce = {}
    pipeline._chat_locks = {}
    pipeline.last_msg_time = {}
    pipeline.yuki = type("Y", (), {"message_buffer": {}})()

    msg = IncomingMessage(
        name="A",
        content="[CQ:image,sub_type=0]",
        raw_text="[CQ:image,sub_type=0]",
        user_id=1,
        source="napcat.group",
        owner_id="100",
    )

    original = cfg.model.image_prefetch_enabled
    cfg.model.image_prefetch_enabled = True
    try:
        await pipeline.enqueue_message("100", "group", message_obj=msg)
        assert "n:http://img/queue" in processor._prefetch, \
            "入队时就应出现预取任务"
        await asyncio.sleep(0)
        assert processor.understand_calls == 1
    finally:
        cfg.model.image_prefetch_enabled = original
        for task in pipeline._timer_tasks.values():
            task.cancel()
