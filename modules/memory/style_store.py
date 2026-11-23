# modules/memory/style_store.py
"""群聊情境表达习惯（StyleHabit）SQLite 持久化存储。

借鉴 MaiBot `expression` 体系，以 `(situation, style)` 结构记录群友在不同
情境下的口癖、梗与表达方式，支持频次累计与注入冷却防复读。
"""

import os
import sqlite3
import threading
import time
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from utils import BASE_DIR

_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "style_habits.db")


@dataclass
class StyleHabit:
    """单条情境表达习惯。"""

    chat_id: str
    situation: str
    style: str
    count: int = 1
    enabled: bool = True
    last_used_at: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0
    id: Optional[int] = None


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _normalize_key(situation: str, style: str) -> str:
    return f"{_normalize_text(situation).lower()}::{_normalize_text(style).lower()}"


class StyleStore:
    """线程安全的情境表达习惯 SQLite 存储。"""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._active_cache: Dict[Tuple[str, int], List[StyleHabit]] = {}
        self._init_db()

    def _get_conn_locked(self) -> sqlite3.Connection:
        if self._conn is None:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._active_cache.clear()

    def _invalidate_chat_locked(self, chat_id: str) -> None:
        cid = str(chat_id)
        for key in [k for k in self._active_cache if k[0] == cid]:
            self._active_cache.pop(key, None)

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn_locked()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS style_habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    norm_key TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    style TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_used_at REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(chat_id, norm_key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_style_chat_enabled "
                "ON style_habits (chat_id, enabled, count)"
            )
            conn.commit()

    @staticmethod
    def _row_to_habit(row: sqlite3.Row) -> StyleHabit:
        return StyleHabit(
            id=row["id"],
            chat_id=row["chat_id"],
            situation=row["situation"],
            style=row["style"],
            count=int(row["count"] or 1),
            enabled=bool(row["enabled"]),
            last_used_at=float(row["last_used_at"] or 0.0),
            created_at=float(row["created_at"] or 0.0),
            updated_at=float(row["updated_at"] or 0.0),
        )

    def record_habits(
        self,
        chat_id: str,
        habits: List[Tuple[str, str]],
    ) -> List[StyleHabit]:
        """批量写入或累加情境表达习惯。"""
        if not habits:
            return []
        cid = str(chat_id)
        now = time.time()
        saved: List[StyleHabit] = []

        with self._lock:
            conn = self._get_conn_locked()
            for raw_sit, raw_style in habits:
                situation = _normalize_text(raw_sit)
                style = _normalize_text(raw_style)
                if not situation or not style:
                    continue
                key = _normalize_key(situation, style)
                row = conn.execute(
                    "SELECT * FROM style_habits WHERE chat_id = ? AND norm_key = ?",
                    (cid, key),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO style_habits (
                            chat_id, norm_key, situation, style, count,
                            enabled, last_used_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 1, 1, 0.0, ?, ?)
                        """,
                        (cid, key, situation, style, now, now),
                    )
                    new_row = conn.execute(
                        "SELECT * FROM style_habits WHERE chat_id = ? AND norm_key = ?",
                        (cid, key),
                    ).fetchone()
                    if new_row is not None:
                        saved.append(self._row_to_habit(new_row))
                else:
                    new_count = int(row["count"] or 1) + 1
                    conn.execute(
                        "UPDATE style_habits SET count = ?, updated_at = ? WHERE id = ?",
                        (new_count, now, row["id"]),
                    )
                    habit = self._row_to_habit(row)
                    habit.count = new_count
                    habit.updated_at = now
                    saved.append(habit)
            conn.commit()
            self._invalidate_chat_locked(cid)
        return saved

    def get_active_habits(self, chat_id: str, *, limit: int = 60) -> List[StyleHabit]:
        """获取指定会话已启用的表达习惯（按频次降序）。"""
        cid = str(chat_id)
        cap = max(1, int(limit))
        cache_key = (cid, cap)
        with self._lock:
            cached = self._active_cache.get(cache_key)
            if cached is None:
                conn = self._get_conn_locked()
                rows = conn.execute(
                    """
                    SELECT * FROM style_habits
                    WHERE chat_id = ? AND enabled = 1
                    ORDER BY count DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (cid, cap),
                ).fetchall()
                cached = [self._row_to_habit(r) for r in rows]
                self._active_cache[cache_key] = cached
            return [replace(h) for h in cached]

    def mark_used(self, habit_ids: List[int], *, timestamp: Optional[float] = None) -> None:
        """记录习惯最近被注入的时间，用于冷却防刷屏。"""
        ids = [int(i) for i in habit_ids if i is not None]
        if not ids:
            return
        id_set = set(ids)
        now = float(timestamp) if timestamp is not None else time.time()
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            conn = self._get_conn_locked()
            conn.execute(
                f"UPDATE style_habits SET last_used_at = ? WHERE id IN ({placeholders})",
                [now, *ids],
            )
            conn.commit()
            for items in self._active_cache.values():
                for habit in items:
                    if habit.id in id_set:
                        habit.last_used_at = now


_default_store: Optional[StyleStore] = None


def get_style_store() -> StyleStore:
    """获取全局默认 StyleStore 实例。"""
    global _default_store
    if _default_store is None:
        _default_store = StyleStore()
    return _default_store
