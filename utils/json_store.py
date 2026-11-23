# utils/json_store.py
"""统一 JSON 原子读写与文件指纹缓存底座。

解决各模块重复手写 `.tmp + os.replace`（或裸 `open("w")` 截断丢数据）以及高频热路径重复反序列化问题：
- `atomic_write_json`：同目录唯一临时文件 + flush + 可选 fsync + `os.replace`；
- `read_json_cached` / `CachedJsonStore`：基于 `(st_mtime_ns, st_size, st_ino)` 三元组指纹缓存，
  即便单测在同一纳秒内通过 `os.replace` 写入同长度新文件，`st_ino` 变化也会立即触发重读。
"""
from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any, Callable, Optional, Tuple

from utils.logger import get_logger

logger = get_logger("json_store")

_FileSig = Tuple[int, int, int]
_GLOBAL_CACHE_LOCK = threading.Lock()
_GLOBAL_READ_CACHE: dict[str, Tuple[_FileSig, Any]] = {}


def _stat_sig(path: str) -> Optional[_FileSig]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def atomic_write_json(
    path: str,
    data: Any,
    *,
    indent: Optional[int] = 2,
    compact: bool = False,
    default: Optional[Callable[[Any], Any]] = None,
    fsync: bool = False,
) -> None:
    """将 JSON 数据原子写入目标路径。"""
    abs_path = os.path.abspath(path)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    base = os.path.basename(abs_path)
    tmp_path = os.path.join(
        parent, f".{base}.tmp.{os.getpid()}.{threading.get_ident()}"
    )
    dump_kwargs: dict[str, Any] = {"ensure_ascii": False}
    if compact:
        dump_kwargs["separators"] = (",", ":")
    elif indent is not None:
        dump_kwargs["indent"] = indent
    if default is not None:
        dump_kwargs["default"] = default

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            if fsync:
                os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
        sig = _stat_sig(abs_path)
        if sig is not None:
            with _GLOBAL_CACHE_LOCK:
                _GLOBAL_READ_CACHE[abs_path] = (sig, copy.deepcopy(data))
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def read_json_cached(
    path: str,
    default: Any = None,
    *,
    copy_result: bool = True,
) -> Any:
    """带 `(mtime_ns, size, ino)` 指纹缓存的安全 JSON 读取。"""
    abs_path = os.path.abspath(path)
    sig = _stat_sig(abs_path)
    if sig is None:
        with _GLOBAL_CACHE_LOCK:
            _GLOBAL_READ_CACHE.pop(abs_path, None)
        return copy.deepcopy(default) if copy_result else default

    with _GLOBAL_CACHE_LOCK:
        cached = _GLOBAL_READ_CACHE.get(abs_path)
        if cached is not None and cached[0] == sig:
            return copy.deepcopy(cached[1]) if copy_result else cached[1]

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning(f"[JsonStore] 读取失败 {abs_path}: {exc}")
        return copy.deepcopy(default) if copy_result else default

    new_sig = _stat_sig(abs_path) or sig
    with _GLOBAL_CACHE_LOCK:
        _GLOBAL_READ_CACHE[abs_path] = (new_sig, data)
    return copy.deepcopy(data) if copy_result else data


class CachedJsonStore:
    """单文件路径绑定的线程安全原子 JSON 存储器。"""

    def __init__(self, path: str, *, default_factory: Callable[[], Any] = dict) -> None:
        self.path = os.path.abspath(path)
        self._default_factory = default_factory
        self._lock = threading.Lock()

    def load(self, *, copy_result: bool = True) -> Any:
        with self._lock:
            return read_json_cached(
                self.path, self._default_factory(), copy_result=copy_result
            )

    def save(
        self,
        data: Any,
        *,
        indent: Optional[int] = 2,
        compact: bool = False,
        default: Optional[Callable[[Any], Any]] = None,
        fsync: bool = False,
    ) -> None:
        with self._lock:
            atomic_write_json(
                self.path,
                data,
                indent=indent,
                compact=compact,
                default=default,
                fsync=fsync,
            )
