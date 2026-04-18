import datetime
import json
import os

import chromadb
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    import jieba.analyse
from sentence_transformers import SentenceTransformer

from config import EMBED_MODEL, VECTOR_DB_PATH, RETRIEVAL_TOP_K, ROBOT_NAME
from utils.logger import get_logger

logger = get_logger("rag")


class MemoryRAG:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        logger.info("[RAG] 初始化记忆库...")
        self.model = SentenceTransformer(EMBED_MODEL)
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="diaries",
            metadata={"hnsw:space": "cosine"} # 使用余弦相似度进行向量匹配
        )
        self.blacklist_path = "blacklist.txt"
        self.name_blacklist = self._load_blacklist()

        logger.info(f"[RAG] 已加载 {len(self.name_blacklist)} 个屏蔽词")
        logger.info("[RAG] 记忆库初始化完成")

    def _load_blacklist(self):
        """从文件加载屏蔽词，支持自动去重和过滤空行"""
        if not os.path.exists(self.blacklist_path):
            # 如果文件不存在，创建一个默认的
            default_list = [ROBOT_NAME, '主人', '哥哥', '池宇健', '人家']
            with open(self.blacklist_path, "w", encoding="utf-8") as f:
                f.write("\n".join(default_list))
            return default_list

        with open(self.blacklist_path, "r", encoding="utf-8") as f:
            # 读取每一行，去除空格，忽略以 # 开头的注释行
            words = [line.strip().lower() for line in f
                     if line.strip() and not line.startswith("#")]
        return list(set(words)) # 去重

    def reload_blacklist(self):
        """提供一个热重载接口"""
        self.name_blacklist = self._load_blacklist()
        logger.info("[RAG] 屏蔽词库已完成热重载")

    def save_diary(self, content, chat_id=None, people=None, emotion=None):
        """保存日记到向量库，包含自动去重逻辑"""

        # 1. 24小时内内容级去重检查
        where_filter = {}
        if chat_id is not None:
            where_filter["chat_id"] = str(chat_id)

        # 检查最近24小时内是否已有完全相同的内容
        time_threshold = datetime.datetime.now().timestamp() - 86400
        where_filter["timestamp"] = {"$gte": time_threshold}

        try:
            existing = self.collection.get(where=where_filter)
            if existing and 'documents' in existing and existing['documents']:
                if content in existing['documents']:
                    logger.info("[RAG] 检测到24小时内重复内容，跳过保存")
                    return
        except Exception as e:
            logger.warning(f"[RAG] 去重检查跳过: {e}")

        # 2. 正常保存逻辑
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
        logger.info(f"[RAG] 日记已存入 (chat_id={chat_id}): {content[:50]}...")

    def search_memory(self, query, chat_id=None, top_k=RETRIEVAL_TOP_K, threshold=1.0):
        """混合检索：支持当前群聊 + 手动录入的记忆"""
        if not query.strip():
            return []

        query_emb = self.model.encode(query).tolist()
        where_filter = {}
        if chat_id is not None:
            # 融合检索逻辑：检索当前 chat_id 或全局 manual_record
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
            # 根据相似度阈值过滤并进行结果集去重
            filtered = []
            seen = set()
            for doc, dist in zip(docs, distances):
                if dist <= threshold and doc not in seen:
                    filtered.append(doc)
                    seen.add(doc)
            return filtered
        return []

    def search_diaries(self, query_text, chat_id=None, n_results=12, top_k = 5):
        """
        并行双池检索：语义池与关键词池并行提取，算法全透明调试版
        """
        logger.debug(f"\n[RAG-Debug] 🔍 开启并行检索流: '{query_text}'")

        total_count = self.collection.count()
        if total_count == 0:
            logger.debug("[RAG-Debug] ❌ 数据库为空，取消检索")
            return []

        # 1. 准备：类型转换与关键词提取
        cid_str = str(chat_id) if chat_id else None
        filter_cond = {"chat_id": {"$in": [cid_str, "manual_record"]}} if cid_str else None

        raw_keywords = jieba.analyse.extract_tags(query_text, topK=top_k, withWeight=True)

        # 直接调用类属性中的黑名单
        keywords_with_weight = [
            (kw, w) for kw, w in raw_keywords
            if kw.lower() not in self.name_blacklist
        ]
        logger.debug(f"[RAG-Debug] 🎯 核心锚点词: {keywords_with_weight}")

        # 2. 【并行池 A】向量语义池
        logger.debug(f"[RAG-Debug] 🌊 正在提取语义池 (Top {n_results})...")
        query_embedding = self.model.encode(query_text).tolist()
        vector_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_cond
        )

        # 3. 【并行池 B】关键词扫描池 (覆盖更广)
        # 取较大范围以确保那些向量距离远但含关键词的日记能被“打捞”
        logger.debug(f"[RAG-Debug] 🎣 正在提取关键词扫描池...")
        all_local_docs = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(100, total_count),
            where=filter_cond
        )

        # 4. 合并与重置逻辑
        combined_map = {} # {doc_id: item_data}

        # 处理语义池
        max_v_score = 0.0
        if vector_results['documents'] and vector_results['documents'][0]:
            # 记录最高向量分作为基准
            max_v_score = 1.0 - vector_results['distances'][0][0]
            for i in range(len(vector_results['documents'][0])):
                doc_id = vector_results['ids'][0][i]
                score = 1.0 - vector_results['distances'][0][i]
                combined_map[doc_id] = {
                    "doc": vector_results['documents'][0][i],
                    "meta": vector_results['metadatas'][0][i],
                    "base_score": score,
                    "source": "语义池"
                }

        # 处理关键词池 (保底分策略)
        initial_kw_score = max_v_score * 0.75
        kw_found_count = 0
        if all_local_docs['documents'] and all_local_docs['documents'][0]:
            for i in range(len(all_local_docs['documents'][0])):
                doc_id = all_local_docs['ids'][0][i]
                content = all_local_docs['documents'][0][i]

                # 检查是否包含关键词
                matched_in_doc = [kw for kw, _ in keywords_with_weight if kw in content]
                if matched_in_doc:
                    if doc_id not in combined_map:
                        combined_map[doc_id] = {
                            "doc": content,
                            "meta": all_local_docs['metadatas'][0][i],
                            "base_score": initial_kw_score,
                            "source": f"关键词池(保底:{initial_kw_score:.2f})"
                        }
                        kw_found_count += 1
        logger.debug(f"[RAG-Debug] ⚖️ 池合并完成: 语义池注入 {len(combined_map)-kw_found_count} 条，关键词池打捞 {kw_found_count} 条")

        # 5. 二次加权计算
        final_results = []
        for item in combined_map.values():
            # 这里的 _calculate_final_item 需要接收 base_score
            scored_item = self._calculate_final_item(
                item["doc"], item["meta"], item["base_score"], keywords_with_weight
            )
            if scored_item:
                # 把来源信息塞进 debug 方便观察
                scored_item["debug"] = f"[{item['source']}] {scored_item['debug']}"
                final_results.append(scored_item)

        # 6. 排序与截断
        final_results.sort(key=lambda x: x['score'], reverse=True)

        logger.debug(f"[RAG-Debug] 📊 排序结果 (Top 3):")
        for i, res in enumerate(final_results[:3]):
            logger.debug(f"   #{i+1} 分数:{res['score']:.4f} | {res['debug']}")

        return final_results[:12]


    @staticmethod
    def _calculate_final_item(doc, meta, base_score, keywords_with_weight):
        keyword_boost = 0.0
        matched_words = []
        for kw, weight in keywords_with_weight:
            if kw in doc:
                # 权重补偿
                keyword_boost += weight * 0.15
                matched_words.append(kw)

        final_score = base_score + keyword_boost
        return {
            "content": doc,
            "metadata": meta,
            "score": final_score,
            "debug": f"基准:{base_score:.2f} + 补偿:{keyword_boost:.2f} (匹配:{matched_words})"
        }

    def clean_duplicate_diaries(self, dry_run=False):
        """物理清理数据库中所有的重复项（保留最新的一条）"""
        logger.info("[RAG] 正在扫描全局重复记录...")
        all_data = self.collection.get()

        if not all_data or not all_data['documents']:
            return None

        seen = {} # (content, chat_id) -> (id, timestamp)
        to_delete = []

        for doc, meta, id in zip(all_data['documents'], all_data['metadatas'], all_data['ids']):
            key = (doc, meta.get('chat_id', 'None'))
            timestamp = meta.get('timestamp', 0)

            if key in seen:
                old_id, old_ts = seen[key]
                if timestamp > old_ts:
                    to_delete.append(old_id)
                    seen[key] = (id, timestamp)
                else:
                    to_delete.append(id)
            else:
                seen[key] = (id, timestamp)

        if dry_run:
            logger.info(f"[RAG] 预览：发现 {len(to_delete)} 条重复记录")
            return to_delete

        if to_delete:
            # 分批删除防止内存溢出
            for i in range(0, len(to_delete), 100):
                self.collection.delete(ids=to_delete[i:i+100])
            logger.info(f"[RAG] 清理完成，已删除 {len(to_delete)} 条重复记录")
            return None
        else:
            logger.info("[RAG] 未发现重复记录")
            return None
