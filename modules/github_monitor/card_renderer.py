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


def render_event_card(repo_key: str, event: dict[str, Any], title: str, action: str) -> str:
    payload = event.get("payload", {})
    actor = event.get("actor", {}).get("login", "someone")
    event_type = event.get("type", "GitHubEvent")
    lines = [repo_key, f"{action}  ·  {event_type}", title or "Untitled"]

    if event_type == "PushEvent":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else "unknown"
        commits = payload.get("commits", [])
        lines.append(f"分支 {branch}  ·  {len(commits)} commits")
        for commit in commits[:6]:
            metadata = commit.get("commit") or {}
            message = str(metadata.get("message") or commit.get("message") or "").splitlines()[0]
            sha = str(commit.get("sha") or "")[:7]
            lines.append(f"{sha or 'unknown'}  {message or '无提交说明'}")
    else:
        body = _event_preview(payload, event_type)
        if body:
            lines.append(body)

    lines.append(f"@{actor}  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"https://github.com/{repo_key}")
    font_regular = _load_font(30)
    font_small = _load_font(24)
    font_title = _load_font(42, bold=True)
    wrapped = []
    for index, line in enumerate(lines):
        font = font_title if index == 0 else font_regular if index == 2 else font_small
        wrapped.extend((text, font) for text in _wrap(line, font, CARD_WIDTH - PADDING * 2))

    line_height = 58
    height = PADDING * 2 + 42 + len(wrapped) * line_height
    image = Image.new("RGB", (CARD_WIDTH, height), "#f7f8fa")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, CARD_WIDTH - 18, height - 18), radius=18, fill="#ffffff", outline="#d0d7de", width=2)
    draw.rectangle((18, 18, 30, height - 18), fill="#238636")
    y = PADDING
    for text, font in wrapped:
        color = "#1f2328" if font == font_title else "#57606a"
        draw.text((PADDING, y), text, font=font, fill=color)
        y += line_height

    CARD_DIR.mkdir(parents=True, exist_ok=True)
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "_", repo_key)
    event_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(event.get("id", "event")))
    path = CARD_DIR / f"{safe_repo}_{event_id}.png"
    image.save(path, format="PNG", optimize=True)
    return str(path.resolve())


def _event_preview(payload: dict[str, Any], event_type: str) -> str:
    if event_type in {"IssueCommentEvent", "PullRequestReviewCommentEvent", "DiscussionCommentEvent"}:
        comment = payload.get("comment", {})
        return _single_line(comment.get("body", ""))[:180]
    if event_type == "DiscussionEvent":
        return _single_line(payload.get("discussion", {}).get("body", ""))[:180]
    return ""


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    if bold:
        candidates.insert(0, Path("C:/Windows/Fonts/msyhbd.ttc"))
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    result = []
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
