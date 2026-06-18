import re
from typing import Any, Dict, List, Optional

from config import cfg
from modules.yuki_memory.store import YukiMemoryStore
from utils.logger import get_logger

logger = get_logger("yuki_memory_retriever")


class YukiMemoryRetriever:
    """主流程用的 Yuki-Memory 结构化上下文检索适配层。"""

    def __init__(self, store: Optional[YukiMemoryStore] = None):
        self.store = store
        self._cfg = cfg.structured_memory

    def retrieve(self, query: str, chat_id=None, top_k: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """检索结构化记忆，失败时返回空上下文，交给旧 RAG 回退。"""
        if not self._cfg.enabled or not query or not str(query).strip():
            return self._empty_context()

        try:
            if self.store is None:
                self.store = YukiMemoryStore()

            limits = {
                "profiles": self._cfg.max_profiles,
                "facts": self._cfg.max_facts,
                "summaries": self._cfg.max_summaries,
            }
            if top_k:
                limits.update(top_k)

            profiles = self.store.search_profiles(query, chat_id=chat_id, top_k=limits["profiles"])
            facts = self.store.search_facts(query, chat_id=chat_id, top_k=limits["facts"])
            summaries = self.store.search_summaries(query, chat_id=chat_id, top_k=limits["summaries"])

            context = {
                "enabled": True,
                "profiles": self._dedupe(profiles),
                "facts": self._dedupe(facts),
                "summaries": self._dedupe(summaries),
                "errors": [],
            }
            logger.info(
                "[YukiMemory] 结构化召回完成 chat_id=%s profile=%s fact=%s summary=%s",
                chat_id,
                len(context["profiles"]),
                len(context["facts"]),
                len(context["summaries"]),
            )
            return context
        except Exception as exc:
            logger.warning(f"[YukiMemory] 结构化召回失败，回退旧 RAG: {exc}")
            context = self._empty_context()
            context["errors"].append(str(exc))
            return context

    @staticmethod
    def _empty_context():
        return {
            "enabled": False,
            "profiles": [],
            "facts": [],
            "summaries": [],
            "errors": [],
        }

    @staticmethod
    def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 (type, subject) 去重合并，每个分组只保留最优条目。"""
        groups = {}
        for item in items or []:
            metadata = item.get("metadata", {}) or {}
            memory_type = metadata.get("type") or metadata.get("candidate_type") or "unknown"
            subject = re.sub(r"\s+", "", str(metadata.get("subject", "")).strip().lower())
            content = str(item.get("content", "")).strip()
            if not content:
                continue

            group_key = (memory_type, subject)
            existing = groups.get(group_key)
            if existing is None:
                groups[group_key] = item
                continue

            existing_meta = existing.get("metadata", {}) or {}
            existing_imp = int(existing_meta.get("importance", 1) or 1)
            existing_conf = float(existing_meta.get("confidence", 0) or 0)
            existing_score = float(existing.get("score", 0) or 0)
            existing_len = len(str(existing.get("content", "")))

            new_imp = int(metadata.get("importance", 1) or 1)
            new_conf = float(metadata.get("confidence", 0) or 0)
            new_score = float(item.get("score", 0) or 0)
            new_len = len(content)

            new_is_better = (
                (new_imp, new_conf, new_score, new_len)
                > (existing_imp, existing_conf, existing_score, existing_len)
            )
            if new_is_better:
                groups[group_key] = item

        return list(groups.values())
