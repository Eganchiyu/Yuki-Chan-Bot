"""艺术创作聚焦模式 (art) 与艺术资产管理 (ArtAssetStore) 单元测试。"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from config import cfg
from core.art_assets import ArtAssetStore, art_asset_store
from core.focus import ToolView, focus_manager
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
        "skip",
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

    custom_asset_dir = os.path.join(tools_media.BASE_DIR, "output", "assets", "character", "_pytest_tmp")
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
        assert saved_asset["reference"].startswith("output/assets/character/_pytest_tmp/")
        assert os.path.isfile(os.path.join(tools_media.BASE_DIR, saved_asset["reference"]))

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
    assert captured["background"] == "transparent"
    assert captured["output_format"] == "png"
    assert captured["input_fidelity"] is None

    # 未知资产名给出清晰提示
    bad_res = await art_draw_tool(ctx, prompt="测试", assets=["不存在的群友"])
    assert bad_res.success is False
    assert bad_res.error == "asset_not_found"


async def test_art_start_contains_director_guide_and_art_draw_preview(monkeypatch, tmp_path):
    """art_start 返回导演指南与默认禁透明规则；art_draw 成品自动附带预览 screenshot。"""
    ctx_start = _make_ctx("c_guide")
    start_res = await art_start_tool(ctx_start, goal="画海报")
    assert "二次元艺术总监生图指南" in start_res.content
    assert "opaque" in start_res.content
    assert "严禁擅自生成透明背景" in start_res.content

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

    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", fake_gen)
    ctx_draw = _make_ctx("c_preview", image_store=store)
    focus_manager.enter("c_preview", "art", goal="自检测试")
    res = await art_draw_tool(ctx_draw, prompt="An anime girl at sunset")
    assert res.success is True
    assert isinstance(res.data.get("screenshot"), dict)
    assert res.data["screenshot"]["index"] == "001"
    assert "已附带成品预览 [img:001]" in res.content


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


async def test_art_gacha_draws_prompt_draft_without_generating_image(monkeypatch):
    """art_gacha 只返回可编辑的抽卡提示词草稿，绝不直接触发生图。"""
    called = False

    async def forbid_gen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("art_gacha should not call generate_image_tool directly")

    monkeypatch.setattr("core.tools.tools_media.generate_image_tool", forbid_gen)
    ctx = _make_ctx("c_gacha")
    focus_manager.enter("c_gacha", "art", goal="盲盒抽卡")

    # 1. 槽位混搭 + lock + 绑定 yuki 资产
    res_slot = await art_gacha_tool(
        ctx,
        pool="slot",
        assets=["yuki"],
        lock={"style": "千禧初高精剧场版原画", "setting": "at a snowy train station"},
        note="冬日车站盲盒",
    )
    assert res_slot.success is True
    assert called is False
    assert res_slot.data["mode"] == "slot"
    assert res_slot.data["assets"] == ["yuki"]
    assert "Yuki" in res_slot.data["prompt"]
    assert "at a snowy train station" in res_slot.data["prompt"]
    assert "early-2000s high-end anime key visual" in res_slot.data["prompt"]
    assert "尚未生图" in res_slot.content
    assert "art_draw" in res_slot.content

    # 2. SSR 蓝图抽卡 + 变量覆写
    res_bp = await art_gacha_tool(
        ctx,
        pool="blueprint",
        blueprint_id="vtuber-stream-thumbnail",
        assets=["yuki"],
        lock={"line 1": "深夜", "line 2": "杂谈"},
    )
    assert res_bp.success is True
    assert called is False
    assert res_bp.data["rarity"] == "SSR"
    assert res_bp.data["aspect_ratio"] == "16:9"
    assert "深夜" in res_bp.data["prompt"] and "杂谈" in res_bp.data["prompt"]

    # 3. 多人资产自动匹配双人蓝图
    res_multi = await art_gacha_tool(ctx, pool="blueprint", assets=["yuki", "master"])
    assert res_multi.success is True
    assert res_multi.data["card_id"] == "martial-dojo-duel"

    # 4. 未知资产 / 未知蓝图清晰报错
    bad_asset = await art_gacha_tool(ctx, assets=["不存在的角色"])
    assert bad_asset.success is False and bad_asset.error == "asset_not_found"

    bad_bp = await art_gacha_tool(ctx, blueprint_id="non-existent-bp")
    assert bad_bp.success is False and bad_bp.error == "invalid_gacha_param"


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
