"""日志系统 (utils/logger.py) 单元测试。"""
import logging
import sys

from utils import logger as logger_module
from utils.logger import (
    ColoredConsoleFormatter,
    ConsoleNoiseFilter,
    PrettyFormatter,
    _compact_log_message,
    _display_width,
    _strip_ansi,
)


def _make_record(message: str, level: int = logging.INFO, exc_info=None, name: str = "test.logger") -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="/tmp/test_logger.py",
        lineno=42,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def _format_with_width(monkeypatch, message: str, width: int, level: int = logging.INFO) -> list[str]:
    formatter = ColoredConsoleFormatter(use_color=True)
    monkeypatch.setattr(formatter, "_get_terminal_width", lambda: width)
    return formatter.format(_make_record(message, level=level)).splitlines()


def test_terminal_width_wrapping(monkeypatch):
    """中文、Emoji、无空格长 token 折行后不超出终端宽度，且优先在分隔符处断开。"""
    lines_cjk = _format_with_width(
        monkeypatch,
        "中文日志内容用于验证显示宽度折行🙂以及后续文本不会发生二次折行错位",
        80,
    )
    assert len(lines_cjk) > 1
    assert all(_display_width(_strip_ansi(line)) <= 79 for line in lines_cjk)

    lines_token = _format_with_width(monkeypatch, "x" * 180, 76)
    assert len(lines_token) > 1
    assert all(_display_width(_strip_ansi(line)) <= 75 for line in lines_token)

    lines_sep = _format_with_width(
        monkeypatch,
        "cfg: a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8, i=9, j=10, k=11, l=12",
        60,
    )
    assert len(lines_sep) > 1
    bodies = [_strip_ansi(line).split("│", 1)[-1].split("├", 1)[-1].strip() for line in lines_sep]
    for body in bodies[1:]:
        first_token = body.split(",")[0].strip()
        assert first_token.count("=") <= 1 and not first_token.startswith("=")


def test_narrow_terminal_layout(monkeypatch):
    """窄屏下优先保留文件行号定位信息，正文另起行避免单字符瀑布。"""
    width = 44
    lines = _format_with_width(monkeypatch, "窄屏正文需要保持可读并连续展示多个字符", width)
    metadata, body_lines = lines[0], lines[1:]

    assert "test_logger.py:42" in metadata
    assert not metadata.endswith("…")
    assert _display_width(_strip_ansi(metadata)) <= width - 1
    assert body_lines and all(line.startswith("├ ") for line in body_lines)
    assert max(_display_width(line.removeprefix("├ ")) for line in body_lines) > 2
    assert all(_display_width(_strip_ansi(line)) <= width - 1 for line in body_lines)


def test_multiline_folding_and_mapping_compaction(monkeypatch):
    """多行长消息折叠为单行摘要并标注原始行数；单行短消息与普通文本不折叠；内嵌 dict 自动压缩。"""
    width = 120
    body = "\n".join(f"第 {i} 行：这是任务执行过程中产生的较长的说明文本" for i in range(40))
    folded = _format_with_width(monkeypatch, f"[Maid] 任务达成: {body}", width)
    assert len(folded) == 1
    assert "+39 行" in folded[0]
    assert _display_width(_strip_ansi(folded[0])) <= width - 1

    single = _format_with_width(monkeypatch, "[Pipeline] 上下文加载完成", width)
    assert len(single) == 1 and "行," not in single[0] and single[0].endswith("上下文加载完成")

    payload = {
        "post_type": "meta_event",
        "meta_event_type": "heartbeat",
        "interval": 10000,
        "padding": "x" * 400,
    }
    compacted = _compact_log_message(f"收到事件: {payload!r}")
    assert compacted.startswith("收到事件: {post_type=")
    assert "meta_event_type='heartbeat'" in compacted
    assert "x" * 400 not in compacted

    prose = "[Pipeline] 检索到 3 条相关日记"
    assert _compact_log_message(prose) == prose


def test_console_noise_filter():
    """控制台过滤器默认拦截项目内高频 DEBUG，保留 INFO 与第三方记录；可通过开关放行。"""
    default_filter = ConsoleNoiseFilter()
    assert default_filter.filter(_make_record("细节", logging.DEBUG, name="session_pipeline")) is False
    assert default_filter.filter(_make_record("正常", logging.INFO, name="session_pipeline")) is True
    assert default_filter.filter(_make_record("frame", logging.DEBUG, name="some.library")) is True

    verbose_filter = ConsoleNoiseFilter(allow_verbose=True)
    assert verbose_filter.filter(_make_record("细节", logging.DEBUG, name="session_pipeline")) is True


def test_file_formatter_truncates_multiline_but_keeps_traceback():
    """文件日志截断超长多行普通消息，但完整保留异常堆栈。"""
    long_msg = "\n".join(f"line {i}" for i in range(logger_module.FILE_MAX_LINES + 20))
    out = PrettyFormatter().format(_make_record(long_msg))
    assert out.count("\n") <= logger_module.FILE_MAX_LINES
    assert "truncated" in out

    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()

    err_out = PrettyFormatter().format(_make_record(long_msg, level=logging.ERROR, exc_info=exc_info))
    assert "truncated" not in err_out
    assert "ValueError: boom" in err_out


def test_setup_logging_decouples_console_and_file(monkeypatch, tmp_path):
    """setup_logging 解耦文件与控制台日志级别，并支持环境变量覆盖控制台级别。"""
    monkeypatch.setattr(logger_module, "LOG_FILE", str(tmp_path / "yuki.log"))
    monkeypatch.setattr(logger_module, "_archive_existing_log", lambda: None)

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    try:
        monkeypatch.setenv("YUKI_LOG_CONSOLE_LEVEL", "")
        logger_module.setup_logging(debug=True)
        console_handler, file_handler = root.handlers
        assert console_handler.level == logging.INFO
        assert file_handler.level == logging.DEBUG
        assert any(isinstance(f, ConsoleNoiseFilter) for f in console_handler.filters)

        for h in root.handlers:
            h.close()
        root.handlers = []

        monkeypatch.setenv("YUKI_LOG_CONSOLE_LEVEL", "DEBUG")
        logger_module.setup_logging(debug=False)
        assert root.handlers[0].level == logging.DEBUG
    finally:
        for h in root.handlers:
            h.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)
