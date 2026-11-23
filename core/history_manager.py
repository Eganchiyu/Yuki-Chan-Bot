# core/history_manager.py
"""会话历史管理器：按 `chat_id` 分片原子存储，支持从旧版单文件 `chat_history.json` 自动平滑迁移。"""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import threading
import urllib.parse
from typing import Any

from config import cfg
from core.reply_format import normalize_reply_markup
from utils.json_store import atomic_write_json
from utils.logger import get_logger

logger = get_logger("history")

_SAFE_CID_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def _derive_history_dir(history_file: str) -> str:
    abs_file = os.path.abspath(history_file)
    parent = os.path.dirname(abs_file)
    base = os.path.basename(abs_file)
    if base == "chat_history.json":
        return os.path.join(parent, "history")
    stem, _ = os.path.splitext(abs_file)
    return f"{stem}_shards"


def _encode_cid_filename(chat_id: str) -> str:
    cid = str(chat_id)
    if _SAFE_CID_RE.match(cid):
        return f"{cid}.json"
    encoded = urllib.parse.quote(cid, safe="")
    return f"u_{encoded}.json"


def _decode_cid_from_shard(filename: str, payload: Any) -> str | None:
    if isinstance(payload, dict) and "chat_id" in payload:
        return str(payload["chat_id"])
    if not filename.endswith(".json"):
        return None
    stem = filename[:-5]
    if stem.startswith("u_"):
        return urllib.parse.unquote(stem[2:])
    return stem


class HistoryManager:
    def __init__(
        self,
        history_file: str = cfg.HISTORY_FILE,
        log_file: str = cfg.LOG_FILE,
        *,
        history_dir: str | None = None,
    ):
        self.history_file = history_file
        self.log_file = log_file
        self.history_dir = os.path.abspath(history_dir or _derive_history_dir(history_file))
        self._cache: dict[str, list] | None = None
        self._dirty_chats: set[str] = set()
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()

    def _shard_path(self, chat_id: str) -> str:
        return os.path.join(self.history_dir, _encode_cid_filename(chat_id))

    def preload(self) -> None:
        """预载分片历史到内存（首次启动自动迁移旧单文件），并修复历史里的错格式标记。"""
        with self._lock:
            data = self._get_data_locked()
            self._repair_reply_markup_locked(data)

    @staticmethod
    def _normalize_message_markup(message: dict) -> bool:
        """归一化单条 assistant 消息里的回复标记，返回是否发生修改。

        只处理 assistant：用户消息里的 `【MEME:...】` 是对方原文，不能改写。
        """
        if message.get("role") != "assistant":
            return False
        content = message.get("content")
        if not isinstance(content, str) or not content:
            return False
        normalized = normalize_reply_markup(content)
        if normalized == content:
            return False
        message["content"] = normalized
        return True

    def _repair_reply_markup_locked(self, data: dict) -> int:
        """把内存中所有 assistant 消息的错格式标记改写为规范格式，只刷发生修改的会话分片。"""
        fixed = 0
        changed_cids: list[str] = []
        for cid, session in data.items():
            if not isinstance(session, list):
                continue
            chat_fixed = 0
            for message in session:
                if isinstance(message, dict) and self._normalize_message_markup(message):
                    chat_fixed += 1
            if chat_fixed:
                fixed += chat_fixed
                changed_cids.append(cid)
        if fixed:
            logger.info(f"[History] 已修复 {fixed} 条回复的错格式标记（涉及 {len(changed_cids)} 个会话）")
            for cid in changed_cids:
                self._save_chat_locked(cid, data[cid])
        return fixed

    def repair_reply_markup(self) -> int:
        """对外暴露的历史标记修复入口，返回修复条数。"""
        with self._lock:
            return self._repair_reply_markup_locked(self._get_data_locked())

    def load(self, *, copy_result: bool = True) -> dict:
        """获取全部历史；默认返回独立快照以兼容旧调用。"""
        with self._lock:
            data = self._get_data_locked()
            return copy.deepcopy(data) if copy_result else data

    @staticmethod
    def _ensure_system_message(session: list, system_content: str | None) -> bool:
        """确保 system 提示词存在，返回会话是否被修改。"""
        if not system_content:
            return False
        if not session:
            session.append({"role": "system", "content": system_content})
            return True
        if session[0].get("role") == "system":
            if session[0].get("content") == system_content:
                return False
            session[0]["content"] = system_content
            return True
        session.insert(0, {"role": "system", "content": system_content})
        return True

    def get_session(self, chat_id: str, system_content: str | None = None) -> list:
        """获取单个会话（O(1) 单会话拷贝），并只在 system 提示词变化时落盘该会话分片。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            session = data.setdefault(cid, [])
            if self._ensure_system_message(session, system_content):
                self._save_chat_locked(cid, session)
            return copy.deepcopy(session)

    def replace_session(self, chat_id: str, session: list) -> list:
        """原子替换单个会话并仅落盘该会话分片，返回独立快照。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            copied = copy.deepcopy(session)
            data[cid] = copied
            self._save_chat_locked(cid, copied)
            return copy.deepcopy(copied)

    def append_session_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        system_content: str | None = None,
        *,
        save_immediately: bool = True,
        return_snapshot: bool = True,
        **extra: Any,
    ):
        """向单个会话追加消息，按需延迟落盘或只写当前会话分片。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            session = data.setdefault(cid, [])
            self._ensure_system_message(session, system_content)
            item = {
                "role": role,
                "content": content,
                "time": datetime.datetime.now().strftime("%Y年%m月%d日%H:%M"),
            }
            item.update(extra)
            self._normalize_message_markup(item)
            session.append(item)
            if save_immediately:
                self._save_chat_locked(cid, session)
            else:
                self._dirty_chats.add(cid)
            return copy.deepcopy(session) if return_snapshot else None

    def _get_data_locked(self) -> dict[str, list]:
        if self._cache is None:
            logger.info("[History] 正在预载分片历史数据到内存...")
            self._cache = self.read_from_disk()
        return self._cache

    def flush(self) -> None:
        """将延迟写入的脏会话逐个落盘。"""
        with self._lock:
            if not self._dirty_chats or self._cache is None:
                return
            for cid in list(self._dirty_chats):
                if cid in self._cache:
                    self._save_chat_locked(cid, self._cache[cid])
            self._dirty_chats.clear()

    def _save_chat_locked(self, cid: str, session: list) -> None:
        shard_file = self._shard_path(cid)
        payload = {"chat_id": cid, "messages": session}
        try:
            atomic_write_json(shard_file, payload, compact=True)
            self._dirty_chats.discard(cid)
        except Exception as e:
            logger.error(f"[History] 保存会话分片失败 ({cid}): {e}")

    def _migrate_legacy_file_if_needed(self) -> dict[str, list]:
        """若旧版单文件 `self.history_file` 存在，自动拆分写入分片目录并重命名备份。"""
        if not self.history_file or not os.path.exists(self.history_file):
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"[History] 读取旧版历史文件失败 ({self.history_file}): {e}")
            return {}

        if not isinstance(raw, dict):
            return {}

        migrated: dict[str, list] = {}
        os.makedirs(self.history_dir, exist_ok=True)
        for k, v in raw.items():
            if not isinstance(v, list):
                continue
            cid = str(k)
            migrated[cid] = v
            shard_file = self._shard_path(cid)
            if not os.path.exists(shard_file):
                try:
                    atomic_write_json(shard_file, {"chat_id": cid, "messages": v}, compact=True)
                except Exception as e:
                    logger.error(f"[History] 迁移分片失败 ({cid}): {e}")

        backup_path = f"{self.history_file}.migrated.bak"
        try:
            os.replace(self.history_file, backup_path)
            logger.info(
                f"[History] 已将 {len(migrated)} 个会话平滑迁移至分片目录 {self.history_dir} "
                f"（旧文件备份为 {backup_path}）"
            )
        except OSError as e:
            logger.debug(f"[History] 旧版历史文件备份重命名跳过: {e}")
        return migrated

    def read_from_disk(self) -> dict[str, list]:
        """从分片目录读取全部会话（若存在未迁移的旧单文件则先自动迁移）。"""
        legacy_data = self._migrate_legacy_file_if_needed()
        result: dict[str, list] = dict(legacy_data)
        if not os.path.isdir(self.history_dir):
            return result

        try:
            entries = sorted(os.listdir(self.history_dir))
        except OSError as e:
            logger.error(f"[History] 扫描分片目录失败: {e}")
            return result

        for name in entries:
            if not name.endswith(".json") or name.startswith("."):
                continue
            full_path = os.path.join(self.history_dir, name)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception as e:
                logger.error(f"[History] 读取分片失败 ({full_path}): {e}")
                continue

            if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
                cid = _decode_cid_from_shard(name, payload)
                if cid is not None:
                    result[cid] = payload["messages"]
            elif isinstance(payload, list):
                cid = _decode_cid_from_shard(name, None)
                if cid is not None:
                    result[cid] = payload
        return result

    def save(self, data: dict) -> None:
        """原子化替换全部历史（同步更新所有分片并清理已移除会话的分片文件）。"""
        if not isinstance(data, dict):
            return
        with self._lock:
            copied = {str(k): copy.deepcopy(v) for k, v in data.items() if isinstance(v, list)}
            self._cache = copied
            os.makedirs(self.history_dir, exist_ok=True)
            expected_files = set()
            for cid, session in copied.items():
                expected_files.add(_encode_cid_filename(cid))
                self._save_chat_locked(cid, session)
            try:
                for name in os.listdir(self.history_dir):
                    if name.endswith(".json") and not name.startswith(".") and name not in expected_files:
                        try:
                            os.remove(os.path.join(self.history_dir, name))
                        except OSError:
                            pass
            except OSError:
                pass
            self._dirty_chats.clear()

    def append_to_log(self, chat_id, sender, message) -> None:
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{time_str}] [{chat_id}] {sender}: {message}\n"
        parent = os.path.dirname(os.path.abspath(self.log_file))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
