# utils/logger.py
import ast
import datetime
import logging
import logging.handlers
import os
import re
import shutil
import sys
import textwrap
import time
import unicodedata

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
_EXCEPTION_FORMATTER = logging.Formatter()

# 控制台输出压缩参数
CONSOLE_MAX_LINES = int(os.getenv("YUKI_LOG_CONSOLE_MAX_LINES", "8"))
CONSOLE_MAX_TEXT = int(os.getenv("YUKI_LOG_CONSOLE_MAX_TEXT", "220"))
CONSOLE_MAX_ITEMS = int(os.getenv("YUKI_LOG_CONSOLE_MAX_ITEMS", "6"))
CONSOLE_WIDTH_REFRESH_INTERVAL = 0.5
CONSOLE_MIN_INLINE_TEXT_WIDTH = 12

# 多行长消息折叠后的摘要长度
CONSOLE_SUMMARY_TEXT = int(os.getenv("YUKI_LOG_CONSOLE_SUMMARY_TEXT", "160"))

# 文件日志单条记录的行数上限：只约束普通多行文本，异常堆栈不受限
FILE_MAX_LINES = int(os.getenv("YUKI_LOG_FILE_MAX_LINES", "60"))

# 折行时优先停靠的分隔符：避免把 ASCII 结构/参数从词中间切开
_WRAP_HINTS = (", ", " | ", " |", "，", "、", "; ", " ")


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
    # websockets 会在 DEBUG 下逐帧打印收发内容并记录每次 keepalive ping/pong，
    # 实测占单日日志一半以上。连接建立/读取中断等关键事件由 network.napcat 自己记录。
    "websockets",
)

# 项目内高频日志：这些 namespace 的 DEBUG 只进文件，不再刷控制台。
# 名字必须与实际 get_logger() 调用一致（core/* 与 modules/* 会折叠成同名 logger）。
VERBOSE_NAMESPACES = (
    "napcat",
    "napcat_listen",
    "session_pipeline",
    "engine",
    "brain",
    "rag",
    "prompts",
    "toolchain",
    "tools",
    "vision_processor",
    "vision_cache",
    "vision_utils",
    "image_store",
    "stickers",
    "maid",
    "github_monitor",
    "qzone",
    "qzone_monitor",
    "qzone_state",
    "shot_memory",
    "shot_renderer",
    "history",
    "llm_client",
    "modes",
    "init",
    "desktop_pet",
)


_READABLE_KEYS = (
    "post_type", "message_type", "meta_event_type", "notice_type", "request_type",
    "sub_type", "user_id", "group_id", "self_id", "sender_id", "target_id",
    "message_id", "interval", "status", "action", "event", "type", "name",
)
_TEXT_KEYS = ("message", "raw_message", "content", "text", "prompt", "response", "payload")


def _silence_noisy_loggers():
    """将指定第三方库的日志级别提升为 WARNING，避免污染主日志。"""
    for prefix in NOISY_NAMESPACES:
        logging.getLogger(prefix).setLevel(logging.WARNING)


def _is_verbose_name(name: str) -> bool:
    """判断 logger 名是否属于项目内高频 namespace。"""
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in VERBOSE_NAMESPACES)


class ConsoleNoiseFilter(logging.Filter):
    """控制台降噪：丢弃项目内高频 namespace 的 DEBUG/TRACE 记录。

    控制台默认级别为 INFO，此时本过滤器是兜底；把控制台调到 DEBUG
    （`YUKI_LOG_CONSOLE_LEVEL=DEBUG`）时它才真正起作用——文件仍保留这些
    DEBUG 明细，控制台不被刷屏。`YUKI_LOG_CONSOLE_VERBOSE=1` 可整体放行。
    """

    def __init__(self, allow_verbose: bool = False):
        super().__init__()
        self.allow_verbose = allow_verbose

    def filter(self, record) -> bool:
        if self.allow_verbose or record.levelno >= logging.INFO:
            return True
        return not _is_verbose_name(record.name)


def _env_level(name: str, default: int) -> int:
    """从环境变量读取日志级别，支持 'DEBUG' / '10' 两种写法。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if raw.isdigit():
        return int(raw)
    level = logging.getLevelName(raw.upper())
    return level if isinstance(level, int) else default


def _verbose_allowed() -> bool:
    """控制台是否放行项目内高频 DEBUG（`YUKI_LOG_CONSOLE_VERBOSE=1`）。"""
    return os.getenv("YUKI_LOG_CONSOLE_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}


def _silence_verbose_loggers(debug: bool = False):
    """非 debug 模式下压低项目内高频调试日志。"""
    if debug:
        # debug 下项目内 DEBUG 是排查依据：文件保留，控制台由 ConsoleNoiseFilter 拦截
        return
    for prefix in VERBOSE_NAMESPACES:
        logging.getLogger(prefix).setLevel(logging.INFO)


def _format_time(record):
    ct = logging.Formatter.converter(record.created)
    t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
    return f"{t}.{int(record.msecs):03d}"


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _char_display_width(char: str) -> int:
    """返回单个 Unicode 字符占用的终端显示列数。"""
    codepoint = ord(char)
    if (
        unicodedata.combining(char)
        or unicodedata.category(char).startswith("C")
        or 0xFE00 <= codepoint <= 0xFE0F
        or 0xE0100 <= codepoint <= 0xE01EF
    ):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _display_width(text: str) -> int:
    """计算去除 ANSI 转义后文本的终端显示宽度。"""
    return sum(_char_display_width(char) for char in _strip_ansi(text))


def _hard_cut(text: str, max_width: int) -> str:
    """按显示宽度裁剪到不超过 max_width，不做任何分隔符偏好。"""
    if max_width <= 0:
        return ""
    width = 0
    for index, char in enumerate(text):
        char_width = _char_display_width(char)
        if width + char_width > max_width:
            return text[:index]
        width += char_width
    return text


def _split_at_hint(line: str, max_width: int) -> int:
    """在显示宽度不超过 max_width 的范围内，找一个优先断行位置。

    返回值是「断点之后」的下标；找不到合适分隔符时返回 0，调用方退回硬折行。
    断点必须落在宽度预算内且用掉足够宽度，否则宁可硬折行，避免折出一串碎片行。
    """
    best = 0
    width = 0
    for index, char in enumerate(line):
        char_width = _char_display_width(char)
        if width + char_width > max_width:
            break
        width += char_width
        # 分隔符断点：把分隔符留在上一行，下一行从新 token 开始
        for hint in _WRAP_HINTS:
            if line.startswith(hint, index):
                candidate = index + len(hint)
                if candidate < len(line) and _display_width(line[:candidate]) <= max_width:
                    best = candidate
                break
    if best <= 0:
        return 0
    if _display_width(line[:best].rstrip()) < max_width * 0.6:
        return 0
    return best


def _wrap_display_line(line: str, max_width: int) -> list[str]:
    """按终端显示列数折行，优先在分隔符处断开，避免从 token 中间切开。"""
    if not line:
        return [""]

    wrapped = []
    remaining = line
    while _display_width(remaining) > max_width:
        split = _split_at_hint(remaining, max_width)
        if split <= 0:
            # 没有可用分隔符：退化为按显示宽度硬折行
            current = []
            current_width = 0
            for char in remaining:
                char_width = _char_display_width(char)
                if current and current_width + char_width > max_width:
                    break
                current.append(char)
                current_width += char_width
            split = len(current)
            if split == 0:
                split = 1
        wrapped.append(remaining[:split].rstrip())
        remaining = remaining[split:]
        # 只吃掉断点自身留下的分隔空白，保留有意义的缩进
        if remaining[:1] == " " and split > 0 and line[split - 1:split] == " ":
            remaining = remaining[1:]
    wrapped.append(remaining)
    return wrapped


def _wrap_display_lines(lines: list[str], max_width: int) -> list[str]:
    wrapped = []
    for line in lines:
        wrapped.extend(_wrap_display_line(line, max_width))
    return wrapped


def _truncate_display(text: str, max_width: int) -> str:
    """将文本截断到指定显示宽度，并尽量保留省略号。

    截断按显示宽度纯裁剪，不做分隔符偏好——否则会在第一个空格处就草草收尾。
    """
    if _display_width(text) <= max_width:
        return text
    if max_width <= 1:
        return "…" if max_width == 1 else ""
    return _hard_cut(text, max_width - 1) + "…"


def _truncate_text(text: str, limit: int = CONSOLE_MAX_TEXT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}... <truncated {omitted} chars>"


def _safe_repr(value, max_text: int = CONSOLE_MAX_TEXT, max_items: int = CONSOLE_MAX_ITEMS):
    if isinstance(value, bytes):
        return f"<bytes:{len(value)} bytes>"
    if isinstance(value, str):
        return repr(_truncate_text(value, max_text))
    if isinstance(value, dict):
        return _compact_mapping(value, max_text=max_text, max_items=max_items)
    if isinstance(value, (list, tuple, set)):
        return _compact_sequence(value, max_text=max_text, max_items=max_items)
    return repr(value)


def _compact_mapping(value: dict, max_text: int = CONSOLE_MAX_TEXT, max_items: int = CONSOLE_MAX_ITEMS):
    parts = []
    used_keys = set()

    for key in _READABLE_KEYS:
        if key in value:
            parts.append(f"{key}={_safe_repr(value[key], max_text=max_text, max_items=max_items)}")
            used_keys.add(key)

    for key in _TEXT_KEYS:
        if key in value:
            parts.append(f"{key}={_safe_repr(value[key], max_text=max_text, max_items=max_items)}")
            used_keys.add(key)

    for key, item in value.items():
        if key in used_keys:
            continue
        if len(parts) >= max_items:
            break
        parts.append(f"{key}={_safe_repr(item, max_text=max_text, max_items=max_items)}")
        used_keys.add(key)

    hidden = len(value) - len(used_keys)
    if hidden > 0:
        parts.append(f"... +{hidden} keys")
    return "{" + ", ".join(parts) + "}"


def _compact_sequence(value, max_text: int = CONSOLE_MAX_TEXT, max_items: int = CONSOLE_MAX_ITEMS):
    items = list(value)
    rendered = [_safe_repr(item, max_text=max_text, max_items=max_items) for item in items[:max_items]]
    hidden = len(items) - len(rendered)
    if hidden > 0:
        rendered.append(f"... +{hidden} items")
    left, right = ("[", "]") if isinstance(value, list) else ("(", ")")
    return left + ", ".join(rendered) + right


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes}B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f}KB"
    return f"{num_bytes / (1024 * 1024):.1f}MB"


def _embedded_spans(message: str) -> list[tuple[int, int]]:
    """扫描消息中可能是结构化字面量的顶层 {} / [] 片段（跳过字符串内的括号）。"""
    spans = []
    stack = []
    quote = None
    escaped = False
    for index, char in enumerate(message):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "{[":
            stack.append(index)
        elif char in "}]" and stack:
            start = stack.pop()
            if not stack:
                spans.append((start, index + 1))
    return spans


def _compact_embedded_structures(message: str, min_length: int = 60) -> str:
    """把消息里内嵌的长 dict/list 字面量替换为键值摘要。

    只在字面量可被解析、且确实过长时才改写；任何异常都原样返回。
    """
    try:
        spans = _embedded_spans(message)
    except Exception:
        return message
    if not spans:
        return message

    parts = []
    cursor = 0
    changed = False
    for start, end in spans:
        if start < cursor or end - start < min_length:
            continue
        literal = message[start:end]
        try:
            value = ast.literal_eval(literal)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            continue
        if isinstance(value, dict):
            compact = _compact_mapping(value)
        elif isinstance(value, (list, tuple, set)):
            compact = _compact_sequence(value)
        else:
            continue
        parts.append(message[cursor:start])
        parts.append(compact)
        cursor = end
        changed = True

    if not changed:
        return message
    parts.append(message[cursor:])
    return "".join(parts)


def _compact_log_message(message: str) -> str:
    stripped = message.strip()
    if not stripped:
        return message

    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        parsed = None

    if isinstance(parsed, dict):
        return _compact_mapping(parsed)
    if isinstance(parsed, (list, tuple, set)):
        return _compact_sequence(parsed)

    # 前缀 + 内嵌结构化字面量（如 `收到: {...}`）也做键值摘要
    message = _compact_embedded_structures(message)

    # 多行消息交给 _fold_console_lines 折叠，此处不按字符截断，
    # 否则规模标注只能反映截断后的残量。
    if len(message.splitlines()) > 1:
        return message

    lowered = stripped.lower()
    if "heartbeat" in lowered and "interval" in lowered:
        return _truncate_text(message, 180)
    if any(key in lowered for key in ("raw_message", "message", "prompt", "payload", "content")):
        return _truncate_text(message, CONSOLE_MAX_TEXT)
    if len(message) > CONSOLE_MAX_TEXT * 2:
        return _truncate_text(message, CONSOLE_MAX_TEXT)
    return message


def _fold_console_lines(
    lines: list[str],
    total_lines: int = None,
    total_bytes: int = None,
    max_width: int = None,
) -> list[str]:
    """把多行长消息折叠为单行「摘要 + 规模标注」。

    控制台只保留可扫读的信息量；完整内容仍在日志文件里。规模标注默认按
    传入的 lines 统计，需要反映压缩前规模时由调用方传入 total_*。
    max_width 应为正文可用宽度（不含续行标记）。
    """
    if len(lines) <= 1:
        return lines

    if total_bytes is None:
        total_bytes = sum(len(line.encode("utf-8", errors="replace")) for line in lines)
    if total_lines is None:
        total_lines = len(lines)

    tail = f"(+{total_lines - 1} 行, {_human_size(total_bytes)})"
    # 摘要按显示宽度裁剪，保证「摘要 + 规模标注」共占一行不被再次折开
    budget = CONSOLE_SUMMARY_TEXT
    if max_width:
        budget = min(budget, max(max_width - _display_width(f" … {tail}"), 16))
    head = _truncate_display(lines[0].strip(), budget).rstrip()
    # _truncate_display 已补过省略号时不再重复拼接
    separator = " " if head.endswith("…") else " … "
    return [f"{head}{separator}{tail}"]


def _record_lines(record, strip_ansi: bool = False, compact: bool = False):
    """获取原始日志行（包含异常信息），可选择去除 ANSI 颜色代码和压缩长内容。"""
    cache_attr = "_yuki_clean_message" if strip_ansi else "_yuki_raw_message"
    if hasattr(record, cache_attr):
        message = getattr(record, cache_attr)
    else:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{_EXCEPTION_FORMATTER.formatException(record.exc_info)}"
        if strip_ansi:
            message = _strip_ansi(message)
        setattr(record, cache_attr, message)

    if compact:
        message = _compact_log_message(message)
    return message.splitlines() or [""]


def _message_scale(record) -> tuple[int, int]:
    """压缩前消息的（行数, 字节数），用于控制台折叠标注。"""
    raw = _record_lines(record, strip_ansi=True, compact=False)
    total_bytes = sum(len(line.encode("utf-8", errors="replace")) for line in raw)
    return len(raw), total_bytes


def _wrap_lines(
    record,
    max_width=None,
    strip_ansi=True,
    compact=False,
    break_long_words=False,
):
    """
    获取原始行，并自动按宽度折叠每一行。

    :param max_width: 每行最大字符数，None 则自动取终端宽度
    :param strip_ansi: 是否先去除 ANSI 颜色代码
    :param compact: 是否压缩结构化长内容
    :param break_long_words: 是否允许折断超长 token
    """
    raw_lines = _record_lines(record, strip_ansi=strip_ansi, compact=compact)

    if max_width is None:
        try:
            terminal_width = shutil.get_terminal_size().columns
            max_width = max(terminal_width - 1, 60)
        except Exception:
            max_width = 120

    wrapped = []
    for line in raw_lines:
        if len(line) <= max_width:
            wrapped.append(line)
        else:
            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=max_width,
                    break_on_hyphens=False,
                    break_long_words=break_long_words,
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

        # 文件日志总宽度约 180，保留完整内容，仅做折行
        message_width = max(180 - prefix_width, 80)
        lines = _wrap_lines(record, max_width=message_width, strip_ansi=True)

        # 异常堆栈不受行数上限约束：截断堆栈会让排障失去意义
        if not record.exc_info and len(lines) > FILE_MAX_LINES:
            hidden = len(lines) - FILE_MAX_LINES
            lines = lines[:FILE_MAX_LINES]
            lines.append(f"... <truncated {hidden} lines>")

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
    自动根据终端宽度折行，默认压缩结构化长内容。

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

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color
        self._terminal_width = 120
        self._terminal_width_checked_at = 0.0

    def formatTime(self, record, datefmt=None):
        return _format_time(record)

    def _get_terminal_width(self):
        now = time.monotonic()
        if now - self._terminal_width_checked_at >= CONSOLE_WIDTH_REFRESH_INTERVAL:
            try:
                self._terminal_width = shutil.get_terminal_size().columns
            except Exception:
                self._terminal_width = 120
            self._terminal_width_checked_at = now
        return self._terminal_width

    @staticmethod
    def _fit_metadata(parts: tuple[str, ...], terminal_width: int) -> str:
        """在宽度内保留尽可能完整的元数据，超宽时先丢时间、再丢文件名。"""
        time_part, level, loc = parts
        candidates = (
            f"{time_part} {level} {loc}",
            f"{level} {loc}",
            loc,
        )
        for candidate in candidates:
            if _display_width(candidate) <= terminal_width:
                return candidate
        return _truncate_display(loc, terminal_width)

    def format(self, record):
        asctime = self.formatTime(record)
        level = record.levelname.ljust(8)
        location = f"{record.filename}:{record.lineno}".ljust(22)

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
        plain_prefix = f"[{asctime}] {level} {location} │"
        terminal_width = max(self._get_terminal_width() - 1, 1)
        prefix_width = _display_width(plain_prefix) + 1
        body_width = terminal_width - prefix_width
        compact_layout = body_width < CONSOLE_MIN_INLINE_TEXT_WIDTH
        raw_lines = _record_lines(record, strip_ansi=True, compact=True)
        # 多行长消息收敛为单行摘要，明细只留在日志文件
        if len(raw_lines) > 1:
            total_lines, total_bytes = _message_scale(record)
            # 续行标记会占掉正文宽度，折叠预算按续行宽度算
            fold_width = terminal_width - 2 if compact_layout else body_width
            raw_lines = _fold_console_lines(
                raw_lines, total_lines, total_bytes, max(fold_width, 16)
            )

        if compact_layout:
            # 窄屏下不让长前缀挤占正文宽度，元数据和正文分行展示。
            metadata = self._fit_metadata(
                (f"[{asctime}]", record.levelname, f"{record.filename}:{record.lineno}"),
                terminal_width,
            )
            first_prefix = "├ " if terminal_width >= 4 else ">"
            marker = first_prefix
            body_width = max(terminal_width - _display_width(first_prefix), 1)
            lines = _wrap_display_lines(raw_lines, body_width)
        else:
            marker = " " * (prefix_width - 2) + "├ "
            lines = _wrap_display_lines(raw_lines, body_width)
            first_prefix = f"{prefix} "

        if len(lines) > CONSOLE_MAX_LINES:
            hidden = len(lines) - CONSOLE_MAX_LINES + 1
            lines = lines[:CONSOLE_MAX_LINES - 1]
            lines.append(_truncate_display(f"... truncated {hidden} lines", body_width))

        rendered = []
        if compact_layout:
            rendered.append(metadata)
            rendered.extend(f"{marker}{line}" for line in lines)
            return "\n".join(rendered)

        for i, line in enumerate(lines):
            rendered.append(f"{first_prefix if i == 0 else marker}{line}")
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


def setup_logging(level: int = None, debug: bool = False, console_level: int = None):
    """
    配置全局日志：
    - 启动时自动归档旧日志
    - 控制台输出（对齐结构 + ANSI 颜色，自动折行，默认 INFO）
    - 文件持久化（追加写入当前 yuki.log，自动折行，始终 DEBUG）

    控制台与文件分级：`debug` 只决定 root 与文件的详细度，控制台级别独立由
    `console_level`（或 `YUKI_LOG_CONSOLE_LEVEL`）控制，默认 INFO。这样
    `debug: true` 不会再让控制台变成 DEBUG 瀑布，排查时仍能翻日志文件。

    :param level: root 级别，None 时按 debug 取 DEBUG/INFO
    :param debug: 兼容旧调用方的开关，等价于 level=DEBUG
    :param console_level: 控制台级别，None 时读 YUKI_LOG_CONSOLE_LEVEL，默认 INFO
    """
    if level is None:
        level = logging.DEBUG if debug else logging.INFO

    if console_level is None:
        console_level = _env_level("YUKI_LOG_CONSOLE_LEVEL", logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler（重复调用时），防止运行中误归档当前日志
    if root.handlers:
        return

    # 首次初始化时归档上一次的日志
    _archive_existing_log()
    _try_enable_windows_ansi()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.addFilter(ConsoleNoiseFilter(allow_verbose=_verbose_allowed()))
    console_handler.setFormatter(ColoredConsoleFormatter(_color_mode(sys.stdout)))
    root.addHandler(console_handler)

    # 文件 handler：追加写入新日志
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PrettyFormatter())
    root.addHandler(file_handler)

    # 抑制冗长日志
    _silence_noisy_loggers()
    _silence_verbose_loggers(debug=debug)


def get_logger(name: str) -> logging.Logger:
    """获取一个已配置好的 logger 实例。"""
    return logging.getLogger(name)
