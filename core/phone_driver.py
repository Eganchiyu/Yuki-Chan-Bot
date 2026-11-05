# core/phone_driver.py
"""Android 设备驱动层：隔离底层 ADB 进程通信、分辨率/IME 缓存、手势拟人化与超时自愈。"""
from __future__ import annotations

import asyncio
import os
import random
import re
import shlex
import sys
import time
from typing import Callable

from config import cfg
from utils.logger import get_logger

logger = get_logger("tools")

ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
_WM_SIZE_RE = re.compile(r"(\d+)\s*x\s*(\d+)")
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.-]+")

# Android shell `input text` 需要转义的 shell 元字符
_SHELL_ESCAPE_CHARS = set('\\"\'`$&|;<>()*?[]{}!#~')


def escape_ascii_for_input(text: str) -> str:
    """逐字符转义 ASCII 文本供 `adb shell input text` 使用，空格转为 %s。"""
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append("%s")
        elif ch in _SHELL_ESCAPE_CHARS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


class AndroidDriver:
    """封装底层 ADB 通信、设备状态缓存与拟人化手势。"""

    def __init__(self) -> None:
        self.serial: str = ""
        self.screen_size: tuple[int, int] | None = None
        self._screen_sizes: dict[str, tuple[int, int]] = {}
        self._adb_keyboard_cache: dict[str, bool] = {}
        self._has_adb_keyboard: bool | None = None
        self._consecutive_timeouts: int = 0

    @staticmethod
    def _tools_cfg():
        return getattr(cfg, "tools", None)

    def _configured_serial(self) -> str:
        return (getattr(self._tools_cfg(), "adb_serial", "") or "").strip()

    def adb_cmd(self, *args: str) -> list[str]:
        cmd = [getattr(self._tools_cfg(), "adb_path", "adb") or "adb"]
        serial = self._configured_serial()
        if serial:
            cmd += ["-s", serial]
        cmd += list(args)
        return cmd

    def _tp_override(self, attr: str, default_fn: Callable):
        """兼容测试对 core.tools.tools_phone 模块级私有函数的 monkeypatch。"""
        tp = sys.modules.get("core.tools.tools_phone")
        if tp is not None:
            fn = getattr(tp, attr, None)
            global_fn = getattr(driver, default_fn.__name__, default_fn)
            if fn is not None and fn != default_fn and fn != global_fn:
                return fn
        return default_fn

    async def _restart_adb_server(self) -> None:
        """连续超时达到阈值时重启 adb server 自愈。"""
        adb_bin = getattr(self._tools_cfg(), "adb_path", "adb") or "adb"
        logger.warning("[PhoneDriver] 连续 ADB 超时达到 2 次，正在执行 kill-server / start-server 自愈")
        for sub in ("kill-server", "start-server"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    adb_bin, sub,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except Exception as exc:
                logger.warning(f"[PhoneDriver] adb {sub} 异常: {exc}")

    async def adb(self, args: list[str], timeout: float = 20.0) -> tuple[int, bytes]:
        """执行 adb 子命令，返回 (退出码, 原始输出字节)。连续超时 2 次自动重启 adb 服务。"""
        override = self._tp_override("_adb", self.adb)
        if override != self.adb:
            return await override(args, timeout=timeout)

        proc = await asyncio.create_subprocess_exec(
            *self.adb_cmd(*args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            self._consecutive_timeouts = 0
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= 2:
                self._consecutive_timeouts = 0
                await self._restart_adb_server()
            raise TimeoutError("adb 执行超时")
        return proc.returncode or 0, stdout or stderr or b""

    async def adb_text(self, args: list[str], timeout: float = 20.0) -> str:
        override = self._tp_override("_adb_text", self.adb_text)
        if override != self.adb_text:
            return await override(args, timeout=timeout)

        code, out = await self.adb(args, timeout=timeout)
        text = out.decode("utf-8", "replace").strip()
        if code != 0:
            raise RuntimeError(text or f"adb 退出码 {code}")
        return text

    async def _refresh_screen_size(self, serial: str) -> None:
        if serial in self._screen_sizes:
            self.screen_size = self._screen_sizes[serial]
            return
        try:
            code, raw = await self.adb(["shell", "wm", "size"], timeout=8.0)
            if code == 0 and raw:
                text = raw.decode("utf-8", "replace")
                matches = _WM_SIZE_RE.findall(text)
                if matches:
                    # 优先取最后一行（Override size 优先于 Physical size）
                    w, h = int(matches[-1][0]), int(matches[-1][1])
                    if w > 0 and h > 0:
                        self._screen_sizes[serial] = (w, h)
                        self.screen_size = (w, h)
        except Exception as exc:
            logger.debug(f"[PhoneDriver] 获取 wm size 失败: {exc}")

    async def _refresh_adb_keyboard(self, serial: str) -> None:
        if serial in self._adb_keyboard_cache:
            self._has_adb_keyboard = self._adb_keyboard_cache[serial]
            return
        try:
            code, raw = await self.adb(["shell", "ime", "list", "-a"], timeout=8.0)
            if code == 0 and raw:
                text = raw.decode("utf-8", "replace").strip()
                if text:
                    installed = ADB_KEYBOARD_IME in text or "com.android.adbkeyboard" in text
                    self._adb_keyboard_cache[serial] = installed
                    self._has_adb_keyboard = installed
        except Exception as exc:
            logger.debug(f"[PhoneDriver] 预检 ADBKeyboard 失败: {exc}")

    async def ensure_device(self) -> str:
        """确认有设备在线，缓存物理分辨率与 ADBKeyboard 状态，返回设备序列号。"""
        override = self._tp_override("_ensure_device", self.ensure_device)
        if override != self.ensure_device:
            return await override()

        try:
            output = await self.adb_text(["devices"], timeout=10)
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

        configured = self._configured_serial()
        serial = configured if configured and configured in devices else devices[0]
        self.serial = serial
        await self._refresh_screen_size(serial)
        await self._refresh_adb_keyboard(serial)
        return serial

    def resolve_screen_size(self, tree: dict | None = None) -> tuple[int, int]:
        """优先从 tree 获取有效屏幕尺寸，否则使用缓存的真实物理分辨率。"""
        if tree and isinstance(tree.get("size"), (tuple, list)) and len(tree["size"]) == 2:
            w, h = int(tree["size"][0] or 0), int(tree["size"][1] or 0)
            if w > 0 and h > 0:
                if not self.screen_size:
                    self.screen_size = (w, h)
                return w, h
        if self.screen_size and min(self.screen_size) > 0:
            return self.screen_size
        return (0, 0)

    def remote_dump_path(self) -> str:
        """动态生成与设备序列号或进程 PID 绑定的临时 dump 路径，避免多设备/多进程冲突。"""
        token = self._configured_serial() or self.serial or str(os.getpid())
        safe_token = _SAFE_TOKEN_RE.sub("_", token).strip("_") or str(os.getpid())
        return f"/data/local/tmp/yuki_ui_{safe_token}.xml"

    async def dump_xml(self) -> str:
        """执行 uiautomator dump 并读取原始 XML 文本。"""
        remote = self.remote_dump_path()
        await self.adb(["shell", "uiautomator", "dump", remote], timeout=20)
        code, raw = await self.adb(["exec-out", "cat", remote], timeout=20)
        xml_text = raw.decode("utf-8", "replace")
        if code != 0 or "<hierarchy" not in xml_text:
            raise RuntimeError(f"控件树读取失败: {xml_text[:200]}")
        return xml_text

    async def screencap(self) -> bytes:
        override = self._tp_override("_screencap", self.screencap)
        if override != self.screencap:
            return await override()

        code, raw = await self.adb(["exec-out", "screencap", "-p"], timeout=20)
        if code != 0 or not raw:
            raise RuntimeError("截图失败")
        return raw

    async def current_ime(self) -> str:
        override = self._tp_override("_current_ime", self.current_ime)
        if override != self.current_ime:
            return await override()

        try:
            return await self.adb_text(["shell", "settings", "get", "secure", "default_input_method"], timeout=10)
        except Exception:
            return ""

    async def set_ime(self, ime_id: str) -> None:
        override = self._tp_override("_set_ime", self.set_ime)
        if override != self.set_ime:
            await override(ime_id)
            return

        await self.adb(["shell", "ime", "set", ime_id], timeout=15)

    async def input_text(self, text: str) -> tuple[bool, str]:
        """输入文字：修复 %s 转义漏洞，预检 ADBKeyboard 避免无效等待。"""
        override = self._tp_override("_input_text", self.input_text)
        if override != self.input_text:
            return await override(text)

        # 纯 ASCII 且不含 %s（Android input text 会把 %s 当成空格）时走 input text
        if re.fullmatch(r"[\x20-\x7e]+", text) and "%s" not in text:
            escaped = escape_ascii_for_input(text)
            await self.adb(["shell", "input", "text", escaped], timeout=20)
            return True, "input text"

        quoted = shlex.quote(text)

        # 若未预检过，尝试快速预检一次
        if self._has_adb_keyboard is None:
            await self._refresh_adb_keyboard(self.serial or self._configured_serial() or "default")

        # 首选：仅在未确认缺失 ADBKeyboard 时，临时切换到 ADBKeyboard 广播输入
        if self._has_adb_keyboard is not False:
            original_ime = await self.current_ime()
            try:
                await self.adb(["shell", "ime", "enable", ADB_KEYBOARD_IME], timeout=15)
                await self.set_ime(ADB_KEYBOARD_IME)
                await asyncio.sleep(0.4)
                output = await self.adb_text([
                    "shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", quoted,
                ], timeout=20)
                await asyncio.sleep(0.3)
                if original_ime and original_ime != ADB_KEYBOARD_IME:
                    await self.set_ime(original_ime)
                if "Broadcast completed" in output and "error" not in output.lower():
                    return True, "ADBKeyboard 广播"
            except Exception as exc:
                logger.warning(f"[PhoneDriver] ADBKeyboard 输入失败: {exc}")
                if original_ime and original_ime != ADB_KEYBOARD_IME:
                    try:
                        await self.set_ime(original_ime)
                    except Exception:
                        pass

        # 兜底：写剪贴板后按粘贴键
        try:
            await self.adb(["shell", "cmd", "clipboard", "set-text", quoted], timeout=15)
            await self.adb(["shell", "input", "keyevent", "KEYCODE_PASTE"], timeout=15)
            return True, "剪贴板粘贴（请确认输入框内容）"
        except Exception:
            return False, ""

    async def tap(self, x: int, y: int) -> None:
        await self.adb(["shell", "input", "tap", str(int(x)), str(int(y))], timeout=15)

    async def long_press(self, x: int, y: int, duration: int = 800) -> None:
        """长按：使用 (x, y) -> (x+2, y+2) 防止定制 ROM 忽略距离为 0 的 swipe。"""
        ix, iy = int(x), int(y)
        await self.adb(
            ["shell", "input", "swipe", str(ix), str(iy), str(ix + 2), str(iy + 2), str(int(duration))],
            timeout=15,
        )

    async def swipe(
        self,
        x1: int | float,
        y1: int | float,
        x2: int | float,
        y2: int | float,
        duration: int = 300,
        *,
        jitter: bool = True,
    ) -> tuple[int, int, int, int, int]:
        """滑动：加入 ±3px 坐标微扰与 ±20ms 时长抖动，降低风控脚本判定概率。"""
        ix1, iy1, ix2, iy2 = int(x1), int(y2 if False else y1), int(x2), int(y2)
        dur = int(duration or 300)
        if jitter:
            ix1 = max(0, ix1 + random.randint(-3, 3))
            iy1 = max(0, iy1 + random.randint(-3, 3))
            ix2 = max(0, ix2 + random.randint(-3, 3))
            iy2 = max(0, iy2 + random.randint(-3, 3))
            dur = max(50, dur + random.randint(-20, 20))
        await self.adb(
            ["shell", "input", "swipe", str(ix1), str(iy1), str(ix2), str(iy2), str(dur)],
            timeout=15,
        )
        return ix1, iy1, ix2, iy2, dur

    async def keyevent(self, code: str) -> None:
        await self.adb(["shell", "input", "keyevent", code], timeout=15)

    async def launch(self, package: str) -> str:
        """启动 App，返回错误说明；空字符串表示成功。"""
        code, raw = await self.adb([
            "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1",
        ], timeout=25)
        output = raw.decode("utf-8", "replace")
        if "aborted" in output.lower() or "no activities found" in output.lower():
            try:
                installed = await self.adb_text(["shell", "pm", "list", "packages", "-3"], timeout=15)
                names = [line.split(":")[-1].strip() for line in installed.splitlines() if line.strip()]
                sample = "、".join(names[:12]) or "（读取失败）"
            except Exception:
                sample = "（读取失败）"
            return f"没找到 App「{package}」：请改传包名。已安装的第三方应用示例：{sample}"
        if code != 0:
            return f"启动 {package} 失败（退出码 {code}）"
        return ""

    async def wait_expect(
        self,
        expect: dict,
        max_nodes: int,
        timeout: float,
        dump_tree_fn: Callable,
    ) -> tuple[bool, dict]:
        """指数退避轮询等待预期界面出现（0.4s -> 0.6s -> 0.9s -> 1.2s...），降低低端机 UI 卡顿。"""
        package = (expect or {}).get("package") or ""
        labels = (expect or {}).get("labels") or []
        deadline = time.monotonic() + max(0.5, timeout)
        tree = await dump_tree_fn(max_nodes)
        backoff_intervals = (0.4, 0.6, 0.9, 1.2, 1.6)
        attempt = 0
        while True:
            current = {node["label"] for node in tree["nodes"] if node.get("label")}
            package_ok = not package or tree.get("package") == package
            if package_ok and all(label in current for label in labels):
                return True, tree
            now = time.monotonic()
            if now >= deadline:
                return False, tree
            delay = backoff_intervals[min(attempt, len(backoff_intervals) - 1)]
            attempt += 1
            await asyncio.sleep(min(delay, max(0.05, deadline - now)))
            tree = await dump_tree_fn(max_nodes)


driver = AndroidDriver()
