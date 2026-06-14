from typing import Any, Dict, List, Optional

from modules.yuki_memory.store import YukiMemoryStore
from utils.logger import get_logger

logger = get_logger("yuki_memory_retriever")


class YukiMemoryRetriever:
    """主流程用的 Yuki-Memory 结构化上下文检索适配层。"""

    def __init__(self, store: Optional[YukiMemoryStore] = None, enabled: bool = True):
        self.store = store
        self.enabled = enabled

    def retrieve(self, query: str, chat_id=None, top_k: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """检索结构化记忆，失败时返回空上下文，交给旧 RAG 回退。"""
        if not self.enabled or not query or not str(query).strip():
            return self._empty_context()

        try:
            if self.store is None:
                self.store = YukiMemoryStore()

            limits = {
                "profiles": 2,
                "facts": 6,
                "summaries": 4,
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
        seen = set()
        result = []
        for item in items or []:
            metadata = item.get("metadata", {}) or {}
            key = metadata.get("candidate_id") or metadata.get("source_diary_id") or item.get("content")
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
