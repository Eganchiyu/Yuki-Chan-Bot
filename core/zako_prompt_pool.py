# core/zako_prompt_pool.py
"""外部提示词语料库（Zako-Prompt-Tools）读取与抽样。

语料来源：https://github.com/xiaoshengyvlin/Zako-Prompt-Tools（MIT）
把它的 ``data/json/<分级>/<主题>.json`` 放到 ``data/zako/json/`` 下即可启用；
数据文件不入 git，缺失时本模块 ``available()`` 返回 False，抽卡回落原有逻辑。

格式：``{"1girl, apron, kitchen, smile": "<post_id>", ...}``（Danbooru 标签串）
首次抽样时会（基于文件大小/mtime）构建 ``data/zako/prompts.db`` 索引。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Iterable, Sequence

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

ZAKO_DATA_DIR = os.path.join(BASE_DIR, "data", "zako")
VALID_RATINGS = ("G", "S", "Q", "E")
BUILD_STATE_FILE = "build_state.json"
TAG_MAP_FILE = "tag_map.sqlite"
BATCH_SIZE = 10000
# tag_map.sqlite 的 category：0=通用 1=画师 3=版权/作品 4=角色 5=meta
KEEP_CATEGORIES = (0, 5)
# 形如 `hasumi (blue archive)`、`star (sky)` 的 Danbooru 消歧义标签
_DISAMBIG_TAG = re.compile(r"[a-z0-9_.\-']+ \([a-z0-9_.\- :&'!]+\)", re.IGNORECASE)


def clean_tag_text(tag_text: str) -> str:
    """去掉消歧义标签与重复项，返回可直接当灵感种子的标签串。"""
    parts: list[str] = []
    seen: set[str] = set()
    for raw in str(tag_text or "").split(","):
        token = raw.strip()
        if not token:
            continue
        # 含 `xxx (yyy)` 的一律整条丢弃：多是他人角色/作品名或消歧义标签
        if _DISAMBIG_TAG.search(token) or token.startswith("("):
            continue
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        parts.append(token)
    return ", ".join(parts)


class ZakoPromptPool:
    """Zako-Prompt-Tools 标签语料的只读抽样器（含自动建索引）。"""

    def __init__(self, base_dir: str = ZAKO_DATA_DIR):
        self.base_dir = base_dir
        self.json_dir = os.path.join(base_dir, "json")
        self.db_path = os.path.join(base_dir, "prompts.db")
        self.tag_map_path = os.path.join(base_dir, TAG_MAP_FILE)
        self._ready = False
        self._tag_map: sqlite3.Connection | None = None
        self._category_cache: dict[str, int | None] = {}

    # ---------- 标签分类（画师/作品/角色过滤） ----------

    def _category_of(self, token: str) -> int | None:
        """查 tag_map.sqlite 的 category；没有映射库或查不到时返回 None。"""
        key = str(token or "").strip().lower().replace(" ", "_")
        if not key:
            return None
        if key in self._category_cache:
            return self._category_cache[key]
        category: int | None = None
        if os.path.isfile(self.tag_map_path):
            try:
                if self._tag_map is None:
                    self._tag_map = sqlite3.connect(
                        f"file:{self.tag_map_path}?mode=ro", uri=True
                    )
                row = self._tag_map.execute(
                    "SELECT category FROM tags WHERE name = ?", (key,)
                ).fetchone()
                if row:
                    category = int(row[0])
            except Exception as exc:
                logger.warning(f"[Zako] 标签分类查询失败，跳过过滤: {exc}")
                self._tag_map = None
                self.tag_map_path = ""  # 本次进程内不再重试
        self._category_cache[key] = category
        return category

    def clean_tags(self, tag_text: str) -> str:
        """只保留通用/情绪类标签，去掉消歧义标签、他人画师/作品/角色与重复项。

        没有 tag_map.sqlite 时不做分类过滤（只做消歧义与去重）。
        """
        cleaned = clean_tag_text(tag_text)
        if not cleaned:
            return ""
        has_map = bool(self.tag_map_path) and os.path.isfile(self.tag_map_path)
        kept: list[str] = []
        for token in cleaned.split(","):
            token = token.strip()
            if not token or token.startswith("(") or token.endswith(":"):
                continue
            if has_map and self._category_of(token) not in KEEP_CATEGORIES:
                continue
            kept.append(token)
        return ", ".join(kept)

    # ---------- 可用性 ----------

    def _source_files(self) -> list[tuple[str, str, str]]:
        """返回 [(rating, topic, path)]；只认 ``json/<G|S|Q|E>/*.json`` 结构。"""
        if not os.path.isdir(self.json_dir):
            return []
        found: list[tuple[str, str, str]] = []
        for sub in sorted(os.listdir(self.json_dir)):
            sub_path = os.path.join(self.json_dir, sub)
            if not (os.path.isdir(sub_path) and sub.upper() in VALID_RATINGS):
                continue
            for fname in sorted(os.listdir(sub_path)):
                if not fname.endswith(".json"):
                    continue
                topic = fname[:-5].strip()
                if topic:
                    found.append((sub.upper(), topic, os.path.join(sub_path, fname)))
        return found

    def available(self) -> bool:
        """语料目录存在且至少有一个数据文件。"""
        return bool(self._source_files())

    def stats(self) -> dict[str, Any]:
        files = self._source_files()
        return {
            "available": bool(files),
            "files": len(files),
            "json_dir": self.json_dir,
            "db_path": self.db_path,
            "db_exists": os.path.isfile(self.db_path),
        }

    # ---------- 索引构建 ----------

    def _snapshot(self, files: Sequence[tuple[str, str, str]]) -> dict[str, list[Any]]:
        state: dict[str, list[Any]] = {}
        for rating, topic, path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            state[path] = [rating, topic, st.st_size, int(st.st_mtime)]
        return state

    def _needs_rebuild(self, files: Sequence[tuple[str, str, str]]) -> bool:
        if not os.path.isfile(self.db_path):
            return True
        state_file = os.path.join(self.base_dir, BUILD_STATE_FILE)
        if not os.path.isfile(state_file):
            return True
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                previous = json.load(f)
        except Exception:
            return True
        return previous != self._snapshot(files)

    def _build_db(self, files: Sequence[tuple[str, str, str]]) -> int:
        os.makedirs(self.base_dir, exist_ok=True)
        tmp_path = self.db_path + ".building"
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        conn = sqlite3.connect(tmp_path)
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute(
                "CREATE TABLE prompts ("
                "tag_text TEXT NOT NULL, "
                "post_id TEXT NOT NULL DEFAULT '', "
                "rating TEXT NOT NULL DEFAULT 'S', "
                "topic TEXT NOT NULL DEFAULT ''"
                ")"
            )
            total = 0
            for rating, topic, path in files:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as exc:
                    logger.warning(f"[Zako] 读取语料失败 {path}: {exc}")
                    continue
                if not isinstance(data, dict):
                    continue
                batch: list[tuple[str, str, str, str]] = []
                for tag_text, post_id in data.items():
                    text = str(tag_text).strip()
                    if not text:
                        continue
                    batch.append((text, str(post_id), rating, topic))
                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(
                            "INSERT INTO prompts (tag_text, post_id, rating, topic) VALUES (?, ?, ?, ?)",
                            batch,
                        )
                        total += len(batch)
                        batch = []
                if batch:
                    conn.executemany(
                        "INSERT INTO prompts (tag_text, post_id, rating, topic) VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    total += len(batch)
            conn.execute("CREATE INDEX idx_prompts_rating ON prompts(rating)")
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp_path, self.db_path)
        try:
            with open(os.path.join(self.base_dir, BUILD_STATE_FILE), "w", encoding="utf-8") as f:
                json.dump(self._snapshot(files), f, ensure_ascii=False)
        except Exception as exc:
            logger.warning(f"[Zako] 写索引状态失败: {exc}")
        logger.info(f"[Zako] 语料索引已构建：{total} 条 -> {self.db_path}")
        return total

    def _ensure_db(self) -> bool:
        if self._ready:
            return True
        files = self._source_files()
        if not files:
            return False
        if self._needs_rebuild(files):
            logger.info("[Zako] 正在构建提示词语料索引（首次抽样可能稍慢）…")
            try:
                self._build_db(files)
            except Exception as exc:
                logger.warning(f"[Zako] 构建索引失败，回落原有抽卡: {exc}")
                return False
        self._ready = True
        return True

    # ---------- 抽样 ----------

    @staticmethod
    def _normalize_ratings(ratings: Iterable[str] | str) -> list[str]:
        if isinstance(ratings, str):
            items = [r.strip().upper() for r in ratings.replace("，", ",").split(",")]
        else:
            items = [str(r).strip().upper() for r in ratings]
        picked = [r for r in items if r in VALID_RATINGS]
        return picked or ["G", "S", "Q"]

    def sample(
        self,
        rng: Any = None,
        ratings: Iterable[str] | str = ("G", "S", "Q"),
        topic: str = "",
        exclude_topics: Iterable[str] | str = (),
    ) -> dict[str, Any] | None:
        """随机抽一条标签串；语料缺失或查询失败返回 None。"""
        if not self._ensure_db():
            return None
        picked_ratings = self._normalize_ratings(ratings)
        params: list[str] = list(picked_ratings)
        where = f"rating IN ({','.join('?' * len(picked_ratings))})"
        topic = str(topic or "").strip()
        if topic:
            where += " AND topic = ?"
            params.append(topic)
        if isinstance(exclude_topics, str):
            excluded = [t.strip() for t in exclude_topics.replace("，", ",").split(",") if t.strip()]
        else:
            excluded = [str(t).strip() for t in exclude_topics if str(t).strip()]
        if excluded and not topic:
            where += f" AND topic NOT IN ({','.join('?' * len(excluded))})"
            params.extend(excluded)
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            try:
                if rng is not None:
                    # 先取总数再随机定位，避免每轮 ORDER BY RANDOM() 全表扫描
                    total = conn.execute(
                        f"SELECT COUNT(*) FROM prompts WHERE {where}", params
                    ).fetchone()[0]
                    if not total:
                        return None
                    offset = rng.randrange(total)
                    row = conn.execute(
                        f"SELECT tag_text, post_id, rating, topic FROM prompts "
                        f"WHERE {where} LIMIT 1 OFFSET ?",
                        params + [offset],
                    ).fetchone()
                else:
                    row = conn.execute(
                        f"SELECT tag_text, post_id, rating, topic FROM prompts "
                        f"WHERE {where} ORDER BY RANDOM() LIMIT 1",
                        params,
                    ).fetchone()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"[Zako] 抽样失败: {exc}")
            return None
        if not row:
            return None
        cleaned = self.clean_tags(row[0])
        if not cleaned:
            return None
        return {"tag_text": cleaned, "post_id": row[1], "rating": row[2], "topic": row[3]}

    def list_topics(self, ratings: Iterable[str] | str = ("G", "S", "Q")) -> list[str]:
        if not self._ensure_db():
            return []
        picked = self._normalize_ratings(ratings)
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            try:
                rows = conn.execute(
                    f"SELECT DISTINCT topic FROM prompts WHERE rating IN "
                    f"({','.join('?' * len(picked))}) ORDER BY topic",
                    picked,
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return []
        return [r[0] for r in rows]


zako_prompt_pool = ZakoPromptPool()
