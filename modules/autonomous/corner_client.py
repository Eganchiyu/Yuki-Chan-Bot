# modules/autonomous/corner_client.py
"""Yuki's Corner 公网展柜轻量客户端。

职责边界：
- 零第三方依赖（仅标准库 urllib + asyncio.to_thread），网络异常优雅降级，绝不中断自主轮；
- 严格限制本地打包目录（仅允许 workspace/、output/、temp_images/），防止误读 configs/ 等敏感路径；
- 负责三件事：上架作品（publish_work）、拉取访客纸条与作品互动回流（fetch_feedback）、更新展柜状态（update_status）。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from config import cfg
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("autonomous.corner")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VALID_KINDS = ("toy", "art", "zine", "note")
ALLOWED_ROOT_NAMES = ("workspace", "output", "temp_images")
ALLOWED_ASSET_EXTS = frozenset({
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".txt", ".md",
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".mp3", ".wav", ".ogg", ".woff2", ".woff", ".ttf",
})
MAX_COLLECT_FILES = 40
MAX_SINGLE_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_RAW_BYTES = 12 * 1024 * 1024
CORNER_LOCAL_ROOT = Path(BASE_DIR) / "workspace" / "yuki_corner"


def _base_url() -> str:
    return str(getattr(cfg.autonomous, "corner_base_url", "") or "").strip().rstrip("/")


def _public_url() -> str:
    pub = str(getattr(cfg.autonomous, "corner_public_url", "") or "").strip().rstrip("/")
    return pub or _base_url()


def _token() -> str:
    return str(getattr(cfg.autonomous, "corner_token", "") or "").strip()


def is_configured() -> bool:
    return bool(_base_url() and _token())


def public_url_of(slug: str) -> str:
    base = _public_url()
    return f"{base}/w/{slug}" if base else ""


def normalize_slug(raw: str, fallback_prefix: str = "work") -> str:
    text = re.sub(r"[^a-z0-9_-]+", "-", str(raw or "").strip().lower()).strip("-_")
    if text and SLUG_RE.match(text):
        return text[:64]
    import time
    return f"{fallback_prefix}-{int(time.time())}"[:64]


def _resolve_safe_path(path_str: str) -> Path | None:
    """只允许读取项目下 workspace/、output/、temp_images/ 内的真实文件。"""
    raw = str(path_str or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = Path(BASE_DIR) / p
    try:
        resolved = p.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file():
        return None
    base_resolved = Path(BASE_DIR).resolve()
    allowed_roots = [(base_resolved / name).resolve() for name in ALLOWED_ROOT_NAMES]
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    logger.warning(f"[Corner] 拒绝读取白名单目录之外的文件: {resolved}")
    return None


def _encode_file(path: Path, rel_name: str) -> tuple[dict[str, str], int]:
    raw = path.read_bytes()
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise ValueError(f"文件过大（>8MB）：{rel_name}")
    return {
        "path": rel_name.replace("\\", "/").lstrip("/"),
        "content_b64": base64.b64encode(raw).decode("ascii"),
    }, len(raw)


def collect_publish_files(
    *,
    slug: str,
    kind: str,
    entry_file: str = "",
    inline_content: str = "",
    inline_filename: str = "",
    cover_file: str = "",
    extra_files: list[str] | None = None,
) -> tuple[str, str, list[dict[str, str]], Path]:
    """收集并打包待发布文件，同时确保本地 workspace/yuki_corner/<slug>/ 有备份。

    返回 (entry_rel_path, cover_rel_path, encoded_files, local_entry_path)。
    """
    local_dir = CORNER_LOCAL_ROOT / slug
    local_dir.mkdir(parents=True, exist_ok=True)

    encoded: list[dict[str, str]] = []
    seen: set[str] = set()
    total_bytes = 0
    entry_rel = ""
    local_entry_path = local_dir / "index.html"

    def _add_path(file_path: Path, rel_name: str) -> None:
        nonlocal total_bytes
        clean_rel = rel_name.replace("\\", "/").lstrip("/")
        if not clean_rel or clean_rel in seen:
            return
        if len(encoded) >= MAX_COLLECT_FILES:
            return
        item, size = _encode_file(file_path, clean_rel)
        if total_bytes + size > MAX_TOTAL_RAW_BYTES:
            raise ValueError("打包总大小超过 12MB 上限")
        seen.add(clean_rel)
        encoded.append(item)
        total_bytes += size

    resolved_entry = _resolve_safe_path(entry_file) if entry_file else None
    if resolved_entry is not None:
        local_entry_path = resolved_entry
        corner_root_resolved = CORNER_LOCAL_ROOT.resolve()
        # 如果入口文件放在 workspace/yuki_corner/<subdir>/ 内，打包整个作品子目录
        try:
            rel_to_corner = resolved_entry.relative_to(corner_root_resolved)
            in_dedicated_subdir = len(rel_to_corner.parts) >= 2
        except ValueError:
            in_dedicated_subdir = False

        if in_dedicated_subdir:
            pack_root = resolved_entry.parent
            entry_rel = resolved_entry.relative_to(pack_root).as_posix()
            _add_path(resolved_entry, entry_rel)
            for child in sorted(pack_root.rglob("*")):
                if not child.is_file():
                    continue
                if any(part.startswith(".") for part in child.relative_to(pack_root).parts):
                    continue
                if child.suffix.lower() not in ALLOWED_ASSET_EXTS:
                    continue
                rel = child.relative_to(pack_root).as_posix()
                if rel != entry_rel:
                    _add_path(child, rel)
        else:
            entry_rel = resolved_entry.name
            _add_path(resolved_entry, entry_rel)
    elif inline_content:
        default_name = "index.html" if kind in ("toy", "zine") else "note.txt"
        fname = os.path.basename(str(inline_filename or default_name).strip()) or default_name
        local_entry_path = local_dir / fname
        local_entry_path.write_text(str(inline_content), encoding="utf-8")
        entry_rel = fname
        _add_path(local_entry_path, fname)
    else:
        raise ValueError("请提供已存在的 entry_file（位于 workspace/ 或 output/）或直接提供 inline_content")

    cover_rel = ""
    if cover_file:
        resolved_cover = _resolve_safe_path(cover_file)
        if resolved_cover is not None:
            # 封面如果在刚才打包的子目录里，复用相对路径；否则放 assets/<name>
            cover_candidate = resolved_cover.name
            if cover_candidate in seen:
                cover_rel = cover_candidate
            else:
                cover_rel = f"assets/{resolved_cover.name}"
                _add_path(resolved_cover, cover_rel)

    for extra in extra_files or []:
        resolved_extra = _resolve_safe_path(extra)
        if resolved_extra is not None:
            rel = resolved_extra.name if resolved_extra.name not in seen else f"assets/{resolved_extra.name}"
            _add_path(resolved_extra, rel)

    return entry_rel, cover_rel, encoded, local_entry_path


def _http_request_sync(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str = "",
    timeout: float = 15.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {body[:200]}") from exc


async def publish_work(
    *,
    slug: str,
    title: str,
    kind: str,
    summary: str = "",
    notes: str = "",
    entry_file: str = "",
    inline_content: str = "",
    inline_filename: str = "",
    cover_file: str = "",
    extra_files: list[str] | None = None,
    tags: list[str] | None = None,
    session_id: str = "",
    source_chat: str = "",
    visibility: str = "public",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """打包并发布作品到 Yuki's Corner；未配置远端时返回本地落盘信息。"""
    clean_slug = normalize_slug(slug, fallback_prefix=kind or "work")
    clean_kind = str(kind or "note").strip().lower()
    if clean_kind not in VALID_KINDS:
        clean_kind = "note"
    entry_rel, cover_rel, encoded_files, local_path = await asyncio.to_thread(
        collect_publish_files,
        slug=clean_slug,
        kind=clean_kind,
        entry_file=entry_file,
        inline_content=inline_content,
        inline_filename=inline_filename,
        cover_file=cover_file,
        extra_files=extra_files,
    )

    if not is_configured():
        return {
            "ok": True,
            "published_remote": False,
            "slug": clean_slug,
            "local_path": str(local_path),
            "page_url": "",
            "message": "展柜远端尚未配置，已妥善保存在本地 workspace/yuki_corner/。",
        }

    payload = {
        "slug": clean_slug,
        "title": str(title or clean_slug).strip()[:80],
        "kind": clean_kind,
        "summary": str(summary or "").strip()[:300],
        "notes": str(notes or "").strip()[:4000],
        "entry_file": entry_rel,
        "cover_file": cover_rel,
        "tags": [str(t).strip()[:20] for t in (tags or []) if str(t).strip()][:8],
        "session_id": str(session_id or ""),
        "source_chat": str(source_chat or ""),
        "visibility": "unlisted" if str(visibility).strip().lower() == "unlisted" else "public",
        "files": encoded_files,
    }
    url = f"{_base_url()}/api/publish"
    resp = await asyncio.to_thread(
        _http_request_sync, "POST", url, payload=payload, token=_token(), timeout=timeout
    )
    resp["published_remote"] = bool(resp.get("ok"))
    resp["local_path"] = str(local_path)
    if resp.get("ok") and not resp.get("page_url"):
        resp["page_url"] = public_url_of(clean_slug)
    return resp


async def fetch_feedback(*, limit: int = 8, mark_read: bool = False, timeout: float = 5.0) -> dict[str, Any] | None:
    """拉取展柜最新访客纸条与作品互动汇总（未配置或超时返回 None）。"""
    if not is_configured():
        return None
    mark = "1" if mark_read else "0"
    url = f"{_base_url()}/api/feedback?limit={int(limit)}&mark_read={mark}"
    try:
        data = await asyncio.to_thread(
            _http_request_sync, "GET", url, token=_token(), timeout=timeout
        )
        return data if isinstance(data, dict) and data.get("ok") else None
    except Exception as exc:
        logger.debug(f"[Corner] 拉取展柜反馈失败（忽略）: {exc}")
        return None


async def update_status(mood: str, activity: str, latest_slug: str = "", timeout: float = 4.0) -> bool:
    """轻量更新展柜顶部 Yuki 状态气泡（失败静默）。"""
    if not is_configured():
        return False
    url = f"{_base_url()}/api/status"
    try:
        res = await asyncio.to_thread(
            _http_request_sync,
            "POST",
            url,
            payload={"mood": mood, "activity": activity, "latest_slug": latest_slug},
            token=_token(),
            timeout=timeout,
        )
        return bool(isinstance(res, dict) and res.get("ok"))
    except Exception as exc:
        logger.debug(f"[Corner] 更新展柜状态失败（忽略）: {exc}")
        return False
