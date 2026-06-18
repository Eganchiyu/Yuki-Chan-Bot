"""缓存路径管理 + 自动清理

无 AstrBot 依赖，纯 stdlib + pathlib。
"""
import os
import time
import logging
from pathlib import Path

logger = logging.getLogger("jm_cli.cache")

# ── 路径常量 ──────────────────────────────────────────────
PLUGIN_NAME = "astrbot_plugin_jm_downloader"

# 默认缓存根目录（可通过 init_cache(data_dir) 覆盖）
_data_dir: Path | None = None


def init_cache(data_dir: str | Path) -> None:
    """手动指定缓存根目录（CLI 模式下使用）"""
    global _data_dir
    _data_dir = Path(data_dir)
    _data_dir.mkdir(parents=True, exist_ok=True)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_root() -> Path:
    """缓存根目录"""
    if _data_dir is not None:
        return _ensure_dir(_data_dir / "cache")
    # 回退：脚本同级 data/ 目录
    fallback = Path(__file__).resolve().parent.parent / "data"
    return _ensure_dir(fallback / "cache")


def get_jm_cache_path() -> Path:
    """JM 图片缓存目录"""
    return _ensure_dir(get_cache_root() / "jmcomic")


def get_jm_chapter_path(album_id: str, photo_id: str) -> Path:
    """指定章节的缓存目录"""
    return _ensure_dir(get_jm_cache_path() / str(album_id) / str(photo_id))


def get_jm_output_cache_dir() -> Path:
    """输出文件缓存目录（PDF/ZIP）"""
    return _ensure_dir(get_jm_cache_path() / "_output")


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    import unicodedata
    cleaned = unicodedata.normalize("NFKC", name)
    result = []
    for ch in cleaned:
        if ch.isalnum() or ch in ("_", "-", ".", "(", ")", "[", "]", "（", "）", "【", "】"):
            result.append(ch)
        elif ch.isspace():
            result.append("_")
        else:
            result.append("-")
    sanitized = "".join(result)
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized[:80].strip("_-")


def get_cached_output_path(album_id: str, ext: str, title: str = "", chapter_range: str = "") -> Path:
    """获取缓存的输出文件路径
    
    格式: {album_id}_{title}_ch{range}.{ext}
    """
    parts = [str(album_id)]
    if title:
        parts.append(_sanitize_filename(title))
    if chapter_range:
        parts.append(f"ch{chapter_range}")
    filename = "_".join(parts) + f".{ext}"
    return get_jm_output_cache_dir() / filename


# ── 缓存清理 ──────────────────────────────────────────────
_size_check_cooldown: float = 0.0
_SIZE_CHECK_INTERVAL = 300.0  # 5 分钟


def _get_dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _remove_old_files(path: Path, cutoff_timestamp: float) -> int:
    removed = 0
    try:
        for entry in path.rglob("*"):
            if not entry.is_file():
                continue
            try:
                if entry.stat().st_mtime < cutoff_timestamp:
                    entry.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    # 清理空目录
    try:
        for entry in sorted(path.rglob("*"), reverse=True):
            if entry.is_dir():
                try:
                    entry.rmdir()
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def ensure_cache_limits(retention_days: int = 3, max_size_gb: float = 3.0) -> None:
    """检查并执行缓存清理"""
    global _size_check_cooldown
    cache_dir = get_jm_cache_path()

    # 1. 清理超过 retention_days 天的文件
    cutoff_days = time.time() - retention_days * 86400
    removed_days = _remove_old_files(cache_dir, cutoff_days)
    if removed_days > 0:
        logger.info(f"🧹 清理了 {removed_days} 个超过{retention_days}天的文件")

    # 2. 检查总大小（冷却 5 分钟）
    now = time.time()
    if max_size_gb <= 0:
        return
    if now - _size_check_cooldown < _SIZE_CHECK_INTERVAL:
        return
    _size_check_cooldown = now

    total_bytes = _get_dir_size(cache_dir)
    total_gb = total_bytes / (1024**3)
    if total_gb > max_size_gb:
        logger.info(f"🧹 缓存 {total_gb:.2f}GB 超限 {max_size_gb}GB，清理超过12小时的旧文件")
        cutoff_hours = now - 12 * 3600
        removed_oversize = _remove_old_files(cache_dir, cutoff_hours)
        logger.info(f"🧹 清理了 {removed_oversize} 个文件")


def clear_all_cache() -> tuple[int, float]:
    """清空所有缓存，返回 (文件数, 释放MB)"""
    cache_dir = get_jm_cache_path()
    if not cache_dir.exists():
        return 0, 0.0

    total_bytes = 0
    file_count = 0
    for f in cache_dir.rglob("*"):
        if f.is_file():
            try:
                total_bytes += f.stat().st_size
                file_count += 1
            except OSError:
                pass

    import shutil
    shutil.rmtree(str(cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)

    size_mb = total_bytes / (1024 * 1024)
    logger.info(f"🧹 缓存清理完成: {file_count} 个文件, {size_mb:.1f} MB")
    return file_count, size_mb
