# core/tools/tools_ncm.py
"""网易云音乐工具：搜索、下载与扫码登录保障。"""
import json
import os
import re
from urllib.parse import quote_plus

import aiohttp

from config import cfg
from core.ncm_login import clear_pending, generate_qr, load_pending, poll_login, save_cookie, save_pending
from core.toolchain import ToolResult
from utils.http_client import create_tcp_connector

from .tools_common import logger

_NCM_REFERER = "https://music.163.com/"
_NCM_SEARCH_URL = "https://music.163.com/api/search/get"
_NCM_PLAYER_URL = "https://music.163.com/api/song/enhance/player/url"
_NCM_SONG_DETAIL_URL = "https://music.163.com/api/v3/song/detail"
_NCM_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _ncm_cookie_text() -> str | None:
    """读取网易云 Cookie 文件，返回 Cookie 字符串；文件缺失/读取失败返回 None。"""
    path = os.path.expanduser(getattr(cfg.paths, "ncm_cookie_file", "~/.cache/ncm_cookie.txt"))
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return text or None
    except Exception:
        return None


def _ncm_csrf(cookie_text: str) -> str:
    m = re.search(r"__csrf=([^;]+)", cookie_text or "")
    return m.group(1) if m else ""


def _ncm_headers(cookie_text: str) -> dict:
    return {
        "Cookie": cookie_text,
        "Referer": _NCM_REFERER,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": _NCM_UA,
    }


async def _ncm_song_title(song_id) -> str:
    """获取歌曲名称用于文件名，失败返回空字符串。"""
    try:
        payload = {"c": json.dumps([{"id": int(song_id), "v": 0}])}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
            async with session.post(
                _NCM_SONG_DETAIL_URL,
                headers={"Referer": _NCM_REFERER, "User-Agent": _NCM_UA},
                data=payload,
            ) as resp:
                data = await resp.json(content_type=None)
        songs = (data.get("songs") or [])
        if not songs:
            return ""
        s = songs[0]
        name = s.get("name") or ""
        artists = "/".join(a.get("name", "") for a in s.get("ar", []) if a.get("name"))
        if name and artists:
            return f"{name} - {artists}"
        return name or ""
    except Exception:
        return ""


async def ncm_search_tool(context, keyword, limit=5):
    """搜索网易云音乐歌曲，返回歌曲列表（含 id/歌手/专辑/时长）。"""
    if not keyword:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_keyword")

    cookie_text = _ncm_cookie_text()
    if not cookie_text:
        return ToolResult(
            success=False,
            content="未找到网易云 Cookie 文件（配置: cfg.paths.ncm_cookie_file）。需要先在浏览器登录 music.163.com 并复制 Cookie。",
            error="missing_cookie",
        )

    try:
        limit = max(1, min(int(limit), 5))
    except (TypeError, ValueError):
        limit = 5

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
            async with session.post(
                _NCM_SEARCH_URL,
                headers=_ncm_headers(cookie_text),
                data=f"s={quote_plus(keyword)}&type=1&limit={limit}&offset=0",
            ) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[NCM] 搜索失败: {e}")
        return ToolResult(success=False, content=f"搜索失败: {str(e)}", error=str(e))

    if data.get("code") != 200:
        # Cookie 失效/未登录 → 触发二维码登录流程
        login_result = await _ncm_ensure_login(context, action_desc="搜索歌曲")
        if login_result is not None:
            return login_result
        # 登录成功，重试一次搜索
        retry_cookie = _ncm_cookie_text() or ""
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
                async with session.post(
                    _NCM_SEARCH_URL,
                    headers=_ncm_headers(retry_cookie),
                    data=f"s={quote_plus(keyword)}&type=1&limit={limit}&offset=0",
                ) as resp:
                    data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"[NCM] 搜索重试失败: {e}")
            return ToolResult(success=False, content=f"搜索失败: {str(e)}", error=str(e))
        if data.get("code") != 200:
            return ToolResult(
                success=False,
                content=f"搜索失败: {data.get('message') or data.get('code')}",
                error="ncm_api_error",
            )

    songs = (data.get("result") or {}).get("songs") or []
    results = []
    for s in songs[:limit]:
        artists = "/".join(a.get("name", "") for a in s.get("artists", []))
        album = (s.get("album") or {}).get("name", "")
        duration = s.get("duration", 0) // 1000
        results.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "artists": artists,
            "album": album,
            "duration": f"{duration // 60}:{duration % 60:02d}",
        })

    if not results:
        return ToolResult(success=False, content="没有找到相关歌曲", error="no_result")

    lines = [
        f"{i + 1}. {r['name']} - {r['artists']}（专辑:{r['album']}，时长:{r['duration']}，id:{r['id']}）"
        for i, r in enumerate(results)
    ]
    return ToolResult(
        success=True,
        content="找到以下歌曲：\n" + "\n".join(lines),
        data={"songs": results, "keyword": keyword},
    )


async def ncm_download_tool(context, song_id, quality="320000", filename=None):
    """下载网易云音乐歌曲到本地（默认 320kbps），返回文件路径；之后可用 send_qq_file 发送。"""
    if not song_id:
        return ToolResult(success=False, content="缺少歌曲 ID", error="missing_song_id")

    cookie_text = _ncm_cookie_text()
    if not cookie_text:
        # 未配置 Cookie → 触发二维码登录流程
        login_result = await _ncm_ensure_login(context, action_desc="下载歌曲")
        if login_result is not None:
            return login_result
        cookie_text = _ncm_cookie_text() or ""

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
            # 1. 获取播放直链（必须 POST；GET 形式会返回空）
            async with session.post(
                _NCM_PLAYER_URL,
                headers=_ncm_headers(cookie_text),
                data=f"ids=[{song_id}]&br={quality}",
            ) as resp:
                url_data = await resp.json(content_type=None)

        if url_data.get("code") != 200:
            # Cookie 失效 → 触发二维码登录流程后重试一次
            login_result = await _ncm_ensure_login(context, action_desc="下载歌曲")
            if login_result is not None:
                return login_result
            cookie_text = _ncm_cookie_text() or ""
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
                async with session.post(
                    _NCM_PLAYER_URL,
                    headers=_ncm_headers(cookie_text),
                    data=f"ids=[{song_id}]&br={quality}",
                ) as resp:
                    url_data = await resp.json(content_type=None)

        items = url_data.get("data") or []
        if not items or not items[0].get("url"):
            return ToolResult(
                success=False,
                content="该歌曲可能为 VIP/版权受限，无法获取下载链接。可换一首或降码率（quality=128000）再试。",
                error="no_stream_url",
            )
        song_url = items[0]["url"]

        # 2. 下载到本地
        output_dir = os.path.abspath(os.path.expanduser(getattr(cfg.paths, "ncm_download_dir", "./output/ncm")))
        os.makedirs(output_dir, exist_ok=True)
        if not filename:
            # 用歌名生成可读文件名：歌名 - 歌手.mp3
            title = await _ncm_song_title(song_id)
            if title:
                # 清洗文件名非法字符并限长
                safe = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", title).strip()
                safe = safe[:80].strip() or f"song_{song_id}"
                filename = f"{safe}.mp3"
            else:
                filename = f"song_{song_id}.mp3"
        filename = os.path.basename(filename)  # 防路径穿越
        if not filename.endswith(".mp3"):
            filename += ".mp3"
        filepath = os.path.join(output_dir, filename)

        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
            async with session.get(song_url) as resp:
                if resp.status != 200:
                    return ToolResult(
                        success=False,
                        content=f"下载失败: HTTP {resp.status}",
                        error="download_failed",
                    )
                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
    except Exception as e:
        logger.error(f"[NCM] 下载失败: {e}")
        return ToolResult(success=False, content=f"下载失败: {str(e)}", error=str(e))

    size = os.path.getsize(filepath)
    logger.info(f"[NCM] 已下载: {filepath} ({size} bytes)")
    return ToolResult(
        success=True,
        content=f"歌曲已下载: {filepath}（{size // 1024 // 1024}MB，{quality}bps）",
        data={"file_path": filepath, "song_id": song_id, "size": size},
    )


async def _ncm_ensure_login(context, action_desc="操作") -> ToolResult | None:
    """NCM 登录保障：Cookie 无效时自动处理二维码登录。

    策略（跨调用状态机）：
    1. 已有待扫码二维码 → 轮询登录状态；成功保存 Cookie 并返回 None（继续原操作）；
       仍未扫码 → 返回提示（再次调用本工具即重试轮询）
    2. 无待扫码记录 → 生成新二维码并发送图片，返回提示让用户扫码后再次调用

    Returns:
        None = 登录已就绪，调用方可继续原操作
        ToolResult = 需要用户扫码/操作，调用方直接返回该结果
    """
    # 1. 有待扫码的二维码？轮询一次
    pending = load_pending()
    if pending:
        poll_result = await poll_login(pending["unikey"], timeout_seconds=30)
        if poll_result.get("success"):
            if save_cookie(poll_result.get("cookie", "")):
                clear_pending()
                logger.info("[NCM] 二维码登录成功，Cookie 已保存")
                return None
            return ToolResult(success=False, content="登录成功但 Cookie 保存失败", error="save_cookie_failed")
        # 未成功：若二维码过期则清除并重新生成；否则提示用户继续等待
        msg = poll_result.get("message", "尚未完成")
        if "过期" in msg:
            clear_pending()
        else:
            return ToolResult(
                success=False,
                content=f"{action_desc}需要网易云登录：二维码已生成等待扫码，请用网易云音乐 App 扫码后再次调用。",
                error="ncm_login_pending",
            )

    # 2. 生成新二维码
    qr_result = await generate_qr()
    if not qr_result.get("success"):
        return ToolResult(success=False, content=qr_result.get("message", "生成二维码失败"), error="qr_failed")

    unikey = qr_result["unikey"]
    image_path = qr_result["image_path"]
    save_pending(unikey)

    return ToolResult(
        success=False,
        content=(
            f"{action_desc}失败：网易云登录已过期。二维码路径：{image_path}，"
            "请用 send_qq_file 把二维码图片发送到群里让用户扫码；"
            "扫码完成后再次调用本工具即可继续。"
        ),
        error="ncm_cookie_expired",
        data={"qr_image_path": image_path},
    )
