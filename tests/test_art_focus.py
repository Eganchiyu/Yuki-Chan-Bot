"""艺术创作聚焦模式 (art) 与艺术资产管理 (ArtAssetStore) 单元测试。"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from config import cfg
from core.art_assets import ArtAssetStore, art_asset_store
from core.focus import ToolView, focus_manager
from core.art_gen_jobs import art_gen_store
from core.focus.domains.art import (
    ART,
    art_asset_tool,
    art_draw_tool,
    art_finish_tool,
    art_gacha_tool,
    art_start_tool,
)
from core.toolchain import FunctionRegistry, ToolContext, ToolResult, ToolRuntime
from core.tools import TOOL_SPECS
from core.tools import tools_media


# 1x1 合法 PNG 字节
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _flush_triggers():
    """把 create_task 起的「触发回复」跑到完成。"""
    for _ in range(5):
        await asyncio.sleep(0)


def _make_ctx(chat_id: str = "c_art", image_store=None, history=None) -> ToolContext:
    runtime = ToolRuntime(
        sender=SimpleNamespace(),
        yuki_state=SimpleNamespace(),
        image_store=image_store,
    )
    meta = {"history_manager": history} if history is not None else {}
    return ToolContext(
        chat_id=chat_id,
        mode="group",
        session=[],
        combined_text="",
        runtime=runtime,
        metadata=meta,
    )


@pytest.fixture(autouse=True)
def _clean_focus_state():
    focus_manager._states.clear()
    yield
    focus_manager._states.clear()


def test_builtin_initial_assets_present():
    """默认内置 yuki 与 master 两张参考图资产，包含 reference 字段与简短外貌描述。"""
    items = {a["key"]: a for a in art_asset_store.list()}
    assert "yuki" in items and "master" in items
    assert items["yuki"]["reference"] == "output/assets/character/yuki_reference.png"
    assert items["master"]["reference"] == "output/assets/character/master_reference.png"
    assert "白长发" in items["yuki"]["description"] and "蓝瞳" in items["yuki"]["description"]
    assert "黑长发" in items["master"]["description"] and "绿瞳" in items["master"]["description"]


def test_default_view_hides_generate_image_and_exposes_art_start():
    """常态模式下不再暴露 generate_image，仅暴露极简入口 art_start；聚焦时展开创作工具集。"""
    reg = FunctionRegistry()
    reg.scan_and_register(TOOL_SPECS)

    default_view = ToolView.resolve(reg, focus_manager, "c_art")
    assert "generate_image" not in default_view.visible
    assert "art_start" in default_view.visible
    assert "art_draw" not in default_view.visible
    assert "art_gacha" not in default_view.visible
    assert "art_asset" not in default_view.visible
    assert "art_finish" not in default_view.visible

    focus_manager.enter("c_art", ART.name, goal="画立绘")
    focused_view = ToolView.resolve(reg, focus_manager, "c_art")
    assert focused_view.visible == {
        "art_draw",
        "art_gacha",
        "art_asset",
        "art_finish",
        "search_diary",
        "send_master_private",
        "send_qq_file",
    }


async def test_art_start_immediately_outputs_registered_assets():
    """调用 art_start 时立即返回当前已登记资产列表，无需多请求一轮。"""
    ctx = _make_ctx("c_art_start")
    res = await art_start_tool(ctx, goal="给群友画双人图")
    assert res.success is True
    assert focus_manager.is_focused("c_art_start", "art") is True
    assert "yuki_reference.png" in res.content
    assert "master_reference.png" in res.content
    assert len(res.data["assets"]) >= 2


async def test_art_asset_crud_with_temp_store(tmp_path, monkeypatch):
    """art_asset 支持登记群友三视图（自动持久化拷贝）、修改描述、查询与删除。"""
    temp_img_dir = os.path.join(tools_media.BASE_DIR, "temp_images")
    os.makedirs(temp_img_dir, exist_ok=True)
    src_img = os.path.join(temp_img_dir, "pytest_chiyujian_sheet.png")
    with open(src_img, "wb") as f:
        f.write(_TINY_PNG)

    # 落盘目录放临时目录：校验容器里代码树与 output/ 都是只读的
    custom_asset_dir = str(tmp_path / "assets" / "character" / "_pytest_tmp")
    store = ArtAssetStore(
        json_path=str(tmp_path / "art_assets.json"),
        asset_dir=custom_asset_dir,
    )
    monkeypatch.setattr("core.focus.domains.art.art_asset_store", store)

    fake_image_store = SimpleNamespace(resolve=lambda idx: src_img if idx == "001" else None)
    ctx = _make_ctx("c_crud", image_store=fake_image_store)

    try:
        # 1. 登记池宇健三视图（使用 [img:001] 索引）
        reg_res = await art_asset_tool(
            ctx,
            action="register",
            key="池宇健",
            owner="池宇健",
            reference="[img:001]",
            description="银短发，金瞳，机能风黑外套，三视图",
            tags=["三视图", "立绘"],
        )
        assert reg_res.success is True
        saved_asset = store.get("池宇健")
        assert saved_asset is not None
        assert os.path.dirname(saved_asset["reference"]) == custom_asset_dir
        assert os.path.isfile(saved_asset["reference"])

        # 2. 修改描述
        upd_res = await art_asset_tool(
            ctx,
            action="update",
            key="池宇健",
            description="银白短发，金瞳，护目镜发饰，黑金机能外套",
        )
        assert upd_res.success is True
        assert "护目镜发饰" in store.get("池宇健")["description"]

        # 3. 列表查看
        list_res = await art_asset_tool(ctx, action="list")
        assert list_res.success is True
        assert "池宇健" in list_res.content

        # 4. 删除资产
        del_res = await art_asset_tool(ctx, action="delete", key="池宇健")
        assert del_res.success is True
        assert store.get("池宇健") is None
    finally:
        if os.path.exists(src_img):
            os.remove(src_img)
        if os.path.isdir(custom_asset_dir):
            import shutil
            shutil.rmtree(custom_asset_dir, ignore_errors=True)


async def test_art_draw_resolves_multiple_assets_and_aspect_ratio(monkeypatch):
    """art_draw 支持同时选择多张登记资产图（如 yuki + 主人）并默认 opaque + high 品质与高保真。"""
    captured = {}

    async def fake_gen(
        context,
        prompt,
        size="1024*1024",
        image_paths=None,
        aspect_ratio=None,
        seed=None,
        quality=None,
        background=None,
        input_fidelity=None,
        output_format=None,
    ):
        captured["prompt"] = prompt
        captured["size"] = size
        captured["image_paths"] = image_paths
        captured["aspect_ratio"] = aspect_ratio
        captured["seed"] = seed
        captured["quality"] = quality
        captured["background"] = background
        captured["input_fidelity"] = input_fidelity
        captured["output_format"] = output_format
        return ToolResult(
            success=True,
            content="图像已生成并保存: /tmp/out.png",
            data={"file_path": "/tmp/out.png", "prompt": prompt, "size": "1024x1536"},
        )

    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", fake_gen)
    ctx = _make_ctx("c_draw")
    focus_manager.enter("c_draw", "art", goal="双人同框")

    res = await art_draw_tool(
        ctx,
        prompt="Yuki和主人在樱花树下散步，高品质流畅线条",
        assets=["yuki", "主人"],
        aspect_ratio="2:3",
        seed=42,
        note="画樱花散步",
    )
    assert res.success is True
    # 异步：工具立刻返回任务号，参数交给后台任务
    assert res.data["art_job"] == "queued"
    job = await art_gen_store.wait(res.data["job_id"])
    assert job is not None and job.status == "done"
    assert captured["size"] == "1024*1536"
    assert captured["seed"] == 42
    assert captured["quality"] == "high"
    assert captured["background"] == "opaque"
    assert captured["input_fidelity"] == "high"
    assert captured["output_format"] is None
    assert captured["image_paths"] == [
        "output/assets/character/yuki_reference.png",
        "output/assets/character/master_reference.png",
    ]
    assert res.data["used_assets"] == ["yuki", "master"]
    assert res.data["background"] == "opaque"

    # 仅显式要求透明背景时才切 transparent + png
    res_trans = await art_draw_tool(
        ctx,
        prompt="Chibi Yuki sticker, no background",
        background="transparent",
    )
    assert res_trans.success is True
    await art_gen_store.wait(res_trans.data["job_id"])
    assert captured["background"] == "transparent"
    assert captured["output_format"] == "png"
    assert captured["input_fidelity"] is None

    # 未知资产名给出清晰提示
    bad_res = await art_draw_tool(ctx, prompt="测试", assets=["不存在的群友"])
    assert bad_res.success is False
    assert bad_res.error == "asset_not_found"


async def test_art_draw_injects_reference_legend_for_multiple_assets(monkeypatch):
    """多张参考图时自动在 prompt 前注入「image N = 谁」的绑定说明，单图不注入。"""
    captured: list[str] = []

    async def fake_gen(
        context,
        prompt,
        size="1024*1024",
        image_paths=None,
        aspect_ratio=None,
        seed=None,
        quality=None,
        background=None,
        input_fidelity=None,
        output_format=None,
    ):
        captured.append(prompt)
        return ToolResult(
            success=True,
            content="图像已生成并保存: /tmp/out.png",
            data={"file_path": "/tmp/out.png", "prompt": prompt, "size": "1024x1536"},
        )

    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", fake_gen)
    ctx = _make_ctx("c_legend")
    focus_manager.enter("c_legend", "art", goal="双人同框")

    many = await art_draw_tool(ctx, prompt="two girls on the beach", assets=["yuki", "master"])
    await art_gen_store.wait(many.data["job_id"])
    legend_prompt = captured[-1]
    assert legend_prompt.startswith("【参考图对应关系")
    assert "image 1 = yuki（Yuki）：白长发" in legend_prompt
    assert "image 2 = master（主人）：黑长发" in legend_prompt
    assert legend_prompt.endswith("two girls on the beach")
    # 原始 prompt 仍保留在任务记录里，便于排障
    job = art_gen_store.get(many.data["job_id"])
    assert job is not None and job.prompt == "two girls on the beach"

    one = await art_draw_tool(ctx, prompt="solo yuki", assets=["yuki"])
    await art_gen_store.wait(one.data["job_id"])
    assert captured[-1] == "solo yuki"


async def test_art_start_contains_director_guide_and_async_draw_delivery(monkeypatch, tmp_path):
    """art_start 返回导演指南与默认禁透明规则；art_draw 后台画完后自动发图并注入带预览的汇报。"""
    ctx_start = _make_ctx("c_guide")
    start_res = await art_start_tool(ctx_start, goal="画海报")
    assert "二次元艺术总监生图指南" in start_res.content
    assert "opaque" in start_res.content
    assert "背景铁律" in start_res.content
    assert "异步" in start_res.content or "自动把图发到会话里" in start_res.content

    out_png = tmp_path / "preview.png"
    out_png.write_bytes(_TINY_PNG)

    from modules.vision.image_store import ImageStore
    store = ImageStore(store_dir=str(tmp_path / "img_store"))

    async def fake_gen(context, **kwargs):
        return ToolResult(
            success=True,
            content=f"图像已生成并保存: {out_png}",
            data={"file_path": str(out_png), "prompt": kwargs["prompt"], "size": "1024x1024"},
        )

    sent = []
    triggered = []

    async def fake_send_local_image(chat_id, path, mode="group"):
        sent.append((str(chat_id), path))

    async def fake_process_callback(chat_id, mode, debounce_flag=True, force_reply=None, **kwargs):
        triggered.append((str(chat_id), bool(force_reply)))

    class FakeHistory:
        def __init__(self):
            self.messages = []

        def append_session_message(self, chat_id, role, content, **extra):
            self.messages.append({"chat_id": str(chat_id), "role": role, "content": content, **extra})

    history = FakeHistory()
    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", fake_gen)
    ctx_draw = _make_ctx("c_preview", image_store=store, history=history)
    ctx_draw.runtime.sender = SimpleNamespace(send_local_image=fake_send_local_image)
    ctx_draw.metadata["process_callback"] = fake_process_callback
    focus_manager.enter("c_preview", "art", goal="自检测试")

    res = await art_draw_tool(ctx_draw, prompt="An anime girl at sunset")
    assert res.success is True
    assert res.data["art_job"] == "queued"
    job = await art_gen_store.wait(res.data["job_id"])
    assert job.status == "done"
    assert isinstance(job.result.get("screenshot"), dict)
    assert job.result["screenshot"]["index"] == "001"

    # 自动把成品发到会话里
    assert sent == [("c_preview", str(out_png))]
    # 汇报写进历史并触发一次强制回复
    assert len(history.messages) == 1
    report = history.messages[0]
    assert report["is_art_report"] is True
    assert "已经自动发到会话里" in report["content"]
    assert "[img:001]" in report["content"]
    assert report["image_attachments"]
    await _flush_triggers()
    assert triggered == [("c_preview", True)]


async def test_generate_image_openai_gpt_image_params_and_400_fallback(monkeypatch, tmp_path):
    """gpt-image 模型默认带 quality=high / background=opaque（参考图带 input_fidelity=high），遇 400 自动剥离降级。"""
    monkeypatch.setattr(cfg.api, "image_gen_api_key", "test-key")
    monkeypatch.setattr(cfg.api, "image_gen_url", "https://example.invalid/v1")
    monkeypatch.setattr(cfg.model, "image_gen", "gpt-image-2.6-sunburst")

    import base64
    import sys
    import types

    calls = []

    class FakeBadRequest(Exception):
        def __init__(self, msg):
            super().__init__(msg)
            self.status_code = 400

    class FakeImages:
        def generate(self, **kwargs):
            calls.append(("generate", dict(kwargs)))
            # 模拟中转站拒绝 background/output_format 或 response_format，降级到仅保留 quality 后成功
            if "background" in kwargs:
                raise FakeBadRequest("unsupported background")
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(_TINY_PNG).decode())])

        def edit(self, **kwargs):
            calls.append(("edit", {k: v for k, v in kwargs.items() if k != "image"}))
            if "input_fidelity" in kwargs:
                raise FakeBadRequest("unsupported input_fidelity")
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(_TINY_PNG).decode())])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.images = FakeImages()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    ctx = _make_ctx("c_openai_fallback")
    res1 = await tools_media.generate_image_tool(ctx, prompt="anime girl", aspect_ratio="2:3")
    assert res1.success is True
    assert calls[0][0] == "generate"
    assert calls[0][1]["quality"] == "high"
    assert calls[0][1]["background"] == "opaque"
    assert calls[1][1]["quality"] == "high"
    assert "background" not in calls[1][1]
    if res1.data and res1.data.get("file_path") and os.path.exists(res1.data["file_path"]):
        os.remove(res1.data["file_path"])

    # 带参考图走 edit，默认带 input_fidelity=high
    calls.clear()
    res2 = await tools_media.generate_image_tool(
        ctx,
        prompt="keep hair and face",
        image_paths=["output/assets/character/yuki_reference.png"],
        aspect_ratio="1:1",
    )
    assert res2.success is True
    assert calls[0][0] == "edit"
    assert calls[0][1]["input_fidelity"] == "high"
    assert calls[0][1]["background"] == "opaque"
    assert calls[1][0] == "edit"
    assert calls[1][1]["quality"] == "high"
    assert "input_fidelity" not in calls[1][1]
    if res2.data and res2.data.get("file_path") and os.path.exists(res2.data["file_path"]):
        os.remove(res2.data["file_path"])


class _StubPool:
    """替代真实语料库的抽样桩。"""

    def __init__(self, available: bool):
        self._available = available
        self.calls: list[dict] = []

    def available(self) -> bool:
        return self._available

    def sample(self, rng=None, ratings=("G", "S"), topic="", exclude_topics=()):
        self.calls.append({"ratings": ratings, "topic": topic, "exclude_topics": exclude_topics})
        if not self._available:
            return None
        return {
            "tag_text": "1girl, apron, kitchen, smile, sunlight",
            "post_id": "123",
            "rating": "G",
            "topic": "【优质】日常治愈",
        }


async def test_art_gacha_returns_single_random_prompt(monkeypatch):
    """art_gacha 无参数，只回一句提示词灵感，绝不触发生图。"""
    from core import art_gacha as gacha_mod

    called = False

    async def forbid_gen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("art_gacha should not call generate_image_tool directly")

    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", forbid_gen)
    ctx = _make_ctx("c_gacha")
    focus_manager.enter("c_gacha", "art", goal="盲盒抽卡")

    # 1. 语料库不可用：回落到内置词条池，仍是一句 prompt
    monkeypatch.setattr(gacha_mod, "zako_prompt_pool", _StubPool(False))
    res = await art_gacha_tool(ctx)
    assert res.success is True
    assert called is False
    assert res.data["source"] in ("slot", "blueprint")
    assert res.data["prompt"] and res.content == res.data["prompt"]

    # 2. 语料库可用：直接返回标签串
    stub = _StubPool(True)
    monkeypatch.setattr(gacha_mod, "zako_prompt_pool", stub)
    monkeypatch.setattr(cfg.tools, "art_gacha_zako_share", 1.0)
    res_zako = await art_gacha_tool(ctx)
    assert res_zako.success is True
    assert res_zako.data["source"] == "zako"
    assert res_zako.content == "1girl, apron, kitchen, smile, sunlight"
    assert stub.calls and stub.calls[0]["ratings"] == cfg.tools.art_gacha_zako_ratings

    # 3. 内置池：多次抽取覆盖到槽位与蓝图两种来源
    monkeypatch.setattr(gacha_mod, "zako_prompt_pool", _StubPool(False))
    sources = set()
    prompts = set()
    for _ in range(40):
        r = await art_gacha_tool(ctx)
        sources.add(r.data["source"])
        prompts.add(r.data["prompt"])
    assert {"slot", "blueprint"} <= sources
    assert len(prompts) > 5


async def test_generate_image_native_400_compatibility_fallback(monkeypatch, tmp_path):
    """当上游 wan 原生接口对 seed 或特殊画幅返回 HTTP 400 时，自动降级参数重试成功。"""
    monkeypatch.setattr(cfg.api, "image_gen_api_key", "test-key")
    monkeypatch.setattr(cfg.api, "image_gen_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(cfg.model, "image_gen", "wan2.7-image")

    posted_params = []

    class FakeResp:
        def __init__(self, status, data=None, body=b""):
            self.status = status
            self._data = data or {}
            self._body = body

        async def json(self, content_type=None):
            return self._data

        async def read(self):
            return self._body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, url, headers=None, json=None):
            params = dict((json or {}).get("parameters") or {})
            posted_params.append(params)
            # 模拟前两次（带 seed、以及非 1024*1024 尺寸）被模型拒绝返回 400，降级到 1024*1024 时成功
            if "seed" in params or params.get("size") == "1024x1536":
                return FakeResp(400, {"code": "InvalidParameter", "message": "unsupported parameter"})
            return FakeResp(
                200,
                {
                    "output": {
                        "choices": [
                            {"message": {"content": [{"image": "https://example.com/gen.png"}]}}
                        ]
                    }
                },
            )

        def get(self, url):
            return FakeResp(200, body=_TINY_PNG)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(tools_media.aiohttp, "ClientSession", FakeSession)
    ctx = _make_ctx("c_fallback")
    res = await tools_media.generate_image_tool(
        ctx,
        prompt="测试降级回退",
        aspect_ratio="2:3",
        seed=12345,
    )
    assert res.success is True
    assert len(posted_params) == 3
    assert posted_params[0] == {"size": "1024x1536", "n": 1, "seed": 12345}
    assert posted_params[1] == {"size": "1024x1536", "n": 1}
    assert posted_params[2] == {"size": "1024*1024", "n": 1}
    if res.data and res.data.get("file_path") and os.path.exists(res.data["file_path"]):
        os.remove(res.data["file_path"])


async def test_art_draw_failure_report_explains_reason(monkeypatch):
    """后台画失败时，汇报里要写清原因、错误码与下一步怎么办。"""
    async def fake_gen(context, **kwargs):
        return ToolResult(
            success=False,
            content="图像生成失败: API 返回 400: {'error': 'unsupported size'}",
            error="reference_not_supported",
        )

    class FakeHistory:
        def __init__(self):
            self.messages = []

        def append_session_message(self, chat_id, role, content, **extra):
            self.messages.append({"role": role, "content": content, **extra})

    history = FakeHistory()
    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", fake_gen)
    ctx = _make_ctx("c_fail", history=history)
    focus_manager.enter("c_fail", "art", goal="失败汇报")
    res = await art_draw_tool(ctx, prompt="A very long prompt", assets=["yuki"])
    assert res.success is True

    job = await art_gen_store.wait(res.data["job_id"])
    assert job.status == "failed"
    report = history.messages[0]["content"]
    assert "【画图失败】" in report
    assert "- 原因: 图像生成失败: API 返回 400" in report
    assert "错误码: reference_not_supported" in report
    assert "去掉 assets / image_paths 再画" in report


async def test_art_gacha_uses_zako_corpus_when_enabled(monkeypatch):
    """外部语料库开启时 art_gacha 吐标签串；关掉总开关就回落内置词条池。"""
    from core import art_gacha as gacha_mod

    ctx = _make_ctx("c_gacha_src")
    focus_manager.enter("c_gacha_src", "art", goal="语料库抽卡")

    fake = _StubPool(True)
    monkeypatch.setattr(gacha_mod, "zako_prompt_pool", fake)
    monkeypatch.setattr(cfg.tools, "art_gacha_zako_share", 1.0)

    res = await art_gacha_tool(ctx)
    assert res.data["source"] == "zako"
    assert fake.calls[0]["ratings"] == cfg.tools.art_gacha_zako_ratings
    assert fake.calls[0]["exclude_topics"] == cfg.tools.art_gacha_zako_exclude_topics

    monkeypatch.setattr(cfg.tools, "art_gacha_zako_enabled", False)
    res2 = await art_gacha_tool(ctx)
    assert res2.data["source"] in ("slot", "blueprint")


def test_zako_clean_tags_strips_disambiguation_and_duplicates(tmp_path):
    """语料标签清洗：去掉消歧义标签与重复项；无分类表时只做这两步。"""
    from core.zako_prompt_pool import ZakoPromptPool, clean_tag_text

    assert clean_tag_text("hasumi (blue archive), 1girl, smile, smile") == "1girl, smile"
    assert clean_tag_text("star (sky), night") == "night"
    assert clean_tag_text("raiden shogun (genshin impact), apron") == "apron"

    bare = ZakoPromptPool(base_dir=str(tmp_path))
    assert bare.available() is False
    assert bare.clean_tags("1girl, apron, apron") == "1girl, apron"
    assert bare.sample() is None
