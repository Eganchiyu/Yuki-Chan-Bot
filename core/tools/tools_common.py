# core/tools/tools_common.py
"""工具模块共享的日志、存储与通用辅助函数。"""
import re

from modules.shot_memory import ShotMemoryStore
from utils.logger import get_logger

logger = get_logger("tools")

# 截屏记忆存储（快照工具与图片索引解析共享）
shot_memory_store = ShotMemoryStore()


def _resolve_image_path(context, path: str) -> str:
    """解析 [img:XXX]/[shot:N] 索引为真实文件路径，普通路径原样返回。"""
    m = re.match(r'^\[img:(\d{3})\]$', path)
    if m:
        idx = m.group(1)
        image_store = getattr(context, "image_store", None)
        if image_store:
            resolved = image_store.resolve(idx)
            if resolved:
                return resolved

    shot = re.match(r'^\[shot:(\d+)\]$', path)
    if shot:
        resolved = shot_memory_store.resolve(context.chat_id, shot.group(1))
        if resolved:
            return resolved
    return path


def _compact_text(text, max_len=500):
    text = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}...（已截断，原长{len(text)}字）"
