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
    assert "art_asset" not in default_view.visible
    assert "art_finish" not in default_view.visible

    focus_manager.enter("c_art", ART.name, goal="画立绘")
    focused_view = ToolView.resolve(reg, focus_manager, "c_art")
    assert focused_view.visible == {
        "art_draw",
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
    """art_draw 支持同时选择多张登记资产图（如 yuki + 主人）并按 aspect_ratio 解析画幅。"""
    captured = {}

    async def fake_gen(context, prompt, size="1024*1024", image_paths=None, aspect_ratio=None, seed=None):
        captured["prompt"] = prompt
        captured["size"] = size
        captured["image_paths"] = image_paths
        captured["aspect_ratio"] = aspect_ratio
        captured["seed"] = seed
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
    assert captured["image_paths"] == [
        "output/assets/character/yuki_reference.png",
        "output/assets/character/master_reference.png",
    ]
    assert res.data["used_assets"] == ["yuki", "master"]

    # 未知资产名给出清晰提示
    bad_res = await art_draw_tool(ctx, prompt="测试", assets=["不存在的群友"])
    assert bad_res.success is False
    assert bad_res.error == "asset_not_found"


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
