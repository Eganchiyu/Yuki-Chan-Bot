"""视觉处理、原生多模态图块、占位符清扫与入站图片预取测试。"""
import asyncio
import io

from PIL import Image

from config import cfg
from core.engine.engine_reply import EngineReplyService
from core.session_pipeline import IncomingMessage, SessionPipeline
from modules.vision.image_store import ImageStore
from modules.vision.prefetch import prefetch_images, resolve_image
from modules.vision.processor import MemeProcessor, _clean_description, _valid_description


def _png_bytes(color=(10, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "PNG")
    return buf.getvalue()


class _FakeSender:
    @staticmethod
    async def parse_cq_codes(text, chat_id):
        return text


class _FakeHistory:
    def __init__(self):
        self.messages = []
        self.logs = []

    def append_to_log(self, chat_id, tag, content):
        self.logs.append(content)

    def append_session_message(self, chat_id, role, content, **extra):
        self.messages.append({"role": role, "content": content, **extra})
        return [{"role": "system", "content": "sys"}] + self.messages


class _FakeMemeProcessor:
    def __init__(self, image_store=None):
        self.image_store = image_store
        self._prefetch = {}
        self.register_calls = 0
        self.understand_calls = 0

    async def register_from_url(self, url):
        self.register_calls += 1
        if isinstance(self.image_store, ImageStore):
            idx = self.image_store.register(_png_bytes(), url=url, ext=".png")
            return {"index": idx, "attachment": self.image_store.attachment(idx)}
        return {"index": "001", "attachment": {"index": "001", "id": "x"}, "native": True}

    async def understand_from_url(self, url, is_meme=False):
        self.understand_calls += 1
        idx = (
            self.image_store.register(_png_bytes(), url=url, ext=".png")
            if isinstance(self.image_store, ImageStore) and not is_meme
            else None
        )
        return {"description": f"描述:{url}", "index": idx}

    @staticmethod
    def extract_urls_from_text(text):
        images = [{"url": f"http://img/{s}", "is_meme": s != "0"} for s in ("0", "1")]
        cleaned = text.replace("[CQ:image,sub_type=0]", "[图片占位符]").replace("[CQ:image,sub_type=1]", "[图片占位符]")
        return cleaned, images


def _build_pipeline(processor, image_store=None):
    pipeline = SessionPipeline.__new__(SessionPipeline)
    pipeline.meme_processor = processor
    pipeline.image_store = image_store
    pipeline.sender = _FakeSender()
    pipeline.history_manager = _FakeHistory()
    pipeline.yuki = type(
        "Y",
        (),
        {
            "message_buffer": {},
            "user_mapping": type("M", (), {"update": staticmethod(lambda *a, **k: None)})(),
            "boost_activity": staticmethod(lambda *a, **k: asyncio.sleep(0)),
        },
    )()
    pipeline._timer_tasks = {}
    pipeline._skip_debounce = {}
    pipeline._chat_locks = {}
    pipeline.last_msg_time = {}
    pipeline._recent_msg_times = {}
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


# ==================== 原生视觉路由与图块渲染 ====================

async def test_native_vision_switch_routing(tmp_path, monkeypatch):
    """原生视觉开启时：普通图登记附件、表情包转写；关闭时全走转写。"""
    store = ImageStore(store_dir=str(tmp_path / "store"))
    processor = _FakeMemeProcessor(store)
    pipeline = _build_pipeline(processor, store)

    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", True)
    res_on = await pipeline.normalize_incoming_content({
        "chat_id": "100",
        "incoming_messages": [{"user_id": 1, "name": "A", "content": "[CQ:image,sub_type=0][CQ:image,sub_type=1]"}],
        "message_objs": [],
    })
    assert processor.register_calls == 1 and processor.understand_calls == 1
    assert len(res_on["native_images"]) == 1
    assert "[图片]" in res_on["combined_text"] and "[表情:描述:http://img/1]" in res_on["combined_text"]

    processor.register_calls = processor.understand_calls = 0
    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", False)
    res_off = await pipeline.normalize_incoming_content({
        "chat_id": "100",
        "incoming_messages": [{"user_id": 1, "name": "A", "content": "[CQ:image,sub_type=0][CQ:image,sub_type=1]"}],
        "message_objs": [],
    })
    assert processor.register_calls == 0 and processor.understand_calls == 2
    assert res_off["native_images"] == []
    assert "[图片:描述:http://img/0]" in res_off["combined_text"]


async def test_prepare_model_messages_and_limits(tmp_path, monkeypatch):
    """_prepare_model_messages 渲染 image_url 图块、不泄漏元数据、支持降级，并遵守轮数与张数上限。"""
    store = ImageStore(store_dir=str(tmp_path / "render"))
    processor = MemeProcessor(image_store=store)

    async def fake_understand(_):
        return "被转写"

    processor.understand_bytes = fake_understand
    service = _build_reply_service(store, processor)
    idx = store.register(_png_bytes(), ext=".png")
    att = store.attachment(idx)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "看这张", "image_attachments": [att]},
    ]
    native = await service._prepare_model_messages(messages, native_vision=True)
    assert [b["type"] for b in native[1]["content"]] == ["text", "image_url"]
    assert native[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert all("image_attachments" not in m for m in native)
    assert service._used_image_slots(native) == 1

    degraded = await service._prepare_model_messages(messages, native_vision=False)
    assert isinstance(degraded[1]["content"], str) and "[图片:被转写]" in degraded[1]["content"]
    assert service._used_image_slots(degraded) == 0

    # 轮数与张数限制
    three_turns = [{"role": "user", "content": k, "image_attachments": [att]} for k in ("A", "B", "C")]
    monkeypatch.setattr(cfg.model, "native_vision_history_turns", 1)
    assert service._used_image_slots(await service._prepare_model_messages(three_turns, native_vision=True)) == 1

    monkeypatch.setattr(cfg.model, "native_vision_history_turns", 3)
    monkeypatch.setattr(cfg.model, "native_vision_max_images", 2)
    assert service._used_image_slots(await service._prepare_model_messages(three_turns, native_vision=True)) == 2


def test_attachment_identity_blocks_index_reuse(tmp_path):
    """短索引被复用后，旧附件引用因哈希身份不匹配返回 None，防止串图。"""
    store = ImageStore(store_dir=str(tmp_path / "id"))
    first_idx = store.register(_png_bytes(), ext=".png")
    stale = store.attachment(first_idx)
    store._counter = 0
    store.register(_png_bytes((200, 10, 10)), ext=".png")
    assert store.read_attachment(stale) is None


# ==================== 占位符兜底与视觉缓存卫生 ====================

async def test_placeholder_never_leaks_on_empty_or_missing_image():
    """视觉返回空串或无图片解析时，[图片占位符] 必须被消费/清扫，且不写入历史日志。"""
    class _EmptyProc:
        image_store = None
        _prefetch = {}

        @staticmethod
        def extract_urls_from_text(text):
            return text.replace("[CQ:image,sub_type=1]", "[图片占位符]"), [{"url": "http://img/e", "is_meme": True}]

        async def understand_from_url(self, url, is_meme=False):
            return {"description": "", "index": None}

    pipeline = _build_pipeline(_EmptyProc())
    res = await pipeline.normalize_incoming_content({
        "chat_id": "100",
        "incoming_messages": [{"user_id": 1, "name": "A", "content": "[CQ:image,sub_type=1] 看看"}],
        "message_objs": [],
    })
    assert "[图片占位符]" not in res["combined_text"]
    assert "[表情:未知图片/表情]" in res["combined_text"]
    assert "[图片占位符]" not in pipeline.history_manager.logs[0]

    class _NoImgProc:
        image_store = None
        _prefetch = {}

        @staticmethod
        def extract_urls_from_text(text):
            return text, []

    res2 = await _build_pipeline(_NoImgProc()).normalize_incoming_content({
        "chat_id": "100",
        "incoming_messages": [{"user_id": 1, "name": "A", "content": "[图片占位符] 你好"}],
        "message_objs": [],
    })
    assert "[图片占位符]" not in res2["combined_text"] and "[图片]" in res2["combined_text"]


async def test_vision_cache_ignores_empty_and_deepseek_disables_thinking(monkeypatch):
    """空识别结果不入缓存、脏空缓存被忽略重新识别，DeepSeek 视觉端点自动关闭思考。"""
    class _FakeCache:
        def __init__(self):
            self.data = {}
            self.saves = 0

        def get(self, k):
            return self.data.get(k)

        def set(self, k, v):
            self.data[k] = v

        def save(self):
            self.saves += 1

    proc = MemeProcessor.__new__(MemeProcessor)
    proc.cache = _FakeCache()
    proc.semaphore = asyncio.Semaphore(1)
    proc.image_store = None
    proc._prefetch = {}
    proc._vision_chat = None

    async def empty_api(_):
        return ""

    proc.call_api = empty_api
    assert await proc.understand_bytes(_png_bytes()) == "未知图片"
    assert proc.cache.data == {} and proc.cache.saves == 0

    # 脏空缓存不命中
    proc.cache.set(proc.get_image_hash(_png_bytes()), "   ")

    async def ok_api(_):
        return "  微笑\n表情  "

    proc.call_api = ok_api
    assert await proc.understand_bytes(_png_bytes()) == "微笑 表情"
    assert proc.cache.saves == 1

    # 命中有效缓存后不再请求 API
    async def fail_api(_):
        raise AssertionError("不应再次调用 API")

    proc.call_api = fail_api
    assert await proc.understand_bytes(_png_bytes()) == "微笑 表情"

    assert _clean_description("  微笑\n\n") == "微笑" and _clean_description(None) == ""
    assert _valid_description("微笑") is True and _valid_description("  ") is False

    monkeypatch.setattr(cfg.api, "image_process_url", "https://api.deepseek.com/v1")
    assert MemeProcessor._no_thinking_kwargs() == {"reasoning_effort": "none"}
    monkeypatch.setattr(cfg.api, "image_process_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert MemeProcessor._no_thinking_kwargs() == {}


# ==================== 入站图片后台预取 ====================

async def test_image_prefetch_dedup_buckets_and_ttl(monkeypatch):
    """预取复用、同批去重、表情包与普通图分桶、原生视觉预取、开关回退及 TTL 淘汰。"""
    monkeypatch.setattr(cfg.model, "image_prefetch_enabled", True)
    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", False)

    proc = _FakeMemeProcessor()
    assert prefetch_images(proc, [{"url": "http://img/a", "is_meme": False}, {"url": "http://img/a", "is_meme": False}]) == 1
    await asyncio.sleep(0)
    res = await resolve_image(proc, "http://img/a", False)
    assert res["description"] == "描述:http://img/a" and proc.understand_calls == 1

    # 同 URL 作为普通图和表情包各调度一次
    proc2 = _FakeMemeProcessor()
    assert prefetch_images(proc2, [{"url": "http://img/s", "is_meme": False}, {"url": "http://img/s", "is_meme": True}]) == 2
    await asyncio.sleep(0)
    assert proc2.understand_calls == 2

    # 原生视觉预取走 register_from_url
    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", True)
    proc_native = _FakeMemeProcessor(image_store=object())
    prefetch_images(proc_native, [{"url": "http://img/c", "is_meme": False}])
    await asyncio.sleep(0)
    res_native = await resolve_image(proc_native, "http://img/c", False)
    assert res_native.get("native") is True and proc_native.register_calls == 1 and proc_native.understand_calls == 0

    # TTL 过期淘汰
    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", False)
    monkeypatch.setattr(cfg.model, "image_prefetch_ttl", 0.01)
    proc_ttl = _FakeMemeProcessor()
    prefetch_images(proc_ttl, [{"url": "http://img/old", "is_meme": False}])
    await asyncio.sleep(0.03)
    prefetch_images(proc_ttl, [{"url": "http://img/old", "is_meme": False}])
    await asyncio.sleep(0)
    assert proc_ttl.understand_calls == 2

    # 关闭预取开关退回同步处理
    monkeypatch.setattr(cfg.model, "image_prefetch_enabled", False)
    proc_off = _FakeMemeProcessor()
    assert prefetch_images(proc_off, [{"url": "http://img/b", "is_meme": False}]) == 0
    res_off = await resolve_image(proc_off, "http://img/b", False)
    assert res_off["description"] == "描述:http://img/b" and proc_off.understand_calls == 1


async def test_pipeline_enqueue_schedules_prefetch_immediately(monkeypatch):
    """enqueue_message 收到含图消息时立即调度后台预取。"""
    monkeypatch.setattr(cfg.model, "image_prefetch_enabled", True)
    monkeypatch.setattr(cfg.model, "llm_native_vision_enabled", False)

    proc = _FakeMemeProcessor()
    proc.extract_urls_from_text = lambda text: (
        text.replace("[CQ:image,sub_type=0]", "[图片占位符]"),
        [{"url": "http://img/queue", "is_meme": False}],
    )
    pipeline = _build_pipeline(proc)
    msg = IncomingMessage(
        name="A", content="[CQ:image,sub_type=0]", raw_text="[CQ:image,sub_type=0]",
        user_id=1, source="napcat.group", owner_id="100",
    )
    try:
        await pipeline.enqueue_message("100", "group", message_obj=msg)
        assert "n:http://img/queue" in proc._prefetch
        await asyncio.sleep(0)
        assert proc.understand_calls == 1
    finally:
        for task in pipeline._timer_tasks.values():
            task.cancel()
