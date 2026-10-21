# tests/test_vision_placeholder.py
"""图片占位符兜底回归：识别为空或图片未解析时，[图片占位符] 绝不允许漏进模型上下文。

背景：视觉模型（deepseek-flash）不关思考时 max_tokens 被 reasoning_content 吃光，
content 返回空串；旧逻辑用 `elif is_meme and desc` 判断，空串被当成「无需替换」，
占位符原样进入 LLM 上下文与历史。
"""
import asyncio
import io
import os
import sys

from PIL import Image

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import cfg
from core.session_pipeline import SessionPipeline
from modules.vision.processor import MemeProcessor, _clean_description, _valid_description


class _FakeSender:
    @staticmethod
    async def parse_cq_codes(text, chat_id):
        return text


class _FakeHistory:
    def __init__(self):
        self.logs = []

    def append_to_log(self, chat_id, tag, content):
        self.logs.append(content)


class _FakeYuki:
    def __init__(self):
        self.user_mapping = type("M", (), {"update": staticmethod(lambda *a, **k: None)})()

    async def boost_activity(self, chat_id):
        return None


class _EmptyDescProcessor:
    """图片能解析出来，但视觉模型返回空描述。"""

    image_store = None

    def __init__(self):
        self._prefetch = {}

    @staticmethod
    def extract_urls_from_text(text):
        return (
            text.replace("[CQ:image,sub_type=1]", "[图片占位符]"),
            [{"url": "http://img/empty", "is_meme": True}],
        )

    async def understand_from_url(self, url, is_meme=False):
        return {"description": "", "index": None}


class _NoImageProcessor:
    """一个图都没解析出来，但文本里已经带着占位符（例如 CQ 码被截断）。"""

    image_store = None

    def __init__(self):
        self._prefetch = {}

    @staticmethod
    def extract_urls_from_text(text):
        return text, []

    async def understand_from_url(self, url, is_meme=False):
        raise AssertionError("没有图片时不应触发识别")


def _build_pipeline(processor):
    pipeline = SessionPipeline.__new__(SessionPipeline)
    pipeline.meme_processor = processor
    pipeline.sender = _FakeSender()
    pipeline.history_manager = _FakeHistory()
    pipeline.yuki = _FakeYuki()
    return pipeline


def _normalize(pipeline, content):
    context = {
        "chat_id": "100",
        "incoming_messages": [{"user_id": 1, "name": "A", "content": content}],
        "message_objs": [],
    }
    return asyncio.run(pipeline.normalize_incoming_content(context))


def test_empty_description_still_consumes_placeholder():
    """视觉描述为空：必须替换成「未知图片/表情」，而不是把占位符留给模型。"""
    result = _normalize(_build_pipeline(_EmptyDescProcessor()), "[CQ:image,sub_type=1] 再试一次yuki")

    assert "[图片占位符]" not in result["combined_text"]
    assert "[表情:未知图片/表情]" in result["combined_text"]


def test_leftover_placeholder_is_swept_when_no_image_parsed():
    """上游没解析出图片也带占位符时，兜底清扫不能再漏给模型。"""
    result = _normalize(_build_pipeline(_NoImageProcessor()), "[图片占位符] 你好")

    assert "[图片占位符]" not in result["combined_text"], "残留占位符必须被清扫"
    assert "[图片]" in result["combined_text"]


def test_logged_incoming_text_has_no_placeholder():
    """写进日志/历史的那一份文本同样不允许出现占位符。"""
    pipeline = _build_pipeline(_EmptyDescProcessor())
    _normalize(pipeline, "[CQ:image,sub_type=1] 看看这个")
    assert "[图片占位符]" not in pipeline.history_manager.logs[0]


# ==================== 视觉结果与缓存 ====================


class _FakeCache:
    """替代 MemeCache：不落盘，只记录写入。"""

    def __init__(self):
        self.data = {}
        self.saves = 0

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        self.saves += 1


def _png_bytes(color=(10, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "PNG")
    return buf.getvalue()


def _bare_processor(call_api):
    processor = MemeProcessor.__new__(MemeProcessor)
    processor.cache = _FakeCache()
    processor.semaphore = asyncio.Semaphore(1)
    processor.image_store = None
    processor._prefetch = {}
    processor._vision_chat = None
    processor.call_api = call_api
    return processor


def test_empty_vision_result_is_not_cached():
    """空描述不写缓存且按未知图片处理；有效描述才写缓存并被复用。"""
    calls = {"n": 0}

    async def empty_api(b64):
        calls["n"] += 1
        return ""

    processor = _bare_processor(empty_api)
    assert asyncio.run(processor.understand_bytes(_png_bytes())) == "未知图片"
    assert processor.cache.data == {}, "空描述不能进缓存，否则同一张图永远识别为空"
    assert processor.cache.saves == 0

    async def ok_api(b64):
        return "  微笑\n表情  "

    processor.call_api = ok_api
    assert asyncio.run(processor.understand_bytes(_png_bytes())) == "微笑 表情"
    assert processor.cache.data, "有效描述应写入缓存"

    async def boom(b64):
        raise AssertionError("命中缓存后不应再请求")

    processor.call_api = boom
    assert asyncio.run(processor.understand_bytes(_png_bytes())) == "微笑 表情"


def test_cached_empty_description_is_ignored():
    """历史脏数据（缓存值为空串）不能命中，必须重新识别。"""
    processor = _bare_processor(lambda b64: None)
    hash_key = processor.get_image_hash(_png_bytes())
    processor.cache.set(hash_key, "   ")

    async def ok_api(b64):
        return "委屈"

    processor.call_api = ok_api
    assert asyncio.run(processor.understand_bytes(_png_bytes())) == "委屈"


def test_description_helpers():
    assert _clean_description("  微笑\n\n") == "微笑"
    assert _clean_description(None) == ""
    assert _clean_description(["块"]) == ""
    assert _valid_description("微笑") is True
    assert _valid_description("   ") is False
    assert _valid_description(None) is False


def test_no_thinking_kwargs_only_for_deepseek():
    """只对 DeepSeek 端点下发关思考参数，避免其它视觉端点 400。"""
    original_url = cfg.api.image_process_url
    raw = getattr(cfg, "_raw", None)
    original_raw_flag = None
    if isinstance(raw, dict) and isinstance(raw.get("model"), dict):
        original_raw_flag = raw["model"].get("disable_thinking")
        raw["model"]["disable_thinking"] = True
    try:
        cfg.api.image_process_url = "https://api.deepseek.com/v1"
        if cfg.DISABLE_THINKING:
            assert MemeProcessor._no_thinking_kwargs() == {"reasoning_effort": "none"}

        cfg.api.image_process_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert MemeProcessor._no_thinking_kwargs() == {}
    finally:
        cfg.api.image_process_url = original_url
        if isinstance(raw, dict) and isinstance(raw.get("model"), dict) and original_raw_flag is not None:
            raw["model"]["disable_thinking"] = original_raw_flag
