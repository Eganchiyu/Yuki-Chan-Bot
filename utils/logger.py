# utils/logger.py
import logging
import logging.handlers
import os
import re
import shutil
import sys
import textwrap
import time
import datetime

from utils import BASE_DIR

LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "yuki.log")
ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1B\][\x30-\x3F]*[\x20-\x2F]*[\x40-\x7E]|"
    r"\x1B\[[0-?]*[ -/]*[@-~]|\x1B[@-_])"
)

# 自定义 TRACE 级别（比 DEBUG 更低），用于收纳第三方库的冗长日志
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

# ---------- 启动时日志归档 ----------

def _archive_existing_log():
    """
    启动时：若 yuki.log 已存在，按最后修改时间重命名为归档文件，
    归档文件永久保留。
    """
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        return

    mtime = os.path.getmtime(LOG_FILE)
    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(LOGS_DIR, f"yuki_{mtime_str}.log")

    # 防冲突
    counter = 1
    original = archive_path
    while os.path.exists(archive_path):
        base, ext = os.path.splitext(original)
        archive_path = f"{base}_{counter}{ext}"
        counter += 1

    os.rename(LOG_FILE, archive_path)

# ---------- 公用方法 ----------

# 第三方库命名空间：这些库的 INFO/DEBUG 日志过于冗长，直接提升为 WARNING
NOISY_NAMESPACES = (
    "gradio", "httpx", "httpcore", "uvicorn", "fastapi",
    "watchfiles", "PIL", "markdown_it", "starlette", "asyncio",
)


def _silence_noisy_loggers():
    """将指定第三方库的日志级别提升为 WARNING，避免污染主日志。"""
    for prefix in NOISY_NAMESPACES:
        logging.getLogger(prefix).setLevel(logging.WARNING)


def _format_time(record):
    ct = logging.Formatter.converter(record.created)
    t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
    return f"{t}.{int(record.msecs):03d}"


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _record_lines(record, strip_ansi: bool = False):
    """获取原始日志行（包含异常信息），可选择去除 ANSI 颜色代码。"""
    message = record.getMessage()
    if record.exc_info:
        message = f"{message}\n{logging.Formatter().formatException(record.exc_info)}"
    if strip_ansi:
        message = _strip_ansi(message)
    return message.splitlines() or [""]


def _wrap_lines(record, max_width=None, strip_ansi=True):
    """
    获取原始行，并自动按宽度折叠每一行。
    
    :param max_width: 每行最大字符数，None 则自动取终端宽度（控制台）或固定 180（文件）
    :param strip_ansi: 是否先去除 ANSI 颜色代码
    """
    raw_lines = _record_lines(record, strip_ansi=strip_ansi)

    if max_width is None:
        # 控制台默认：使用终端实际宽度，留一点余量
        try:
            terminal_width = shutil.get_terminal_size().columns
            max_width = max(terminal_width - 1, 60)  # 至少 60 列
        except Exception:
            max_width = 120

    wrapped = []
    for line in raw_lines:
        if len(line) <= max_width:
            wrapped.append(line)
        else:
            # 按宽度折行，保留中文/英文单词完整性
            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=max_width,
                    break_on_hyphens=False,
                    break_long_words=False,
                    replace_whitespace=False,
                    drop_whitespace=False,
                )
            )
    return wrapped


def _color_mode(stream) -> bool:
    mode = os.getenv("YUKI_LOG_COLOR", "auto").lower()
    if mode == "always":
        return True
    if mode == "never" or os.getenv("NO_COLOR") is not None:
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


# ---------- 文件日志 Formatter ----------

class PrettyFormatter(logging.Formatter):
    """
    文件日志格式：固定宽度对齐，时间到毫秒，保留消息原始内容。
    自动折行，保持续行对齐。
    
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
        prefix = f"{asctime} | {level} | {location} |"
        prefix_width = len(prefix) + 1            # "| " 后的空格也算
        continuation = " " * (prefix_width - 1) + "├"

        # 文件日志固定宽度 180，兼顾可读性与文件大小
        lines = _wrap_lines(record, max_width=180, strip_ansi=True)

        rendered = []
        for i, line in enumerate(lines):
            if i == 0:
                rendered.append(f"{prefix} {line}")
            else:
                rendered.append(f"{continuation} {line}")
        return "\n".join(rendered)


# ---------- 控制台日志 Formatter ----------

class ColoredConsoleFormatter(logging.Formatter):
    """
    控制台日志格式：带 ANSI 颜色的对齐结构。
    自动根据终端宽度折行。
    
    配色：
        时间      → 灰色
        TRACE     → 深灰色
        DEBUG     → 灰色
        INFO      → 青色
        WARNING   → 黄色
        ERROR     → 红色
        CRITICAL  → 加粗红色背景
        位置      → 蓝色
        消息正文  → 默认终端色（白色）
    """

    C_TIME = '\033[90m'
    C_LOC = '\033[34m'
    C_RESET = '\033[0m'

    LEVEL_COLORS = {
        'TRACE': '\033[90m',
        'DEBUG': '\033[90m',
        'INFO': '\033[36m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[1;37;41m',
    }

    def formatTime(self, record, datefmt=None):
        return _format_time(record)

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    def format(self, record):
        asctime = self.formatTime(record)
        level = record.levelname.ljust(8)
        location = f"{record.filename}:{record.lineno}".ljust(22)
        prefix_width = len(f"[{asctime}] {level} {location} │")

        if self.use_color:
            c_time = self.C_TIME
            c_loc = self.C_LOC
            c_lvl = self.LEVEL_COLORS.get(record.levelname, self.C_RESET)
            c_reset = self.C_RESET
        else:
            c_time = c_loc = c_lvl = c_reset = ""

        prefix = (
            f"{c_time}[{asctime}]{c_reset} "
            f"{c_lvl}{level}{c_reset} "
            f"{c_loc}{location}{c_reset} │"
        )
        continuation = " " * (prefix_width - 1) + "├"
        # 控制台自动取终端宽度
        lines = _wrap_lines(record, max_width=None, strip_ansi=True)

        rendered = []
        for i, line in enumerate(lines):
            if i == 0:
                rendered.append(f"{prefix} {line}")
            else:
                rendered.append(f"{continuation} {line}")
        return "\n".join(rendered)


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


def setup_logging(level: int = None, debug: bool = False):
    """
    配置全局日志：
    - 启动时自动归档旧日志
    - 控制台输出（对齐结构 + ANSI 颜色，自动折行）
    - 文件持久化（追加写入当前 yuki.log，自动折行）
    """
    if level is None:
        level = logging.DEBUG if debug else logging.INFO

    # 先归档上一次的日志
    _archive_existing_log()

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler（重复调用时）
    if root.handlers:
        return

    _try_enable_windows_ansi()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredConsoleFormatter(_color_mode(sys.stdout)))
    root.addHandler(console_handler)

    # 文件 handler：追加写入新日志
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PrettyFormatter())
    root.addHandler(file_handler)

    # 抑制第三方库的冗长日志
    _silence_noisy_loggers()


def get_logger(name: str) -> logging.Logger:
    """获取一个已配置好的 logger 实例。"""
    return logging.getLogger(name)