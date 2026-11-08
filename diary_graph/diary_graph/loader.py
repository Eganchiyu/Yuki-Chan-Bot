"""从 Yuki 的 ChromaDB 只读加载日记。

不依赖 chromadb 包：直接读 chroma.sqlite3 的 embeddings / embedding_metadata /
segments / collections 表，速度快且不触发向量模型加载。
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# 日记正文前缀形如 【日记(2026-11-05 12:00)】：
PREFIX_RE = re.compile(r"【日记\((\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?")
PREFIX_LEN = 0


@dataclass
class Diary:
    id: str
    text: str
    timestamp: float
    chat_id: str = ""

    @property
    def when(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.timestamp)

    @property
    def date(self) -> str:
        return self.when.strftime("%Y-%m-%d %H:%M")


_QUERY = """
SELECT e.id, m.key, m.string_value, m.float_value, m.int_value
FROM embeddings e
JOIN segments s ON s.id = e.segment_id
JOIN collections c ON c.id = s.collection
JOIN embedding_metadata m ON m.id = e.id
WHERE c.name = ? AND m.key IN ('chroma:document', 'timestamp', 'chat_id')
"""


def _coerce_ts(prefix: re.Match | None, raw: float | None) -> float:
    """优先用正文前缀里的时间，其次用 metadata timestamp。"""
    if prefix:
        y, mo, d, hh, mm = prefix.groups()
        try:
            return dt.datetime(
                int(y), int(mo), int(d), int(hh or 0), int(mm or 0)
            ).timestamp()
        except ValueError:
            pass
    return float(raw or 0.0)


def load_diaries(db_path: str | Path, collection: str = "diaries",
                 limit: int | None = None) -> list[Diary]:
    db_path = Path(db_path).expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"找不到记忆库文件: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(_QUERY, (collection,)).fetchall()
    finally:
        conn.close()

    docs: dict[str, dict[str, object]] = {}
    for eid, key, sval, fval, ival in rows:
        rec = docs.setdefault(str(eid), {})
        if key == "chroma:document":
            rec["text"] = sval or ""
        elif key == "timestamp":
            rec["ts"] = fval if fval is not None else ival
        elif key == "chat_id":
            rec["chat_id"] = sval or ""

    diaries: list[Diary] = []
    for eid, rec in docs.items():
        text = str(rec.get("text") or "").strip()
        if not text:
            continue
        m = PREFIX_RE.search(text[:40])
        diaries.append(Diary(
            id=eid,
            text=text,
            timestamp=_coerce_ts(m, rec.get("ts")),  # type: ignore[arg-type]
            chat_id=str(rec.get("chat_id") or ""),
        ))

    diaries.sort(key=lambda d: d.timestamp)
    if limit:
        diaries = diaries[-limit:]
    return diaries
