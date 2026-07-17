from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from utils import BASE_DIR


CARD_DIR = Path(BASE_DIR) / "workspace" / "github_monitor"
CARD_WIDTH = 1000
PADDING = 48
HEADER_HEIGHT = 64
BADGE_RADIUS = 8


# 事件类型配色
EVENT_COLORS: dict[str, str] = {
    "PushEvent": "#1a7f37",
    "IssuesEvent": "#8956e3",
    "PullRequestEvent": "#2563eb",
    "IssueCommentEvent": "#6e7781",
    "PullRequestReviewCommentEvent": "#6e7781",
    "DiscussionEvent": "#d73a49",
    "DiscussionCommentEvent": "#6e7781",
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


def _event_color(event_type: str) -> str:
    return EVENT_COLORS.get(event_type, "#6e7781")


def _badge_label(event_type: str) -> str:
    return BADGE_LABELS.get(event_type, event_type)


def render_event_card(
    repo_key: str,
    event: dict[str, Any],
    title: str,
    action: str,
    commits: list[dict[str, Any]] | None = None,
    compare_data: dict[str, Any] | None = None,
) -> str:
    payload = event.get("payload", {})
    actor = event.get("actor", {}).get("login", "someone")
    event_type = event.get("type", "GitHubEvent")
    event_color = _event_color(event_type)

    # ---------- 构建内容行 ----------
    header_lines = [repo_key, f"{action}  ·  {event_type}"]
    body_lines: list[str] = [title or "Untitled"]

    if event_type == "PushEvent":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else "unknown"
        commits = commits if commits is not None else payload.get("commits", [])
        compare_data = compare_data or {}
        files = compare_data.get("files", [])
        additions = sum(_change_count(f.get("additions")) for f in files if isinstance(f, dict))
        deletions = sum(_change_count(f.get("deletions")) for f in files if isinstance(f, dict))
        body_lines.append(f"分支 {branch}  ·  {len(commits)} commits  ·  {len(files)} files")
        if files:
            body_lines.append(f"代码变更  +{additions} / -{deletions}")
        for commit in commits[:6]:
            metadata = commit.get("commit") or {}
            message = _single_line(metadata.get("message") or commit.get("message"))[:160]
            sha = str(commit.get("sha") or "")[:7]
            comment_count = int(metadata.get("comment_count", 0) or 0)
            comment_text = f"  ·  {comment_count} comments" if comment_count else ""
            body_lines.append(f"• {sha or 'unknown'}  {message or '无提交说明'}{comment_text}")
        if len(commits) > 6:
            body_lines.append(f"其余 {len(commits) - 6} 个提交未展开")
        compare_url = compare_data.get("html_url") or payload.get("compare")
        if compare_url:
            body_lines.append(str(compare_url))
    else:
        body = _event_preview(payload, event_type)
        if body:
            body_lines.append(body)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    footer_lines = [f"@{actor}  ·  {timestamp}", f"https://github.com/{repo_key}"]

    # ---------- 字体 ----------
    font_header_repo = _load_font(26, bold=True)
    font_header_meta = _load_font(22)
    font_title = _load_font(34, bold=True)
    font_body = _load_font(24)
    font_footer = _load_font(22)
    font_badge = _load_font(18, bold=True)

    # ---------- 自动换行 ----------
    header_wrapped: list[str] = []
    for idx, line in enumerate(header_lines):
        header_wrapped.extend(
            _wrap(
                line,
                font_header_repo if idx == 0 else font_header_meta,
                CARD_WIDTH - PADDING * 2 - 140,
            )
        )

    body_wrapped: list[str] = []
    for idx, line in enumerate(body_lines):
        body_wrapped.extend(
            _wrap(
                line,
                font_title if idx == 0 else font_body,
                CARD_WIDTH - PADDING * 2,
            )
        )

    footer_wrapped: list[str] = []
    for line in footer_lines:
        footer_wrapped.extend(_wrap(line, font_footer, CARD_WIDTH - PADDING * 2))

    line_height = 42
    header_lines_count = len(header_wrapped)
    body_lines_count = len(body_wrapped)
    footer_lines_count = len(footer_wrapped)

    section_gap = 16
    height = (
        PADDING
        + HEADER_HEIGHT
        + section_gap
        + body_lines_count * line_height
        + section_gap
        + footer_lines_count * line_height
        + PADDING
    )

    # ---------- 绘制底图 ----------
    image = Image.new("RGB", (CARD_WIDTH, height), "#f6f8fa")
    draw = ImageDraw.Draw(image)

    # 卡片主体（覆盖 header 以下全部区域，包括 footer）
    card_top = PADDING + HEADER_HEIGHT + section_gap - 8
    card_bottom = height - PADDING + 8
    _draw_rounded_rectangle(
        draw,
        (PADDING - 8, card_top, CARD_WIDTH - PADDING + 8, card_bottom),
        radius=16,
        fill="#ffffff",
        outline="#d0d7de",
        width=1,
    )

    # ---------- 顶部 Header 条 ----------
    header_top = PADDING
    header_bottom = PADDING + HEADER_HEIGHT
    _draw_rounded_rectangle(
        draw,
        (PADDING - 8, header_top, CARD_WIDTH - PADDING + 8, header_bottom),
        radius=16,
        fill=event_color,
    )
    # 覆盖底部圆角，使 header 与 body 平滑连接
    _draw_rounded_rectangle(
        draw,
        (PADDING - 8, header_bottom - 16, CARD_WIDTH - PADDING + 8, header_bottom),
        radius=16,
        fill=event_color,
    )

    # Header 文字
    y = header_top + 14
    for idx, text in enumerate(header_wrapped):
        fill = "#ffffff" if idx == 0 else "#e8e8e8"
        draw.text((PADDING + 12, y), text, font=font_header_repo if idx == 0 else font_header_meta, fill=fill)
        y += 32

    # Badge（事件类型标签）
    badge_text = _badge_label(event_type)
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    badge_width = badge_bbox[2] - badge_bbox[0] + 24
    badge_height = badge_bbox[3] - badge_bbox[1] + 12
    badge_x = CARD_WIDTH - PADDING - badge_width - 12
    badge_y = header_top + (HEADER_HEIGHT - badge_height) // 2
    _draw_rounded_rectangle(
        draw,
        (badge_x, badge_y, badge_x + badge_width, badge_y + badge_height),
        radius=BADGE_RADIUS,
        fill="#ffffff",
    )
    badge_text_y = badge_y + (badge_height - (badge_bbox[3] - badge_bbox[1])) // 2 - badge_bbox[1]
    draw.text(
        (badge_x + 12, badge_text_y),
        badge_text,
        font=font_badge,
        fill=event_color,
    )

    # ---------- Body 区域 ----------
    y = header_bottom + section_gap
    for idx, line in enumerate(body_wrapped):
        if idx == 0:
            draw.text((PADDING, y), line, font=font_title, fill="#1f2328")
        else:
            draw.text((PADDING, y), line, font=font_body, fill="#57606a")
        y += line_height

    # ---------- Footer 区域 ----------
    footer_y = y + section_gap
    # 分割线
    draw.line(
        (PADDING, footer_y, CARD_WIDTH - PADDING, footer_y),
        fill="#d0d7de",
        width=1,
    )
    footer_y += 12
    for idx, text in enumerate(footer_wrapped):
        if idx == len(footer_wrapped) - 1:
            draw.text((PADDING, footer_y), text, font=font_footer, fill="#0969da")
        else:
            draw.text((PADDING, footer_y), text, font=font_footer, fill="#57606a")
        footer_y += line_height

    # ---------- 保存 ----------
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "_", repo_key)
    event_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(event.get("id", "event")))
    path = CARD_DIR / f"{safe_repo}_{event_id}.png"
    image.save(path, format="PNG", optimize=True)
    return str(path.resolve())


def _event_preview(payload: dict[str, Any], event_type: str) -> str:
    if event_type in {"IssueCommentEvent", "PullRequestReviewCommentEvent", "DiscussionCommentEvent"}:
        comment = payload.get("comment", {})
        return _single_line(comment.get("body", ""))[:160]
    if event_type == "DiscussionEvent":
        return _single_line(payload.get("discussion", {}).get("body", ""))[:160]
    return ""


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _change_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    if not bold:
        candidates = candidates[1:]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    result: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and font.getlength(candidate) > max_width:
            result.append(current)
            current = char
        else:
            current = candidate
    result.append(current or "")
    return result


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
