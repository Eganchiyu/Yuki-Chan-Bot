import asyncio
import datetime
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from utils import BASE_DIR
from utils.http_client import create_tcp_connector
from utils.logger import get_logger

logger = get_logger("shot_renderer")

WIDTH = 900
PADDING_X = 34
AVATAR_SIZE = 48
BUBBLE_MAX_WIDTH = 640
TEXT_MAX_WIDTH = 580
MEDIA_MAX_WIDTH = 360
MEDIA_MAX_HEIGHT = 260
CACHE_DIR = os.path.join(BASE_DIR, "data", "shot_memory", "media_cache")


@dataclass
class RenderPart:
    kind: str
    text: str = ""
    image_path: str = ""


@dataclass
class RenderMessage:
    role: str
    name: str
    content: str = ""
    time: str = ""
    user_id: str = ""
    raw_segments: list = field(default_factory=list)
    parts: list[RenderPart] = field(default_factory=list)


async def render_snapshot(chat_id, note: str, history_messages: list[dict], message_objs: list[dict] | None, gateway=None, live_messages: list[dict] | None = None) -> tuple[bytes, dict]:
    group_meta = await fetch_group_meta(gateway, chat_id)
    messages = build_live_render_messages(live_messages) if live_messages else []
    if not messages:
        messages = build_render_messages(history_messages, message_objs)
    await enrich_member_names(gateway, chat_id, messages)
    await prepare_message_parts(messages)
    avatar_map = await load_avatars(messages)
    image = draw_snapshot(group_meta, note, messages, avatar_map)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    text = "\n".join(f"{m.name}: {parts_to_text(m)}" for m in messages)
    return out.getvalue(), {"group_name": group_meta.get("group_name", ""), "group_remark": group_meta.get("group_remark", ""), "text": text}


def build_live_render_messages(live_messages: list[dict] | None) -> list[RenderMessage]:
    result = []
    for item in live_messages or []:
        content = normalize_content(item.get("raw_text") or item.get("content") or "")
        role = "assistant" if item.get("is_bot") else "user"
        result.append(RenderMessage(
            role=role,
            name=item.get("name") or ("Yuki" if role == "assistant" else "群友"),
            content=content,
            time=item.get("time", ""),
            user_id=str(item.get("user_id") or ""),
            raw_segments=item.get("segments") or [],
        ))
    return result[-14:]


def build_render_messages(history_messages: list[dict], message_objs: list[dict] | None) -> list[RenderMessage]:
    result: list[RenderMessage] = []
    for item in history_messages:
        role = item.get("role", "")
        if role in ("system", "tool"):
            continue
        content = normalize_content(item.get("content", ""))
        if not content:
            continue
        name = "Yuki" if role == "assistant" else extract_name(content) or "群友"
        content = strip_prefix(content)
        result.append(RenderMessage(role=role, name=name, content=content, time=item.get("time", "")))

    uid_by_name = {}
    for obj in message_objs or []:
        name = obj.get("name") or extract_name(obj.get("content", ""))
        uid = obj.get("user_id")
        if name and uid:
            uid_by_name[str(name)] = str(uid)
    for msg in result:
        if msg.name in uid_by_name:
            msg.user_id = uid_by_name[msg.name]
    return result[-14:]


async def prepare_message_parts(messages: list[RenderMessage]) -> None:
    async with aiohttp.ClientSession(
        connector=create_tcp_connector(),
        timeout=aiohttp.ClientTimeout(total=18),
    ) as session:
        tasks = [prepare_one_message(session, msg) for msg in messages]
        await asyncio.gather(*tasks, return_exceptions=True)


async def prepare_one_message(session: aiohttp.ClientSession, msg: RenderMessage) -> None:
    parts = parts_from_segments(msg.raw_segments)
    if not parts:
        parts = parts_from_cq_text(msg.content)
    prepared = []
    for part in parts:
        if part.kind == "image" and part.text:
            path = await materialize_image(session, part.text)
            if path:
                prepared.append(RenderPart(kind="image", image_path=path))
            else:
                prepared.append(RenderPart(kind="text", text="[图片]"))
        else:
            prepared.append(part)
    msg.parts = merge_text_parts(prepared) or [RenderPart(kind="text", text=msg.content or "")]


def parts_from_segments(segments) -> list[RenderPart]:
    parts = []
    if isinstance(segments, str):
        return parts_from_cq_text(segments)
    if not isinstance(segments, list):
        return []
    for seg in segments:
        if isinstance(seg, str):
            parts.extend(parts_from_cq_text(seg))
            continue
        if not isinstance(seg, dict):
            continue
        typ = seg.get("type")
        data = seg.get("data") or {}
        if typ == "text":
            text = data.get("text") or seg.get("text") or ""
            if text:
                parts.append(RenderPart(kind="text", text=text))
        elif typ == "image":
            src = data.get("url") or data.get("file") or data.get("path") or ""
            parts.append(RenderPart(kind="image", text=src))
        elif typ == "face":
            face_id = data.get("id") or data.get("face_id") or ""
            parts.append(RenderPart(kind="face", text=f"[表情:{face_id}]" if face_id else "[表情]"))
        elif typ == "at":
            qq = data.get("qq") or ""
            parts.append(RenderPart(kind="text", text=f"@{qq}" if qq else "@某人"))
        elif typ == "reply":
            parts.append(RenderPart(kind="text", text="[回复]"))
        else:
            parts.append(RenderPart(kind="text", text=f"[{typ}]" if typ else "[消息]"))
    return parts


def parts_from_cq_text(text: str) -> list[RenderPart]:
    text = str(text or "")
    if not text:
        return []
    parts = []
    pattern = re.compile(r"\[CQ:(\w+),?([^\]]*)\]")
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            parts.append(RenderPart(kind="text", text=text[pos:match.start()]))
        typ = match.group(1)
        attrs = parse_cq_attrs(match.group(2))
        if typ == "image":
            parts.append(RenderPart(kind="image", text=attrs.get("url") or attrs.get("file") or ""))
        elif typ == "face":
            face_id = attrs.get("id") or ""
            parts.append(RenderPart(kind="face", text=f"[表情:{face_id}]" if face_id else "[表情]"))
        elif typ == "at":
            parts.append(RenderPart(kind="text", text=f"@{attrs.get('qq', '某人')}"))
        else:
            parts.append(RenderPart(kind="text", text=f"[{typ}]"))
        pos = match.end()
    if pos < len(text):
        parts.append(RenderPart(kind="text", text=text[pos:]))
    return parts


def parse_cq_attrs(raw: str) -> dict:
    attrs = {}
    for item in str(raw or "").split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            attrs[k.strip()] = v.strip()
    return attrs


def merge_text_parts(parts: list[RenderPart]) -> list[RenderPart]:
    merged = []
    for part in parts:
        if part.kind in ("text", "face"):
            text = part.text
            if part.kind == "face":
                text = f" {text} "
            if merged and merged[-1].kind == "text":
                merged[-1].text += text
            elif text:
                merged.append(RenderPart(kind="text", text=text))
        else:
            merged.append(part)
    return [p for p in merged if p.kind != "text" or p.text.strip()]


async def materialize_image(session: aiohttp.ClientSession, src: str) -> str | None:
    src = str(src or "").strip()
    if not src:
        return None
    if src.startswith("file:///"):
        src = src[8:]
    if os.path.isfile(src):
        return os.path.abspath(src)
    if not src.startswith(("http://", "https://")):
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    ext = os.path.splitext(urlparse(src).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}_{abs(hash(src)) % 1000000}{ext}"
    path = os.path.join(CACHE_DIR, filename)
    try:
        async with session.get(src) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        logger.debug(f"[ShotRenderer] download image failed: {e}")
        return None


def load_media_image(path: str) -> Image.Image | None:
    try:
        img = Image.open(path)
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = ImageOps.exif_transpose(img.convert("RGB"))
        img.thumbnail((MEDIA_MAX_WIDTH, MEDIA_MAX_HEIGHT), Image.LANCZOS)
        return img
    except (FileNotFoundError, UnidentifiedImageError, OSError) as e:
        logger.debug(f"[ShotRenderer] open media failed {path}: {e}")
        return None


def qlogo_url(user_id: str, spec: int = 100) -> str:
    return f"https://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec={spec}&img_type=jpg"


async def fetch_group_meta(gateway, chat_id) -> dict:
    if not gateway:
        return {"group_id": str(chat_id), "group_name": f"群聊 {chat_id}", "group_remark": ""}
    return await gateway.get_group_meta(chat_id)


async def enrich_member_names(gateway, chat_id, messages: list[RenderMessage]) -> None:
    if not gateway:
        return
    user_ids = sorted({m.user_id for m in messages if m.user_id})

    async def fetch(uid: str):
        try:
            info = await gateway.get_member_info(chat_id, uid)
            if isinstance(info, dict):
                return uid, info.get("card") or info.get("nickname") or ""
        except Exception as e:
            logger.debug(f"[ShotRenderer] get_group_member_info failed uid={uid}: {e}")
        return uid, ""

    results = await asyncio.gather(*(fetch(uid) for uid in user_ids), return_exceptions=True)
    name_map = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        uid, name = result
        if name:
            name_map[uid] = name
    for msg in messages:
        if msg.user_id and name_map.get(msg.user_id):
            msg.name = name_map[msg.user_id]


async def load_avatars(messages: list[RenderMessage]) -> dict[str, Image.Image]:
    user_ids = sorted({m.user_id for m in messages if m.user_id})
    if not user_ids:
        return {}

    async def fetch(session, uid):
        try:
            async with session.get(qlogo_url(uid), timeout=8) as resp:
                if resp.status != 200:
                    return uid, None
                data = await resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB").resize((AVATAR_SIZE, AVATAR_SIZE))
            return uid, circle_crop(img)
        except Exception:
            return uid, None

    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
        pairs = await asyncio.gather(*(fetch(session, uid) for uid in user_ids), return_exceptions=True)
    avatar_map = {}
    for result in pairs:
        if isinstance(result, Exception):
            continue
        uid, img = result
        if img is not None:
            avatar_map[uid] = img
    return avatar_map


def draw_snapshot(group_meta: dict, note: str, messages: list[RenderMessage], avatar_map: dict[str, Image.Image]) -> Image.Image:
    fonts = {
        "title": load_font(26, bold=True),
        "meta": load_font(15),
        "name": load_font(15, bold=True),
        "text": load_font(20),
        "note": load_font(18, bold=True),
        "small": load_font(13),
    }
    blocks = [measure_message(msg, fonts["text"]) for msg in messages]
    note_lines = wrap_text(note or "截屏留念", fonts["note"], WIDTH - 112)
    note_line_h = line_height(fonts["note"]) + 8
    note_h = 58 + len(note_lines) * note_line_h + 24
    total_height = 118 + sum(b["block_h"] for b in blocks) + 18 + note_h + 28
    total_height = max(total_height, 520)

    img = Image.new("RGB", (WIDTH, total_height), (241, 244, 248))
    draw = ImageDraw.Draw(img)
    draw_header(draw, group_meta, fonts)

    y = 118
    for block in blocks:
        draw_message(img, draw, block, avatar_map, fonts, y)
        y += block["block_h"]

    note_top = y + 18
    draw.rounded_rectangle((PADDING_X, note_top, WIDTH - PADDING_X, note_top + note_h), radius=14, fill=(255, 248, 220), outline=(231, 206, 137))
    draw.text((PADDING_X + 22, note_top + 18), "截屏留念", fill=(116, 81, 24), font=fonts["note"])
    ty = note_top + 54
    for line in note_lines:
        draw.text((PADDING_X + 22, ty), line, fill=(67, 54, 32), font=fonts["note"])
        ty += note_line_h
    return img


def measure_message(msg: RenderMessage, font_text) -> dict:
    items = []
    content_w = 120
    content_h = 0
    gap = 8
    for part in msg.parts or [RenderPart(kind="text", text=msg.content)]:
        if part.kind == "image" and part.image_path:
            media = load_media_image(part.image_path)
            if media:
                w, h = media.size
                items.append({"kind": "image", "image": media, "w": w, "h": h})
                content_w = max(content_w, w)
                content_h += h + gap
                continue
        lines = wrap_text(part.text or "[图片]", font_text, TEXT_MAX_WIDTH)
        lh = line_height(font_text) + 6
        h = len(lines) * lh
        w = max((text_width(line, font_text) for line in lines), default=80)
        items.append({"kind": "text", "lines": lines, "w": w, "h": h, "line_h": lh})
        content_w = max(content_w, w)
        content_h += h + gap
    if content_h:
        content_h -= gap
    bubble_w = min(BUBBLE_MAX_WIDTH, max(140, content_w + 34))
    bubble_h = max(48, content_h + 24)
    return {"msg": msg, "items": items, "bubble_w": bubble_w, "bubble_h": bubble_h, "block_h": bubble_h + 38}


def draw_message(img: Image.Image, draw: ImageDraw.ImageDraw, block: dict, avatar_map: dict[str, Image.Image], fonts: dict, y: int) -> None:
    msg = block["msg"]
    is_yuki = msg.role == "assistant"
    x_avatar = WIDTH - PADDING_X - AVATAR_SIZE if is_yuki else PADDING_X
    avatar = avatar_map.get(msg.user_id)
    if avatar:
        img.paste(avatar, (x_avatar, y + 24), avatar)
    else:
        draw_initial_avatar(draw, x_avatar, y + 24, msg.name, is_yuki, fonts["name"])

    bubble_w = block["bubble_w"]
    bubble_h = block["bubble_h"]
    x_bubble = x_avatar - 18 - bubble_w if is_yuki else x_avatar + AVATAR_SIZE + 18
    draw.text((x_bubble, y), msg.name, fill=(86, 99, 117), font=fonts["name"])
    if msg.time:
        draw.text((x_bubble + text_width(msg.name, fonts["name"]) + 10, y + 2), compact_time(msg.time), fill=(145, 154, 166), font=fonts["small"])

    bubble_color = (208, 235, 196) if is_yuki else (255, 255, 255)
    draw.rounded_rectangle((x_bubble, y + 24, x_bubble + bubble_w, y + 24 + bubble_h), radius=12, fill=bubble_color, outline=(207, 216, 226))
    ty = y + 36
    for item in block["items"]:
        if item["kind"] == "image":
            img.paste(item["image"], (x_bubble + 17, ty))
            ty += item["h"] + 8
        else:
            for line in item["lines"]:
                draw.text((x_bubble + 17, ty), line, fill=(32, 38, 46), font=fonts["text"])
                ty += item["line_h"]
            ty += 8


def draw_header(draw: ImageDraw.ImageDraw, group_meta: dict, fonts: dict) -> None:
    draw.rectangle((0, 0, WIDTH, 96), fill=(35, 45, 62))
    title = group_meta.get("group_name") or f"群聊 {group_meta.get('group_id', '')}"
    draw.text((PADDING_X, 22), title, fill=(255, 255, 255), font=fonts["title"])
    meta_text = f"群号 {group_meta.get('group_id', '')}"
    if group_meta.get("group_remark"):
        meta_text += f" · {group_meta['group_remark']}"
    meta_text += f" · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    draw.text((PADDING_X, 59), meta_text, fill=(190, 202, 218), font=fonts["meta"])


def normalize_content(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_name(text: str) -> str:
    m = re.match(r'^【"([^"]+)"】说:\s*', text or "")
    return m.group(1) if m else ""


def strip_prefix(text: str) -> str:
    return re.sub(r'^【"[^"]+"】说:\s*', "", text or "").strip()


def parts_to_text(msg: RenderMessage) -> str:
    values = []
    for part in msg.parts:
        if part.kind == "image":
            values.append("[图片]")
        else:
            values.append(part.text)
    return "".join(values) or msg.content


def circle_crop(img: Image.Image) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, img.size[0] - 1, img.size[1] - 1), fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (0, 0), mask)
    return out


def draw_initial_avatar(draw: ImageDraw.ImageDraw, x: int, y: int, name: str, is_yuki: bool, font) -> None:
    color = (116, 159, 245) if not is_yuki else (238, 139, 173)
    draw.ellipse((x, y, x + AVATAR_SIZE, y + AVATAR_SIZE), fill=color)
    initial = (name or "?").strip()[:1].upper()
    tw = text_width(initial, font)
    bbox = font.getbbox(initial)
    th = bbox[3] - bbox[1]
    draw.text((x + (AVATAR_SIZE - tw) / 2, y + (AVATAR_SIZE - th) / 2 - 2), initial, fill=(255, 255, 255), font=font)


def wrap_text(text: str, font, max_width: int) -> list[str]:
    text = str(text or "")
    if not text:
        return [""]
    lines = []
    for para in text.split("\n"):
        current = ""
        for ch in para:
            candidate = current + ch
            if text_width(candidate, font) <= max_width or not current:
                current = candidate
            else:
                lines.append(current.rstrip())
                current = ch
        if current:
            lines.append(current.rstrip())
    return lines or [""]


def compact_time(text: str) -> str:
    text = str(text or "")
    m = re.search(r"(\d{1,2})月(\d{1,2})日(\d{1,2}:\d{2})", text)
    if m:
        return f"{m.group(1)}/{m.group(2)} {m.group(3)}"
    m = re.search(r"(\d{1,2}:\d{2})", text)
    return m.group(1) if m else text[:16]


def text_width(text: str, font) -> int:
    try:
        return int(font.getlength(text))
    except Exception:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]


def line_height(font) -> int:
    try:
        ascent, descent = font.getmetrics()
        return ascent + descent
    except Exception:
        bbox = font.getbbox("国Ag")
        return bbox[3] - bbox[1]


def load_font(size: int, bold: bool = False):
    candidates = []
    if os.name == "nt":
        candidates.extend([
            r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
        ])
    candidates.extend([
        "/usr/share/fonts/sarasa-gothic/Sarasa-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/sarasa-gothic/Sarasa-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()
