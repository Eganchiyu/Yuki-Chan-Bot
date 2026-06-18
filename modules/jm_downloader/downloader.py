"""JM 下载器 — 纯下载逻辑，无 AstrBot 依赖

提供：
  - fetch_album_info(album_id) → dict  获取本子元数据
  - download_chapter(client, photo_id, album_id) → list[Path]  下载单章图片
  - download_album(album_id, range_start, range_end, ...) → dict  完整流程
"""
import asyncio
import logging
import time
from pathlib import Path

from .cache import get_jm_cache_path, get_jm_chapter_path, get_cached_output_path, ensure_cache_limits
from .converter import images_to_pdf, images_to_zip

logger = logging.getLogger("jm_cli.downloader")


# ── 元数据获取 ─────────────────────────────────────────────
def fetch_album_info(album_id: str | int, proxy: str = "") -> dict:
    """获取本子元数据，返回 dict:
    
    {
        "album_id": int,
        "title": str,
        "authors": list[str],
        "tags": list[str],
        "total_chapters": int,
        "episode_list": [(photo_id, title, ...), ...],
    }
    """
    from jmcomic import JmModuleConfig

    option = JmModuleConfig.option_class().default()
    client = option.build_jm_client()

    if proxy:
        try:
            client.set_proxy(proxy)
        except Exception:
            logger.warning(f"设置代理失败: {proxy}")

    album = client.get_album_detail(int(album_id))

    title = getattr(album, "title", "未知标题") or "未知标题"
    authors = getattr(album, "authors", []) or []
    author_str = ", ".join(authors) if authors else "未知作者"
    tags = getattr(album, "tags", []) or []
    episode_list = getattr(album, "episode_list", []) or []

    return {
        "album_id": int(album_id),
        "title": title,
        "authors": authors,
        "author_str": author_str,
        "tags": tags,
        "total_chapters": len(episode_list),
        "episode_list": episode_list,
    }


# ── 单章下载 ──────────────────────────────────────────────
def download_chapter(photo_id: str | int, album_id: str | int, proxy: str = "") -> list[Path]:
    """下载单章所有图片，返回本地图片路径列表"""
    from jmcomic import JmModuleConfig

    photo_id_str = str(photo_id)
    album_id_str = str(album_id)

    cache_chapter_dir = get_jm_chapter_path(album_id_str, photo_id_str)
    download_base = str(cache_chapter_dir.parent)

    option = JmModuleConfig.option_class().construct({
        "dir_rule": {
            "rule": "Bd_Pid",
            "base_dir": download_base,
        },
        "download": {
            "image": {"suffix": ".webp"},
        },
    })

    if proxy:
        try:
            option.client.proxy = proxy
        except Exception:
            pass

    dler = JmModuleConfig.downloader_class()(option)
    dler.download_photo(int(photo_id_str))

    # 收集该章图片
    album_dir = get_jm_cache_path() / album_id_str
    image_paths: list[Path] = []
    for ext in ("*.webp", "*.jpg", "*.png"):
        for f in sorted(cache_chapter_dir.rglob(ext)):
            image_paths.append(f)
        if image_paths:
            break

    if not image_paths:
        # 回退：搜索整个 album 目录
        for ext in ("*.webp", "*.jpg", "*.png"):
            for f in sorted(album_dir.rglob(ext)):
                if ".preview." not in f.name:
                    image_paths.append(f)

    return image_paths


# ── 检查缓存 ──────────────────────────────────────────────
def check_cached_images(album_id: str, episode_list: list, range_start: int, range_end: int) -> bool:
    """检查指定范围的图片是否全部已缓存"""
    for chapter_idx in range(range_start - 1, range_end):
        photo_id_str = episode_list[chapter_idx][0]
        chapter_dir = get_jm_chapter_path(album_id, str(photo_id_str))
        if not chapter_dir.exists():
            return False
        found = False
        for ext in ("*.webp", "*.jpg", "*.png"):
            if list(chapter_dir.glob(ext)):
                found = True
                break
        if not found:
            return False
    return True


def collect_cached_images(album_id: str) -> list[Path]:
    """收集已缓存的所有图片"""
    album_dir = get_jm_cache_path() / str(album_id)
    if not album_dir.exists():
        return []

    image_paths: list[Path] = []
    for ext in ("*.webp", "*.jpg", "*.png"):
        for f in sorted(album_dir.rglob(ext)):
            if ".preview." not in f.name:
                image_paths.append(f)
    return image_paths


# ── 完整下载流程 ──────────────────────────────────────────
def download_album(
    album_id: str | int,
    range_start: int | None = None,
    range_end: int | None = None,
    max_chapters: int = 30,
    proxy: str = "",
    output_format: str = "zip",       # "zip" | "pdf" | "both" | "none"
    zip_password: str = "FloatSakura",
    retention_days: int = 3,
    max_cache_gb: float = 3.0,
) -> dict:
    """完整下载流程，返回结果 dict:
    
    {
        "success": bool,
        "title": str,
        "authors": str,
        "tags": list,
        "chapter_range": str,          # "第1章~第30章"
        "chapter_range_compact": str,  # "1-30"
        "total_chapters": int,
        "success_count": int,
        "fail_count": int,
        "image_count": int,
        "elapsed": float,
        "pdf_path": Path | None,
        "zip_path": Path | None,
        "image_paths": list[Path],
        "error": str | None,
    }
    """
    start = time.perf_counter()
    album_id_str = str(album_id)

    result = {
        "success": False,
        "album_id": album_id_str,
        "title": "",
        "authors": "",
        "tags": [],
        "chapter_range": "",
        "chapter_range_compact": "",
        "total_chapters": 0,
        "success_count": 0,
        "fail_count": 0,
        "image_count": 0,
        "elapsed": 0.0,
        "pdf_path": None,
        "zip_path": None,
        "image_paths": [],
        "error": None,
    }

    # 1. 获取元数据
    try:
        info = fetch_album_info(album_id_str, proxy=proxy)
    except Exception as exc:
        result["error"] = f"获取本子信息失败: {exc}"
        return result

    result["title"] = info["title"]
    result["authors"] = info["author_str"]
    result["tags"] = info["tags"]
    result["total_chapters"] = info["total_chapters"]
    episode_list = info["episode_list"]

    if info["total_chapters"] == 0:
        result["error"] = f"本子 {album_id} 未找到任何章节"
        return result

    # 2. 章节范围校验
    total = info["total_chapters"]
    if range_start is None and range_end is None:
        if total > max_chapters:
            result["error"] = f"本子共 {total} 章（>{max_chapters}），请指定范围，如 {album_id} 1-{max_chapters}"
            return result
        range_start, range_end = 1, total
    else:
        if range_start is None:
            range_start = 1
        if range_end is None:
            range_end = total
        range_start = max(1, range_start)
        range_end = min(total, range_end)
        span = range_end - range_start + 1
        if span > max_chapters:
            result["error"] = f"章节跨度 {span} 章（>{max_chapters}），请缩小范围"
            return result

    result["chapter_range"] = f"第{range_start}章~第{range_end}章（共{total}章）"
    result["chapter_range_compact"] = f"{range_start}-{range_end}"

    # 3. 检查缓存
    images_cached = check_cached_images(album_id_str, episode_list, range_start, range_end)

    if images_cached:
        logger.info(f"📦 图片缓存命中: album_id={album_id_str}")
        all_images = collect_cached_images(album_id_str)
    else:
        # 4. 逐章下载
        logger.info(f"📥 开始下载: {info['title']} 第{range_start}-{range_end}章")
        all_images: list[Path] = []
        success_count = 0
        fail_count = 0

        for chapter_idx in range(range_start - 1, range_end):
            chapter_num = chapter_idx + 1
            photo_id_str, episode_title, _ = episode_list[chapter_idx]
            label = f"第{chapter_num}章 {episode_title}" if episode_title else f"第{chapter_num}章"

            try:
                ch_start = time.perf_counter()
                paths = download_chapter(photo_id_str, album_id_str, proxy=proxy)
                if paths:
                    all_images.extend(paths)
                    success_count += 1
                    ch_time = time.perf_counter() - ch_start
                    logger.info(f"  ✅ {label} | {len(paths)}张 | {ch_time:.1f}s")
                else:
                    fail_count += 1
                    logger.warning(f"  ⏭️ {label} (无图片)")
            except Exception as exc:
                fail_count += 1
                logger.error(f"  ❌ {label}: {exc}")

        result["success_count"] = success_count
        result["fail_count"] = fail_count

    if not all_images:
        result["error"] = f"本子 {album_id} 未获取到任何图片"
        return result

    result["image_count"] = len(all_images)
    result["image_paths"] = all_images

    # 5. 生成输出文件
    send_zip = output_format in ("zip", "both")
    send_pdf = output_format in ("pdf", "both")

    if send_pdf:
        pdf_path = get_cached_output_path(album_id_str, "pdf", info["title"], result["chapter_range_compact"])
        if not pdf_path.exists():
            images_to_pdf(all_images, pdf_path)
        if pdf_path.exists():
            result["pdf_path"] = pdf_path

    if send_zip:
        zip_path = get_cached_output_path(album_id_str, "zip", info["title"], result["chapter_range_compact"])
        if not zip_path.exists():
            images_to_zip(all_images, zip_path, password=zip_password)
        if zip_path.exists():
            result["zip_path"] = zip_path

    # 6. 缓存清理
    try:
        ensure_cache_limits(retention_days, max_cache_gb)
    except Exception as exc:
        logger.warning(f"缓存清理失败: {exc}")

    result["success"] = True
    result["elapsed"] = time.perf_counter() - start
    return result
