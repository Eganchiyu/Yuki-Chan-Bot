import logging

from utils.logger import (
    ColoredConsoleFormatter,
    ConsoleNoiseFilter,
    PrettyFormatter,
    _compact_log_message,
    _display_width,
    _strip_ansi,
)


def _make_record(message: str, level: int = logging.INFO, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
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


def test_chinese_wrap_respects_terminal_width(monkeypatch):
    """中文与 Emoji 折行后，每个物理行都不超过终端宽度。"""
    width = 80
    lines = _format_with_width(
        monkeypatch,
        "中文日志内容用于验证显示宽度折行🙂以及后续文本不会发生二次折行错位",
        width,
    )

    assert len(lines) > 1
    assert all(_display_width(_strip_ansi(line)) <= width - 1 for line in lines)


def test_long_unbroken_token_respects_terminal_width(monkeypatch):
    """无空格长 token 必须按显示宽度硬折行。"""
    width = 76
    lines = _format_with_width(monkeypatch, "x" * 180, width)

    assert len(lines) > 1
    assert all(_display_width(_strip_ansi(line)) <= width - 1 for line in lines)


def test_narrow_terminal_uses_separate_body_lines(monkeypatch):
    """前缀放不下时正文另起行，避免退化为单字符瀑布。"""
    width = 44
    lines = _format_with_width(monkeypatch, "窄屏正文需要保持可读并连续展示多个字符", width)
    metadata = lines[0]
    body_lines = lines[1:]

    assert metadata == _strip_ansi(metadata)
    assert _display_width(metadata) <= width - 1
    assert "INFO" in metadata
    assert not metadata.startswith("├ ")
    assert body_lines
    assert all(line.startswith("├ ") for line in body_lines)
    assert max(_display_width(line.removeprefix("├ ")) for line in body_lines) > 2
    assert all(_display_width(_strip_ansi(line)) <= width - 1 for line in body_lines)


def test_narrow_terminal_keeps_most_specific_metadata(monkeypatch):
    """窄屏放不下完整元数据时，优先保留定位信息而不是从中间截断。"""
    width = 44
    lines = _format_with_width(monkeypatch, "正文", width)

    assert "test_logger.py:42" in lines[0]
    assert not lines[0].endswith("…")


def test_multiline_message_folds_to_summary(monkeypatch):
    """多行长消息折叠成一行摘要 + 规模标注，明细只留在日志文件。"""
    width = 120
    body = "\n".join(f"第 {i} 行：这是任务执行过程中产生的较长的说明文本" for i in range(40))
    lines = _format_with_width(monkeypatch, f"[Maid] 任务达成: {body}", width)

    assert len(lines) == 1
    assert "+39 行" in lines[0]
    assert _display_width(_strip_ansi(lines[0])) <= width - 1


def test_single_line_message_is_not_folded(monkeypatch):
    """单行短消息不应出现折叠标注。"""
    lines = _format_with_width(monkeypatch, "[Pipeline] 上下文加载完成", 120)

    assert len(lines) == 1
    assert "行," not in lines[0]
    assert lines[0].endswith("上下文加载完成")


def test_embedded_mapping_is_compacted():
    """前缀 + 内嵌 dict 字面量压缩为键值摘要。"""
    payload = {
        "post_type": "meta_event",
        "meta_event_type": "heartbeat",
        "interval": 10000,
        "self_id": 3580583831,
        "status": {"online": True, "good": True},
        "padding": "x" * 400,
    }
    compacted = _compact_log_message(f"收到事件: {payload!r}")

    assert compacted.startswith("收到事件: {post_type=")
    assert "meta_event_type='heartbeat'" in compacted
    assert "x" * 400 not in compacted
    assert len(compacted) < 400


def test_plain_prose_message_is_untouched():
    """普通散文日志不因压缩逻辑被改写。"""
    message = "[Pipeline] 检索到 3 条相关日记"

    assert _compact_log_message(message) == message


def test_wrap_prefers_separator_boundary(monkeypatch):
    """折行优先落在分隔符处，不从 ASCII token 中间切开。"""
    width = 60
    lines = _format_with_width(
        monkeypatch,
        "cfg: a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8, i=9, j=10, k=11, l=12",
        width,
    )

    assert len(lines) > 1
    bodies = [_strip_ansi(line).split("│", 1)[-1].split("├", 1)[-1].strip() for line in lines]
    # 续行都以完整 token 开头，没有 `k=1` 这种被切开的赋值
    for body in bodies[1:]:
        first_token = body.split(",")[0].strip()
        assert first_token.count("=") <= 1
        assert not first_token.startswith("=")


def test_fold_reports_pre_truncation_scale(monkeypatch):
    """折叠标注反映压缩前规模，而不是截断后的残量。"""
    width = 120
    line_count = 40
    lines = _format_with_width(
        monkeypatch,
        "\n".join(f"第 {i} 行：说明文本" for i in range(line_count)),
        width,
    )

    assert len(lines) == 1
    assert f"+{line_count - 1} 行" in lines[0]
    assert _display_width(_strip_ansi(lines[0])) <= width - 1


def test_console_noise_filter_drops_verbose_debug():
    """控制台过滤器拦截项目内高频 DEBUG，但保留 INFO 与第三方记录。"""
    noise_filter = ConsoleNoiseFilter()
    verbose_debug = _make_record("细节", level=logging.DEBUG)
    verbose_debug.name = "session_pipeline"
    ordinary_info = _make_record("[Pipeline] 上下文加载完成", level=logging.INFO)
    ordinary_info.name = "session_pipeline"
    third_party_debug = _make_record("frame", level=logging.DEBUG)
    third_party_debug.name = "some.library"

    assert noise_filter.filter(verbose_debug) is False
    assert noise_filter.filter(ordinary_info) is True
    assert noise_filter.filter(third_party_debug) is True


def test_console_noise_filter_can_be_disabled():
    """YUKI_LOG_CONSOLE_VERBOSE=1 时整体放行。"""
    noise_filter = ConsoleNoiseFilter(allow_verbose=True)
    record = _make_record("细节", level=logging.DEBUG)
    record.name = "session_pipeline"

    assert noise_filter.filter(record) is True


def test_file_formatter_truncates_runaway_multiline_message():
    """普通多行文本在文件里也有行数上限，避免单条记录吃掉整个日志。"""
    from utils import logger as logger_module

    record = _make_record("\n".join(f"line {i}" for i in range(logger_module.FILE_MAX_LINES + 20)))
    out = PrettyFormatter().format(record)

    assert out.count("\n") <= logger_module.FILE_MAX_LINES
    assert "truncated" in out


def test_file_formatter_keeps_full_traceback():
    """异常堆栈不受行数上限约束，否则排障失去意义。"""
    from utils import logger as logger_module

    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    long_message = "\n".join(f"frame {i}" for i in range(logger_module.FILE_MAX_LINES + 20))
    out = PrettyFormatter().format(_make_record(long_message, level=logging.ERROR, exc_info=exc_info))

    assert "truncated" not in out
    assert "ValueError: boom" in out


def test_setup_logging_decouples_console_and_file(monkeypatch, tmp_path):
    """debug=True 时文件仍记 DEBUG，控制台默认只到 INFO。"""
    from utils import logger as logger_module

    monkeypatch.setenv("YUKI_LOG_CONSOLE_LEVEL", "")
    monkeypatch.setattr(logger_module, "LOG_FILE", str(tmp_path / "yuki.log"))
    monkeypatch.setattr(logger_module, "_archive_existing_log", lambda: None)

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    try:
        logger_module.setup_logging(debug=True)
        console_handler, file_handler = root.handlers

        assert console_handler.level == logging.INFO
        assert file_handler.level == logging.DEBUG
        assert any(isinstance(f, ConsoleNoiseFilter) for f in console_handler.filters)
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def test_setup_logging_console_level_env_override(monkeypatch, tmp_path):
    """YUKI_LOG_CONSOLE_LEVEL 可显式把控制台拉到 DEBUG。"""
    from utils import logger as logger_module

    monkeypatch.setenv("YUKI_LOG_CONSOLE_LEVEL", "DEBUG")
    monkeypatch.setattr(logger_module, "LOG_FILE", str(tmp_path / "yuki.log"))
    monkeypatch.setattr(logger_module, "_archive_existing_log", lambda: None)

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    try:
        logger_module.setup_logging(debug=False)
        console_handler = root.handlers[0]

        assert console_handler.level == logging.DEBUG
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)
