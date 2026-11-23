# modules/memory/jargon_store.py
"""群黑话（Jargon）SQLite 持久化存储。

按词条归一化聚合出现次数、按群会话记录分布与最近证据上下文片段，
支持阈值触发推断、白话/真黑话判定以及手动覆盖。
"""

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils import BASE_DIR

_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "jargon.db")
_MAX_EVIDENCE_SEGMENTS = 10


@dataclass
class JargonRecord:
    """单条黑话/候选词记录。"""

    content: str
    meaning: str = ""
    evidence: List[str] = field(default_factory=list)
    session_counts: Dict[str, int] = field(default_factory=dict)
    count: int = 0
    is_jargon: Optional[bool] = None
    is_complete: bool = False
    last_inference_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    id: Optional[int] = None


def _normalize_key(content: str) -> str:
    return " ".join((content or "").strip().split()).lower()


class JargonStore:
    """线程安全的黑话 SQLite 存储。"""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jargon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    norm_key TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    meaning TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    session_counts_json TEXT NOT NULL DEFAULT '{}',
                    count INTEGER NOT NULL DEFAULT 0,
                    is_jargon INTEGER DEFAULT NULL,
                    is_complete INTEGER NOT NULL DEFAULT 0,
                    last_inference_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jargon_verified ON jargon (is_jargon, count)"
            )
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JargonRecord:
        try:
            evidence = json.loads(row["evidence_json"] or "[]")
            if not isinstance(evidence, list):
                evidence = []
        except Exception:
            evidence = []
        try:
            session_counts = json.loads(row["session_counts_json"] or "{}")
            if not isinstance(session_counts, dict):
                session_counts = {}
        except Exception:
            session_counts = {}
        raw_flag = row["is_jargon"]
        is_jargon = None if raw_flag is None else bool(raw_flag)
        return JargonRecord(
            id=row["id"],
            content=row["content"],
            meaning=row["meaning"] or "",
            evidence=[str(x) for x in evidence if x],
            session_counts={str(k): int(v) for k, v in session_counts.items()},
            count=int(row["count"] or 0),
            is_jargon=is_jargon,
            is_complete=bool(row["is_complete"]),
            last_inference_count=int(row["last_inference_count"] or 0),
            created_at=float(row["created_at"] or 0.0),
            updated_at=float(row["updated_at"] or 0.0),
        )

    def record_candidates(
        self,
        chat_id: str,
        candidates: List[tuple[str, str]],
    ) -> List[JargonRecord]:
        """批量累加候选词出现次数与证据片段，返回更新后的记录列表。"""
        if not candidates:
            return []
        cid = str(chat_id)
        now = time.time()
        updated: List[JargonRecord] = []

        with self._lock, self._connect() as conn:
            for raw_content, evidence_snippet in candidates:
                content = " ".join((raw_content or "").strip().split())
                key = _normalize_key(content)
                if not key:
                    continue
                snippet = (evidence_snippet or "").strip()

                row = conn.execute(
                    "SELECT * FROM jargon WHERE norm_key = ?", (key,)
                ).fetchone()
                if row is None:
                    ev_list = [snippet] if snippet else []
                    sc_dict = {cid: 1}
                    conn.execute(
                        """
                        INSERT INTO jargon (
                            norm_key, content, meaning, evidence_json,
                            session_counts_json, count, is_jargon, is_complete,
                            last_inference_count, created_at, updated_at
                        ) VALUES (?, ?, '', ?, ?, 1, NULL, 0, 0, ?, ?)
                        """,
                        (
                            key,
                            content,
                            json.dumps(ev_list, ensure_ascii=False),
                            json.dumps(sc_dict, ensure_ascii=False),
                            now,
                            now,
                        ),
                    )
                    new_row = conn.execute(
                        "SELECT * FROM jargon WHERE norm_key = ?", (key,)
                    ).fetchone()
                    if new_row is not None:
                        updated.append(self._row_to_record(new_row))
                else:
                    rec = self._row_to_record(row)
                    rec.count += 1
                    rec.session_counts[cid] = rec.session_counts.get(cid, 0) + 1
                    if snippet and snippet not in rec.evidence:
                        rec.evidence.append(snippet)
                        rec.evidence = rec.evidence[-_MAX_EVIDENCE_SEGMENTS:]
                    conn.execute(
                        """
                        UPDATE jargon
                        SET evidence_json = ?, session_counts_json = ?,
                            count = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            json.dumps(rec.evidence, ensure_ascii=False),
                            json.dumps(rec.session_counts, ensure_ascii=False),
                            rec.count,
                            now,
                            rec.id,
                        ),
                    )
                    rec.updated_at = now
                    updated.append(rec)
            conn.commit()
        return updated

    def update_inference_result(
        self,
        content: str,
        *,
        is_jargon: Optional[bool],
        meaning: str,
        last_inference_count: int,
        is_complete: bool = False,
    ) -> None:
        """写回黑话推断结果。"""
        key = _normalize_key(content)
        if not key:
            return
        flag_val = None if is_jargon is None else (1 if is_jargon else 0)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jargon
                SET is_jargon = ?, meaning = ?, last_inference_count = ?,
                    is_complete = ?, updated_at = ?
                WHERE norm_key = ?
                """,
                (
                    flag_val,
                    (meaning or "").strip(),
                    int(last_inference_count),
                    1 if is_complete else 0,
                    now,
                    key,
                ),
            )
            conn.commit()

    def load_verified_jargons(self, chat_id: str) -> List[JargonRecord]:
        """读取已确认为真黑话且有释义的条目（优先本群出现过的，按频次降序）。"""
        cid = str(chat_id)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jargon
                WHERE is_jargon = 1 AND meaning != ''
                ORDER BY count DESC
                """
            ).fetchall()
        records = [self._row_to_record(r) for r in rows]
        # 本群出现过的排前面
        records.sort(
            key=lambda r: (1 if cid in r.session_counts else 0, r.session_counts.get(cid, 0), r.count),
            reverse=True,
        )
        return records

    def list_jargons(self, *, only_verified: bool = False, limit: int = 50) -> List[JargonRecord]:
        """列出黑话记录，便于调试与检查。"""
        sql = "SELECT * FROM jargon"
        if only_verified:
            sql += " WHERE is_jargon = 1"
        sql += " ORDER BY count DESC, updated_at DESC LIMIT ?"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, (max(1, int(limit)),)).fetchall()
        return [self._row_to_record(r) for r in rows]


_default_store: Optional[JargonStore] = None


def get_jargon_store() -> JargonStore:
    """获取全局默认 JargonStore 实例。"""
    global _default_store
    if _default_store is None:
        _default_store = JargonStore()
    return _default_store
