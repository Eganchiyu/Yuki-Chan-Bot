# core/tools/tools_phone.py
"""手机操作工具：通过 adb 控制插在电脑上的 Android 手机。

设计要点（避免"对着看不见的屏幕猜坐标"）：
    1. 每次动作后自动等待界面刷新，并重新 dump 无障碍控件树；
    2. 控件树精简成 [#编号] + 中心坐标，模型只需传 target=编号 就能精准点按；
    3. 控件树文字信息不足、或模型主动要求时，附一张缩放到低分辨率的截图，
       并在图上把 [#编号] 画在对应控件位置（Set-of-Mark），既能看图又能对上号。
"""
import asyncio
import base64
import io
import os
import re
import shlex
import xml.etree.ElementTree as ET

from config import cfg
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

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_SCREENSHOT_DIR = os.path.join(os.path.abspath(BASE_DIR), "temp", "phone_shots")


def _tools_cfg():
    return getattr(cfg, "tools", None)


def _adb_cmd(*args: str) -> list[str]:
    cmd = [getattr(_tools_cfg(), "adb_path", "adb") or "adb"]
    serial = (getattr(_tools_cfg(), "adb_serial", "") or "").strip()
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return cmd


async def _adb(args: list[str], timeout: float = 20.0) -> tuple[int, bytes]:
    """执行 adb 子命令，返回 (退出码, 原始输出字节)。"""
    proc = await asyncio.create_subprocess_exec(
        *_adb_cmd(*args),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError("adb 执行超时")
    return proc.returncode or 0, stdout or stderr or b""


async def _adb_text(args: list[str], timeout: float = 20.0) -> str:
    code, out = await _adb(args, timeout=timeout)
    text = out.decode("utf-8", "replace").strip()
    if code != 0:
        raise RuntimeError(text or f"adb 退出码 {code}")
    return text


async def _ensure_device() -> str:
    """确认有设备在线，返回设备序列号；否则抛 RuntimeError。"""
    try:
        output = await _adb_text(["devices"], timeout=10)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "adb 不可用：当前环境没装 platform-tools，或 adb 不在 PATH 里（可在配置 tools.adb_path 指定绝对路径）。"
        ) from exc
    devices = [
        line.split("\t")[0]
        for line in output.splitlines()[1:]
        if line.strip() and "\tdevice" in line
    ]
    if not devices:
        raise RuntimeError("没有检测到已连接的手机：请确认数据线插好、手机已开启 USB 调试并在弹窗里点了允许。")
    return devices[0]


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
        clickable = node.get("clickable") == "true" or node.get("long-clickable") == "true"
        scrollable = node.get("scrollable") == "true"
        editable = "EditText" in cls
        area = (x2 - x1) * (y2 - y1)
        if not (label or clickable or scrollable or editable):
            continue
        if not label and area >= screen_area * 0.9:
            continue  # 根容器之类的整屏空壳
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
        kept.append({
            "label": label[:60],
            "kind": kind,
            "bounds": bounds,
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
        })
        if len(kept) >= max_nodes:
            break

    for index, item in enumerate(kept, 1):
        item["index"] = index
    return {
        "package": package,
        "size": (root_bounds[2] - root_bounds[0], root_bounds[3] - root_bounds[1]),
        "nodes": kept,
    }


def _format_tree(tree: dict) -> str:
    width, height = tree["size"]
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
    remote = "/data/local/tmp/yuki_ui.xml"
    await _adb(["shell", "uiautomator", "dump", remote], timeout=20)
    code, raw = await _adb(["exec-out", "cat", remote], timeout=20)
    xml_text = raw.decode("utf-8", "replace")
    if code != 0 or "<hierarchy" not in xml_text:
        raise RuntimeError(f"控件树读取失败: {xml_text[:200]}")
    return _compact_tree(xml_text, max_nodes)


async def _screencap() -> bytes:
    code, raw = await _adb(["exec-out", "screencap", "-p"], timeout=20)
    if code != 0 or not raw:
        raise RuntimeError("截图失败")
    return raw


async def _input_text(text: str) -> tuple[bool, str]:
    """输入文字：ASCII 走 input text，中文走 ADBKeyboard 广播，最后兜底剪贴板粘贴。"""
    if re.fullmatch(r"[\x20-\x7e]+", text):
        await _adb(["shell", "input", "text", shlex.quote(text).replace(" ", "%s")], timeout=20)
        return True, "input text"

    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    for action, payload in (("ADB_INPUT_B64", b64), ("ADB_INPUT_TEXT", text)):
        try:
            output = await _adb_text([
                "shell", "am", "broadcast", "-a", action, "--es", "msg", payload,
            ], timeout=20)
        except Exception:
            continue
        if "Broadcast completed" in output and "error" not in output.lower():
            return True, f"广播 {action}"

    # 兜底：写剪贴板后按粘贴键（部分系统支持）
    try:
        await _adb(["shell", "cmd", "clipboard", "set-text", text], timeout=15)
        await _adb(["shell", "input", "keyevent", "KEYCODE_PASTE"], timeout=15)
        return True, "剪贴板粘贴（请确认输入框内容）"
    except Exception:
        return False, ""


def _resolve_target(target) -> tuple[int, int] | None:
    """target 支持 "x,y" 坐标串。控件编号由调用方先行解析。"""
    if isinstance(target, str) and "," in target:
        try:
            x, y = target.split(",", 1)
            return int(float(x)), int(float(y))
        except ValueError:
            return None
    return None


async def phone_action_tool(context, action="inspect", target=None, text="", direction="up",
                            duration=300, app="", seconds=1.0, include_screenshot=False,
                            note="", remember=True):
    """手机操作：inspect/tap/long_press/input/swipe/key/launch/back/home/wait。"""
    action = (action or "inspect").strip().lower()
    tools_cfg = _tools_cfg()
    max_nodes = int(getattr(tools_cfg, "phone_max_nodes", 60) or 60)
    wait_seconds = float(getattr(tools_cfg, "phone_wait_seconds", 1.0) or 1.0)

    try:
        await _ensure_device()
    except RuntimeError as exc:
        return ToolResult(success=False, content=str(exc), error="device_unavailable")

    steps: list[str] = []

    async def tap_node(index: int) -> str | None:
        tree = await _dump_tree(max_nodes)
        node = next((n for n in tree["nodes"] if n["index"] == index), None)
        if not node:
            return f"没有 [#{index}] 这个控件，请重新 inspect 当前界面。"
        await _adb(["shell", "input", "tap", str(node["cx"]), str(node["cy"])], timeout=15)
        steps.append(f"tap #{index}({node['label'][:12] or '无文字'})")
        return None

    try:
        if action in ("inspect", "查看", "看看"):
            steps.append("inspect")

        elif action in ("tap", "click", "点击"):
            coords = _resolve_target(target)
            if coords:
                await _adb(["shell", "input", "tap", str(coords[0]), str(coords[1])], timeout=15)
                steps.append(f"tap ({coords[0]},{coords[1]})")
            elif str(target or "").lstrip("#").isdigit():
                error = await tap_node(int(str(target).lstrip("#")))
                if error:
                    return ToolResult(success=False, content=error, error="node_not_found")
            else:
                return ToolResult(success=False, content="tap 需要 target=控件编号 或 target=\"x,y\"",
                                  error="invalid_target")

        elif action in ("long_press", "longpress", "长按"):
            coords = _resolve_target(target)
            if not coords:
                if not str(target or "").lstrip("#").isdigit():
                    return ToolResult(success=False, content="long_press 需要控件编号或坐标",
                                      error="invalid_target")
                tree = await _dump_tree(max_nodes)
                index = int(str(target).lstrip("#"))
                node = next((n for n in tree["nodes"] if n["index"] == index), None)
                if not node:
                    return ToolResult(success=False, content=f"没有 [#{index}] 这个控件",
                                      error="node_not_found")
                coords = (node["cx"], node["cy"])
            await _adb(["shell", "input", "swipe", str(coords[0]), str(coords[1]),
                        str(coords[0]), str(coords[1]), "800"], timeout=15)
            steps.append(f"long_press ({coords[0]},{coords[1]})")

        elif action in ("input", "text", "输入"):
            if target is not None:
                if str(target).lstrip("#").isdigit():
                    error = await tap_node(int(str(target).lstrip("#")))
                    if error:
                        return ToolResult(success=False, content=error, error="node_not_found")
                    await asyncio.sleep(0.3)
                else:
                    coords = _resolve_target(target)
                    if not coords:
                        return ToolResult(success=False, content="input 的 target 需要控件编号或坐标",
                                          error="invalid_target")
                    await _adb(["shell", "input", "tap", str(coords[0]), str(coords[1])], timeout=15)
                    await asyncio.sleep(0.3)
            if not text:
                return ToolResult(success=False, content="input 缺少 text 参数", error="missing_text")
            ok, method = await _input_text(text)
            if not ok:
                return ToolResult(
                    success=False,
                    content=("文字输入失败：非 ASCII 文字需要手机安装 ADBKeyboard 输入法"
                             "（或改用应用内的英文/数字输入）。"),
                    error="input_failed",
                )
            steps.append(f"input \"{text[:20]}\" via {method}")

        elif action in ("swipe", "scroll", "滑动"):
            tree_now = await _dump_tree(max_nodes)
            width, height = tree_now["size"] if min(tree_now["size"]) > 0 else (1080, 2400)
            direction = (direction or "up").strip().lower()
            parts = [int(float(v)) for v in re.split(r"[,\s]+", str(target or "")) if v.strip()]
            if len(parts) == 4:
                x1, y1, x2, y2 = parts
            else:
                cx, cy = width // 2, height // 2
                span = height // 4
                mapping = {
                    "up": (cx, cy + span, cx, cy - span),
                    "down": (cx, cy - span, cx, cy + span),
                    "left": (cx + span, cy, cx - span, cy),
                    "right": (cx - span, cy, cx + span, cy),
                }
                if direction not in mapping:
                    return ToolResult(success=False, content="direction 只能是 up/down/left/right",
                                      error="invalid_direction")
                x1, y1, x2, y2 = mapping[direction]
            await _adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2),
                        str(int(duration or 300))], timeout=15)
            steps.append(f"swipe {direction}")

        elif action in ("key", "按键"):
            name = str(target or "").strip()
            code = KEY_ALIASES.get(name.lower(), name.upper() or "KEYCODE_BACK")
            await _adb(["shell", "input", "keyevent", code], timeout=15)
            steps.append(f"key {code}")

        elif action in ("back", "返回", "home", "主页"):
            code = "KEYCODE_HOME" if action in ("home", "主页") else "KEYCODE_BACK"
            await _adb(["shell", "input", "keyevent", code], timeout=15)
            steps.append(f"key {code}")

        elif action in ("launch", "open", "打开"):
            raw = (app or target or "").strip()
            if not raw:
                return ToolResult(success=False, content="launch 需要 app 参数（App 名称或包名）",
                                  error="missing_app")
            package = APP_ALIASES.get(raw.lower(), raw)
            await _adb(["shell", "monkey", "-p", package, "-c",
                        "android.intent.category.LAUNCHER", "1"], timeout=25)
            steps.append(f"launch {package}")
            wait_seconds = max(wait_seconds, 2.0)

        elif action in ("wait", "等待"):
            pause = max(0.2, min(float(seconds or wait_seconds), 10.0))
            await asyncio.sleep(pause)
            steps.append(f"wait {pause:.1f}s")

        else:
            return ToolResult(success=False, content=f"不支持的 action: {action}", error="invalid_action")

        # 操作后等界面稳定，再回传最新控件树
        await asyncio.sleep(wait_seconds)
        tree = await _dump_tree(max_nodes)
    except TimeoutError as exc:
        return ToolResult(success=False, content=f"手机操作超时: {exc}", error="timeout",
                          data={"action": action, "note": note})
    except Exception as exc:
        logger.error(f"[Phone] {action} 失败: {exc}")
        return ToolResult(success=False, content=f"手机操作失败: {exc}", error="action_failed",
                          data={"action": action, "note": note})

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
