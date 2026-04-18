import json
import os

from config import CACHE_DIR, CACHE_FILE
from utils.logger import get_logger

logger = get_logger("vision_cache")


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
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"[MemeCache] 加载缓存失败: {e}")
                self.cache = {}
        else:
            logger.info("[MemeCache] 缓存文件不存在")
            self.cache = {}

    def _load_stats(self):
        """加载统计信息"""
        stats_file = CACHE_FILE.replace('.json', '_stats.json')
        if os.path.exists(stats_file):
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    self.stats = json.load(f)
                logger.info(f"[MemeCache] 已加载 {len(self.stats)} 条统计信息")
            except Exception as e:
                logger.warning(f"[MemeCache] 加载统计信息失败: {e}")
                self.stats = {}
        else:
            logger.info("[MemeCache] 统计文件不存在")
            self.stats = {}

    def save_stats(self):
        """保存统计信息"""
        stats_file = CACHE_FILE.replace('.json', '_stats.json')
        try:
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
            logger.info(f"[MemeCache] 统计信息已保存到 {stats_file}")
        except Exception as e:
            logger.error(f"[MemeCache] 保存统计信息失败: {e}")

    def save(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            logger.info(f"[MemeCache] 缓存已保存到 {CACHE_FILE}")
            self.save_stats()  # 同时保存统计信息
        except Exception as e:
            logger.error(f"[MemeCache] 保存缓存失败: {e}")

    def get(self, key):
        # 每次获取前重新加载文件，确保手动修改生效
        self._load_cache()
        value = self.cache.get(key)

        # 如果命中缓存，增加统计次数
        if value is not None:
            self.stats[key] = self.stats.get(key, 0) + 1
            # 每10次命中自动保存一次统计
            if self.stats[key] % 10 == 0:
                self.save_stats()
        return value

    def set(self, key, value):
        self.cache[key] = value
        # 新添加的缓存，初始化统计次数为0
        if key not in self.stats:
            self.stats[key] = 0
            logger.info("[MemeCache] 对当前信息初始化统计")

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
            logger.info(f"[MemeCache] 已清理 {len(to_delete)} 条使用次数低于 {threshold} 的缓存")

        return to_delete
