import asyncio
import base64
import hashlib
import re
import aiohttp
import cv2
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from config import MAX_CONCURRENT_MEME, LLM_API_KEY, IMAGE_PROCESS_API_URL, REQUEST_TIMEOUT, VISION_MODEL, \
    IMAGE_PROCESS_API_KEY
from core.prompts import VISION_PROMPT
from modules.vision.utils import log
from modules.vision.cache import MemeCache
from utils.logger import get_logger

logger = get_logger("vision_processor")

class MemeProcessor:
    def __init__(self):
        self.cache = MemeCache()
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_MEME)

    @staticmethod
    def get_image_hash(image_data):
        return hashlib.md5(image_data).hexdigest()

    @staticmethod
    def compress_image(image_data, max_size=640, quality=70):
        try:
            encoded = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("无法读取图片")
                return None
            h, w = img.shape[:2]
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                logger.debug(f"尺寸从 {w}x{h} 压缩到 {new_w}x{new_h}")
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buffer = cv2.imencode('.jpg', img, encode_param)
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.error(f"压缩失败: {e}")
            return None

    @staticmethod  # 加上这个装饰器 # 修改这个函数，加上 self 参数
    def is_retryable_error(exception):  # 加上 self
        if isinstance(exception, asyncio.TimeoutError):
            return True
        if isinstance(exception, aiohttp.ClientError):
            return True
        if isinstance(exception, aiohttp.ClientResponseError) and exception.status in (429, 500, 502, 503, 504):
            return True
        return False

    # 然后修改 @retry 的调用方式
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception(lambda e: MemeProcessor.is_retryable_error(e)),  # 这里也要改
        reraise=True
    )
    async def call_api(self, b64_data):
        logger.debug(f"token:{IMAGE_PROCESS_API_KEY}, url:{IMAGE_PROCESS_API_URL}")
        headers = {
            "Authorization": f"Bearer {IMAGE_PROCESS_API_KEY}",
            "Content-Type": "application/json"
        }
        #Qwen/Qwen3-VL-8B-Instruct
        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                        {"type": "text",
                         "text": VISION_PROMPT}
                    ]
                }
            ],
            "max_tokens": 50,
            "temperature": 0.75
        }
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.post(IMAGE_PROCESS_API_URL, json=payload, headers=headers) as resp:
                logger.debug(f"[DEBUG] 响应状态码: {resp.status}")
                if resp.status == 200:
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    text = await resp.text()
                    logger.debug(f"[DEBUG] 错误响应: {text}")  # 看看具体错误
                    logger.error(f"API 返回错误 {resp.status}: {text[:200]}")
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=text
                    )

    async def understand_from_url(self, img_url, llm):

        if not VISION_MODEL:
            logger.info("未设置视觉模型，跳过图像识别")
            # 如果没有配置视觉模型，直接返回占位符，不进行下载和API调用
            return "[未知动画表情]"

        # 1. 熔断拦截
        llm.check_auto_recovery()
        if llm.is_degraded:
            return "[未知动画表情]"

        # 2. 缓存处理
        img_url = img_url.replace("&amp;", "&")
        cache_key = f"url:{img_url}"

        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"[MemeCache] 命中URL缓存: {cached}")
            return f"[动画表情:{cached}]"

        try:
            logger.info("[Meme Understanding] 开始下载图片")
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.error(f"[Meme Understanding] 下载失败，HTTP {resp.status}")
                        return "[未知动画表情]"
                    content = await resp.read()

            img_hash = self.get_image_hash(content)

            # 检查哈希缓存
            cached = self.cache.get(img_hash)
            if cached:
                logger.info(f"[MemeCache] 命中哈希缓存: {cached}")
                return f"[动画表情:{cached}]"

            logger.info("[MemeCache] 开始压缩...")
            b64_data = self.compress_image(content)
            if not b64_data:
                return "[未知动画表情]"

            logger.info("[Meme Understanding] 发送AI请求...")
            async with self.semaphore:
                analysis = await self.call_api(b64_data)

            logger.info(f"[Meme Understanding] 识别结果: {analysis}")
            clean_analysis = analysis.strip().replace('\n', ' ').replace('\r', '')

            # 保存到缓存
            self.cache.set(img_hash, clean_analysis)
            self.cache.set(cache_key, clean_analysis)
            self.cache.save()
            logger.info(f"[MemeCache] 已保存新结果: {clean_analysis}")

            return f"[动画表情:{clean_analysis}]"

        except Exception as e:
            logger.error(f"[Meme ERROR] 理解表情失败: {e}")
            return "[未知动画表情]"

    @staticmethod
    def extract_urls_from_text(text):
        """提取文本中的图片URL，并返回替换后的文本和URL列表

        例如输入: "这是一个表情[CQ:image,url=https://example.com/image.jpg]"

        输出: ("这是一个表情[图片占位符]", ["https://example.com/image.jpg"])
        """
        pattern = r'\[CQ:image,.*?url=([^,\]]+).*?\]'

        modified_text = re.sub(pattern, "[图片占位符]", text)
        urls = re.findall(pattern, text)
        return modified_text, urls

    # 新增：对外暴露的统计方法
    def get_cache_stats(self):
        """获取缓存统计报告"""
        return self.cache.get_stats_report()

    def clean_low_usage_cache(self, threshold=5, dry_run=True):
        """
        清理低使用率缓存
        threshold: 使用次数阈值
        dry_run: 预览模式，不实际删除
        """
        return self.cache.clean_low_usage(threshold, dry_run)
