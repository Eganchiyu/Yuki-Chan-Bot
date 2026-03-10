# memory_rag.py
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
        
        # 初始化时自动清理重复（可选）
        # self.clean_duplicate_diaries()

    def save_diary(self, content, chat_id=None, people=None, emotion=None):
        """保存日记到向量库，自动去重"""
        
        # 构建查询条件
        where_filter = {}
        if chat_id is not None:
            where_filter["chat_id"] = str(chat_id)
        
        # 检查最近24小时内是否已有相同内容
        time_threshold = datetime.datetime.now().timestamp() - 86400  # 24小时前
        where_filter["timestamp"] = {"$gte": time_threshold}
        
        try:
            existing = self.collection.get(
                where=where_filter
            )
            
            # 检查是否内容重复
            if existing and 'documents' in existing and existing['documents']:
                for doc in existing['documents']:
                    if doc == content:  # 内容相同
                        print(f"[RAG] 检测到24小时内重复日记，跳过保存")
                        return
        except Exception as e:
            print(f"[RAG] 去重检查失败: {e}，继续保存...")
        
        # 正常保存逻辑
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
            where_filter["chat_id"] = str(chat_id)
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
            
            # 再次去重（防止数据库里已有重复）
            seen = set()
            unique_filtered = []
            for doc in filtered:
                if doc not in seen:
                    seen.add(doc)
                    unique_filtered.append(doc)
            
            if len(filtered) != len(unique_filtered):
                print(f"[RAG] 检索到 {len(filtered)} 条，去重后 {len(unique_filtered)} 条")
            
            return unique_filtered
        return []

    def clean_duplicate_diaries(self, dry_run=False):
        """清理重复日记
        dry_run: True 只预览不删除
        """
        print("[RAG] 开始清理重复日记...")
        
        # 获取所有数据
        all_data = self.collection.get()
        
        if not all_data or 'documents' not in all_data or not all_data['documents']:
            print("[RAG] 数据库为空")
            return
        
        seen = {}  # key -> id
        to_delete = []
        
        for i, (doc, meta, id) in enumerate(zip(
            all_data['documents'], 
            all_data['metadatas'], 
            all_data['ids']
        )):
            chat_id = meta.get('chat_id', 'None')
            timestamp = meta.get('timestamp', 0)
            
            # 用内容和chat_id作为key
            key = (doc, chat_id)
            
            if key in seen:
                # 保留时间戳更新的，删除旧的
                old_id, old_timestamp = seen[key]
                if timestamp > old_timestamp:
                    # 当前这条更新，删除旧的
                    to_delete.append(old_id)
                    seen[key] = (id, timestamp)
                else:
                    # 当前这条更旧，删除当前
                    to_delete.append(id)
            else:
                seen[key] = (id, timestamp)
        
        if dry_run:
            print(f"[RAG] 预览：发现 {len(to_delete)} 条重复日记")
            return to_delete
        
        if to_delete:
            print(f"[RAG] 发现 {len(to_delete)} 条重复日记，正在清理...")
            # 分批删除，避免一次性删除太多
            batch_size = 100
            for i in range(0, len(to_delete), batch_size):
                batch = to_delete[i:i+batch_size]
                self.collection.delete(ids=batch)
                print(f"[RAG] 已删除第 {i//batch_size + 1} 批，{len(batch)} 条")
            print(f"[RAG] 清理完成，共删除 {len(to_delete)} 条重复日记")
        else:
            print("[RAG] 没有发现重复日记")

# 如果直接运行此文件，执行清理
if __name__ == "__main__":
    print("="*50)
    print("记忆库维护工具")
    print("="*50)
    print("1. 清理重复日记")
    print("2. 预览重复日记")
    print("3. 退出")
    
    choice = input("请选择 (1-3): ").strip()
    
    rag = MemoryRAG()  # 初始化
    
    if choice == "1":
        rag.clean_duplicate_diaries(dry_run=False)
    elif choice == "2":
        to_delete = rag.clean_duplicate_diaries(dry_run=True)
        if to_delete:
            print(f"\n预览完成，共 {len(to_delete)} 条重复日记")
            confirm = input("是否确认删除？(y/n): ").strip().lower()
            if confirm == 'y':
                rag.clean_duplicate_diaries(dry_run=False)
    else:
        print("退出")