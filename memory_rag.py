# memory_rag.py
import os
# 必须在 import sentence_transformers 之前设置
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
import chromadb
from sentence_transformers import SentenceTransformer
import datetime
import json
from config import VECTOR_DB_PATH, EMBED_MODEL, RETRIEVAL_TOP_K


class MemoryRAG:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        print("[RAG] 初始化记忆库...")
        self.model = SentenceTransformer(EMBED_MODEL)
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="diaries",
            metadata={"hnsw:space": "cosine"}
        )
        print("[RAG] 记忆库初始化完成")

    def save_diary(self, content, chat_id=None, people=None, emotion=None):
        """保存日记到向量库，chat_id用于群聊隔离"""
        embedding = self.model.encode(content).tolist()
        doc_id = f"diary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content) % 10000:04d}"
        metadata = {"timestamp": datetime.datetime.now().timestamp()}
        if chat_id is not None:
            metadata["chat_id"] = str(chat_id)
        if people:
            metadata["people"] = json.dumps(people, ensure_ascii=False)
        if emotion:
            metadata["emotion"] = emotion
        self.collection.add(
            documents=[content],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[doc_id]
        )
        print(f"[RAG] 日记已存入 (chat_id={chat_id}): {content[:50]}...")

    def search_memory(self, query, chat_id=None, top_k=RETRIEVAL_TOP_K, threshold=1.0):
        if not query.strip():
            return []
        query_emb = self.model.encode(query).tolist()
        where_filter = {}
        if chat_id is not None:
            # 这里我们允许查询时同时检索特定 chat_id 和 manual_record 的记忆，确保手动录入的记忆也能被检索到
            where_filter["chat_id"] = {"$in": [str(chat_id), "manual_record"]}
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            where=where_filter,
            include=["documents", "distances"]
        )
        if results['documents'] and results['documents'][0]:
            docs = results['documents'][0]
            distances = results['distances'][0]
            # 过滤距离大于 threshold 的结果
            filtered = [doc for doc, dist in zip(docs, distances) if dist <= threshold]
            return filtered
        return []

