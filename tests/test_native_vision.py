# tests/test_native_vision.py
"""原生视觉输入回归测试：普通图片进模型、表情包仍转写、备用线路按需降级。"""
import asyncio
import io
import os
import shutil
import sys

from PIL import Image

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import cfg
from core.engine.engine_reply import EngineReplyService
from core.session_pipeline import SessionPipeline
from modules.vision.image_store import ImageStore
from modules.vision.processor import MemeProcessor
from utils import llm_client


def _png_bytes(color=(10, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "PNG")
    return buf.getvalue()


class _FakeMemeProcessor:
    """记录图片走的是原生登记还是转写。"""

    def __init__(self, image_store):
        self.image_store = image_store
        self.register_calls = 0
        self.understand_calls = 0

    async def register_from_url(self, url):
        self.register_calls += 1
        idx = self.image_store.register(_png_bytes(), url=url, ext=".png")
        return {"index": idx, "attachment": self.image_store.attachment(idx)}

    async def understand_from_url(self, url, is_meme=False):
        self.understand_calls += 1
        idx = None if is_meme else self.image_store.register(_png_bytes(), url=url, ext=".png")
        return {"description": "转写结果", "index": idx}

    @staticmethod
    def extract_urls_from_text(text):
        images = []
        for sub_type in ("0", "1"):
            images.append({"url": f"http://img/{sub_type}", "is_meme": sub_type != "0"})
        return text.replace("[CQ:image,sub_type=0]", "[图片占位符]").replace(
            "[CQ:image,sub_type=1]", "[图片占位符]"
        ), images


class _FakeSender:
    @staticmethod
    async def parse_cq_codes(text, chat_id):
        return text


class _FakeHistory:
    def __init__(self):
        self.messages = []

    def append_to_log(self, *args, **kwargs):
        return None

    def append_session_message(self, chat_id, role, content, **extra):
        self.messages.append({"role": role, "content": content, **extra})
        return [{"role": "system", "content": "sys"}] + self.messages


def _build_pipeline(image_store, processor, tmp_dir):
    pipeline = SessionPipeline.__new__(SessionPipeline)
    pipeline.meme_processor = processor
    pipeline.image_store = image_store
    pipeline.sender = _FakeSender()
    pipeline.history_manager = _FakeHistory()
    pipeline.yuki = type("Y", (), {"user_mapping": type("M", (), {"update": lambda *a: None})()})()
    return pipeline


def _build_reply_service(image_store, processor):
    return EngineReplyService(
        yuki=None,
        history=None,
        sender=None,
        tool_registry=None,
        tool_manager=None,
        get_process_callback=lambda: None,
        get_image_store=lambda: image_store,
        get_meme_processor=lambda: processor,
    )


def test_native_switch_keeps_meme_transcribed_and_plain_image_native():
    """开关开启时，普通图片登记为附件，表情包仍走转写。"""
    tmp_dir = "data/_test_native_vision"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    store = ImageStore(store_dir=tmp_dir)
    processor = _FakeMemeProcessor(store)
    pipeline = _build_pipeline(store, processor, tmp_dir)

    original = cfg.model.llm_native_vision_enabled
    cfg.model.llm_native_vision_enabled = True
    try:
        context = {
            "chat_id": "100",
            "incoming_messages": [
                {"user_id": 1, "name": "A", "content": "[CQ:image,sub_type=0][CQ:image,sub_type=1]"}
            ],
            "message_objs": [],
        }
        result = asyncio.run(pipeline.normalize_incoming_content(context))

        assert processor.register_calls == 1, "普通图片应只登记一次"
        assert processor.understand_calls == 1, "表情包应走转写"
        assert len(result["native_images"]) == 1, "普通图片应产生一个附件引用"
        assert "[图片]" in result["combined_text"]
        assert "[表情:转写结果]" in result["combined_text"]
    finally:
        cfg.model.llm_native_vision_enabled = original
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_native_switch_off_falls_back_to_transcription():
    """开关关闭时，普通图片与表情包都沿用外挂视觉转写。"""
    tmp_dir = "data/_test_native_vision_off"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    store = ImageStore(store_dir=tmp_dir)
    processor = _FakeMemeProcessor(store)
    pipeline = _build_pipeline(store, processor, tmp_dir)

    original = cfg.model.llm_native_vision_enabled
    cfg.model.llm_native_vision_enabled = False
    try:
        context = {
            "chat_id": "100",
            "incoming_messages": [
                {"user_id": 1, "name": "A", "content": "[CQ:image,sub_type=0][CQ:image,sub_type=1]"}
            ],
            "message_objs": [],
        }
        result = asyncio.run(pipeline.normalize_incoming_content(context))

        assert processor.register_calls == 0
        assert processor.understand_calls == 2
        assert result["native_images"] == []
        assert "[图片:转写结果]" in result["combined_text"]
    finally:
        cfg.model.llm_native_vision_enabled = original
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_prepare_model_messages_renders_image_blocks_without_leaking_meta():
    """原生模式下渲染 imageUrl 图块，且不把附件元数据泄漏给模型。"""
    tmp_dir = "data/_test_native_vision_render"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    store = ImageStore(store_dir=tmp_dir)
    processor = MemeProcessor(image_store=store)

    async def fake_understand(_):
        return "被转写"

    processor.understand_bytes = fake_understand
    service = _build_reply_service(store, processor)

    idx = store.register(_png_bytes(), ext=".png")
    attachment = store.attachment(idx)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "看这张", "image_attachments": [attachment]},
    ]
    try:
        native = asyncio.run(service._prepare_model_messages(messages, native_vision=True))
        assert isinstance(native[1]["content"], list)
        assert [block["type"] for block in native[1]["content"]] == ["text", "image_url"]
        assert native[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert all("image_attachments" not in message for message in native)
        assert service._used_image_slots(native) == 1

        degraded = asyncio.run(service._prepare_model_messages(messages, native_vision=False))
        assert isinstance(degraded[1]["content"], str)
        assert "[图片:被转写]" in degraded[1]["content"]
        assert service._used_image_slots(degraded) == 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_prepare_model_messages_respects_turn_and_count_limits():
    """超过保留轮数或张数上限的图片不再作为图块输入。"""
    tmp_dir = "data/_test_native_vision_limit"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    store = ImageStore(store_dir=tmp_dir)
    processor = MemeProcessor(image_store=store)

    async def fake_understand(_):
        return "被转写"

    processor.understand_bytes = fake_understand
    service = _build_reply_service(store, processor)
    idx = store.register(_png_bytes(), ext=".png")
    attachment = store.attachment(idx)
    messages = [
        {"role": "user", "content": "A", "image_attachments": [attachment]},
        {"role": "user", "content": "B", "image_attachments": [attachment]},
        {"role": "user", "content": "C", "image_attachments": [attachment]},
    ]

    original_turns = cfg.model.native_vision_history_turns
    original_max = cfg.model.native_vision_max_images
    try:
        cfg.model.native_vision_history_turns = 1
        out = asyncio.run(service._prepare_model_messages(messages, native_vision=True))
        assert service._used_image_slots(out) == 1, "只保留最近一轮的图片"

        cfg.model.native_vision_history_turns = 3
        cfg.model.native_vision_max_images = 2
        out = asyncio.run(service._prepare_model_messages(messages, native_vision=True))
        assert service._used_image_slots(out) == 2, "单次图片张数应受限"
    finally:
        cfg.model.native_vision_history_turns = original_turns
        cfg.model.native_vision_max_images = original_max
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_attachment_identity_blocks_index_reuse():
    """短索引被复用后，旧附件引用不应读到新图。"""
    tmp_dir = "data/_test_native_vision_identity"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    store = ImageStore(store_dir=tmp_dir)
    try:
        first_idx = store.register(_png_bytes(), ext=".png")
        stale = store.attachment(first_idx)
        # 强制让索引计数器回到同一位置后再次登记，模拟索引复用
        store._counter = 0
        store.register(_png_bytes((200, 10, 10)), ext=".png")
        assert store.read_attachment(stale) is None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_backup_line_degrades_to_text_when_vision_unsupported():
    """主线路失败且备用不支持视觉时，才按需生成纯文本消息。"""
    calls = []

    async def fake_chat_completion_raw(base_url, api_key, messages, model, timeout=60.0, **kwargs):
        calls.append({"base_url": base_url, "messages": messages})
        if len(calls) == 1:
            raise RuntimeError("主线路不可用")
        return {"role": "assistant", "content": "备用线路回复"}

    factory_calls = []

    async def fallback_factory():
        factory_calls.append(True)
        return [{"role": "user", "content": "纯文本降级"}]

    original_backup_vision = cfg.model.backup_native_vision_enabled
    original_raw = llm_client.chat_completion_raw
    llm_client.chat_completion_raw = fake_chat_completion_raw
    llm_client._fallback_state["is_degraded"] = False
    try:
        cfg.model.backup_native_vision_enabled = False
        message = asyncio.run(llm_client.llm_chat_raw(
            messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}],
            fallback_messages_factory=fallback_factory,
        ))
        assert message["content"] == "备用线路回复"
        assert factory_calls == [True], "备用不支持视觉时应生成纯文本消息"
        assert calls[1]["messages"] == [{"role": "user", "content": "纯文本降级"}]

        calls.clear()
        factory_calls.clear()
        cfg.model.backup_native_vision_enabled = True
        asyncio.run(llm_client.llm_chat_raw(
            messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}],
            fallback_messages_factory=fallback_factory,
        ))
        assert factory_calls == [], "备用支持视觉时应直接复用原消息"
    finally:
        cfg.model.backup_native_vision_enabled = original_backup_vision
        llm_client.chat_completion_raw = original_raw
        llm_client._fallback_state["is_degraded"] = False
