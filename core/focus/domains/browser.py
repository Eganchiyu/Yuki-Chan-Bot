# core/focus/domains/browser.py
"""浏览器聚焦域声明与入口/退出工具实现。"""
from __future__ import annotations

import time
from typing import Any

from core.browser_driver import BROWSER_LOCK, BrowserUnavailableError, driver
from core.browser_tree import format_browser_tree
from core.focus.domain import BASE_KEEP_TOOLS, FocusDomain
from core.focus.manager import focus_manager, register_domain
from core.focus.tools import make_focus_finish_handler
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")


def _browser_stub(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    action = data.get("action")
    if action:
        steps = data.get("steps") or []
        step_str = f" ({' / '.join(str(s) for s in steps[:3])})" if steps else ""
        return f"browser_action {action}{step_str}"
    return str(payload.get("content") or "").replace("\n", " ")

BROWSER = FocusDomain(
    name="browser",
    title="浏览器",
    entry_tool="browser_start",
    exit_tool="browser_finish",
    domain_tools=frozenset({"browser_action"}),
    keep_tools=BASE_KEEP_TOOLS,
    summary_prefix="【浏览器操作总结】",
    exit_hint=(
        "（你已结束本轮浏览并收起浏览器窗口，回到聊天中。"
        "请保持你平时作为 Yuki 的可爱灵巧语气和自己的主见自然回复，别写 AI 腔或机械汇报流水账。）"
    ),
    idle_turns_key="browser_focus_idle_turns",
    max_rounds_key="browser_focus_max_rounds",
    default_fallback="已完成浏览器浏览与操作。",
    empty_trace_fallback="已打开浏览器查看了页面内容。",
    stub=_browser_stub,
)

register_domain(BROWSER)

_YUKI_BROWSER_GUIDE = (
    "【已进入浏览器聚焦模式】已展开 browser_action / browser_finish，并收起其他无关日常工具。\n"
    "- 保持你自己的样子：像 Yuki 平常坐在电脑前自己逛网页那样灵巧、带点好奇心和主见去操作与判断，"
    "决定要看什么、点哪个按钮、什么时候顺手吐槽或发给主人/群友看；千万不要用客服腔、AI腔或机械流水账汇报每一步。\n"
    "- 页面阅读法：下面给的是「[页面文本]」和按常用/显眼程度**降序编好号**的 Top 24 主视觉控件（`#1` 最关键，含少量 `[Bar]` 栏位重要按钮）。\n"
    "- 截图按需省流量：首屏会附一张 720p 大号红框标注图；后续控件明确时会自动跳过截图，只靠交互树+文本就能飞快操作；"
    "一旦你觉得画面看不准或想亲眼看一眼图，随时传 `screenshot=\"high\"` 或 `action=\"screenshot\"` 自己叫图！\n"
    "- 逛完/办完事请调 `browser_finish(summary=\"...\")` 收起浏览器，再用平时聊天口吻自然说出你的发现或感想。"
)


async def browser_start_tool(context: Any, goal: str = "", url: str = "") -> ToolResult:
    """打开或接管宿主机 Chrome 进入浏览器聚焦模式，返回首屏交互树与 720p 标注截图。"""
    from core.tools.tools_browser import _LAST_BROWSER_TREES, collect_browser_state

    t0 = time.monotonic()
    cid = str(getattr(context, "chat_id", "") or "default")
    history = (
        (context.metadata or {}).get("history_manager")
        if isinstance(context.metadata, dict)
        else None
    )
    focus_manager.enter(cid, BROWSER.name, goal=goal, history=history)
    if goal:
        focus_manager.record_step(cid, f"打开浏览器: {goal}", domain=BROWSER.name)

    try:
        async with BROWSER_LOCK:
            await driver.ensure_connected()
            dest = (url or "").strip()
            if dest:
                await driver.navigate(dest)
            else:
                await driver.wait_until_stable(timeout=3.0)
            tree, attachment, shot_hint, _ = await collect_browser_state(
                context,
                screenshot_mode="blur",
                is_entry=True,
            )
            _LAST_BROWSER_TREES[cid] = tree
    except BrowserUnavailableError as exc:
        focus_manager.abort(cid, BROWSER.name)
        return ToolResult(
            success=False,
            content=str(exc),
            data={"focus": "aborted", "browser_focus": "aborted", "no_persist": True},
            error="browser_unavailable",
            name="browser_start",
        )
    except Exception as exc:
        focus_manager.abort(cid, BROWSER.name)
        logger.warning(f"[BrowserFocus] 启动失败: {exc}")
        return ToolResult(
            success=False,
            content=f"浏览器启动/打开页面失败: {exc}",
            data={"focus": "aborted", "browser_focus": "aborted", "no_persist": True},
            error="browser_start_failed",
            name="browser_start",
        )

    tree_text = format_browser_tree(tree)
    shot_line = (
        f"\n已附首屏 720p 标注截图 {shot_hint}（大号红框/橙框编号与上面 [#编号] 一一对应）"
        if shot_hint
        else ""
    )
    content = f"{_YUKI_BROWSER_GUIDE}\n\n{tree_text}{shot_line}"
    return ToolResult(
        success=True,
        content=content,
        data={
            "focus": "entered",
            "browser_focus": "entered",
            "goal": goal or "",
            "url": tree.get("url") or "",
            "title": tree.get("title") or "",
            "node_count": len(tree.get("nodes") or []),
            "screenshot": attachment,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "no_persist": False,
        },
        name="browser_start",
    )


browser_finish_tool = make_focus_finish_handler(BROWSER)
