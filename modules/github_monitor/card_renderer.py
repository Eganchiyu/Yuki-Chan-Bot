from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from utils import BASE_DIR


CARD_DIR = Path(BASE_DIR) / "workspace" / "github_monitor"

# 设计系统：尺寸
CARD_WIDTH = 1000
CARD_RADIUS = 20
SHADOW_OFFSET = 5
SHADOW_BLUR = 12
SHADOW_ALPHA = 26
SHADOW_MARGIN = 20

PADDING_X = 52
PADDING_Y = 44
HEADER_MIN_HEIGHT = 80
BADGE_RADIUS = 10
SECTION_GAP = 22
MIN_BODY_HEIGHT = 120

# 设计系统：颜色（现代、协调、层级清晰）
BACKGROUND_COLOR = "#f3f4f6"          # 温暖浅灰，减轻视觉疲劳
CARD_BG_COLOR = "#ffffff"             # 纯白卡片，干净通透
CARD_BORDER_COLOR = "#e5e7eb"         # 柔和边框，让阴影成为主角
TITLE_COLOR = "#111827"               # 深墨黑，标题对比更强
BODY_COLOR = "#4b5563"                # 均衡灰，正文阅读舒适
FOOTER_COLOR = "#6b7280"              # 比正文稍浅，层级分明
LINK_COLOR = "#2563eb"                # 鲜亮蓝，链接更醒目
ADDITIONS_COLOR = "#16a34a"           # 清新绿，与 Push 事件统一
DELETIONS_COLOR = "#dc2626"           # 醒目红，与 Discussion 事件统一
MUTED_COLOR = "#9ca3af"               # 柔和灰，用于次要注释

# 事件类型配色（更鲜明、对比更舒适的现代色调）
EVENT_COLORS: dict[str, str] = {
    "PushEvent": "#16a34a",
    "IssuesEvent": "#7c3aed",
    "PullRequestEvent": "#2563eb",
    "IssueCommentEvent": "#6b7280",
    "PullRequestReviewCommentEvent": "#6b7280",
    "DiscussionEvent": "#dc2626",
    "DiscussionCommentEvent": "#6b7280",
}

BADGE_LABELS: dict[str, str] = {
    "PushEvent": "Push",
    "IssuesEvent": "Issue",
    "PullRequestEvent": "PR",
    "IssueCommentEvent": "Comment",
    "PullRequestReviewCommentEvent": "PR Review",
    "DiscussionEvent": "Discussion",
    "DiscussionCommentEvent": "Comment",
}

_FONT_CACHE: dict[tuple[int, bool, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


@dataclass
class TextLine:
    """正文行定义，支持提交项特殊渲染。"""

    text: str
    font: ImageFont.ImageFont
    color: str
    indent: int = 0
    sha: str = ""
    comments: str = ""
    is_stats: bool = False
    additions: int = 0
    deletions: int = 0
    prefix_width: int = 0
    comment_width: int = 0


@dataclass
class BodyBlock:
    """正文块，由若干文本行组成，可设置上下边距。"""

    lines: list[TextLine]
    top_margin: int = 0
    bottom_margin: int = 0


def _event_color(event_type: str) -> str:
    """返回事件类型对应的主色。"""
    return EVENT_COLORS.get(event_type, "#6e7781")


def _badge_label(event_type: str) -> str:
    """返回事件类型对应的 Badge 文案。"""
    return BADGE_LABELS.get(event_type, event_type)


def _load_font(
    size: int,
    bold: bool = False,
    mono: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载字体，优先使用系统 CJK 字体，带缓存。"""
    key = (size, bold, mono)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    candidates: list[Path] = []
    if mono:
        candidates = [
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("C:/Windows/Fonts/cour.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ]
    else:
        candidates = [
            Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path(
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
            ) if bold else Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ]

    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.load_default()
    for candidate in candidates:
        if candidate.exists():
            try:
                font = ImageFont.truetype(str(candidate), size)
                break
            except OSError:
                continue

    _FONT_CACHE[key] = font
    return font


def _line_height(font: ImageFont.ImageFont) -> int:
    """根据字体度量计算行高。"""
    bbox = font.getbbox("测试TestAy")
    if bbox:
        return int((bbox[3] - bbox[1]) * 1.48)
    return int(font.size * 1.48)


def _text_width(text: str, font: ImageFont.ImageFont) -> int:
    """计算文本渲染宽度。"""
    if hasattr(font, "getlength"):
        return int(font.getlength(text))
    bbox = font.getbbox(text)
    if bbox:
        return bbox[2] - bbox[0]
    return len(text) * font.size // 2


def _is_cjk(char: str) -> bool:
    """判断字符是否属于 CJK 字符，用于智能换行。"""
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0x3040 <= code <= 0x309F  # Hiragana
        or 0x30A0 <= code <= 0x30FF  # Katakana
        or 0xFF00 <= code <= 0xFFEF  # Full-width forms
    )


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """智能换行：英文单词尽量不截断，CJK 按字符换行，超长单词强制截断。

    Args:
        text: 原始文本。
        font: 用于宽度测量的字体。
        max_width: 最大行宽（像素）。

    Returns:
        换行后的文本列表。
    """
    if not text:
        return [""]
    if max_width <= 0:
        return [text]

    result: list[str] = []
    current = ""
    i = 0
    n = len(text)

    while i < n:
        char = text[i]

        # 空白字符：吸收到当前行末尾，不单独换行
        if char.isspace():
            if current and _text_width(current + char, font) <= max_width:
                current += char
            i += 1
            continue

        # CJK 字符：每个字符都是潜在断点
        if _is_cjk(char):
            candidate = current + char
            if current and _text_width(candidate, font) > max_width:
                result.append(current.rstrip())
                current = char
            else:
                current = candidate
            i += 1
            continue

        # 非 CJK 单词：整体尝试放入当前行
        word_start = i
        while i < n and not _is_cjk(text[i]) and not text[i].isspace():
            i += 1
        word = text[word_start:i]

        candidate = current + word
        if current and _text_width(candidate, font) > max_width:
            result.append(current.rstrip())
            current = word
        else:
            current = candidate

        # 单词本身超过行宽时强制按字符截断
        if _text_width(current, font) > max_width:
            forced = ""
            for c in current:
                cand = forced + c
                if forced and _text_width(cand, font) > max_width:
                    result.append(forced)
                    forced = c
                else:
                    forced = cand
            current = forced

    if current:
        result.append(current.rstrip())

    return result or [""]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """将 3/6 位十六进制颜色转为 RGB 元组。"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _darken(hex_color: str, amount: int = 25) -> str:
    """将颜色加深指定量。"""
    r, g, b = _hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(max(0, r - amount), max(0, g - amount), max(0, b - amount))


def _draw_gradient_header(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    base_color: str,
) -> None:
    """绘制顶部圆角、底部平直的渐变 Header。"""
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = max(1, y2 - y1)
    base = _hex_to_rgb(base_color)
    dark = _hex_to_rgb(_darken(base_color, 25))

    gradient = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(gradient)
    for row in range(height):
        ratio = row / max(1, height - 1)
        r = int(base[0] + (dark[0] - base[0]) * ratio)
        g = int(base[1] + (dark[1] - base[1]) * ratio)
        b = int(base[2] + (dark[2] - base[2]) * ratio)
        draw.line([(0, row), (width, row)], fill=(r, g, b))

    # 顶部圆角、底部平直的遮罩
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        (0, -CARD_RADIUS, width, height + CARD_RADIUS),
        radius=CARD_RADIUS,
        fill=255,
    )

    image.paste(gradient, (x1, y1), mask)


def _draw_rounded_rectangle(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    radius: int,
    fill: str | None = None,
    outline: str | None = None,
    width: int = 1,
) -> None:
    """绘制圆角矩形，兼容旧版 Pillow。"""
    x1, y1, x2, y2 = bbox
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=width)


def _measure_badge(text: str, font: ImageFont.ImageFont, padding_x: int = 14, padding_y: int = 8) -> tuple[int, int]:
    """测量圆角标签的宽高。"""
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    return text_w + padding_x * 2, text_h + padding_y * 2


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    text_color: str,
    bg_color: str,
    x: int,
    y: int,
    radius: int = BADGE_RADIUS,
    padding_x: int = 14,
    padding_y: int = 8,
) -> tuple[int, int]:
    """绘制圆角标签，返回实际宽高。"""
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    badge_w = text_w + padding_x * 2
    badge_h = text_h + padding_y * 2
    _draw_rounded_rectangle(
        draw,
        (x, y, x + badge_w, y + badge_h),
        radius=radius,
        fill=bg_color,
    )
    text_x = x + padding_x
    text_y = y + (badge_h - text_h) // 2 - bbox[1]
    draw.text((text_x, text_y), text, font=font, fill=text_color)
    return badge_w, badge_h


def _draw_shadow(
    image: Image.Image,
    card_bbox: tuple[int, int, int, int],
    radius: int,
    offset: int = SHADOW_OFFSET,
    blur: int = SHADOW_BLUR,
    alpha: int = SHADOW_ALPHA,
) -> None:
    """在卡片下方绘制柔和投影。"""
    x1, y1, x2, y2 = card_bbox
    shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.rounded_rectangle(
        (x1, y1 + offset, x2, y2 + offset),
        radius=radius,
        fill=(0, 0, 0, alpha),
    )
    if blur > 0:
        try:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur / 2))
        except Exception:
            pass
    image.paste(shadow_layer, (0, 0), shadow_layer)


def _event_preview(payload: dict[str, Any], event_type: str) -> str:
    """提取非 Push 事件的正文预览，提升卡片信息密度。"""
    if event_type in {"IssueCommentEvent", "PullRequestReviewCommentEvent", "DiscussionCommentEvent"}:
        comment = payload.get("comment", {})
        return _single_line(comment.get("body", ""))[:220]
    if event_type == "DiscussionEvent":
        return _single_line(payload.get("discussion", {}).get("body", ""))[:220]
    if event_type in {"IssuesEvent"}:
        return _single_line(payload.get("issue", {}).get("body", ""))[:220]
    if event_type in {"PullRequestEvent"}:
        return _single_line(payload.get("pull_request", {}).get("body", ""))[:220]
    return ""


def _single_line(value: Any) -> str:
    """将多行文本压缩为单行。"""
    return " ".join(str(value or "").split())


def _change_count(value: Any) -> int:
    """安全地将变更数转换为非负整数。"""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _build_body_blocks(
    repo_key: str,
    event: dict[str, Any],
    title: str,
    action: str,
    commits: list[dict[str, Any]] | None,
    compare_data: dict[str, Any] | None,
    fonts: dict[str, ImageFont.ImageFont],
) -> list[BodyBlock]:
    """根据事件类型构建正文块列表。

    保持与外界的输入/输出契约不变，只负责渲染内容的组织。
    """
    payload = event.get("payload", {})
    event_type = event.get("type", "GitHubEvent")
    blocks: list[BodyBlock] = []

    # 标题
    blocks.append(
        BodyBlock(
            lines=[TextLine(title or "Untitled", fonts["title"], TITLE_COLOR)],
            bottom_margin=4,
        )
    )

    if event_type == "PushEvent":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else "unknown"
        commits = commits if commits is not None else payload.get("commits", [])
        compare_data = compare_data or {}
        files = compare_data.get("files", [])
        additions = sum(_change_count(f.get("additions")) for f in files if isinstance(f, dict))
        deletions = sum(_change_count(f.get("deletions")) for f in files if isinstance(f, dict))

        # 分支 / 提交数 / 文件数
        meta = f"分支 {branch}  ·  {len(commits)} commits  ·  {len(files)} files"
        blocks.append(
            BodyBlock(
                lines=[TextLine(meta, fonts["meta"], BODY_COLOR)],
                bottom_margin=8,
            )
        )

        # 代码变更统计
        if files:
            blocks.append(
                BodyBlock(
                    lines=[
                        TextLine(
                            "",
                            fonts["stats"],
                            TITLE_COLOR,
                            is_stats=True,
                            additions=additions,
                            deletions=deletions,
                        )
                    ],
                    bottom_margin=12,
                )
            )

        # 提交列表
        commit_lines: list[TextLine] = []
        displayed = commits[:6]
        for commit in displayed:
            metadata = commit.get("commit") or {}
            message = _single_line(metadata.get("message") or commit.get("message"))[:300]
            sha = str(commit.get("sha") or "")[:7]
            comment_count = int(metadata.get("comment_count", 0) or 0)
            comments = f"{comment_count} comments" if comment_count else ""
            prefix = f"●  {sha or 'unknown'}  "
            comment_suffix = f"  ·  {comments}" if comments else ""
            commit_lines.append(
                TextLine(
                    text=message or "无提交说明",
                    font=fonts["body"],
                    color=BODY_COLOR,
                    indent=16,
                    sha=sha or "unknown",
                    comments=comments,
                    prefix_width=_text_width(prefix, fonts["body"]),
                    comment_width=_text_width(comment_suffix, fonts["body"]),
                )
            )

        if commit_lines:
            blocks.append(
                BodyBlock(
                    lines=commit_lines,
                    top_margin=4,
                    bottom_margin=8,
                )
            )

        if len(commits) > 6:
            blocks.append(
                BodyBlock(
                    lines=[
                        TextLine(
                            f"其余 {len(commits) - 6} 个提交未展开",
                            fonts["body_small"],
                            MUTED_COLOR,
                            indent=16,
                        )
                    ],
                    bottom_margin=8,
                )
            )

        compare_url = compare_data.get("html_url") or payload.get("compare")
        if compare_url:
            blocks.append(
                BodyBlock(
                    lines=[TextLine(str(compare_url), fonts["body_small"], LINK_COLOR)],
                    top_margin=4,
                )
            )
    else:
        body = _event_preview(payload, event_type)
        if body:
            blocks.append(
                BodyBlock(
                    lines=[TextLine(body, fonts["body"], BODY_COLOR)],
                    top_margin=4,
                )
            )

    return blocks


def _measure_body(
    blocks: list[BodyBlock],
    max_body_width: int,
) -> tuple[list[tuple[TextLine, int, list[str]]], int]:
    """测量正文块，返回每行的渲染信息及总高度。

    Returns:
        (lines_info, total_height)，其中 lines_info 每个元素为
        (原始行定义, 行高, 换行后的文本列表)。
    """
    lines_info: list[tuple[TextLine, int, list[str]]] = []
    total_height = 0

    for idx, block in enumerate(blocks):
        if not block.lines:
            continue
        if idx > 0:
            total_height += block.top_margin

        for line in block.lines:
            available_width = max_body_width - line.indent
            if line.sha:
                # 提交行需预留前缀（● + SHA + 间距）和评论后缀空间
                available_width -= line.prefix_width
                if line.comments:
                    available_width -= line.comment_width
                available_width = max(available_width, 40)
            wrapped = _wrap(line.text, line.font, available_width)
            lh = _line_height(line.font)
            total_height += len(wrapped) * lh
            lines_info.append((line, lh, wrapped))

        total_height += block.bottom_margin

    return lines_info, max(MIN_BODY_HEIGHT, total_height)


def _draw_commit_line(
    draw: ImageDraw.ImageDraw,
    line: TextLine,
    wrapped: list[str],
    x: int,
    y: int,
    event_color: str,
) -> int:
    """绘制提交行：彩色圆点 + 蓝色 SHA + 灰色消息，返回占用的总高度。"""
    bullet = "●"
    sha = line.sha or "unknown"
    bullet_w = _text_width(f"{bullet}  ", line.font)
    prefix_w = line.prefix_width
    comment_text = f"  ·  {line.comments}" if line.comments else ""

    consumed = 0
    for wrap_idx, wtext in enumerate(wrapped):
        line_y = y + consumed
        if wrap_idx == 0:
            draw.text((x, line_y), bullet, font=line.font, fill=event_color)
            draw.text((x + bullet_w, line_y), f"{sha}  ", font=line.font, fill=LINK_COLOR)
            draw.text((x + prefix_w, line_y), wtext, font=line.font, fill=line.color)
            if comment_text:
                msg_w = _text_width(wtext, line.font)
                draw.text(
                    (x + prefix_w + msg_w, line_y),
                    comment_text,
                    font=line.font,
                    fill=MUTED_COLOR,
                )
        else:
            # 后续行与消息起始对齐
            draw.text((x + prefix_w, line_y), wtext, font=line.font, fill=line.color)
        consumed += _line_height(line.font)

    return consumed


def _draw_stats_line(
    draw: ImageDraw.ImageDraw,
    line: TextLine,
    x: int,
    y: int,
) -> None:
    """绘制代码变更统计行：绿色新增 + 灰色分隔 + 红色删除。"""
    plus = f"+{line.additions}"
    minus = f"-{line.deletions}"
    sep = " / "

    draw.text((x, y), plus, font=line.font, fill=ADDITIONS_COLOR)
    x += _text_width(plus, line.font)
    draw.text((x, y), sep, font=line.font, fill=BODY_COLOR)
    x += _text_width(sep, line.font)
    draw.text((x, y), minus, font=line.font, fill=DELETIONS_COLOR)


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    line: TextLine,
    wrapped: list[str],
    x: int,
    y: int,
) -> int:
    """绘制普通文本行，返回占用的总高度。"""
    lh = _line_height(line.font)
    for idx, wtext in enumerate(wrapped):
        draw.text((x, y + idx * lh), wtext, font=line.font, fill=line.color)
    return len(wrapped) * lh


def render_event_card(
    repo_key: str,
    event: dict[str, Any],
    title: str,
    action: str,
    commits: list[dict[str, Any]] | None = None,
    compare_data: dict[str, Any] | None = None,
) -> str:
    """渲染 GitHub 事件卡片并返回保存的 PNG 文件路径。

    此函数只负责渲染内容的呈现，不改变与外界的数据流通：
    输入参数、返回值、文件保存路径规则均保持原契约。

    Args:
        repo_key: 仓库标识，如 "owner/repo"。
        event: GitHub Events API 返回的单个事件字典。
        title: 事件标题。
        action: 已格式化的动作描述。
        commits: Push 事件的提交列表（可选）。
        compare_data: Push 事件的 compare API 数据（可选）。

    Returns:
        生成的 PNG 文件绝对路径。
    """
    actor = event.get("actor", {}).get("login", "someone")
    event_type = event.get("type", "GitHubEvent")
    event_color = _event_color(event_type)

    # 加载字体
    fonts: dict[str, ImageFont.ImageFont] = {
        "header_repo": _load_font(26, bold=True),
        "header_meta": _load_font(20),
        "title": _load_font(34, bold=True),
        "body": _load_font(24),
        "body_small": _load_font(22),
        "meta": _load_font(22),
        "stats": _load_font(24, bold=True),
        "footer": _load_font(21),
        "badge": _load_font(17, bold=True),
    }

    # 构建正文块
    body_blocks = _build_body_blocks(
        repo_key, event, title, action, commits, compare_data, fonts
    )

    # 计算正文尺寸
    body_width = CARD_WIDTH - PADDING_X * 2
    body_lines_info, body_height = _measure_body(body_blocks, body_width)

    # Header 尺寸
    header_lines = [repo_key, f"{action}  ·  {event_type}"]
    badge_w, badge_h = _measure_badge(_badge_label(event_type), fonts["badge"])
    header_text_max_width = CARD_WIDTH - PADDING_X * 2 - badge_w - 24
    header_wrapped: list[tuple[str, ImageFont.ImageFont, str]] = []
    for idx, line in enumerate(header_lines):
        font = fonts["header_repo"] if idx == 0 else fonts["header_meta"]
        color = "#ffffff" if idx == 0 else "#ffffffcc"
        header_wrapped.extend((t, font, color) for t in _wrap(line, font, header_text_max_width))
    header_text_height = sum(_line_height(f) for _, f, _ in header_wrapped)
    header_height = max(HEADER_MIN_HEIGHT, header_text_height + 28)

    # Footer 尺寸
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    footer_lines = [f"@{actor}  ·  {timestamp}", f"https://github.com/{repo_key}"]
    footer_wrapped: list[tuple[str, ImageFont.ImageFont, str]] = []
    for idx, line in enumerate(footer_lines):
        color = LINK_COLOR if idx == len(footer_lines) - 1 else FOOTER_COLOR
        footer_wrapped.extend((t, fonts["footer"], color) for t in _wrap(line, fonts["footer"], body_width))
    footer_text_height = sum(_line_height(f) for _, f, _ in footer_wrapped)
    footer_height = footer_text_height + 32

    # 总高度（卡片主体，不含投影边距）
    card_height = (
        PADDING_Y + header_height + SECTION_GAP + body_height + SECTION_GAP + footer_height + PADDING_Y
    )

    # 创建带透明通道的画布，用于投影合成
    canvas_width = CARD_WIDTH + SHADOW_MARGIN * 2
    canvas_height = card_height + SHADOW_MARGIN * 2
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

    card_left = SHADOW_MARGIN
    card_top = SHADOW_MARGIN
    card_right = card_left + CARD_WIDTH
    card_bottom = card_top + card_height

    # 投影
    _draw_shadow(canvas, (card_left, card_top, card_right, card_bottom), CARD_RADIUS)

    # 卡片背景
    draw = ImageDraw.Draw(canvas)
    _draw_rounded_rectangle(
        draw,
        (card_left, card_top, card_right, card_bottom),
        radius=CARD_RADIUS,
        fill=CARD_BG_COLOR,
        outline=CARD_BORDER_COLOR,
        width=1,
    )

    # 渐变 Header
    header_bbox = (card_left, card_top, card_right, card_top + header_height)
    _draw_gradient_header(canvas, header_bbox, event_color)

    # Header 文字（垂直居中）
    header_text_top = card_top + (header_height - header_text_height) // 2
    y = header_text_top
    for text, font, color in header_wrapped:
        draw.text((card_left + PADDING_X, y), text, font=font, fill=color)
        y += _line_height(font)

    # Header Badge（垂直居中）
    badge_x = card_right - PADDING_X - badge_w
    badge_y = card_top + (header_height - badge_h) // 2
    _draw_badge(
        draw,
        _badge_label(event_type),
        fonts["badge"],
        event_color,
        CARD_BG_COLOR,
        badge_x,
        badge_y,
        radius=BADGE_RADIUS,
    )

    # Body 区域
    body_top = card_top + header_height + SECTION_GAP
    y = body_top
    block_line_idx = 0
    for block_idx, block in enumerate(body_blocks):
        if not block.lines:
            continue
        if block_idx > 0:
            y += block.top_margin

        for line in block.lines:
            line_def, lh, wrapped = body_lines_info[block_line_idx]
            block_line_idx += 1
            x = card_left + PADDING_X + line_def.indent

            if line_def.is_stats:
                _draw_stats_line(draw, line_def, x, y)
                y += lh
            elif line_def.sha:
                y += _draw_commit_line(draw, line_def, wrapped, x, y, event_color)
            else:
                y += _draw_wrapped_text(draw, line_def, wrapped, x, y)

        y += block.bottom_margin

    # Footer
    footer_top = card_top + header_height + SECTION_GAP + body_height + SECTION_GAP
    draw.line(
        (card_left + PADDING_X, footer_top, card_right - PADDING_X, footer_top),
        fill=CARD_BORDER_COLOR,
        width=1,
    )
    y = footer_top + 16
    for text, font, color in footer_wrapped:
        draw.text((card_left + PADDING_X, y), text, font=font, fill=color)
        y += _line_height(font)

    # 合成到最终 RGB 图像
    final = Image.new("RGB", (canvas_width, canvas_height), BACKGROUND_COLOR)
    final.paste(canvas, (0, 0), canvas)

    # 保存
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "_", repo_key)
    event_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(event.get("id", "event")))
    path = CARD_DIR / f"{safe_repo}_{event_id}.png"
    final.save(path, format="PNG", optimize=True)
    return str(path.resolve())
