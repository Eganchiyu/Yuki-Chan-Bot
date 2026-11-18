# core/tools/tools_browser.py
"""浏览器操作工具：通过 CDP 控制宿主机 Chrome，配合主视觉交互树与按需 720p 大号截图标注。"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from core.browser_driver import (
    BROWSER_LOCK,
    BrowserActionError,
    BrowserUnavailableError,
    driver,
)
from core.browser_tree import (
    VIEWPORT_PROBE_JS,
    annotate_browser_screenshot,
    assess_visual_clarity,
    build_browser_tree,
    format_browser_tree,
)
from core.focus.manager import focus_manager
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

_SCREENSHOT_DIR = os.path.join(os.path.abspath(BASE_DIR), "temp", "browser_shots")
_LAST_BROWSER_TREES: dict[str, dict[str, Any]] = {}


def _browser_stub(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    action = data.get("action")
    if action:
        steps = data.get("steps") or []
        step_str = f" ({' / '.join(str(s) for s in steps[:3])})" if steps else ""
        return f"browser_action {action}{step_str}"
    return str(payload.get("content") or "").replace("\n", " ")


def _index_of(target: Any) -> int | None:
    raw = str(target or "").lstrip("#").strip()
    return int(raw) if raw.isdigit() else None


def _parse_coords(target: Any) -> tuple[int, int] | None:
    if isinstance(target, str) and "," in target:
        parts = [p.strip() for p in target.split(",", 1)]
        try:
            return int(float(parts[0])), int(float(parts[1]))
        except ValueError:
            return None
    return None


def _resolve_point(target: Any, tree: dict[str, Any]) -> tuple[int, int, str]:
    coords = _parse_coords(target)
    if coords is not None:
        return coords[0], coords[1], f"@({coords[0]},{coords[1]})"
    idx = _index_of(target)
    if idx is None:
        raise ValueError("target 需要控件编号（如 1 或 #1）或坐标 \"x,y\"")
    node = next((n for n in (tree.get("nodes") or []) if n.get("index") == idx), None)
    if node is None:
        raise BrowserActionError(f"当前视口没有 [#{idx}] 这个控件，请先 inspect 看看最新界面。")
    label = (node.get("label") or "")[:20] or "控件"
    return int(node["cx"]), int(node["cy"]), f"#{idx}({label})"


def _register_screenshot(context: Any, jpeg_bytes: bytes) -> tuple[dict | None, str]:
    store = getattr(context, "image_store", None)
    if store is not None:
        try:
            index = store.register(jpeg_bytes, url="browser_screenshot", ext=".jpg")
            attachment = store.attachment(index)
            if attachment:
                return attachment, f"[img:{index}]"
        except Exception as exc:
            logger.warning(f"[Browser] 注册截图失败: {exc}")
    try:
        os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
        path = os.path.join(_SCREENSHOT_DIR, f"browser_{os.getpid()}.jpg")
        with open(path, "wb") as f:
            f.write(jpeg_bytes)
        return None, path
    except OSError as exc:
        logger.warning(f"[Browser] 保存截图失败: {exc}")
        return None, ""


async def collect_browser_state(
    context: Any,
    *,
    screenshot_mode: str = "auto",
    is_entry: bool = False,
) -> tuple[dict[str, Any], dict | None, str, str]:
    """抽取当前浏览器主视觉交互树，并按策略决定是否附带 720p/高清标注截图。"""
    frames = await driver.collect_frames_snapshot(VIEWPORT_PROBE_JS)
    tree = build_browser_tree(frames)

    mode = (screenshot_mode or "auto").strip().lower()
    if mode not in ("auto", "blur", "low", "high", "none"):
        mode = "auto"

    is_clear, clarity_reason = assess_visual_clarity(tree, is_entry=is_entry)
    want_shot = False
    high_res = False
    if mode == "high":
        want_shot = True
        high_res = True
    elif mode in ("blur", "low"):
        want_shot = True
        high_res = False
    elif mode == "none":
        want_shot = False
    else:
        want_shot = not is_clear

    attachment = None
    shot_hint = ""
    if want_shot:
        try:
            raw_png = await driver.capture_screenshot()
            annotated = annotate_browser_screenshot(raw_png, tree, high_res=high_res)
            if annotated:
                attachment, shot_hint = _register_screenshot(context, annotated)
        except Exception as exc:
            logger.warning(f"[Browser] 截图标注失败: {exc}")

    return tree, attachment, shot_hint, clarity_reason


async def browser_action_tool(
    context: Any,
    action: str = "inspect",
    target: str | None = None,
    text: str = "",
    url: str = "",
    key: str = "",
    direction: str = "down",
    screenshot: str = "auto",
    clear: bool = False,
    seconds: float = 1.0,
    note: str = "",
    remember: bool = True,
) -> ToolResult:
    """在浏览器聚焦模式下查看或操控宿主机 Chrome 页面。"""
    t0 = time.monotonic()
    act = (action or "inspect").strip().lower()
    cid = str(getattr(context, "chat_id", "") or "default")
    shot_mode = (screenshot or "auto").strip().lower()
    if act in ("screenshot", "截图", "看图"):
        act = "inspect"
        if shot_mode in ("auto", "none", ""):
            shot_mode = "high"

    steps: list[str] = []
    tab_summary = ""

    try:
        async with BROWSER_LOCK:
            await driver.ensure_connected()
            last_tree = _LAST_BROWSER_TREES.get(cid)

            if act in ("inspect", "查看", "看看"):
                await driver.wait_until_stable(timeout=2.5)
                steps.append("inspect" if shot_mode != "high" else "screenshot(high)")

            elif act in ("open", "goto", "打开", "跳转"):
                dest = (url or target or "").strip()
                await driver.navigate(dest)
                steps.append(f"open {dest[:60]}")

            elif act in ("click", "tap", "点击", "double_click", "双击", "hover", "悬停"):
                if not last_tree:
                    frames = await driver.collect_frames_snapshot(VIEWPORT_PROBE_JS)
                    last_tree = build_browser_tree(frames)
                px, py, label = _resolve_point(target, last_tree)
                if act in ("hover", "悬停"):
                    await driver.hover_at(px, py)
                    steps.append(f"hover {label}")
                elif act in ("double_click", "双击"):
                    await driver.click_at(px, py, click_count=2)
                    steps.append(f"double_click {label}")
                else:
                    await driver.click_at(px, py)
                    steps.append(f"click {label}")

            elif act in ("input", "type", "输入"):
                if not text:
                    raise ValueError("input 需要 text 参数")
                px, py = None, None
                prefix = ""
                if target is not None and str(target).strip():
                    if not last_tree:
                        frames = await driver.collect_frames_snapshot(VIEWPORT_PROBE_JS)
                        last_tree = build_browser_tree(frames)
                    px, py, label = _resolve_point(target, last_tree)
                    prefix = f"{label} + "
                await driver.input_text(text, x=px, y=py, clear=bool(clear))
                steps.append(f'{prefix}input "{text[:20]}"')

            elif act in ("press", "key", "按键"):
                k = (key or str(target or "")).strip()
                await driver.press_key(k)
                steps.append(f"press {k}")

            elif act in ("scroll", "滚动", "滑动"):
                px, py = None, None
                if target is not None and str(target).strip():
                    if not last_tree:
                        frames = await driver.collect_frames_snapshot(VIEWPORT_PROBE_JS)
                        last_tree = build_browser_tree(frames)
                    px, py, _ = _resolve_point(target, last_tree)
                d = (direction or "down").strip().lower()
                await driver.scroll(d, x=px, y=py)
                steps.append(f"scroll {d}")

            elif act in ("back", "后退", "返回"):
                moved = await driver.go_back()
                steps.append("back" if moved else "back(已是首页)")

            elif act in ("forward", "前进"):
                moved = await driver.go_forward()
                steps.append("forward" if moved else "forward(无下一页)")

            elif act in ("reload", "refresh", "刷新"):
                await driver.reload()
                steps.append("reload")

            elif act in ("wait", "等待"):
                sec = max(0.2, min(float(seconds or 1.0), 8.0))
                await asyncio.sleep(sec)
                await driver.wait_until_stable(timeout=3.0)
                steps.append(f"wait {sec:.1f}s")

            elif act in ("tabs", "list_tabs", "标签页"):
                tabs = await driver.list_tabs()
                lines = [
                    f"[#{t['index']}] {'*当前* ' if t['active'] else ''}{t['title'] or '无标题'} | {t['url']}"
                    for t in tabs[:15]
                ]
                tab_summary = "当前打开的标签页：\n" + ("\n".join(lines) if lines else "（暂无标签页）")
                steps.append("tabs")

            elif act in ("switch_tab", "切标签"):
                if target is None or not str(target).strip():
                    raise ValueError("switch_tab 需要 target 指定标签页编号（如 2）或标题/URL关键词")
                switched = await driver.switch_tab(target)
                await driver.wait_until_stable(timeout=3.0)
                steps.append(f"switch_tab #{switched.get('index')} {switched.get('title', '')[:20]}")

            elif act in ("new_tab", "新标签"):
                dest = (url or str(target or "") or "about:blank").strip()
                await driver.new_tab(dest)
                steps.append(f"new_tab {dest[:40]}")

            elif act in ("close_tab", "关标签"):
                closed = await driver.close_tab(target)
                await driver.ensure_connected()
                steps.append(f"close_tab {str(closed)[:24]}")

            else:
                raise ValueError(f"不支持的浏览器 action: {action}")

            tree, attachment, shot_hint, clarity_reason = await collect_browser_state(
                context,
                screenshot_mode=shot_mode,
            )
            _LAST_BROWSER_TREES[cid] = tree

    except BrowserUnavailableError as exc:
        return ToolResult(
            success=False,
            content=str(exc),
            error="browser_unavailable",
            data={"action": act, "note": note or ""},
            name="browser_action",
        )
    except (ValueError, BrowserActionError) as exc:
        return ToolResult(
            success=False,
            content=str(exc),
            error="invalid_action",
            data={"action": act, "note": note or ""},
            name="browser_action",
        )
    except TimeoutError as exc:
        return ToolResult(
            success=False,
            content=f"浏览器操作超时: {exc}",
            error="timeout",
            data={"action": act, "note": note or ""},
            name="browser_action",
        )
    except Exception as exc:
        logger.error(f"[Browser] {act} 失败: {exc}")
        return ToolResult(
            success=False,
            content=f"浏览器操作失败: {exc}",
            error="action_failed",
            data={"action": act, "note": note or ""},
            name="browser_action",
        )

    if act != "inspect" or focus_manager.is_focused(cid, "browser"):
        focus_manager.record_step(cid, " / ".join(steps), note, domain="browser")

    lines = [f"已完成: {' / '.join(steps)}"]
    if tab_summary:
        lines.append(tab_summary)
    lines.append(format_browser_tree(tree))
    if shot_hint:
        kind_label = "高清截图" if shot_mode == "high" else "720p 标注截图"
        lines.append(f"已附{kind_label} {shot_hint}（大号红框/橙框编号与上面 [#编号] 一一对应）")
    else:
        lines.append(
            f"（控件与文本明确 [{clarity_reason}]，已省去截图；如需确认视觉细节可传 screenshot=\"high\" 或 action=\"screenshot\"）"
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return ToolResult(
        success=True,
        content="\n".join(lines),
        data={
            "action": act,
            "steps": steps,
            "url": tree.get("url") or "",
            "title": tree.get("title") or "",
            "node_count": len(tree.get("nodes") or []),
            "clarity": clarity_reason,
            "screenshot": attachment,
            "note": note or "",
            "elapsed_ms": elapsed_ms,
            "no_persist": not remember,
        },
        name="browser_action",
    )
