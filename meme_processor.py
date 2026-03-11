# meme_processor.py
import aiohttp
import asyncio
import base64
import cv2
import numpy as np
import os
import re
import json
import hashlib
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from config import SILICONFLOW_API_KEY, SILICONFLOW_API_URL, CACHE_DIR, CACHE_FILE, MAX_CONCURRENT_MEME, DEBUG, \
    REQUEST_TIMEOUT, OPENAI_API_URL, OPENAI_API_KEY


def log(msg):
    if DEBUG:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [表情理解] {msg}")


class MemeCache:
    def __init__(self):
        self.cache = {}
        self.stats = {}  # 新增：统计每个key的使用次数
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        self._load_cache()
        self._load_stats()  # 新增：加载统计信息

    def _load_cache(self):
        """从文件加载缓存到内存"""
        # 使用 print 强制输出，不受 DEBUG 控制
        print(f"[MemeCache] 重新加载缓存文件: {CACHE_FILE}")
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    new_cache = json.load(f)
                # 检查是否有变化
                if new_cache != self.cache:
                    print(f"[MemeCache] 缓存已更新，原有 {len(self.cache)} 条，现在 {len(new_cache)} 条")
                    self.cache = new_cache
                else:
                    print(f"[MemeCache] 缓存无变化，仍为 {len(self.cache)} 条")
            except Exception as e:
                print(f"[MemeCache] 加载缓存失败: {e}")
                self.cache = {}
        else:
            print(f"[MemeCache] 缓存文件不存在")
            self.cache = {}

    def _load_stats(self):
        """加载统计信息"""
        stats_file = CACHE_FILE.replace('.json', '_stats.json')
        if os.path.exists(stats_file):
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    self.stats = json.load(f)
                print(f"[MemeCache] 已加载 {len(self.stats)} 条统计信息")
            except Exception as e:
                print(f"[MemeCache] 加载统计信息失败: {e}")
                self.stats = {}
        else:
            print(f"[MemeCache] 统计文件不存在，将创建新文件")
            self.stats = {}

    def save_stats(self):
        """保存统计信息"""
        stats_file = CACHE_FILE.replace('.json', '_stats.json')
        try:
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
            print(f"[MemeCache] 统计信息已保存到 {stats_file}")
        except Exception as e:
            print(f"[MemeCache] 保存统计信息失败: {e}")

    def save(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            print(f"[MemeCache] 缓存已保存到 {CACHE_FILE}")
            self.save_stats()  # 同时保存统计信息
        except Exception as e:
            print(f"[MemeCache] 保存缓存失败: {e}")

    def get(self, key):
        # 每次获取前重新加载文件，确保手动修改生效
        self._load_cache()
        value = self.cache.get(key)
        
        # 如果命中缓存，增加统计次数
        if value is not None:
            self.stats[key] = self.stats.get(key, 0) + 1
            print(f"[MemeCache] key {key[:30]}... 使用次数: {self.stats[key]}")
            # 每10次命中自动保存一次统计
            if self.stats[key] % 10 == 0:
                self.save_stats()
        
        print(f"[MemeCache] 获取 key: {key[:50]}... = {value}")
        return value

    def set(self, key, value):
        self.cache[key] = value
        # 新添加的缓存，初始化统计次数为0
        if key not in self.stats:
            self.stats[key] = 0
            print(f"[MemeCache] 初始化统计: {key[:30]}... = 0")

    def clear(self):
        self.cache = {}
        self.stats = {}  # 同时清空统计
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        stats_file = CACHE_FILE.replace('.json', '_stats.json')
        if os.path.exists(stats_file):
            os.remove(stats_file)
        print("[MemeCache] 缓存和统计已清空")

    def get_stats_report(self):
        """生成统计报告，按使用次数排序"""
        # 将统计信息和对应的缓存值组合
        report = []
        for key, count in self.stats.items():
            value = self.cache.get(key, "【值已丢失】")
            # 截断过长的key和value以便显示
            short_key = key[:50] + "..." if len(key) > 50 else key
            short_value = value[:30] + "..." if len(value) > 30 else value
            report.append({
                'key': short_key,
                'full_key': key,
                'value': short_value,
                'full_value': value,
                'count': count
            })
        
        # 按使用次数排序（从高到低）
        report.sort(key=lambda x: x['count'], reverse=True)
        return report

    def clean_low_usage(self, threshold=5, dry_run=True):
        """
        清理使用次数低于阈值的缓存
        threshold: 阈值，使用次数低于此值的将被清理
        dry_run: 如果为True，只预览不实际删除
        返回被清理的条目列表
        """
        to_delete = []
        for key, count in self.stats.items():
            if count < threshold:
                to_delete.append({
                    'key': key,
                    'count': count,
                    'value': self.cache.get(key, "【值已丢失】")
                })
        
        if not dry_run:
            for item in to_delete:
                key = item['key']
                if key in self.cache:
                    del self.cache[key]
                if key in self.stats:
                    del self.stats[key]
            self.save()
            print(f"[MemeCache] 已清理 {len(to_delete)} 条使用次数低于 {threshold} 的缓存")
        
        return to_delete


class MemeProcessor:
    def __init__(self):
        self.cache = MemeCache()
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_MEME)

    def get_image_hash(self, image_data):
        return hashlib.md5(image_data).hexdigest()

    def compress_image(self, image_data, max_size=640, quality=70):
        try:
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                log("无法读取图片")
                return None
            h, w = img.shape[:2]
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                log(f"尺寸从 {w}x{h} 压缩到 {new_w}x{new_h}")
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buffer = cv2.imencode('.jpg', img, encode_param)
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            log(f"压缩失败: {e}")
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
        retry=retry_if_exception(is_retryable_error),  # 这里也要改
        reraise=True
    )
    async def call_api(self, b64_data):
        print(f"token:{OPENAI_API_KEY[:10]}, url:{OPENAI_API_URL}")
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        #Qwen/Qwen3-VL-8B-Instruct
        payload = {
            "model": "qwen3-vl-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                        {"type": "text",
                         "text": "用词或短句描述这个群友发的表情包的描述或表达的情感，不超过15个字。带文字图片输出文字。长段文字直接输出“长段文字”"}
                    ]
                }
            ],
            "max_tokens": 50,
            "temperature": 0.75
        }
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.post(OPENAI_API_URL, json=payload, headers=headers) as resp:
                print(f"[DEBUG] 响应状态码: {resp.status}")
                if resp.status == 200:
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    text = await resp.text()
                    print(f"[DEBUG] 错误响应: {text}")  # 看看具体错误
                    log(f"API 返回错误 {resp.status}: {text[:200]}")
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=text
                    )

    async def understand_from_url(self, img_url):
        # 强制重新加载缓存文件
        img_url = img_url.replace("&amp;", "&")
        cache_key = f"url:{img_url}"

        # 使用 print 强制输出调试信息
        print(f"[Meme Understanding] 完整URL: {img_url}")
        print(f"[Meme Understanding] 缓存key: {cache_key}")

        cached = self.cache.get(cache_key)
        if cached:
            print(f"[Meme Understanding] 命中URL缓存: {cached}")
            return f"[动画表情:{cached}]"

        try:
            print(f"【下载调试】开始下载图片")
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        print(f"【下载调试】下载失败，HTTP {resp.status}")
                        return "[动画表情]"
                    content = await resp.read()
                    if len(content) > 10 * 1024 * 1024:
                        print("【下载调试】图片超过10MB，跳过")
                        return "[动画表情]"

            img_hash = self.get_image_hash(content)
            print(f"【哈希调试】图片哈希 = {img_hash}")

            # 检查哈希缓存
            cached = self.cache.get(img_hash)
            if cached:
                print(f"【哈希调试】命中哈希缓存: {cached}")
                return f"[动画表情:{cached}]"

            print("【处理调试】开始压缩...")
            b64_data = self.compress_image(content)
            if not b64_data:
                return "[动画表情]"

            print("【API调试】发送AI请求...")
            async with self.semaphore:
                analysis = await self.call_api(b64_data)

            print(f"【API调试】识别结果: {analysis}")
            clean_analysis = analysis.strip().replace('\n', ' ').replace('\r', '')

            # 保存到缓存
            self.cache.set(img_hash, clean_analysis)
            self.cache.set(cache_key, clean_analysis)
            self.cache.save()
            print(f"[MemeCache] 已保存新结果: {clean_analysis}")

            return f"[动画表情:{clean_analysis}]"

        except Exception as e:
            print(f"【错误调试】理解表情失败: {e}")
            return "[动画表情]"


    def extract_urls_from_text(self, text):
        pattern = r'\[CQ:image,.*?url=([^,\]]+).*?\]'

        def replace_with_placeholder(match):
            return "[图片占位符]"

        modified_text = re.sub(pattern, replace_with_placeholder, text)
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