# core/art_assets.py
"""艺术资产管理：群友/角色立绘参考图的登记、持久化存储与检索。"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from html import unescape as html_unescape
from typing import Any

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")


def _clean_ref(value: Any) -> str:
    if not value:
        return ""
    text = html_unescape(str(value)).strip().strip("`'\"").strip()
    return text.strip("`'\"").strip()

DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_ASSETS_JSON_PATH = os.path.join(DATA_DIR, "art_assets.json")
CHARACTER_ASSET_DIR = os.path.join(BASE_DIR, "output", "assets", "character")

BUILTIN_ASSETS: list[dict[str, Any]] = [
    {
        "key": "yuki",
        "owner": "Yuki",
        "description": "白长发，蓝瞳，雪花蓝白丝带发饰，白披肩配深蓝连衣裙，白过膝袜",
        "reference": "output/assets/character/yuki_reference.png",
        "tags": ["立绘", "人设"],
        "aliases": ["Yuki", "yuki", "自己", "我"],
        "updated_at": "2026-11-12",
    },
    {
        "key": "master",
        "owner": "主人",
        "description": "黑长发，绿瞳，绿色X发夹，黑绿连帽夹克配白衬衫黑领结，黑百褶裙，小猫黑袜运动鞋",
        "reference": "output/assets/character/master_reference.png",
        "tags": ["立绘", "人设"],
        "aliases": ["主人", "master", "哥哥", "哥哥大人", "阿澄", "asumi"],
        "updated_at": "2026-11-12",
    },
]


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", "_", text)


def _safe_filename_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or f"asset_{int(time.time())}"


def _normalize_str_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        parts = re.split(r"[,，、/\s]+", val.strip())
        return [p.strip() for p in parts if p.strip()]
    if isinstance(val, (list, tuple, set)):
        out: list[str] = []
        for item in val:
            s = str(item or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    return []


def _to_rel_path(path: str) -> str:
    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(path)
    try:
        if os.path.commonpath([real_base, real_target]) == real_base:
            rel = os.path.relpath(real_target, real_base)
            return rel.replace("\\", "/")
    except ValueError:
        pass
    return path


class ArtAssetStore:
    """管理已登记的角色/群友立绘与参考图资产。"""

    def __init__(
        self,
        json_path: str = DEFAULT_ASSETS_JSON_PATH,
        asset_dir: str = CHARACTER_ASSET_DIR,
    ):
        self.json_path = json_path
        self.asset_dir = asset_dir
        self._lock = threading.RLock()
        self._assets: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            loaded: list[dict[str, Any]] = []
            if os.path.isfile(self.json_path):
                try:
                    with open(self.json_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict) and isinstance(raw.get("assets"), list):
                        loaded = raw["assets"]
                    elif isinstance(raw, list):
                        loaded = raw
                except Exception as exc:
                    logger.warning(f"[ArtAsset] 读取资产文件失败 {self.json_path}: {exc}")

            self._assets.clear()
            for item in loaded:
                norm = self._normalize_item(item)
                if norm:
                    self._assets[norm["key"]] = norm

            if not self._assets:
                for item in BUILTIN_ASSETS:
                    norm = self._normalize_item(item)
                    if norm:
                        self._assets[norm["key"]] = norm
                self._save_unlocked()

    def _normalize_item(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        key = _normalize_key(item.get("key") or item.get("name") or item.get("id") or "")
        reference = _clean_ref(item.get("reference") or item.get("image_path") or "")
        if not key or not reference:
            return None
        owner = str(item.get("owner") or key).strip()
        description = str(item.get("description") or item.get("desc") or "").strip()
        tags = _normalize_str_list(item.get("tags"))
        aliases = _normalize_str_list(item.get("aliases"))
        updated_at = str(item.get("updated_at") or time.strftime("%Y-%m-%d %H:%M")).strip()
        return {
            "key": key,
            "owner": owner,
            "description": description,
            "reference": reference,
            "tags": tags,
            "aliases": aliases,
            "updated_at": updated_at,
        }

    def _save_unlocked(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
            payload = {"version": 1, "assets": list(self._assets.values())}
            tmp_path = f"{self.json_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.json_path)
        except Exception as exc:
            logger.warning(f"[ArtAsset] 保存资产文件失败 {self.json_path}: {exc}")

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._assets.values()]

    def find_key(self, query: str) -> str | None:
        """按 key / owner / aliases 查找单个资产主键。"""
        q = str(query or "").strip()
        if not q:
            return None
        q_norm = _normalize_key(q).lower()
        q_lower = q.lower()
        with self._lock:
            # 1. key 精确匹配
            for k in self._assets:
                if k.lower() == q_norm or k.lower() == q_lower:
                    return k
            # 2. owner 或 aliases 精确匹配
            for k, item in self._assets.items():
                if str(item.get("owner") or "").strip().lower() == q_lower:
                    return k
                aliases = [str(a).strip().lower() for a in (item.get("aliases") or [])]
                if q_lower in aliases or q_norm in aliases:
                    return k
            # 3. 子串包含匹配（唯一时命中）
            candidates = [
                k for k, item in self._assets.items()
                if q_lower in k.lower()
                or q_lower in str(item.get("owner") or "").lower()
                or any(q_lower in str(a).lower() for a in (item.get("aliases") or []))
            ]
            if len(candidates) == 1:
                return candidates[0]
        return None

    def get(self, query: str) -> dict[str, Any] | None:
        with self._lock:
            k = self.find_key(query)
            return dict(self._assets[k]) if k and k in self._assets else None

    def resolve_many(self, queries: list[str] | str | None) -> tuple[list[dict[str, Any]], list[str]]:
        """批量解析资产标识，返回 (命中的资产列表, 未命中的查询词列表)。"""
        if not queries:
            return [], []
        raw_list = [queries] if isinstance(queries, str) else list(queries)
        matched: list[dict[str, Any]] = []
        missing: list[str] = []
        seen_keys: set[str] = set()
        with self._lock:
            for q in raw_list:
                q_str = str(q or "").strip()
                if not q_str:
                    continue
                item = self.get(q_str)
                if item is None:
                    missing.append(q_str)
                elif item["key"] not in seen_keys:
                    seen_keys.add(item["key"])
                    matched.append(item)
        return matched, missing

    def _persist_reference_file(self, context: Any, key: str, reference: str) -> tuple[str, str]:
        """校验参考图并将临时会话图片复制到 output/assets/character/ 永久保存。"""
        from core.tools.tools_media import _resolve_reference_image

        info, error = _resolve_reference_image(context, reference)
        if error or not info:
            return "", error or f"无法解析参考图: {reference}"

        src_real = os.path.realpath(info["path"])
        os.makedirs(self.asset_dir, exist_ok=True)
        asset_dir_real = os.path.realpath(self.asset_dir)

        try:
            in_asset_dir = os.path.commonpath([src_real, asset_dir_real]) == asset_dir_real
        except ValueError:
            in_asset_dir = False

        if in_asset_dir:
            return _to_rel_path(src_real), ""

        ext = os.path.splitext(src_real)[1].lower() or ".png"
        stem = _safe_filename_stem(key)
        dest_filename = f"{stem}_reference{ext}"
        dest_path = os.path.join(self.asset_dir, dest_filename)
        dest_real = os.path.realpath(dest_path)

        if src_real != dest_real:
            try:
                shutil.copy2(src_real, dest_path)
            except OSError as exc:
                return "", f"复制参考图到资产库失败: {exc}"

        return _to_rel_path(dest_path), ""

    def register(
        self,
        key: str,
        reference: str,
        *,
        owner: str = "",
        description: str = "",
        tags: Any = None,
        aliases: Any = None,
        context: Any = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """登记或覆盖一条艺术资产。"""
        norm_key = _normalize_key(key or owner)
        if not norm_key:
            return None, "缺少资产标识 key（或人物名 owner）"
        if not reference:
            return None, "缺少参考图路径或 [img:XXX] 索引（reference）"

        saved_ref, err = self._persist_reference_file(context, norm_key, reference)
        if err:
            return None, err

        with self._lock:
            existing = self._assets.get(norm_key) or {}
            final_owner = str(owner or existing.get("owner") or norm_key).strip()
            final_desc = str(
                description if description is not None and description != "" else (existing.get("description") or "")
            ).strip()
            final_tags = _normalize_str_list(tags) if tags is not None else list(existing.get("tags") or ["立绘"])
            if not final_tags:
                final_tags = ["立绘"]
            final_aliases = (
                _normalize_str_list(aliases) if aliases is not None else list(existing.get("aliases") or [])
            )
            if final_owner and final_owner not in final_aliases and final_owner != norm_key:
                final_aliases.append(final_owner)

            record = {
                "key": norm_key,
                "owner": final_owner,
                "description": final_desc,
                "reference": saved_ref,
                "tags": final_tags,
                "aliases": final_aliases,
                "updated_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._assets[norm_key] = record
            self._save_unlocked()
            return dict(record), ""

    def update(
        self,
        key: str,
        *,
        reference: str | None = None,
        owner: str | None = None,
        description: str | None = None,
        tags: Any = None,
        aliases: Any = None,
        context: Any = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """更新已有资产；若资产不存在且提供了 reference，则直接新建登记。"""
        target_key = self.find_key(key) or _normalize_key(key or owner or "")
        if not target_key:
            return None, "缺少要修改的资产标识 key"

        with self._lock:
            existing = self._assets.get(target_key)
            if existing is None:
                if reference:
                    return self.register(
                        target_key,
                        reference,
                        owner=owner or "",
                        description=description or "",
                        tags=tags,
                        aliases=aliases,
                        context=context,
                    )
                return None, f"未找到资产「{key}」，如需新增请同时提供 reference 参考图"

            saved_ref = existing["reference"]
            if reference:
                saved_ref, err = self._persist_reference_file(context, target_key, reference)
                if err:
                    return None, err

            final_owner = str(owner).strip() if owner is not None and str(owner).strip() else existing["owner"]
            final_desc = (
                str(description).strip()
                if description is not None and str(description).strip()
                else existing["description"]
            )
            final_tags = _normalize_str_list(tags) if tags is not None else list(existing.get("tags") or [])
            final_aliases = (
                _normalize_str_list(aliases) if aliases is not None else list(existing.get("aliases") or [])
            )
            record = {
                "key": target_key,
                "owner": final_owner,
                "description": final_desc,
                "reference": saved_ref,
                "tags": final_tags,
                "aliases": final_aliases,
                "updated_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._assets[target_key] = record
            self._save_unlocked()
            return dict(record), ""

    def delete(self, key: str) -> tuple[dict[str, Any] | None, str]:
        """删除一条已登记资产（仅移除登记索引，不误删底层图片文件）。"""
        target_key = self.find_key(key)
        if not target_key:
            return None, f"未找到要删除的资产: {key}"
        with self._lock:
            removed = self._assets.pop(target_key, None)
            self._save_unlocked()
            return (dict(removed) if removed else None), ""

    def format_asset_line(self, item: dict[str, Any]) -> str:
        tags = "/".join(item.get("tags") or [])
        tag_part = f" [{tags}]" if tags else ""
        desc = item.get("description") or "暂无外貌描述"
        return (
            f"- {item['key']}（人物: {item.get('owner') or item['key']}{tag_part}）："
            f"{desc} | reference: {item['reference']}"
        )

    def format_overview(self) -> str:
        items = self.list()
        if not items:
            return "当前已登记艺术资产：暂无（可用 art_asset action=\"register\" 登记立绘参考图）"
        lines = [f"当前已登记艺术资产（共 {len(items)} 项）："]
        for item in items:
            lines.append(self.format_asset_line(item))
        return "\n".join(lines)


art_asset_store = ArtAssetStore()
