import datetime

import chromadb
from sentence_transformers import SentenceTransformer

from config import cfg
from modules.yuki_memory.models import MemoryRecord
from utils.logger import get_logger

logger = get_logger("yuki_memory")


class YukiMemoryStore:
    """Yuki-Memory 向量存储。"""

    def __init__(self, collection_name="yuki_memory", db_path=None, model=None, client=None):
        self.collection_name = collection_name
        self.model = model or SentenceTransformer(cfg.EMBED_MODEL)
        self.client = client or chromadb.PersistentClient(path=db_path or cfg.VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"[YukiMemory] 已初始化 collection={collection_name}")

    def save(self, record: MemoryRecord) -> str:
        """保存一条标准记忆。"""
        embedding = self.model.encode(record.content).tolist()
        self.collection.add(
            documents=[record.content],
            embeddings=[embedding],
            metadatas=[record.to_metadata()],
            ids=[record.memory_id],
        )
        logger.info(f"[YukiMemory] 记忆已保存 type={record.type} chat_id={record.chat_id}")
        return record.memory_id

    def save_summary(
        self,
        content,
        chat_id=None,
        subject=None,
        source="runtime_summary",
        source_ids=None,
        memory_id=None,
        created_at=None,
        importance=3,
    ) -> str:
        """保存 summary 记忆。"""
        now = datetime.datetime.now().timestamp()
        record = MemoryRecord(
            memory_id=memory_id or self._build_memory_id("summary", content),
            type="summary",
            content=content,
            chat_id=chat_id,
            subject=subject,
            source=source,
            source_ids=source_ids or [],
            created_at=created_at or now,
            updated_at=now,
            importance=importance,
        )
        return self.save(record)

    def search(self, query, chat_id=None, memory_types=None, top_k=8, status="active"):
        """搜索标准记忆，返回兼容旧 search_diaries 的结构。"""
        if not query or not query.strip():
            return []

        where_filter = self._build_where_filter(chat_id, memory_types, status)
        query_embedding = self.model.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_query_results(results)

    def search_summaries(self, query, chat_id=None, top_k=8):
        """搜索 summary 记忆。"""
        return self.search(query, chat_id=chat_id, memory_types=["summary"], top_k=top_k)

    def search_facts(self, query, chat_id=None, top_k=8):
        """搜索事实与偏好类记忆。"""
        return self.search(
            query,
            chat_id=chat_id,
            memory_types=["fact", "preference", "relationship", "todo", "event"],
            top_k=top_k,
        )

    def search_profiles(self, query, chat_id=None, top_k=8):
        """搜索画像记忆。"""
        return self.search(query, chat_id=chat_id, memory_types=["profile"], top_k=top_k)

    def get_latest_snapshot(self, chat_id=None, snapshot_type=None):
        """获取最新 snapshot。"""
        where_filter = self._build_where_filter(chat_id, ["snapshot"], "active")
        if snapshot_type:
            where_filter = self._append_and_filter(where_filter, {"snapshot_type": snapshot_type})

        results = self.collection.get(where=where_filter, include=["documents", "metadatas"])
        records = []
        for memory_id, content, metadata in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
        ):
            records.append(MemoryRecord.from_chroma(memory_id, content, metadata))
        if not records:
            return None
        return max(records, key=lambda record: record.updated_at or 0)

    def mark_accessed(self, memory_ids):
        """更新访问计数。"""
        now = datetime.datetime.now().timestamp()
        for memory_id in memory_ids:
            existing = self.collection.get(ids=[memory_id], include=["metadatas"])
            metadatas = existing.get("metadatas", [])
            if not metadatas:
                continue
            metadata = dict(metadatas[0] or {})
            metadata["access_count"] = int(metadata.get("access_count", 0)) + 1
            metadata["last_accessed"] = now
            self.collection.update(ids=[memory_id], metadatas=[metadata])

    def supersede(self, old_id, new_record: MemoryRecord) -> str:
        """用新记忆替代旧记忆。"""
        new_record.supersedes = old_id
        new_id = self.save(new_record)

        existing = self.collection.get(ids=[old_id], include=["metadatas"])
        metadatas = existing.get("metadatas", [])
        if metadatas:
            metadata = dict(metadatas[0] or {})
            metadata["status"] = "superseded"
            metadata["updated_at"] = datetime.datetime.now().timestamp()
            self.collection.update(ids=[old_id], metadatas=[metadata])
        return new_id

    @staticmethod
    def _build_memory_id(memory_type, content):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"ymem_{memory_type}_{timestamp}_{hash(content) % 10000:04d}"

    @staticmethod
    def _append_and_filter(current_filter, new_filter):
        if not current_filter:
            return new_filter
        if "$and" in current_filter:
            return {"$and": current_filter["$and"] + [new_filter]}
        return {"$and": [current_filter, new_filter]}

    def _build_where_filter(self, chat_id=None, memory_types=None, status="active"):
        filters = []
        if chat_id is not None:
            filters.append({"chat_id": str(chat_id)})
        if memory_types:
            types = [str(memory_type) for memory_type in memory_types]
            filters.append({"type": types[0]} if len(types) == 1 else {"type": {"$in": types}})
        if status:
            filters.append({"status": status})

        if not filters:
            return None
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}

    @staticmethod
    def _format_query_results(results):
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]

        formatted = []
        for index, content in enumerate(documents):
            distance = distances[index] if index < len(distances) else 1.0
            score = 1.0 - distance
            metadata = metadatas[index] if index < len(metadatas) else {}
            memory_id = ids[index] if index < len(ids) else ""
            formatted.append({
                "content": content,
                "metadata": metadata,
                "score": score,
                "debug": f"[YukiMemory] id={memory_id} score={score:.4f}",
            })
        return formatted
