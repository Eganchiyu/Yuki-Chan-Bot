import logging

from utils.logger import ColoredConsoleFormatter, _display_width, _strip_ansi


def _make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="/tmp/test_logger.py",
        lineno=42,
        msg=message,
        args=(),
        exc_info=None,
    )


def _format_with_width(monkeypatch, message: str, width: int) -> list[str]:
    formatter = ColoredConsoleFormatter(use_color=True)
    monkeypatch.setattr(formatter, "_get_terminal_width", lambda: width)
    return formatter.format(_make_record(message)).splitlines()


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
    assert metadata.endswith("…")
    assert _display_width(metadata) == width - 1
    assert "INFO" in metadata
    assert "test_logger.py" in metadata
    assert not metadata.startswith("├ ")
    assert body_lines
    assert all(line.startswith("├ ") for line in body_lines)
    assert max(_display_width(line.removeprefix("├ ")) for line in body_lines) > 2
    assert all(_display_width(_strip_ansi(line)) <= width - 1 for line in body_lines)
