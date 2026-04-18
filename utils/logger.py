# utils/logger.py
import logging
import logging.handlers
import os
import sys
import time

from config import BASE_DIR, DEBUG

LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "yuki.log")

# ---------- 公用方法 ----------

def _format_time(record):
    ct = logging.Formatter.converter(record.created)
    t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
    return f"{t}.{int(record.msecs):03d}"


# ---------- 文件日志 Formatter ----------

class PrettyFormatter(logging.Formatter):
    """
    文件日志格式：固定宽度对齐，时间到毫秒，保留消息原始内容。

    输出示例：
        2026-04-19 00:52:05.123 | INFO     | main.py:225            | [System] 初始化完成
        2026-04-19 00:52:05.456 | DEBUG    | brain.py:48            | [Activity] 活跃度波动
        2026-04-19 00:52:05.789 | CRITICAL | main.py:279            | 发生未知致命错误
    """

    def formatTime(self, record, datefmt=None):
        return _format_time(record)

    def format(self, record):
        asctime = self.formatTime(record)
        level = record.levelname.ljust(8)
        location = f"{record.filename}:{record.lineno}".ljust(22)
        msg = record.getMessage()
        return f"{asctime} | {level} | {location} | {msg}"


# ---------- 控制台日志 Formatter ----------

class ColoredConsoleFormatter(logging.Formatter):
    """
    控制台日志格式：与文件日志相同的对齐结构，但带 ANSI 颜色。

    配色：
        时间      → 灰色
        DEBUG     → 灰色
        INFO      → 青色
        WARNING   → 黄色
        ERROR     → 红色
        CRITICAL  → 加粗红色
        位置      → 蓝色
        消息正文  → 默认终端色（白色）
    """

    C_TIME = '\033[90m'
    C_LOC = '\033[34m'
    C_RESET = '\033[0m'

    LEVEL_COLORS = {
        'DEBUG': '\033[90m',
        'INFO': '\033[36m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[1;31m',
    }

    def formatTime(self, record, datefmt=None):
        return _format_time(record)

    def format(self, record):
        asctime = self.formatTime(record)
        level = record.levelname.ljust(8)
        location = f"{record.filename}:{record.lineno}".ljust(22)
        msg = record.getMessage()

        c_time = self.C_TIME
        c_loc = self.C_LOC
        c_lvl = self.LEVEL_COLORS.get(record.levelname, self.C_RESET)
        c_reset = self.C_RESET

        return (
            f"{c_time}{asctime}{c_reset} "
            f"{c_lvl}{level}{c_reset} "
            f"{c_loc}{location}{c_reset} "
            f"{msg}"
        )


# ---------- 初始化辅助 ----------

def _try_enable_windows_ansi():
    """在 Windows 上尝试启用 ANSI 颜色支持（适用于 Windows 10+ / Windows Terminal）"""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass


def setup_logging(level: int = None):
    """
    配置全局日志：
    - 控制台输出（对齐结构 + ANSI 颜色）
    - 文件持久化（TimedRotatingFileHandler 按天归档，保留 30 天）
    """
    if level is None:
        level = logging.DEBUG if DEBUG else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler（重复调用时）
    if root.handlers:
        return

    _try_enable_windows_ansi()

    # 控制台 handler：带颜色
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredConsoleFormatter())
    root.addHandler(console_handler)

    # 文件 handler：按天归档，保留最近 30 天
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PrettyFormatter())
    file_handler.suffix = "%Y-%m-%d"
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取一个已配置好的 logger 实例。"""
    return logging.getLogger(name)
