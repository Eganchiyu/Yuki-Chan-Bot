import datetime
import json
import os
import concurrent.futures
import warnings

import chromadb

with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    import jieba.analyse
from sentence_transformers import SentenceTransformer

from config import cfg
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
        self.model = SentenceTransformer(cfg.EMBED_MODEL)
        self.client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="diaries",
            metadata={"hnsw:space": "cosine"}  # 核心：使用余弦相似度进行向量匹配
        )
        self.blacklist_path = "blacklist.txt"
        self.name_blacklist = self._load_blacklist()

        logger.info(f"[RAG] 已加载 {len(self.name_blacklist)} 个屏蔽词")
        logger.info("[RAG] 记忆库初始化完成")

    def _load_blacklist(self):
        """从文件加载屏蔽词，支持自动去重和过滤空行"""
        if not os.path.exists(self.blacklist_path):
            default_list = [cfg.ROBOT_NAME, '主人', '哥哥', cfg.MASTER_NAME, '人家']
            with open(self.blacklist_path, "w", encoding="utf-8") as f:
                f.write("\n".join(default_list))
            return default_list

        with open(self.blacklist_path, "r", encoding="utf-8") as f:
            words = [line.strip().lower() for line in f
                     if line.strip() and not line.startswith("#")]
        return list(set(words))

    def reload_blacklist(self):
        self.name_blacklist = self._load_blacklist()
        logger.info("[RAG] 屏蔽词库已完成热重载")

    @staticmethod
    def _build_memory_metadata(
            memory_type="summary",
            chat_id=None,
            people=None,
            emotion=None,
            subject=None,
            status="active",
            confidence=1.0,
            importance=3,
            supersedes=None,
            source_ids=None,
            extra_metadata=None,
    ):
        now = datetime.datetime.now().timestamp()
        metadata = {
            "type": memory_type,
            "status": status,
            "confidence": float(confidence),
            "importance": int(importance),
            "timestamp": now,
            "created_at": now,
            "updated_at": now,
            "access_count": 0,
        }

        if chat_id is not None:
            metadata["chat_id"] = str(chat_id)
        if people:
            metadata["people"] = json.dumps(people, ensure_ascii=False)
        if emotion:
            metadata["emotion"] = emotion
        if subject:
            metadata["subject"] = str(subject)
        if supersedes:
            metadata["supersedes"] = str(supersedes)
        if source_ids:
            metadata["source_ids"] = json.dumps(source_ids, ensure_ascii=False)

        if extra_metadata:
            for key, value in extra_metadata.items():
                if value is None:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    metadata[key] = value
                else:
                    metadata[key] = json.dumps(value, ensure_ascii=False)
        return metadata

    def save_memory(
            self,
            content,
            memory_type="summary",
            chat_id=None,
            people=None,
            emotion=None,
            subject=None,
            status="active",
            confidence=1.0,
            importance=3,
            supersedes=None,
            source_ids=None,
            extra_metadata=None,
    ):
        if not content or not content.strip():
            return None

        where_filter = {"timestamp": {"$gte": datetime.datetime.now().timestamp() - 86400}}
        if chat_id is not None:
            where_filter["chat_id"] = str(chat_id)

        try:
            existing = self.collection.get(where=where_filter)
            if existing and 'documents' in existing and existing['documents']:
                if content in existing['documents']:
                    logger.info("[RAG] 检测到24小时内重复内容，跳过保存")
                    return None
        except Exception as e:
            logger.warning(f"[RAG] 去重检查跳过: {e}")

        embedding = self.model.encode(content).tolist()
        doc_id = f"mem_{memory_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content) % 10000:04d}"
        metadata = self._build_memory_metadata(
            memory_type=memory_type,
            chat_id=chat_id,
            people=people,
            emotion=emotion,
            subject=subject,
            status=status,
            confidence=confidence,
            importance=importance,
            supersedes=supersedes,
            source_ids=source_ids,
            extra_metadata=extra_metadata,
        )

        self.collection.add(
            documents=[content],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[doc_id]
        )
        logger.info(f"[RAG] 记忆已存入 type={memory_type} chat_id={chat_id}: {content[:50]}...")
        return doc_id

    def save_diary(self, content, chat_id=None, people=None, emotion=None):
        return self.save_memory(
            content=content,
            memory_type="summary",
            chat_id=chat_id,
            people=people,
            emotion=emotion,
            importance=3,
        )

    def search_memory(self, query, chat_id=None, top_k=cfg.RETRIEVAL_TOP_K, threshold=1.0):
        if not query.strip():
            return []

        query_emb = self.model.encode(query).tolist()
        where_filter = {}
        if chat_id is not None:
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
            filtered = []
            seen = set()
            for doc, dist in zip(docs, distances):
                if dist <= threshold and doc not in seen:
                    filtered.append(doc)
                    seen.add(doc)
            return filtered
        return []

    def search_diaries(self, query_text, chat_id=None, n_results=8, top_k_keywords=5, speaker_names=None):
        """
        全局日记检索：取消按群聊硬过滤，对当前群聊和当前发言者做重排加权。
        """
        logger.debug(f"\n[RAG] 开启优化版真并行双池检索流: '{query_text}'")

        total_count = self.collection.count()
        if total_count == 0:
            logger.debug("[RAG] 数据库为空，取消检索")
            return []

        cid_str = str(chat_id) if chat_id else None
        filter_cond = None
        speaker_names = [str(name).strip() for name in (speaker_names or []) if str(name).strip()]

        # 1. 提取核心锚点词
        raw_keywords = jieba.analyse.extract_tags(query_text, topK=top_k_keywords, withWeight=True)
        keywords_with_weight = [
            (kw, w) for kw, w in raw_keywords
            if kw.lower() not in self.name_blacklist
        ]
        keywords = [kw for kw, _ in keywords_with_weight]
        logger.debug(f"[RAG] 核心锚点词: {keywords}")

        # 2. 定义并行查询任务
        def fetch_vector_pool():
            query_embedding = self.model.encode(query_text).tolist()
            # 宽进：语义池多抓取一些做基准，确保长线情感匹配
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": max(30, n_results * 6),
            }
            if filter_cond:
                query_kwargs["where"] = filter_cond
            return self.collection.query(**query_kwargs)

        def fetch_keyword_pool():
            if not keywords:
                return {'documents': [], 'metadatas': [], 'ids': []}

            # 【核心优化】：利用数据库底层的 $contains 操作符，彻底告别全表扫内存
            contains_filters = [{"$contains": kw} for kw in keywords]
            doc_filter = {"$or": contains_filters} if len(contains_filters) > 1 else contains_filters[0]

            get_kwargs = {"where_document": doc_filter}
            if filter_cond:
                get_kwargs["where"] = filter_cond
            return self.collection.get(**get_kwargs)

        # 3. 线程池触发真正的并发请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_vector = executor.submit(fetch_vector_pool)
            future_keyword = executor.submit(fetch_keyword_pool)

            vector_results = future_vector.result()
            keyword_results = future_keyword.result()

        # 4. 合并与重排逻辑
        combined_map = {}  # doc_id -> item_data

        # --- 处理语义池 ---
        max_v_score = 0.0
        if vector_results and vector_results['documents'] and vector_results['documents'][0]:
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

        # --- 处理关键词池 ---
        # 保留原有的保底分策略，但现在参与打捞的数据是经过 Chroma 引擎极速过滤的
        initial_kw_score = max_v_score * 0.85
        kw_found_count = 0
        if keyword_results and keyword_results['documents']:
            for i, content in enumerate(keyword_results['documents']):
                doc_id = keyword_results['ids'][i]
                if doc_id not in combined_map:
                    combined_map[doc_id] = {
                        "doc": content,
                        "meta": keyword_results['metadatas'][i],
                        "base_score": initial_kw_score,
                        "source": f"关键词精准打捞(保底:{initial_kw_score:.2f})"
                    }
                    kw_found_count += 1

        # 5. 精准算分与加权补偿
        final_results = []
        for item in combined_map.values():
            scored_item = self._calculate_final_item(
                item["doc"],
                item["meta"],
                item["base_score"],
                keywords_with_weight,
                chat_id=cid_str,
                speaker_names=speaker_names,
            )
            if scored_item:
                scored_item["debug"] = f"[{item['source']}] {scored_item['debug']}"
                final_results.append(scored_item)

        # 6. 截断与严出
        final_results.sort(key=lambda x: x['score'], reverse=True)
        final_output = final_results[:n_results]

        logger.debug(
            f"[RAG] 融合完成: 向量池 {len(combined_map) - kw_found_count}条，关键词池 {kw_found_count}条。最终输出 {len(final_output)} 条")
        for i, res in enumerate(final_output):
            logger.debug(f"   #{i + 1} 分数:{res['score']:.4f} | {res['debug']}")

        return final_output

    @staticmethod
    def _calculate_final_item(
        doc,
        meta,
        base_score,
        keywords_with_weight,
        chat_id=None,
        speaker_names=None,
    ):
        keyword_boost = 0.0
        matched_words = []
        for kw, weight in keywords_with_weight:
            if kw in doc:
                # 原汁原味的权重补偿，发挥极佳的“命中记忆”效果
                keyword_boost += weight * 0.5
                matched_words.append(kw)

        current_chat_boost = 0.0
        if chat_id and str(meta.get("chat_id", "")) == str(chat_id):
            current_chat_boost = 10.0

        speaker_boost = 0.0
        speaker_matches = []
        for name in speaker_names or []:
            if name and name in doc:
                speaker_boost += 0.15
                speaker_matches.append(name)
        speaker_boost = min(speaker_boost, 0.45)

        final_score = base_score + keyword_boost + current_chat_boost + speaker_boost
        return {
            "content": doc,
            "metadata": meta,
            "score": final_score,
            "debug": (
                f"基准:{base_score:.2f} + 关键词补偿:{keyword_boost:.2f} "
                f"+ 当前群聊:{current_chat_boost:.2f} + 发言者:{speaker_boost:.2f} "
                f"(匹配:{matched_words}, 发言者匹配:{speaker_matches})"
            )
        }

    def clean_duplicate_diaries(self, dry_run=False):
        logger.info("[RAG] 正在扫描全局重复记录...")
        all_data = self.collection.get()

        if not all_data or not all_data['documents']:
            return None

        seen = {}
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
            for i in range(0, len(to_delete), 100):
                self.collection.delete(ids=to_delete[i:i + 100])
            logger.info(f"[RAG] 清理完成，已删除 {len(to_delete)} 条重复记录")
            return None
        else:
            logger.info("[RAG] 未发现重复记录")
            return None