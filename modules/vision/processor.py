import asyncio
import base64
import hashlib
import re
import aiohttp
import cv2
import numpy as np
import os  # 新增 os 库用于文件操作
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from config import cfg
from core.prompts import VISION_PROMPT
from modules.vision.utils import log
from modules.vision.cache import MemeCache
from utils.logger import get_logger

logger = get_logger("vision_processor")


class MemeProcessor:
    def __init__(self):
        from providers.registry import ProviderRegistry
        self.cache = MemeCache()
        self.semaphore = asyncio.Semaphore(cfg.MAX_CONCURRENT_MEME)
        self._registry = ProviderRegistry()

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

    @staticmethod
    def is_retryable_error(exception):
        if isinstance(exception, asyncio.TimeoutError):
            return True
        if isinstance(exception, aiohttp.ClientError):
            return True
        if isinstance(exception, aiohttp.ClientResponseError) and exception.status in (429, 500, 502, 503, 504):
            return True
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception(lambda e: MemeProcessor.is_retryable_error(e)),
        reraise=True
    )
    async def call_api(self, b64_data):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                    {"type": "text", "text": VISION_PROMPT}
                ]
            }
        ]

        # 优先使用注册中心的 vision provider（更具扩展性）
        if self._registry and self._registry.has("vision"):
            provider = self._registry.get("vision")
            return await provider.chat(
                messages=messages,
                model=cfg.VISION_MODEL,
                max_tokens=50,
                temperature=0.75
            )

        # 兼容降级：直接走原始 HTTP 请求
        logger.debug(f"url:{cfg.IMAGE_PROCESS_API_URL}")
        headers = {
            "Authorization": f"Bearer {cfg.IMAGE_PROCESS_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": cfg.VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                        {"type": "text", "text": VISION_PROMPT}
                    ]
                }
            ],
            "max_tokens": 50,
            "temperature": 0.75
        }
        async with aiohttp.ClientSession(timeout=cfg.REQUEST_TIMEOUT) as session:
            async with session.post(cfg.IMAGE_PROCESS_API_URL, json=payload, headers=headers) as resp:
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

    async def understand_from_url(self, img_url):
        if not cfg.VISION_MODEL:
            logger.info("未设置视觉模型，跳过图像识别")
            # 如果没有配置视觉模型，直接返回占位符，不进行下载和API调用
            return "[未知动画表情]"

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
        """提取文本中的图片URL，并标记是否为表情包"""
        images_info = []  # 用来存放字典的列表
        modified_text = text

        # 1. 找出所有的图片 CQ 码块
        image_blocks = re.findall(r'\[CQ:image,[^\]]*\]', text)

        for block in image_blocks:
            # 提取 URL
            url_match = re.search(r'url=([^,\]]+)', block)
            if url_match:
                url = url_match.group(1)

                # 兼容多种客户端的 subtype 拼写
                is_meme = 'subType=1' in block or 'sub_type=1' in block or 'subtype=1' in block

                # 把 URL 和 标志位 打包成字典存起来
                images_info.append({
                    "url": url,
                    "is_meme": is_meme
                })

                # 统一将图片替换为占位符，交给后续的 VLM 视觉模型理解
                modified_text = modified_text.replace(block, "[图片占位符]", 1)

        return modified_text, images_info

    def get_cache_stats(self):
        """获取缓存统计报告"""
        return self.cache.get_stats_report()

    def clean_low_usage_cache(self, threshold=5, dry_run=True):
        """清理低使用率缓存"""
        return self.cache.clean_low_usage(threshold, dry_run)

    # ================== 新增：本地化保存方法 ==================
    def save_to_local_sticker_library(self, image_data: bytes, original_ref: str = "") -> str:
        """
        将表情包二进制数据持久化保存到本地图库，并返回绝对路径。
        通过 MD5 哈希防止重复下载和命名冲突。
        """
        # 确保图库目录存在 (存放在项目根目录的 data/stickers 下)
        sticker_dir = os.path.abspath("data/stickers")
        os.makedirs(sticker_dir, exist_ok=True)

        # 计算图片哈希，作为文件名
        img_hash = self.get_image_hash(image_data)

        # 智能提取文件后缀，默认使用 .jpg
        ext = ".jpg"
        if original_ref:
            # 过滤掉 URL 后的参数部分，如 ?v=123
            clean_ref = original_ref.split('?')[0]
            if '.' in clean_ref:
                potential_ext = "." + clean_ref.split('.')[-1].lower()
                # 限制合法后缀
                if potential_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                    ext = potential_ext

        file_name = f"{img_hash}{ext}"
        save_path = os.path.join(sticker_dir, file_name)

        # 如果文件不存在，则写入磁盘
        if not os.path.exists(save_path):
            with open(save_path, "wb") as f:
                f.write(image_data)
            logger.info(f"[MemeProcessor] 成功本地化表情包: {file_name}")

        return save_path