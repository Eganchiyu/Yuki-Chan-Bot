from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

try:
    from utils.logger import get_logger
except ImportError:  # 允许单独运行本文件
    import logging

    def get_logger(name: str = "desktop_pet"):  # type: ignore[misc]
        return logging.getLogger(name)

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend" / "minimal"
CONFIG_PATH = ROOT / "config.json"
ELECTRON_DIST = FRONTEND_DIR / "node_modules" / "electron" / "dist"

logger = get_logger("desktop_pet")

# 记录 Popen 句柄，供退出清理使用
_process: subprocess.Popen[bytes] | None = None
_process_lock = threading.Lock()

ELF_MAGIC = b"\x7fELF"
PE_MAGIC = b"MZ"


def _binary_kind(path: Path) -> str:
    """返回 'elf' / 'pe' / 'unknown'，用于判断 Electron 二进制是否与当前系统匹配。"""
    try:
        with path.open("rb") as handle:
            head = handle.read(2)
    except OSError:
        return "unknown"
    if head == ELF_MAGIC:
        return "elf"
    if head == PE_MAGIC:
        return "pe"
    return "unknown"


def electron_binary() -> Path | None:
    """定位当前平台的 Electron 可执行文件。

    npm 的 `electron` 包在 postinstall 阶段按平台下载二进制，Windows 端拿到的是
    `electron.exe`，Linux 端拿到的是 ELF 的 `electron`。这里按平台取对应文件，
    避免在 Linux 上误用 Windows 构建（那会被 wine 接管，性能和窗口行为都不对）。
    """
    name = "electron.exe" if os.name == "nt" else "electron"
    candidates = [
        ELECTRON_DIST / name,
        FRONTEND_DIR / "node_modules" / ".bin" / ("electron.cmd" if os.name == "nt" else "electron"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def config_enabled() -> bool:
    """读取 config.json 里的 desktopPet.enabled（缺省视为开启）。"""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    pet = data.get("desktopPet")
    if not isinstance(pet, dict) or "enabled" not in pet:
        return True
    return bool(pet.get("enabled"))


def ozone_platform() -> str | None:
    """Linux 下决定 Electron 用 X11 还是 Wayland 后端。

    桌宠需要「全局光标坐标 + 绝对窗口定位 + 拖动」，这三样在原生 Wayland 客户端里
    都拿不到（窗口位置由合成器独占）。因此默认走 XWayland，Hyprland 等合成器都支持。
    需要原生 Wayland 时用 `YUKI_L2D_OZONE_PLATFORM=wayland` 覆盖。
    """
    override = os.getenv("YUKI_L2D_OZONE_PLATFORM", "").strip().lower()
    if override in {"x11", "wayland"}:
        return override
    if override in {"auto", "native"}:
        return None
    if os.environ.get("DISPLAY"):
        return "x11"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    return None


def _linux_flags() -> list[str]:
    flags: list[str] = []
    platform = ozone_platform()
    if platform:
        flags.append(f"--ozone-platform={platform}")
    else:
        flags.append("--ozone-platform-hint=auto")
    if platform == "wayland":
        # 原生 Wayland 下 globalShortcut 必须走 xdg-desktop-portal 的 GlobalShortcuts
        flags.append("--enable-features=GlobalShortcutsPortal")
    return flags


def _log_stream(stream: Any, level: str, prefix: str) -> None:
    """把子进程输出转发到项目日志，避免 Electron 报错被静默吞掉。"""
    try:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if level == "error" and "ERROR" in line.upper():
                logger.warning(f"[DesktopPet/{prefix}] {line}")
            else:
                logger.debug(f"[DesktopPet/{prefix}] {line}")
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _watch_process(proc: subprocess.Popen[bytes]) -> None:
    """等待子进程结束并记录退出码，方便判断桌宠是崩了还是被手动关掉。"""
    code = proc.wait()
    with _process_lock:
        global _process
        if _process is proc:
            _process = None
    if code == 0:
        logger.info("[DesktopPet] 桌宠窗口已关闭")
    else:
        logger.error(
            f"[DesktopPet] 桌宠窗口异常退出 (code={code})。"
            "在 Linux 上可先手动执行以下命令查看完整报错："
            f"  cd {FRONTEND_DIR} && ./node_modules/electron/dist/electron ."
        )


def ensure_server(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    # server 依赖 aiohttp，延迟到真正要起服务时再导入，
    # 这样 desktop.py 可以单独被导入做开关判断/环境自检。
    try:
        from .server import start_background_server
    except ImportError:
        from server import start_background_server

    start_background_server(session_pipeline, pipeline_loop)


def launch_window() -> subprocess.Popen[bytes] | None:
    """用当前平台的 Electron 原生启动桌宠窗口。"""
    binary = electron_binary()
    if binary is None:
        logger.error(
            "[DesktopPet] 未找到 Electron 可执行文件。请先执行："
            f"  cd {FRONTEND_DIR} && npm install"
        )
        return None

    kind = _binary_kind(binary)
    if kind == "pe" and os.name != "nt":
        logger.error(
            "[DesktopPet] 当前 Electron 是 Windows 构建（会被 wine 接管，窗口行为不正常）。"
            "请在本机重新安装 Linux 版本："
            f"  cd {FRONTEND_DIR} && rm -rf node_modules/electron && npm install electron"
        )
        return None
    if kind == "elf" and os.name == "nt":
        logger.error("[DesktopPet] 当前 Electron 是 Linux 构建，无法在 Windows 上运行。")
        return None

    command = [str(binary)]
    if sys.platform.startswith("linux"):
        command.extend(_linux_flags())
    command.append(".")

    env = dict(os.environ)
    env.setdefault("ELECTRON_DISABLE_SECURITY_WARNINGS", "1")

    logger.info(f"[DesktopPet] 启动 Electron: {' '.join(command)} (cwd={FRONTEND_DIR})")
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(FRONTEND_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        logger.error(f"[DesktopPet] Electron 启动失败: {exc}")
        return None

    with _process_lock:
        global _process
        _process = proc

    threading.Thread(target=_log_stream, args=(proc.stdout, "info", "out"), daemon=True).start()
    threading.Thread(target=_log_stream, args=(proc.stderr, "error", "err"), daemon=True).start()
    threading.Thread(target=_watch_process, args=(proc,), daemon=True).start()
    return proc


# ======== 桌宠窗口启动与桌面 API 逻辑主函数 ========

def main(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> subprocess.Popen[bytes] | None:
    """起本地服务并拉起桌宠窗口，返回 Electron 进程句柄（失败返回 None）。"""
    ensure_server(session_pipeline, pipeline_loop)
    return launch_window()


if __name__ == "__main__":
    main()
