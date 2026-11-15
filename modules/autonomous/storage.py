# modules/autonomous/storage.py
"""自主沙盒的五层记忆落盘与运行状态存储。

只做文件读写与 schema 约束，不碰 LLM、不碰会话历史：

- L1 长期日记库   : `MemoryRAG.save_memory(extra_metadata={"type": "autonomous_memo"})`
- L2 工作日记本   : data/work_diary.jsonl
- L3 工作会话档案 : data/work_sessions/<session_id>.json + index.jsonl
- L4 今日工作记忆 : data/daily_work_memory.json（04:00 归档到 daily_work_memory_archive/）
- L5 全局小本本   : core/notebook.py（双区改造在那边）

另有运行状态 data/autonomous_state.json（日配额 / 冷却 / active_mode / 群运行时开关）
与群名缓存 data/group_names.json。
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("autonomous.storage")

DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_PATH = os.path.join(DATA_DIR, "autonomous_state.json")
WORK_DIARY_PATH = os.path.join(DATA_DIR, "work_diary.jsonl")
WORK_SESSIONS_DIR = os.path.join(DATA_DIR, "work_sessions")
WORK_SESSIONS_INDEX = os.path.join(WORK_SESSIONS_DIR, "index.jsonl")
DAILY_MEMORY_PATH = os.path.join(DATA_DIR, "daily_work_memory.json")
DAILY_MEMORY_ARCHIVE_DIR = os.path.join(DATA_DIR, "daily_work_memory_archive")
GROUP_NAMES_PATH = os.path.join(DATA_DIR, "group_names.json")

# 容量约束（对应设计文档 §7）
WORK_LOG_MAX_CHARS = 512
DAILY_MEMORY_MAX_CHARS = 1000
WORK_DIARY_MIN_CHARS = 150
WORK_DIARY_MAX_CHARS = 400
MEMO_MAX_CHARS = 800
INDEX_LOG_HEAD_CHARS = 80

DEFAULT_GROUP_NAME_FALLBACK = "群 {gid}"
DAILY_MEMORY_ARCHIVE_HOUR = 4


# ---------------------------------------------------------------- 基础读写

def _now_ts(now: float | None = None) -> float:
    return float(now if now is not None else time.time())


def _today_str(now: float | None = None) -> str:
    return datetime.datetime.fromtimestamp(_now_ts(now)).strftime("%Y-%m-%d")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[AutonomousStorage] 读取 {path} 失败: {exc}")
        return default


def _write_json(path: str, data) -> None:
    _ensure_dir(os.path.dirname(path))
    temp_file = f"{path}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, path)


def _append_jsonl(path: str, record: dict) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    out.append(record)
    except Exception as exc:
        logger.warning(f"[AutonomousStorage] 读取 {path} 失败: {exc}")
    return out


def truncate_chars(text: str, limit: int) -> str:
    """按字符数截断（超长时保留尾部提示，便于模型知道被截过）。"""
    text = str(text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


# ---------------------------------------------------------------- 运行状态

class AutonomousStateStore:
    """data/autonomous_state.json：日配额、冷却、active_mode、群运行时开关。"""

    def __init__(self, path: str = STATE_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    # -- 通用 --
    def load(self) -> dict:
        data = _load_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("version", 1)
        data.setdefault("daily", {"date": "", "auto_runs": 0})
        data.setdefault("last_run_at", 0.0)
        data.setdefault("group_overrides", {})
        data.setdefault("cooldowns", {})
        data.setdefault("active_mode", {})
        return data

    def save(self, data: dict) -> None:
        with self._lock:
            _write_json(self.path, data)

    # -- 日配额 --
    def auto_runs_today(self, now: float | None = None) -> int:
        data = self.load()
        daily = data.get("daily") or {}
        if daily.get("date") != _today_str(now):
            return 0
        return int(daily.get("auto_runs") or 0)

    def bump_auto_runs(self, now: float | None = None) -> int:
        data = self.load()
        today = _today_str(now)
        daily = data.get("daily") or {}
        if daily.get("date") != today:
            daily = {"date": today, "auto_runs": 0}
        daily["auto_runs"] = int(daily.get("auto_runs") or 0) + 1
        data["daily"] = daily
        data["last_run_at"] = _now_ts(now)
        self.save(data)
        return daily["auto_runs"]

    def last_run_at(self) -> float:
        try:
            return float(self.load().get("last_run_at") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def mark_run(self, now: float | None = None) -> None:
        data = self.load()
        data["last_run_at"] = _now_ts(now)
        self.save(data)

    def cooldown_until(self, chat_id) -> float:
        data = self.load()
        try:
            return float((data.get("cooldowns") or {}).get(str(chat_id)) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def set_cooldown(self, chat_id, until_ts: float) -> None:
        data = self.load()
        cooldowns = dict(data.get("cooldowns") or {})
        cooldowns[str(chat_id)] = float(until_ts)
        data["cooldowns"] = cooldowns
        self.save(data)

    # -- 运行时群开关（优先级高于配置白名单）--
    def get_group_override(self, chat_id) -> bool | None:
        overrides = self.load().get("group_overrides") or {}
        value = overrides.get(str(chat_id))
        if value is None:
            return None
        return bool(value)

    def set_group_override(self, chat_id, enabled: bool) -> None:
        data = self.load()
        overrides = dict(data.get("group_overrides") or {})
        overrides[str(chat_id)] = bool(enabled)
        data["group_overrides"] = overrides
        self.save(data)

    # -- 当前占用（重启后用于 sweep_stale_runs）--
    def get_active_mode(self) -> dict:
        active = self.load().get("active_mode") or {}
        return active if isinstance(active, dict) else {}

    def set_active_mode(self, chat_id, mode: str, run_id: str, session_id: str = "") -> None:
        data = self.load()
        data["active_mode"] = {
            "chat_id": str(chat_id),
            "mode": str(mode),
            "run_id": str(run_id),
            "session_id": str(session_id or ""),
            "started_at": _now_ts(),
        }
        self.save(data)

    def clear_active_mode(self) -> None:
        data = self.load()
        if data.get("active_mode"):
            data["active_mode"] = {}
            self.save(data)


# ---------------------------------------------------------------- L3 工作会话

class WorkSessionStore:
    """data/work_sessions/<session_id>.json + index.jsonl，核心字段 work_log ≤512 字。"""

    def __init__(self, directory: str = WORK_SESSIONS_DIR, index_path: str = WORK_SESSIONS_INDEX):
        self.directory = os.path.abspath(directory)
        self.index_path = os.path.abspath(index_path)

    # -- 路径 --
    def path_of(self, session_id: str) -> str:
        return os.path.join(self.directory, f"{session_id}.json")

    def new_session_id(self, chat_id, now: float | None = None) -> str:
        day = datetime.datetime.fromtimestamp(_now_ts(now)).strftime("%Y%m%d")
        existing = [
            s.get("session_id", "")
            for s in self.list(limit=500)
            if str(s.get("session_id", "")).startswith(f"sess_{day}_")
        ]
        seq = len(existing) + 1
        while True:
            candidate = f"sess_{day}_{seq:02d}"
            if not os.path.exists(self.path_of(candidate)):
                return candidate
            seq += 1

    # -- 读写 --
    def load(self, session_id: str) -> dict | None:
        record = _load_json(self.path_of(session_id), None)
        return record if isinstance(record, dict) else None

    def save(self, record: dict) -> dict:
        session_id = str(record.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("missing_session_id")
        record = dict(record)
        record["updated_at"] = _now_ts()
        record.setdefault("created_at", record["updated_at"])
        record["work_log"] = truncate_chars(record.get("work_log", ""), WORK_LOG_MAX_CHARS)
        record.setdefault("artifacts", [])
        record.setdefault("status", "active")
        record.setdefault("kind", "misc")
        _write_json(self.path_of(session_id), record)
        self._upsert_index(record)
        return record

    def update(self, session_id: str, **fields) -> dict | None:
        record = self.load(session_id)
        if record is None:
            return None
        record.update(fields)
        return self.save(record)

    def _upsert_index(self, record: dict) -> None:
        rows = [r for r in _read_jsonl(self.index_path) if r.get("session_id") != record.get("session_id")]
        rows.append({
            "session_id": record.get("session_id"),
            "title": record.get("title", ""),
            "status": record.get("status", "active"),
            "kind": record.get("kind", "misc"),
            "chat_id": str(record.get("chat_id", "")),
            "updated_at": record.get("updated_at"),
            "log_head": truncate_chars(record.get("work_log", ""), INDEX_LOG_HEAD_CHARS),
        })
        rows.sort(key=lambda r: float(r.get("updated_at") or 0.0))
        _ensure_dir(os.path.dirname(self.index_path))
        temp_file = f"{self.index_path}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temp_file, self.index_path)

    def list(self, status: str | None = None, limit: int = 10, chat_id=None) -> list[dict]:
        rows = _read_jsonl(self.index_path)
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if chat_id is not None:
            rows = [r for r in rows if str(r.get("chat_id")) == str(chat_id)]
        rows.sort(key=lambda r: float(r.get("updated_at") or 0.0), reverse=True)
        return rows[: max(1, int(limit))]

    def latest_resumable(self, chat_id=None) -> dict | None:
        for status in ("active", "paused"):
            rows = self.list(status=status, limit=1, chat_id=chat_id)
            if rows:
                return self.load(str(rows[0]["session_id"]))
        return None


# ---------------------------------------------------------------- L2 工作日记

class WorkDiaryStore:
    """data/work_diary.jsonl：自主轮的思考产物与灵感碎片（150~400 字/条）。"""

    def __init__(self, path: str = WORK_DIARY_PATH):
        self.path = os.path.abspath(path)

    def append(self, *, session_id: str, title: str, kind: str, content: str,
               chat_id=None, now: float | None = None) -> dict:
        record = {
            "ts": _now_ts(now),
            "date": _today_str(now),
            "session_id": str(session_id or ""),
            "title": str(title or ""),
            "kind": str(kind or "insight"),
            "chat_id": str(chat_id) if chat_id is not None else "",
            "content": truncate_chars(content, WORK_DIARY_MAX_CHARS),
        }
        _append_jsonl(self.path, record)
        return record

    def list(self, date_str: str | None = None, limit: int = 10, chat_id=None) -> list[dict]:
        rows = _read_jsonl(self.path)
        if date_str:
            rows = [r for r in rows if r.get("date") == date_str]
        if chat_id is not None:
            rows = [r for r in rows if str(r.get("chat_id")) == str(chat_id)]
        rows.sort(key=lambda r: float(r.get("ts") or 0.0), reverse=True)
        return rows[: max(1, int(limit))]


# ---------------------------------------------------------------- L4 今日工作记忆

class DailyWorkMemoryStore:
    """data/daily_work_memory.json：当日常驻上下文的工作摘要（≤1000 字，18h TTL）。"""

    def __init__(
        self,
        path: str = DAILY_MEMORY_PATH,
        archive_dir: str = DAILY_MEMORY_ARCHIVE_DIR,
        ttl_hours: float | None = None,
    ):
        self.path = os.path.abspath(path)
        self.archive_dir = os.path.abspath(archive_dir)
        self.ttl_hours = ttl_hours
        self._lock = threading.Lock()

    def _ttl(self) -> float:
        if self.ttl_hours is not None:
            return float(self.ttl_hours)
        try:
            from config import cfg

            return float(cfg.autonomous.daily_memory_ttl_hours)
        except Exception:
            return 18.0

    def load(self) -> dict:
        data = _load_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("date", "")
        data.setdefault("entries", [])
        data.setdefault("archived_at", None)
        data.setdefault("updated_at", 0.0)
        data.setdefault("text", "")
        return data

    def _render(self, data: dict) -> str:
        lines = []
        for idx, entry in enumerate(data.get("entries") or [], 1):
            summary = truncate_chars(entry.get("summary", ""), 220)
            tag = entry.get("status") or "记录"
            sid = entry.get("session_id") or ""
            prefix = f"{idx}. [{tag}{(' ' + sid) if sid else ''}] "
            lines.append(prefix + summary)
        return truncate_chars("\n".join(lines), DAILY_MEMORY_MAX_CHARS)

    def add(self, *, summary: str, status: str = "", session_id: str = "",
            artifacts: list[str] | None = None, now: float | None = None) -> dict:
        with self._lock:
            data = self.load()
            today = _today_str(now)
            if data.get("date") != today:
                data = {"date": today, "entries": [], "archived_at": None}
            entries = list(data.get("entries") or [])
            entries.append({
                "ts": _now_ts(now),
                "summary": str(summary or "").strip(),
                "status": status,
                "session_id": session_id,
                "artifacts": list(artifacts or []),
            })
            data["entries"] = entries
            data["updated_at"] = _now_ts(now)
            data["text"] = self._render(data)
            _write_json(self.path, data)
            return data

    def text(self, now: float | None = None) -> str:
        """返回仍然有效的今日工作记忆文本（过期/已归档返回空串）。"""
        data = self.load()
        if not data.get("entries") or data.get("archived_at"):
            return ""
        updated_at = float(data.get("updated_at") or 0.0)
        if updated_at and _now_ts(now) - updated_at > self._ttl() * 3600:
            return ""
        return str(data.get("text") or "")

    def archive_if_due(self, now: float | None = None) -> bool:
        """次日 04:00 后把前一天的工作记忆归档，返回是否执行了归档。"""
        data = self.load()
        if not data.get("entries") or data.get("archived_at"):
            return False
        ts = _now_ts(now)
        dt = datetime.datetime.fromtimestamp(ts)
        if dt.hour < DAILY_MEMORY_ARCHIVE_HOUR:
            return False
        if data.get("date") == dt.strftime("%Y-%m-%d"):
            return False
        _ensure_dir(self.archive_dir)
        target = os.path.join(self.archive_dir, f"{data.get('date') or 'unknown'}.json")
        _write_json(target, data)
        data["archived_at"] = ts
        data["text"] = ""
        _write_json(self.path, data)
        logger.info(f"[AutonomousStorage] 今日工作记忆已归档到 {target}")
        return True


# ---------------------------------------------------------------- 群名缓存

class GroupNameCache:
    """data/group_names.json：群号 → 群名惰性缓存。"""

    def __init__(self, path: str = GROUP_NAMES_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        data = _load_json(self.path, {})
        return data if isinstance(data, dict) else {}

    def name(self, chat_id) -> str:
        gid = str(chat_id)
        cached = self._load().get(gid)
        if cached:
            return str(cached)
        return DEFAULT_GROUP_NAME_FALLBACK.format(gid=gid)

    def label(self, chat_id) -> str:
        """给日记归属标注用：有群名用群名，没有就用群号。"""
        gid = str(chat_id)
        cached = self._load().get(gid)
        return str(cached) if cached else gid

    def remember(self, chat_id, name: str) -> None:
        gid, value = str(chat_id), str(name or "").strip()
        if not gid or not value:
            return
        with self._lock:
            data = self._load()
            if data.get(gid) == value:
                return
            data[gid] = value
            _write_json(self.path, data)

    async def fetch(self, gateway, chat_id) -> str:
        """从 NapCat 拉一次群名并写入缓存（失败静默回落）。"""
        gid = str(chat_id)
        cached = self._load().get(gid)
        if cached:
            return str(cached)
        try:
            meta = await gateway.get_group_meta(gid)
        except Exception as exc:
            logger.debug(f"[AutonomousStorage] 拉取群名失败 {gid}: {exc}")
            return self.name(gid)
        name = ""
        if isinstance(meta, dict):
            name = str(meta.get("group_name") or meta.get("name") or "").strip()
        if name:
            self.remember(gid, name)
            return name
        return self.name(gid)


# ---------------------------------------------------------------- L1 日记只追加

class MemoStore:
    """L1：把思考备忘录只追加写进 diaries 集合，参与后续检索。"""

    MEMO_PREFIX_TEMPLATE = "【{kind}({date})】"

    def __init__(self, memory_rag=None):
        self._memory_rag = memory_rag

    def _rag(self):
        if self._memory_rag is not None:
            return self._memory_rag
        try:
            from modules.memory.rag import MemoryRAG

            self._memory_rag = MemoryRAG()
        except Exception as exc:
            logger.warning(f"[AutonomousStorage] MemoryRAG 初始化失败: {exc}")
            return None
        return self._memory_rag

    @classmethod
    def format_memo(cls, kind: str, content: str, now: float | None = None) -> str:
        date_str = _today_str(now)
        label = "自主随想" if kind in {"memo", "memo_only", "insight"} else "工作记录"
        return f"{cls.MEMO_PREFIX_TEMPLATE.format(kind=label, date=date_str)}{truncate_chars(content, MEMO_MAX_CHARS)}"

    def save_memo(self, *, content: str, chat_id, session_id: str = "",
                  kind: str = "memo", now: float | None = None) -> str | None:
        rag = self._rag()
        if rag is None:
            return None
        text = self.format_memo(kind, content, now)
        extra = {
            "type": "autonomous_memo",
            "session_id": session_id or "",
            "kind": kind,
        }
        if chat_id is not None:
            extra["origin_chat_id"] = str(chat_id)
        try:
            return rag.save_memory(
                content=text,
                memory_type="summary",
                chat_id=chat_id,
                importance=3,
                extra_metadata=extra,
            )
        except Exception as exc:
            logger.error(f"[AutonomousStorage] 写入自主备忘录失败: {exc}")
            return None


# ---------------------------------------------------------------- 日记冷启动采样

class DiarySeedSampler:
    """Phase 1 冷启动：静默抽 2 条近 7 天本群日记 + 1 条 30 天以上旧日记。"""

    def __init__(self, local_count: int = 2, old_count: int = 1,
                 local_days: int = 7, old_days: int = 30):
        self.local_count = local_count
        self.old_count = old_count
        self.local_days = local_days
        self.old_days = old_days

    @staticmethod
    def _collection():
        import chromadb
        from config import cfg

        client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)
        return client.get_collection(name="diaries")

    def sample(self, chat_id=None, now: float | None = None) -> list[dict]:
        """返回 [{"content":..., "source": "本群"/"别的群", "ts":...}]，失败返回空列表。"""
        try:
            collection = self._collection()
        except Exception as exc:
            logger.debug(f"[AutonomousStorage] 日记采样不可用: {exc}")
            return []

        ts_now = _now_ts(now)
        local_cutoff = ts_now - self.local_days * 86400
        old_cutoff = ts_now - self.old_days * 86400
        seeds: list[dict] = []

        def _fetch(where: dict, include_limit: int = 60) -> list[dict]:
            try:
                res = collection.get(where=where, include=["documents", "metadatas"])
            except Exception as exc:
                logger.debug(f"[AutonomousStorage] 日记采样查询失败: {exc}")
                return []
            docs = res.get("documents") or []
            metas = res.get("metadatas") or [None] * len(docs)
            rows = []
            for doc, meta in zip(docs, metas):
                if not doc:
                    continue
                meta = meta or {}
                rows.append({
                    "content": str(doc),
                    "ts": float(meta.get("timestamp") or 0.0),
                    "chat_id": str(meta.get("chat_id") or ""),
                })
            rows.sort(key=lambda r: r["ts"], reverse=True)
            return rows[:include_limit]

        cid = str(chat_id) if chat_id is not None else None
        local_rows = []
        if cid:
            local_rows = [
                r for r in _fetch({"$and": [
                    {"chat_id": cid},
                    {"timestamp": {"$gte": local_cutoff}},
                ]})
                if r["ts"] >= local_cutoff
            ]
        for row in local_rows[: self.local_count]:
            seeds.append({"content": row["content"], "source": "本群", "ts": row["ts"]})

        old_rows = _fetch({"timestamp": {"$lt": old_cutoff}}, include_limit=120)
        if cid and len(old_rows) > 1:
            # 旧日记优先取别的群的，避免同一个群自我复读
            old_rows.sort(key=lambda r: r["chat_id"] == cid)
        for row in old_rows[: self.old_count]:
            source = "本群" if cid and row["chat_id"] == cid else (
                f"群:{row['chat_id']}" if row["chat_id"] else "早期未标群"
            )
            seeds.append({"content": row["content"], "source": source, "ts": row["ts"]})
        return seeds


# ---------------------------------------------------------------- 单例

state_store = AutonomousStateStore()
work_session_store = WorkSessionStore()
work_diary_store = WorkDiaryStore()
daily_memory_store = DailyWorkMemoryStore()
group_name_cache = GroupNameCache()
memo_store = MemoStore()
diary_seed_sampler = DiarySeedSampler()


def init_data_dir() -> None:
    """P0：确保数据目录与初始状态文件存在（幂等）。"""
    _ensure_dir(DATA_DIR)
    _ensure_dir(WORK_SESSIONS_DIR)
    _ensure_dir(DAILY_MEMORY_ARCHIVE_DIR)
    if not os.path.exists(STATE_PATH):
        _write_json(STATE_PATH, {
            "version": 1,
            "daily": {"date": "", "auto_runs": 0},
            "last_run_at": 0.0,
            "group_overrides": {},
            "cooldowns": {},
            "active_mode": {},
        })
    for path in (WORK_DIARY_PATH, WORK_SESSIONS_INDEX):
        if not os.path.exists(path):
            _ensure_dir(os.path.dirname(path))
            open(path, "a", encoding="utf-8").close()
