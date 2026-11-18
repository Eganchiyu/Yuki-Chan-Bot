"""浏览器聚焦模式 (browser) 单元测试（全离线模拟 CDP 与 DOM 快照）。"""
from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from core.browser_driver import BrowserUnavailableError, normalize_url
from core.browser_tree import (
    annotate_browser_screenshot,
    assess_visual_clarity,
    build_browser_tree,
    format_browser_tree,
)
from core.focus import ToolView, focus_manager
from core.focus.domains.browser import BROWSER, browser_finish_tool, browser_start_tool
from core.toolchain import FunctionRegistry, ToolContext, ToolRuntime
from core.tools import TOOL_SPECS
from core.tools import tools_browser
from core.tools.tools_browser import _LAST_BROWSER_TREES, browser_action_tool


class _MemImageStore:
    def __init__(self) -> None:
        self.items: dict[int, bytes] = {}
        self._seq = 0

    def register(self, data: bytes, url: str = "", ext: str = ".jpg") -> int:
        self._seq += 1
        self.items[self._seq] = data
        return self._seq

    def attachment(self, index: int) -> dict:
        return {"index": index, "path": f"/tmp/fake_{index}.jpg"}


def _make_png_bytes(width: int = 1920, height: int = 1080) -> bytes:
    img = Image.new("RGB", (width, height), color=(32, 24, 44))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_ctx(chat_id: str = "c_browser", image_store=None) -> ToolContext:
    runtime = ToolRuntime(
        sender=SimpleNamespace(),
        yuki_state=SimpleNamespace(),
        image_store=image_store,
    )
    return ToolContext(
        chat_id=chat_id,
        mode="group",
        session=[],
        combined_text="",
        runtime=runtime,
        metadata={},
    )


@pytest.fixture(autouse=True)
def _clean_browser_state():
    focus_manager._states.clear()
    _LAST_BROWSER_TREES.clear()
    yield
    focus_manager._states.clear()
    _LAST_BROWSER_TREES.clear()


def test_default_and_focus_views_registered():
    reg = FunctionRegistry()
    reg.scan_and_register(TOOL_SPECS)

    default_view = ToolView.resolve(reg, focus_manager, "c_browser")
    assert "browser_start" in default_view.visible
    assert "browser_action" not in default_view.visible
    assert "browser_finish" not in default_view.visible

    focus_manager.enter("c_browser", BROWSER.name, goal="逛网站")
    focused_view = ToolView.resolve(reg, focus_manager, "c_browser")
    assert "browser_start" not in focused_view.visible
    assert {"browser_action", "browser_finish"} <= focused_view.visible


def test_normalize_url_rules():
    assert normalize_url("www.bilibili.com/toy/HENTI/index.html") == "https://www.bilibili.com/toy/HENTI/index.html"
    assert normalize_url("localhost:8777") == "https://localhost:8777"
    assert normalize_url("http://127.0.0.1:8777") == "http://127.0.0.1:8777"
    assert normalize_url("about:blank") == "about:blank"
    with pytest.raises(ValueError):
        normalize_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        normalize_url("javascript:alert(1)")


def test_tree_ranks_large_main_controls_first_and_caps_at_24_with_bar_quota():
    """主视觉大控件排前、按比例注入 Bar 重要控件、严格 ≤ 24、且跨 iframe 坐标正确偏移。"""
    main_controls = []
    # 25 个主区小链接（干扰项）
    for i in range(25):
        y = 100 + i * 22
        main_controls.append({
            "kind": "链接",
            "tag": "a",
            "role": "link",
            "label": f"普通条目{i}",
            "state": {},
            "region": "main",
            "bounds": [40, y, 160, y + 18],
            "is_primary": False,
            "has_graphic": False,
        })
    # 1 个大号主 CTA 按钮（在 iframe 内，应成为 #1）
    main_controls.append({
        "kind": "按钮",
        "tag": "button",
        "role": "button",
        "label": "开始测试 15 题",
        "state": {},
        "region": "main",
        "bounds": [200, 320, 560, 400],
        "is_primary": True,
        "has_graphic": False,
    })

    bar_controls = [
        {
            "kind": "按钮",
            "tag": "button",
            "role": "button",
            "label": "关注",
            "state": {},
            "region": "bar",
            "bounds": [1210, 200, 1260, 240],
            "is_primary": False,
            "has_graphic": True,
        },
        {
            "kind": "输入",
            "tag": "input",
            "role": "searchbox",
            "label": "搜索",
            "state": {"placeholder": "搜索内容"},
            "region": "bar",
            "bounds": [300, 10, 600, 44],
            "is_primary": False,
            "has_graphic": False,
        },
    ] + [
        {
            "kind": "链接",
            "tag": "a",
            "role": "link",
            "label": f"页脚条款{j}",
            "state": {},
            "region": "bar",
            "bounds": [100 + j * 80, 690, 170 + j * 80, 712],
            "is_primary": False,
            "has_graphic": False,
        }
        for j in range(6)
    ]

    frames = [
        {
            "_is_root": True,
            "_offset_x": 0.0,
            "_offset_y": 0.0,
            "title": "HENTI 测试shell",
            "url": "https://www.bilibili.com/toy/HENTI/index.html",
            "viewport": [1280, 720],
            "scroll": {"pct_y": 0, "can_down": False, "can_up": False},
            "has_modal": False,
            "interactive_canvas_ratio": 0.0,
            "controls": bar_controls,
            "text_blocks": [],
        },
        {
            "_is_root": False,
            "_offset_x": 6.0,
            "_offset_y": 6.0,
            "title": "HENTI inner",
            "url": "https://www.bilibilitoy.com/toy/HENTI/index.html",
            "viewport": [1204, 708],
            "scroll": {"pct_y": 0, "can_down": False, "can_up": False},
            "has_modal": False,
            "interactive_canvas_ratio": 0.0,
            "controls": main_controls,
            "text_blocks": [
                {"text": "穿越之后，你会成为谁？", "level": 1, "region": "main", "x": 120, "y": 140},
                # 与按钮文案完全重复的文本应自动剥离
                {"text": "开始测试 15 题", "level": 0, "region": "main", "x": 210, "y": 330},
            ],
        },
    ]

    tree = build_browser_tree(frames, max_nodes=24, bar_quota=5)
    nodes = tree["nodes"]
    assert len(nodes) == 24
    # 验证降序编号：#1 必为最大最核心的主按钮或搜索框，且大按钮坐标叠加了 iframe offset (+6,+6)
    top_labels = [n["label"] for n in nodes[:3]]
    assert "开始测试 15 题" in top_labels
    cta = next(n for n in nodes if n["label"] == "开始测试 15 题")
    assert cta["bounds"] == (206, 326, 566, 406)

    # Bar 重要控件按比例保留在 24 个之内，且重要项（搜索/关注）排在页脚条款前
    bar_in_tree = [n for n in nodes if n["region"] == "bar"]
    assert 2 <= len(bar_in_tree) <= 5
    bar_labels = [n["label"] for n in bar_in_tree]
    assert "搜索" in bar_labels and "关注" in bar_labels

    # 页面文本去重：保留 H1，剥离与按钮重复的文字
    assert any("[H1] 穿越之后，你会成为谁？" in line for line in tree["text_lines"])
    assert not any("开始测试 15 题" in line for line in tree["text_lines"])


def test_modal_controls_jump_to_top():
    frames = [{
        "_is_root": True,
        "_offset_x": 0.0,
        "_offset_y": 0.0,
        "title": "Demo",
        "url": "https://example.com",
        "viewport": [1280, 720],
        "scroll": {"pct_y": 0},
        "has_modal": True,
        "interactive_canvas_ratio": 0.0,
        "controls": [
            {"kind": "按钮", "tag": "button", "role": "button", "label": "后台按钮", "region": "main", "bounds": [100, 100, 400, 200]},
            {"kind": "按钮", "tag": "button", "role": "button", "label": "确认进入", "region": "modal", "bounds": [500, 400, 620, 444]},
        ],
        "text_blocks": [
            {"text": "首次测试提示说明", "level": 0, "region": "modal", "x": 450, "y": 300},
        ],
    }]
    tree = build_browser_tree(frames)
    assert tree["nodes"][0]["label"] == "确认进入"
    assert tree["nodes"][0]["index"] == 1
    assert "[弹窗] 首次测试提示说明" in tree["text_lines"]


def test_clarity_assessment_and_large_badge_annotation():
    clear_tree = {
        "interactive_canvas_ratio": 0.0,
        "nodes": [
            {"index": 1, "kind": "按钮", "label": "开始", "region": "main", "bounds": (100, 100, 300, 160)},
            {"index": 2, "kind": "按钮", "label": "设置", "region": "main", "bounds": (100, 180, 300, 240)},
            {"index": 3, "kind": "链接", "label": "记录", "region": "bar", "bounds": (100, 20, 200, 50)},
        ],
        "size": (1280, 720),
    }
    assert assess_visual_clarity(clear_tree, is_entry=True) == (False, "first_screen")
    assert assess_visual_clarity(clear_tree, is_entry=False) == (True, "clear")

    canvas_tree = {**clear_tree, "interactive_canvas_ratio": 0.52}
    assert assess_visual_clarity(canvas_tree, is_entry=False) == (False, "interactive_canvas")

    png = _make_png_bytes(1920, 1080)
    jpeg_720 = annotate_browser_screenshot(png, clear_tree, high_res=False)
    assert jpeg_720 is not None
    im = Image.open(io.BytesIO(jpeg_720))
    assert im.width == 1280 and im.height == 720

    jpeg_high = annotate_browser_screenshot(png, clear_tree, high_res=True)
    assert jpeg_high is not None
    im_hi = Image.open(io.BytesIO(jpeg_high))
    assert im_hi.width == 1600


async def test_browser_start_aborted_rolls_back_when_cdp_unavailable(monkeypatch):
    monkeypatch.setattr(
        tools_browser.driver,
        "ensure_connected",
        AsyncMock(side_effect=BrowserUnavailableError("未开启 9222")),
    )
    # browser_start 也导入了 driver
    from core.focus.domains import browser as browser_domain
    monkeypatch.setattr(
        browser_domain.driver,
        "ensure_connected",
        AsyncMock(side_effect=BrowserUnavailableError("未开启 9222")),
    )
    res = await browser_start_tool(_make_ctx("c_abort"), goal="看看网页")
    assert res.success is False
    assert res.data.get("focus") == "aborted"
    assert focus_manager.is_focused("c_abort") is False


async def test_browser_start_and_action_skip_shot_when_clear_or_take_high_on_demand(monkeypatch):
    store = _MemImageStore()
    fake_frames = [{
        "_is_root": True,
        "_offset_x": 0.0,
        "_offset_y": 0.0,
        "title": "HENTI",
        "url": "https://www.bilibili.com/toy/HENTI/index.html",
        "viewport": [1280, 720],
        "scroll": {"pct_y": 0, "can_down": False, "can_up": False},
        "has_modal": False,
        "interactive_canvas_ratio": 0.0,
        "controls": [
            {"kind": "按钮", "tag": "button", "role": "button", "label": "开始测试 15 题", "region": "main", "bounds": [100, 300, 420, 360], "is_primary": True},
            {"kind": "按钮", "tag": "button", "role": "button", "label": "精准测试 30 题", "region": "main", "bounds": [100, 380, 420, 440]},
            {"kind": "按钮", "tag": "button", "role": "button", "label": "测试记录", "region": "main", "bounds": [100, 460, 420, 520]},
            {"kind": "按钮", "tag": "button", "role": "button", "label": "点赞", "region": "bar", "bounds": [1216, 200, 1270, 240]},
        ],
        "text_blocks": [{"text": "穿越之后，你会成为谁？", "level": 1, "region": "main", "x": 100, "y": 140}],
    }]
    png = _make_png_bytes(1280, 720)

    monkeypatch.setattr(tools_browser.driver, "ensure_connected", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(tools_browser.driver, "navigate", AsyncMock(return_value={"settled": True}))
    monkeypatch.setattr(tools_browser.driver, "wait_until_stable", AsyncMock(return_value={"settled": True}))
    monkeypatch.setattr(tools_browser.driver, "collect_frames_snapshot", AsyncMock(return_value=fake_frames))
    monkeypatch.setattr(tools_browser.driver, "capture_screenshot", AsyncMock(return_value=png))
    click_mock = AsyncMock()
    monkeypatch.setattr(tools_browser.driver, "click_at", click_mock)

    ctx = _make_ctx("c_run", image_store=store)
    start_res = await browser_start_tool(ctx, goal="测测 HENTI", url="https://www.bilibili.com/toy/HENTI/index.html")
    assert start_res.success is True
    assert focus_manager.is_focused("c_run", "browser") is True
    # 首屏必附一张 720p 截图
    assert start_res.data["screenshot"] is not None
    assert "开始测试 15 题" in start_res.content

    # 控件明确时：click #1 后自动跳过截图（不增加 store 截图数量）
    before_shots = len(store.items)
    click_res = await browser_action_tool(ctx, action="click", target="#1", note="点开始测试")
    assert click_res.success is True
    click_mock.assert_awaited_once_with(260, 330)
    assert click_res.data["screenshot"] is None
    assert len(store.items) == before_shots
    assert "已省去截图" in click_res.content

    # AI 主动调用截图（action="screenshot" -> 高清图）
    shot_res = await browser_action_tool(ctx, action="screenshot", note="看一眼画面细节")
    assert shot_res.success is True
    assert shot_res.data["screenshot"] is not None
    assert len(store.items) == before_shots + 1

    # 退出聚焦
    fin_res = await browser_finish_tool(ctx, summary="试玩了 B 站 HENTI 性格测试")
    assert fin_res.success is True
    assert focus_manager.is_focused("c_run") is False


async def test_switch_tab_handles_plain_text_activate_and_scroll_fallback(monkeypatch):
    """验证 /json/activate 返回纯文本不会误报 JSON 错误，且 mouseWheel 超时时自动降级 DOM scrollBy。"""
    from core.browser_driver import BrowserDriver

    drv = BrowserDriver()
    fake_tabs = [
        {"id": "t1", "type": "page", "title": "首页", "url": "https://a.com", "webSocketDebuggerUrl": "ws://x/1"},
        {"id": "t2", "type": "page", "title": "Bilibili", "url": "https://www.bilibili.com", "webSocketDebuggerUrl": "ws://x/2"},
    ]

    async def fake_http_req(path, *, method="GET", timeout=3.0):
        if path == "/json/list":
            import json
            return json.dumps(fake_tabs)
        if path.startswith("/json/activate/"):
            return "Target activated"
        return ""

    calls = []

    class FakeCdp:
        connected = True
        _nav_seq = 0
        _child_sessions = {}
        _visible_child_sids = set()

        async def call(self, method, params=None, *, session_id=None, timeout=10.0):
            calls.append((method, params))
            if method == "Input.dispatchMouseEvent" and (params or {}).get("type") == "mouseWheel":
                raise TimeoutError("wheel stalled")
            if method == "Runtime.evaluate":
                expr = (params or {}).get("expression") or ""
                if "innerWidth" in expr:
                    return {"result": {"value": {"w": 1280, "h": 720}}}
                if "scrollBy" in expr:
                    return {"result": {"value": True}}
            return {}

    fake_cdp = FakeCdp()
    monkeypatch.setattr(drv, "_http_request", fake_http_req)
    monkeypatch.setattr(drv, "_attach_target", AsyncMock())
    monkeypatch.setattr(drv, "ensure_connected", AsyncMock(return_value=fake_cdp))
    monkeypatch.setattr(drv, "wait_until_stable", AsyncMock(return_value={"settled": True}))

    drv._cdp = fake_cdp
    switched = await drv.switch_tab("2")
    assert switched["id"] == "t2"

    await drv.scroll("down")
    assert any(m == "Runtime.evaluate" and "scrollBy" in (p or {}).get("expression", "") for m, p in calls)

