# core/tools/tools_phone.py
"""手机操作工具：通过 adb 控制插在电脑上的 Android 手机。

设计要点（避免"对着看不见的屏幕猜坐标"）：
    1. 每次动作后自动等待界面刷新，并重新 dump 无障碍控件树；
    2. 控件树精简成 [#编号] + 中心坐标，模型只需传 target=编号 就能精准点按；
    3. 控件树文字信息不足、或模型主动要求时，附一张缩放到低分辨率的截图，
       并在图上把 [#编号] 画在对应控件位置（Set-of-Mark），既能看图又能对上号；
    4. 每次动作把「与编号无关的语义定位器」写进操作历史，存成组合技后可回放；
    5. 底层 ADB 通信委托给 core.phone_driver.AndroidDriver，内置安全护栏拦截密码与支付界面自动输入。
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import xml.etree.ElementTree as ET

from config import cfg
from core import phone_macro as pm
from core.phone_driver import ADB_KEYBOARD_IME, driver
from core.phone_focus import phone_focus_manager
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

# 常见 App 包名，方便模型直接 launch("美团")
APP_ALIASES = {
    "微信": "com.tencent.mm",
    "qq": "com.tencent.mobileqq",
    "支付宝": "com.eg.android.AlipayGphone",
    "淘宝": "com.taobao.taobao",
    "美团": "com.sankuai.meituan",
    "饿了么": "me.ele",
    "京东": "com.jingdong.app.mall",
    "抖音": "com.ss.android.ugc.aweme",
    "哔哩哔哩": "tv.danmaku.bili",
    "b站": "tv.danmaku.bili",
    "高德地图": "com.autonavi.minimap",
    "网易云音乐": "com.netease.cloudmusic",
    "设置": "com.android.settings",
    "浏览器": "com.huawei.browser",
    "华为浏览器": "com.huawei.browser",
    "备忘录": "com.huawei.notepad",
    "termux": "com.termux",
    "终端": "com.termux",
}

KEY_ALIASES = {
    "back": "KEYCODE_BACK",
    "返回": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "主页": "KEYCODE_HOME",
    "enter": "KEYCODE_ENTER",
    "确认": "KEYCODE_ENTER",
    "search": "KEYCODE_SEARCH",
    "tab": "KEYCODE_TAB",
    "delete": "KEYCODE_DEL",
    "backspace": "KEYCODE_DEL",
    "app_switch": "KEYCODE_APP_SWITCH",
    "recent": "KEYCODE_APP_SWITCH",
    "power": "KEYCODE_POWER",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "paste": "KEYCODE_PASTE",
}

# 会被写进操作历史的动作（inspect / wait 属于观察与等待，不进宏）
RECORDABLE_OPS = {"tap", "long_press", "input", "swipe", "key", "launch"}

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_SCREENSHOT_DIR = os.path.join(os.path.abspath(BASE_DIR), "temp", "phone_shots")


class PhoneStepError(RuntimeError):
    """单步执行失败（定位不到控件、adb 报错等）。"""


def _tools_cfg():
    return getattr(cfg, "tools", None)


# 模块级底层入口委托给 AndroidDriver 单例（保持旧接口与单元测试 monkeypatch 兼容）
_adb_cmd = driver.adb_cmd
_adb = driver.adb
_adb_text = driver.adb_text
_ensure_device = driver.ensure_device
_screencap = driver.screencap
_current_ime = driver.current_ime
_set_ime = driver.set_ime
_input_text = driver.input_text
_launch = driver.launch


def _parse_bounds(node) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.match(node.get("bounds", "") or "")
    if not match:
        return None
    x1, y1, x2, y2 = (int(v) for v in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _node_label(node) -> str:
    text = (node.get("text") or "").strip()
    desc = (node.get("content-desc") or "").strip()
    return text or desc


def _node_priority(item: dict) -> int:
    """节点截断优先级：输入(0) > 可点带文字(1) > 文本(2) > 滚动(3) > 无文字可点(4)。"""
    kind = item.get("kind")
    has_label = bool(item.get("label"))
    if kind == "输入":
        return 0
    if kind == "可点" and has_label:
        return 1
    if kind == "文本":
        return 2
    if kind == "滚动":
        return 3
    return 4


def _compact_tree(xml_text: str, max_nodes: int) -> dict:
    """把原始 uiautomator XML 精简成带编号的可操作节点列表。"""
    root = ET.fromstring(xml_text)
    # 真实 dump 里 package/bounds 挂在第一个 <node> 上，<hierarchy> 只带 rotation
    first_node = root.find("node")
    package = (
        root.get("package")
        or (first_node.get("package") if first_node is not None else "")
        or ""
    )
    root_bounds = (
        _parse_bounds(root)
        or (_parse_bounds(first_node) if first_node is not None else None)
        or (0, 0, 0, 0)
    )
    screen_area = max(1, (root_bounds[2] - root_bounds[0]) * (root_bounds[3] - root_bounds[1]))

    kept: list[dict] = []
    seen: set[tuple[str, tuple[int, int, int, int]]] = set()
    for node in root.iter("node"):
        if node.get("visible-to-user") == "false":
            continue
        bounds = _parse_bounds(node)
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        label = _node_label(node)
        cls = node.get("class") or ""
        res_id = (node.get("resource-id") or "").strip()
        is_password = node.get("password") == "true"
        clickable = node.get("clickable") == "true" or node.get("long-clickable") == "true"
        scrollable = node.get("scrollable") == "true"
        editable = "EditText" in cls or is_password
        area = (x2 - x1) * (y2 - y1)
        if not (label or clickable or scrollable or editable):
            continue
        # 防误杀全屏交互容器：当 scrollable 为 true 时，即使无 label 且面积 >= 0.9 也保留
        if not label and not scrollable and area >= screen_area * 0.9:
            continue
        key = (label, bounds)
        if key in seen:
            continue
        # 父节点先入列：同文案的子节点落在已保留节点范围内时跳过，点父节点命中率更高
        if label and any(
            item["label"] == label
            and item["bounds"][0] <= x1 and item["bounds"][1] <= y1
            and item["bounds"][2] >= x2 and item["bounds"][3] >= y2
            for item in kept
        ):
            continue
        seen.add(key)

        if editable:
            kind = "输入"
        elif clickable:
            kind = "可点"
        elif scrollable:
            kind = "滚动"
        else:
            kind = "文本"

        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        candidate = {
            "label": label[:60],
            "kind": kind,
            "cls": cls,
            "id": res_id,
            "password": is_password,
            "bounds": bounds,
            "cx": center[0],
            "cy": center[1],
            "_area": area,
        }

        # 中心点重合且 kind 相同时：保留面积更小（更具体）的节点，防止外层透明容器吃掉内层按钮
        dup_idx = next(
            (i for i, item in enumerate(kept) if item["kind"] == kind and (item["cx"], item["cy"]) == center),
            None,
        )
        if dup_idx is not None:
            if area < kept[dup_idx].get("_area", area + 1):
                kept[dup_idx] = candidate
            continue

        kept.append(candidate)

    # 智能截断：当超出 max_nodes 时，先按优先级排序截取前 max_nodes 个，再按屏幕从上到下、从左到右重新排列并分配 index
    if max_nodes and max_nodes > 0 and len(kept) > max_nodes:
        kept.sort(key=lambda item: (_node_priority(item), item["cy"], item["cx"]))
        kept = kept[:max_nodes]
        kept.sort(key=lambda item: (item["cy"], item["cx"], item["bounds"][1], item["bounds"][0]))

    for index, item in enumerate(kept, 1):
        item.pop("_area", None)
        item["index"] = index
    return {
        "package": package,
        "size": (root_bounds[2] - root_bounds[0], root_bounds[3] - root_bounds[1]),
        "nodes": kept,
    }


def _format_tree(tree: dict) -> str:
    width, height = driver.resolve_screen_size(tree)
    lines = [f"[手机屏幕] 应用: {tree['package'] or '未知'} | 尺寸: {width}x{height}"]
    if not tree["nodes"]:
        lines.append("(这个界面没有可识别的控件，可能还在加载，或需要用截图确认)")
    for item in tree["nodes"]:
        label = item["label"] or "(无文字)"
        lines.append(f"[#{item['index']}] [{item['kind']}] {label} @({item['cx']},{item['cy']})")
    return "\n".join(lines)


def _annotate_screenshot(png_bytes: bytes, tree: dict) -> bytes | None:
    """缩放截图并把 [#编号] 画在控件位置上，返回 JPEG 字节。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("[Phone] 缺少 Pillow，跳过截图标注")
        return None

    max_width = int(getattr(_tools_cfg(), "phone_screenshot_max_width", 720) or 720)
    quality = int(getattr(_tools_cfg(), "phone_screenshot_quality", 70) or 70)
    try:
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception as exc:
        logger.warning(f"[Phone] 截图解码失败: {exc}")
        return None

    scale = min(1.0, max_width / max(1, image.width))
    if scale < 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(image)
    for item in tree["nodes"]:
        x1, y1, x2, y2 = (int(v * scale) for v in item["bounds"])
        draw.rectangle([x1, y1, x2, y2], outline=(255, 64, 64), width=2)
        label = f"#{item['index']}"
        tx, ty = max(0, x1), max(0, y1 - 12)
        draw.rectangle([tx, ty, tx + 8 * len(label) + 4, ty + 12], fill=(255, 64, 64))
        draw.text((tx + 2, ty), label, fill=(255, 255, 255))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _register_screenshot(context, jpeg_bytes: bytes) -> tuple[dict | None, str]:
    """把截图注册进图片索引，返回 (附件引用, 提示文本)。"""
    store = getattr(context, "image_store", None)
    if store is not None:
        try:
            index = store.register(jpeg_bytes, url="phone_screenshot", ext=".jpg")
            attachment = store.attachment(index)
            if attachment:
                return attachment, f"[img:{index}]"
        except Exception as exc:
            logger.warning(f"[Phone] 注册截图失败: {exc}")
    try:
        os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
        path = os.path.join(_SCREENSHOT_DIR, f"phone_{os.getpid()}.jpg")
        with open(path, "wb") as f:
            f.write(jpeg_bytes)
        return None, path
    except OSError as exc:
        logger.warning(f"[Phone] 保存截图失败: {exc}")
        return None, ""


async def _dump_tree(max_nodes: int) -> dict:
    xml_text = await driver.dump_xml()
    tree = _compact_tree(xml_text, max_nodes)
    driver.resolve_screen_size(tree)
    return tree


def _resolve_target(target) -> tuple[int, int] | None:
    """target 支持 "x,y" 坐标串。控件编号由调用方先行解析。"""
    if isinstance(target, str) and "," in target:
        try:
            x, y = target.split(",", 1)
            return int(float(x)), int(float(y))
        except ValueError:
            return None
    return None


# ---------------- 单步步骤：构造 / 执行 / 校验 ----------------

def _index_of(target) -> int | None:
    raw = str(target or "").lstrip("#").strip()
    return int(raw) if raw.isdigit() else None


def _find_node(tree: dict, index: int) -> dict:
    node = next((n for n in tree["nodes"] if n["index"] == index), None)
    if not node:
        raise PhoneStepError(f"没有 [#{index}] 这个控件，请重新 inspect 当前界面。")
    return node


def _node_point_step(op: str, node: dict, tree: dict, **extra) -> dict:
    return {
        "op": op,
        "label": (node.get("label") or "")[:40],
        "loc": pm.build_locator(node, tree),
        **extra,
    }


def _screen_dimensions(tree: dict) -> tuple[int, int]:
    w, h = driver.resolve_screen_size(tree)
    if w > 0 and h > 0:
        return w, h
    # 若设备尚未缓存物理分辨率且 tree 无尺寸，使用安全正数比例基准
    return 1, 1


def _swipe_coords(tree: dict, target, direction: str) -> tuple[float, float, float, float, str]:
    width, height = _screen_dimensions(tree)
    parts = [float(v) for v in re.split(r"[,\s]+", str(target or "")) if v.strip()]
    if len(parts) == 4:
        return parts[0], parts[1], parts[2], parts[3], "自定义坐标"
    cx, cy = width // 2, height // 2
    span = height // 4
    mapping = {
        "up": (cx, cy + span, cx, cy - span),
        "down": (cx, cy - span, cx, cy + span),
        "left": (cx + span, cy, cx - span, cy),
        "right": (cx - span, cy, cx + span, cy),
    }
    direction = (direction or "up").strip().lower()
    if direction not in mapping:
        raise ValueError("direction 只能是 up/down/left/right")
    x1, y1, x2, y2 = mapping[direction]
    return x1, y1, x2, y2, direction


async def _prepare_step(action: str, tree: dict, *, target=None, text="", direction="up",
                        duration=300, app="", seconds=1.0) -> tuple[dict | None, str]:
    """把一次工具调用翻译成可记录的单步。inspect 返回 (None, 展示文本)。"""
    if action in ("inspect", "查看", "看看"):
        return None, "inspect"

    if action in ("tap", "click", "点击"):
        coords = _resolve_target(target)
        if coords:
            step = {"op": "tap", "label": "", "loc": pm.locator_at(coords[0], coords[1], tree)}
            return step, f"tap ({coords[0]},{coords[1]})"
        index = _index_of(target)
        if index is None:
            raise ValueError("tap 需要 target=控件编号 或 target=\"x,y\"")
        node = _find_node(tree, index)
        step = _node_point_step("tap", node, tree)
        return step, f"tap #{index}({node['label'][:12] or '无文字'})"

    if action in ("long_press", "longpress", "长按"):
        coords = _resolve_target(target)
        if coords:
            step = {
                "op": "long_press",
                "label": "",
                "loc": pm.locator_at(coords[0], coords[1], tree),
            }
            return step, f"long_press ({coords[0]},{coords[1]})"
        index = _index_of(target)
        if index is None:
            raise ValueError("long_press 需要控件编号或坐标")
        node = _find_node(tree, index)
        step = _node_point_step("long_press", node, tree)
        return step, f"long_press #{index}({node['label'][:12] or '无文字'})"

    if action in ("input", "text", "输入"):
        if not text:
            raise ValueError("input 缺少 text 参数")
        step = {"op": "input", "label": "", "text": text}
        display = f'input "{text[:20]}"'
        if target is not None:
            index = _index_of(target)
            if index is not None:
                target_node = _find_node(tree, index)
                step.update({"label": (target_node["label"] or "")[:40], "loc": pm.build_locator(target_node, tree)})
                display = f"tap #{index}({target_node['label'][:12] or '输入框'}) + " + display
            else:
                coords = _resolve_target(target)
                if not coords:
                    raise ValueError("input 的 target 需要控件编号或坐标")
                step["loc"] = pm.locator_at(coords[0], coords[1], tree)
                display = f"tap ({coords[0]},{coords[1]}) + " + display
        return step, display

    if action in ("swipe", "scroll", "滑动"):
        x1, y1, x2, y2, label = _swipe_coords(tree, target, direction)
        width, height = _screen_dimensions(tree)
        step = {
            "op": "swipe",
            "label": "",
            "from_rel": [round(x1 / width, 4), round(y1 / height, 4)],
            "to_rel": [round(x2 / width, 4), round(y2 / height, 4)],
            "duration": int(duration or 300),
        }
        return step, f"swipe {label}"

    if action in ("scroll_to_find", "滑动查找"):
        target_text = (text or str(target or "")).strip()
        if not target_text:
            raise ValueError("scroll_to_find 需要 text 参数指定要查找的目标文案")
        direction = (direction or "up").strip().lower()
        if direction not in ("up", "down", "left", "right"):
            raise ValueError("direction 只能是 up/down/left/right")
        step = {
            "op": "scroll_to_find",
            "label": target_text[:40],
            "text": target_text,
            "direction": direction,
            "duration": int(duration or 300),
        }
        return step, f'scroll_to_find "{target_text[:20]}" ({direction})'

    if action in ("key", "按键"):
        name = str(target or "").strip()
        code = KEY_ALIASES.get(name.lower(), name.upper() or "KEYCODE_BACK")
        return {"op": "key", "label": "", "key": code}, f"key {code}"

    if action in ("back", "返回", "home", "主页"):
        code = "KEYCODE_HOME" if action in ("home", "主页") else "KEYCODE_BACK"
        return {"op": "key", "label": "", "key": code}, f"key {code}"

    if action in ("launch", "open", "打开"):
        raw = (app or target or "").strip()
        if not raw:
            raise ValueError("launch 需要 app 参数（App 名称或包名）")
        package = APP_ALIASES.get(raw.lower(), raw)
        return {"op": "launch", "label": raw, "app": raw, "package": package}, f"launch {package}"

    if action in ("wait", "等待"):
        pause = max(0.2, min(float(seconds or 1.0), 10.0))
        return {"op": "wait", "label": "", "seconds": pause}, f"wait {pause:.1f}s"

    raise ValueError(f"不支持的 action: {action}")


def _step_point(step: dict, tree: dict) -> tuple[int, int, str]:
    matched = pm.resolve_locator(tree, step.get("loc") or {})
    if not matched:
        label = (step.get("loc") or {}).get("text") or "坐标点"
        raise PhoneStepError(f"找不到控件「{label}」：界面可能已经变了，请先 inspect 看看现在的界面。")
    x, y, label, method = matched
    if method in ("fuzzy", "point", "id"):
        logger.info(f"[Phone] 定位器匹配方式 {method}: {label}")
    return x, y, label


async def _exec_step(step: dict, tree: dict) -> str:
    """执行单步（录制与回放共用同一套语义）。返回展示文本。"""
    op = step.get("op")

    if op == "launch":
        package = step.get("package") or ""
        error = await _launch(package)
        if error:
            raise PhoneStepError(error)
        return f"launch {package}"

    if op == "key":
        code = step.get("key") or "KEYCODE_BACK"
        await _adb(["shell", "input", "keyevent", code], timeout=15)
        return f"key {code}"

    if op == "wait":
        pause = float(step.get("seconds") or 1.0)
        await asyncio.sleep(pause)
        return f"wait {pause:.1f}s"

    if op == "swipe":
        width, height = _screen_dimensions(tree)
        from_rel = step.get("from_rel") or [0.5, 0.75]
        to_rel = step.get("to_rel") or [0.5, 0.25]
        x1, y1 = int(from_rel[0] * width), int(from_rel[1] * height)
        x2, y2 = int(to_rel[0] * width), int(to_rel[1] * height)
        dur = int(step.get("duration") or 300)
        sx1, sy1, sx2, sy2, _ = await driver.swipe(x1, y1, x2, y2, duration=dur, jitter=True)
        return f"swipe ({sx1},{sy1})->({sx2},{sy2})"

    if op in ("tap", "long_press"):
        x, y, label = _step_point(step, tree)
        if op == "tap":
            await _adb(["shell", "input", "tap", str(x), str(y)], timeout=15)
            return f"tap {label or f'({x},{y})'}"
        # 长按拟人化：swipe x y (x+2) (y+2) 800，防止定制 ROM 忽略距离为 0 的滑动
        await driver.long_press(x, y, duration=800)
        return f"long_press {label or f'({x},{y})'}"

    if op == "input":
        element = ""
        if step.get("loc"):
            x, y, label = _step_point(step, tree)
            await _adb(["shell", "input", "tap", str(x), str(y)], timeout=15)
            element = label or f"({x},{y})"
            await asyncio.sleep(0.3)
        text = str(step.get("text") or "")
        ok, method = await _input_text(text)
        if not ok:
            raise PhoneStepError(
                "文字输入失败：非 ASCII 文字需要手机安装 ADBKeyboard 输入法（或改用应用内的英文/数字输入）。"
            )
        prefix = f"tap {element} + " if element else ""
        return f'{prefix}input "{text[:20]}" via {method}'

    raise PhoneStepError(f"不支持的步骤: {op}")


async def _wait_expect(expect: dict, max_nodes: int, timeout: float) -> tuple[bool, dict]:
    """指数退避轮询等待「动作后该出现的界面」出现，返回 (是否满足, 最后的控件树)。"""
    return await driver.wait_expect(expect, max_nodes, timeout, _dump_tree)


def _find_matching_node(tree: dict, keyword: str) -> dict | None:
    for node in tree.get("nodes") or []:
        label = node.get("label") or ""
        if keyword in label:
            return node
    return None


async def _exec_scroll_to_find(
    context,
    tree: dict,
    target_text: str,
    direction: str,
    duration: int,
    max_nodes: int,
    wait_seconds: float,
    remember: bool,
    max_scrolls: int = 5,
) -> tuple[dict, list[str], bool]:
    """循环滑动查找包含 target_text 的控件，最多 max_scrolls 次。"""
    steps_log: list[str] = []
    matched = _find_matching_node(tree, target_text)
    if matched:
        steps_log.append(f'已在当前屏找到 [#{matched["index"]}]「{matched["label"]}」')
        return tree, steps_log, True

    current_tree = tree
    for count in range(1, max_scrolls + 1):
        before_tree = current_tree
        x1, y1, x2, y2, _ = _swipe_coords(current_tree, None, direction)
        width, height = _screen_dimensions(current_tree)
        swipe_step = {
            "op": "swipe",
            "label": "",
            "from_rel": [round(x1 / width, 4), round(y1 / height, 4)],
            "to_rel": [round(x2 / width, 4), round(y2 / height, 4)],
            "duration": int(duration or 300),
        }
        await _exec_step(swipe_step, current_tree)
        await asyncio.sleep(wait_seconds)
        current_tree = await _dump_tree(max_nodes)

        if remember:
            try:
                pm.phone_history.record(context.chat_id, swipe_step, before_tree, current_tree)
            except Exception as exc:
                logger.warning(f"[Phone] 写历史失败: {exc}")

        matched = _find_matching_node(current_tree, target_text)
        if matched:
            steps_log.append(
                f'scroll_to_find ({direction} x{count}) -> 找到 [#{matched["index"]}]「{matched["label"]}」'
            )
            return current_tree, steps_log, True

    steps_log.append(f'scroll_to_find ({direction} x{max_scrolls}) -> 未找到「{target_text}」')
    return current_tree, steps_log, False


async def phone_action_tool(context, action="inspect", target=None, text="", direction="up",
                            duration=300, app="", seconds=1.0, include_screenshot=False,
                            note="", remember=True):
    """手机操作：inspect/tap/long_press/input/swipe/scroll_to_find/key/launch/back/home/wait。"""
    action = (action or "inspect").strip().lower()
    tools_cfg = _tools_cfg()
    max_nodes = int(getattr(tools_cfg, "phone_max_nodes", 60) or 60)
    wait_seconds = float(getattr(tools_cfg, "phone_wait_seconds", 1.0) or 1.0)

    try:
        await _ensure_device()
    except RuntimeError as exc:
        return ToolResult(success=False, content=str(exc), error="device_unavailable")

    before = None
    step = None
    steps: list[str] = []
    try:
        if action in ("inspect", "查看", "看看"):
            steps.append("inspect")
            await asyncio.sleep(0.1)
            tree = await _dump_tree(max_nodes)
        elif action in ("scroll_to_find", "滑动查找"):
            tree = await _dump_tree(max_nodes)
            step, _ = await _prepare_step(
                action, tree, target=target, text=text, direction=direction,
                duration=duration, app=app, seconds=seconds,
            )
            tree, find_steps, _ = await _exec_scroll_to_find(
                context, tree, step["text"], step["direction"], step["duration"],
                max_nodes, wait_seconds, remember,
            )
            steps.extend(find_steps)
            step = None  # 子滑动步骤已按需记入历史
        else:
            before = await _dump_tree(max_nodes)
            tree = before
            step, display = await _prepare_step(
                action, tree, target=target, text=text, direction=direction,
                duration=duration, app=app, seconds=seconds,
            )
            display_text = await _exec_step(step, tree)
            steps.append(display_text or display)
            if step.get("op") == "launch":
                wait_seconds = max(wait_seconds, 2.0)

            # 操作后等界面稳定，再回传最新控件树
            await asyncio.sleep(wait_seconds if step else 0.1)
            tree = await _dump_tree(max_nodes)
    except ValueError as exc:
        return ToolResult(success=False, content=str(exc), error="invalid_target")
    except PhoneStepError as exc:
        return ToolResult(success=False, content=str(exc), error="node_not_found")
    except TimeoutError as exc:
        return ToolResult(success=False, content=f"手机操作超时: {exc}", error="timeout",
                          data={"action": action, "note": note})
    except Exception as exc:
        logger.error(f"[Phone] {action} 失败: {exc}")
        return ToolResult(success=False, content=f"手机操作失败: {exc}", error="action_failed",
                          data={"action": action, "note": note})

    if remember and before is not None and step and step.get("op") in RECORDABLE_OPS:
        try:
            pm.phone_history.record(context.chat_id, step, before, tree)
        except Exception as exc:  # 历史写失败不影响操作结果
            logger.warning(f"[Phone] 写历史失败: {exc}")

    if action not in ("inspect", "查看", "看看") or phone_focus_manager.is_focused(context.chat_id):
        phone_focus_manager.record_step(context.chat_id, " / ".join(steps), note)

    # 智能按需截图：模型要图，或控件树里几乎没文字（图标/图片页）时补一张
    text_nodes = [n for n in tree["nodes"] if n["kind"] in ("文本", "输入", "可点") and n["label"]]
    want_shot = bool(include_screenshot) or len(text_nodes) < 3
    attachment = None
    shot_hint = ""
    if want_shot:
        try:
            jpeg = _annotate_screenshot(await _screencap(), tree)
            if jpeg:
                attachment, shot_hint = _register_screenshot(context, jpeg)
        except Exception as exc:
            logger.warning(f"[Phone] 截图失败: {exc}")

    lines = [f"已完成: {' / '.join(steps)}", _format_tree(tree)]
    if shot_hint:
        lines.append(f"已附屏幕截图 {shot_hint}（红框编号与上面 [#编号] 对应）")

    return ToolResult(
        success=True,
        content="\n".join(lines),
        data={
            "action": action,
            "steps": steps,
            "package": tree["package"],
            "node_count": len(tree["nodes"]),
            "screenshot": attachment,
            "note": note or "",
            "no_persist": not remember,
        },
    )
