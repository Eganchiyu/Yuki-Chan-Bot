# modules/vision/prefetch.py
"""入站图片预取：消息一到就后台下载并做视觉处理，把耗时挪出回复关键路径。

下载与图像理解的耗时原本集中在管线 normalize 阶段（防抖结束、拿到会话锁之后），
而图片处理本身与防抖等待、排队等锁是互不依赖的。本模块在消息入队的瞬间就为
每张图片起后台任务，管线真正处理时直接取用结果，从而缩短「收到消息 → 开始回复」
的延迟。

预取缓存挂在图片处理器上（`processor._prefetch`），与处理器同生命周期；同一个
URL 在 TTL 内只下载/理解一次，供管线主路径和工具链待合并消息共同复用。
"""
import asyncio
import time

from config import cfg
from utils.logger import get_logger

logger = get_logger("vision_prefetch")


def _cache(processor):
    """取处理器的预取缓存；非真实 dict（测试替身）时返回 None，走同步处理。"""
    cache = getattr(processor, "_prefetch", None)
    return cache if isinstance(cache, dict) else None


def _key(url: str, is_meme: bool) -> str:
    """普通图片与表情包走不同的理解路径，缓存键必须区分。"""
    return f"{'m' if is_meme else 'n'}:{url}"


def _consume_task_exception(task):
    """避免未被消费的预取任务抛出「Task exception was never retrieved」。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.debug(f"[ImagePrefetch] 预取任务异常: {exc}")


def _evict(cache: dict):
    """按 TTL 与条目上限清理预取缓存，防止长时间运行内存膨胀。"""
    now = time.time()
    ttl = max(1.0, cfg.IMAGE_PREFETCH_TTL)
    for key in [k for k, entry in cache.items() if now - entry.get("created", now) > ttl]:
        cache.pop(key, None)
    cap = max(1, cfg.IMAGE_PREFETCH_MAX_ENTRIES)
    while len(cache) > cap:
        cache.pop(next(iter(cache)), None)


async def _process_image(processor, img_url: str, is_meme: bool):
    """按当前配置下载并处理一张入站图片（原生登记或 VLM 转写）。"""
    image_store = getattr(processor, "image_store", None)
    if cfg.LLM_NATIVE_VISION_ENABLED and not is_meme and image_store:
        result = await processor.register_from_url(img_url)
        if result.get("attachment"):
            return {**result, "native": True}
    return await processor.understand_from_url(img_url, is_meme=is_meme)


def prefetch_images(processor, images_info) -> int:
    """消息入队时调用：为每张图片起后台下载/理解任务，同一 URL 去重。

    返回本次新调度的任务数（0 表示关闭、无图片或全部命中在途任务）。
    """
    if not cfg.IMAGE_PREFETCH_ENABLED or not processor or not images_info:
        return 0
    cache = _cache(processor)
    if cache is None:
        return 0

    _evict(cache)
    scheduled = 0
    for img in images_info:
        url = (img or {}).get("url")
        if not url:
            continue
        is_meme = bool(img.get("is_meme"))
        key = _key(url, is_meme)
        entry = cache.get(key)
        if entry is not None and not entry["task"].done():
            continue  # 同一张图已在预取中，复用而不重复下载
        task = asyncio.create_task(_process_image(processor, url, is_meme))
        task.add_done_callback(_consume_task_exception)
        cache[key] = {"task": task, "created": time.time()}
        scheduled += 1

    if scheduled:
        logger.debug(f"[ImagePrefetch] 已调度 {scheduled} 张图片后台预取")
    return scheduled


async def resolve_image(processor, img_url: str, is_meme: bool = False):
    """取图片处理结果：命中预取则直接复用，否则退回同步处理。"""
    cache = _cache(processor)
    if cache is not None:
        key = _key(img_url, is_meme)
        entry = cache.get(key)
        if entry is not None:
            try:
                return await entry["task"]
            except Exception as exc:
                # 失败的结果不再留在缓存里，避免整个 TTL 内反复复用异常
                cache.pop(key, None)
                logger.warning(f"[ImagePrefetch] 预取任务失败，改为同步处理: {exc}")
    return await _process_image(processor, img_url, is_meme)
