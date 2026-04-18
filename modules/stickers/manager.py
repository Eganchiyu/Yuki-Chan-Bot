# modules/sticker/manager.py
import asyncio
import base64
import json
import time
import os
from typing import List, Dict, Optional, Any
import chromadb
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    import jieba
    import jieba.analyse
from sentence_transformers import SentenceTransformer

from config import EMBED_MODEL, VECTOR_DB_PATH, ROBOT_NAME
from modules.vision.processor import MemeProcessor
from network.api_request import ApiCall
from utils.logger import get_logger

logger = get_logger("stickers")


# ================== Prompt（保持不变） ==================
STICKER_ANALYSIS_PROMPT = """
你是一个专业的QQ表情包语义专家。请严格按照JSON格式分析下面这张表情包，只输出合法JSON，不要任何额外文字。

{
  "description": "一句话核心描述（15-25字，包含动作、表情、意图）",
  "emotion": "主要情绪（必须从以下选择一个）：撒娇、吐槽、无语、生气、开心、委屈、调情、震惊、摸鱼、高冷、抽象、群内梗、中性",
  "category": "大类（必须从以下选择一个）：撒娇可爱系、抽象吐槽系、震惊无语系、愤怒生气系、开心庆祝系、委屈哭哭系、调情绿茶系、高冷装逼系、日常摸鱼系、群内梗专用",
  "usage_scenarios": ["适合场景1", "适合场景2"],
  "tags": ["标签1", "标签2", "标签3"]
}

请直接看图进行分析。
"""

EMOTION_JUDGE_PROMPT = """
你现在是Yuki的情绪分析器。请对下面这句话判断**主要情绪**，只输出一个词（必须严格从以下列表选择）：
撒娇、吐槽、无语、生气、开心、委屈、调情、震惊、摸鱼、高冷、抽象、群内梗、中性

Yuki的回复内容：{yuki_message}
"""


class StickerManager:
    def __init__(self, llm: ApiCall):
        self.llm = llm
        self.vl_processor = MemeProcessor()                    # 已支持本地文件
        self.model = SentenceTransformer(EMBED_MODEL)

        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="stickers",
            metadata={"hnsw:space": "cosine"}
        )

        jieba.load_userdict("blacklist.txt") if os.path.exists("blacklist.txt") else None
        logger.info(f"[StickerManager] 初始化完成 | 当前表情包数量: {self.collection.count()}")

    # ====================== 工具函数 ======================


    async def _vl_understand_and_localize(self, image_ref: str) -> tuple[str, str]:
        """工具：视觉理解并本地化"""
        try:
            # --- 就是这里：在读取文件内容之前进行路径清洗 ---
            if image_ref.startswith("file:///"):
                path = image_ref[8:]
            elif image_ref.startswith("file://"):
                path = image_ref[7:]
            else:
                path = image_ref

            # Windows 路径修正（解决类似 /D:/... 的问题）
            if os.name == 'nt' and path.startswith('/') and len(path) > 2 and path[2] == ':':
                path = path[1:]

            # 转换为绝对路径
            path = os.path.abspath(path)

            # 读取二进制内容
            with open(path, "rb") as f:
                content = f.read()

            # --- 路径处理完毕，后续逻辑 ---
            # 1. 调用 processor 获取描述 (保持原签名返回 str)
            description = await self.vl_processor.understand_from_url(image_ref, self.llm)

            # 2. 调用修改后的 processor 保存逻辑获取唯一本地路径
            # 因为 _save_to_local_sticker_library 现在有了 exists 判断，这里不会重复写文件
            final_local_path = self.vl_processor._save_to_local_sticker_library(content, path)

            return description, final_local_path

        except Exception as e:
            logger.error(f"[StickerManager] 本地化过程发生异常: {e}")
            return "未知意图的表情包", image_ref

    async def _structured_analysis(self, image_ref: str) -> Dict[str, Any]:
        """使用 Base64 进行结构化分析，修复 Windows 路径截取问题"""
        prompt_text = STICKER_ANALYSIS_PROMPT

        try:
            # --- 1. 更加鲁棒的路径转换 ---
            if image_ref.startswith("file:///"):
                # 处理 file:///D:/... 这种情况
                local_path = image_ref[8:]
            elif image_ref.startswith("file://"):
                # 处理 file://D:/... 这种情况
                local_path = image_ref[7:]
            else:
                local_path = image_ref

            # 针对 Windows 的特殊处理：如果路径类似 /D:/... 则去掉开头的斜杠
            if os.name == 'nt' and local_path.startswith('/') and local_path[2] == ':':
                local_path = local_path[1:]

            # 转换为绝对路径确保万无一失
            local_path = os.path.abspath(local_path)

            if not os.path.exists(local_path):
                raise FileNotFoundError(f"无法读取文件进行分析，路径不存在: {local_path}")

            # --- 2. 读取并转 Base64 ---
            with open(local_path, "rb") as f:
                img_data = f.read()
                b64_str = base64.b64encode(img_data).decode('utf-8')

            # --- 3. 构造消息请求 ---
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}
                        },
                        {"type": "text", "text": prompt_text}
                    ]
                }
            ]

            raw = await self.llm.robust_api_call(
                model="qwen3-vl-flash",
                messages=messages,
                temperature=0.3,
                max_tokens=400
            )

            # 清洗并解析 JSON
            cleaned = raw.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            return json.loads(cleaned)

        except Exception as e:
            # 这里打印出 local_path 方便你调试
            logger.error(f"[Sticker] Base64 结构化分析失败: {e}")
            # 如果是因为 json.loads 失败，记录一下 raw 内容
            return {"description": "识别失败", "emotion": "中性", "tags": [], "category": "日常摸鱼系"}

    def _build_embed_text(self, analysis: Dict) -> str:
        parts = [
            analysis["description"],
            f"情绪：{analysis['emotion']}",
            f"场景：{' '.join(analysis.get('usage_scenarios', []))}",
            f"标签：{' '.join(analysis.get('tags', []))}"
        ]
        return " | ".join(parts)

    def _embed_text(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()

    async def _judge_emotion(self, yuki_message: str) -> str:
        # （保持不变）
        prompt = EMOTION_JUDGE_PROMPT.format(yuki_message=yuki_message)
        raw = await self.llm.robust_api_call(
            model="deepseek-v3.2",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20
        )
        return raw.strip() or "中性"

    # ====================== 主流程 ======================
    async def ingest_sticker(self, image_ref: str, chat_id: str = "global", owner: str = "admin") -> str:
        """主流程：学习一张表情包（支持网页URL 和 本地文件）"""
        logger.info(f"[Sticker] 开始学习 → {image_ref[:80]}...")

        # Step 1: VL理解 + 本地化（已自动保存原图）
        vl_desc, local_file_ref = await self._vl_understand_and_localize(image_ref)

        # Step 2: 结构化分析（看图）
        analysis = await self._structured_analysis(local_file_ref)   # 传本地图像

        # Step 3~5: 构建嵌入 + 存入
        embed_text = self._build_embed_text(analysis)
        embedding = self._embed_text(embed_text)

        doc_id = f"sticker_{int(time.time())}_{hash(image_ref) % 100000:05d}"
        metadata = {
            "chat_id": str(chat_id),
            "owner": owner,
            "emotion": analysis["emotion"],
            "category": analysis["category"],
            "description": analysis["description"],
            "tags": json.dumps(analysis.get("tags", []), ensure_ascii=False),
            "usage_scenarios": json.dumps(analysis.get("usage_scenarios", []), ensure_ascii=False),
            "use_count": 0,
            "approval_score": 1.0,
            "image_ref": local_file_ref,      # ← 关键：永远是 file:// 本地路径，可直接发送
            "last_used": 0
        }

        self.collection.add(
            documents=[embed_text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[doc_id]
        )

        logger.info(f"[Sticker] ✅ 入库完成 | 本地路径: {local_file_ref} | 情绪: {analysis['emotion']}")
        return doc_id

    # ====================== 主流程2：调取/检索（retrieve） ======================
    async def get_suitable_sticker(self, yuki_message: str, chat_id: str, top_k: int = 10, explore_rate: float = 0.18) -> Optional[Dict]:
        """
        主流程：根据Yuki当前要说的话，返回最合适的一张表情包（含发送所需信息）
        返回 None 表示“不适合发表情包”
        """
        if not yuki_message.strip():
            return None

        logger.info(f"[Sticker] 开始为消息检索表情包: {yuki_message[:60]}...")

        # Step 1: 判断情绪标签
        emotion_tag = await self._judge_emotion(yuki_message)

        # Step 2: 构造查询文本（你的核心设计）
        query_text = f"{yuki_message} | 情绪：{emotion_tag}"

        # Step 3: 双池检索（向量语义 + jieba全局打捞）
        candidates = await self._dual_pool_retrieve(query_text, chat_id, top_k=top_k * 2)

        if not candidates:
            return None

        # Step 4: 融合排名 + 探索机制
        ranked = self._rank_and_explore(candidates, explore_rate=explore_rate)

        # Step 5: 取Top1（你也可以在这里再加一次LLM终审）
        if not ranked:
            return None

        best = ranked[0]
        # 更新使用统计
        self._increment_use_count(best["id"])

        logger.info(f"[Sticker] 选中表情 → 情绪:{best['emotion']} | 描述:{best['description'][:40]} | use_count:{best['use_count']}")
        return best

    async def _dual_pool_retrieve(self, query_text: str, chat_id: str, top_k: int = 20) -> List[Dict]:
        """工具6：双池检索（完全复用你RAG的双池思想）"""
        query_emb = self._embed_text(query_text)

        # 向量池
        vector_results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            where={"chat_id": {"$in": [str(chat_id), "global"]}},
            include=["documents", "metadatas", "distances", "embeddings"]
        )

        candidates = []
        if vector_results["documents"] and vector_results["documents"][0]:
            for i, doc in enumerate(vector_results["documents"][0]):
                meta = vector_results["metadatas"][0][i]
                distance = vector_results["distances"][0][i]
                score = 1.0 - distance
                candidates.append({
                    "id": vector_results["ids"][0][i],
                    "embed_text": doc,
                    "score_vector": score,
                    "score_keyword": 0.0,
                    **meta
                })

        # 关键词池（jieba全局打捞）
        keywords = jieba.analyse.extract_tags(query_text, topK=12)
        # 简单关键词匹配加分
        for cand in candidates:
            matched = sum(1 for kw in keywords if kw in (cand.get("embed_text", "") + " " + str(cand.get("tags", ""))))
            cand["score_keyword"] = matched * 0.3

        return candidates

    def _rank_and_explore(self, candidates: List[Dict], explore_rate: float = 0.18) -> List[Dict]:
        """工具7：融合排名 + 探索低频包"""
        if not candidates:
            return []

        # 融合得分
        for cand in candidates:
            vector_w = cand.get("score_vector", 0.0)
            keyword_w = cand.get("score_keyword", 0.0)
            use_bonus = min(cand.get("use_count", 0) / 20.0, 1.0) * 0.4   # 高频有奖励
            approval = cand.get("approval_score", 1.0)

            cand["final_score"] = (vector_w * 0.55) + (keyword_w * 0.25) + (use_bonus * 0.15) + (approval * 0.05)

        # 排序
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # 探索机制：有一定概率把低频包提到前面
        if len(candidates) > 3 and explore_rate > 0:
            low_freq = [c for c in candidates if c.get("use_count", 0) < 5]
            if low_freq and len(low_freq) > 0:
                import random
                if random.random() < explore_rate:
                    # 把一个低频包随机提到前3位
                    explore_item = random.choice(low_freq)
                    candidates.remove(explore_item)
                    insert_pos = random.randint(0, min(2, len(candidates) - 1))
                    candidates.insert(insert_pos, explore_item)

        return candidates[:8]   # 返回Top8供最终决策

    def _increment_use_count(self, doc_id: str):
        """工具8：更新使用次数（原子化）"""
        try:
            # Chroma目前不支持直接原子更新，这里用get + update
            res = self.collection.get(ids=[doc_id], include=["metadatas"])
            if res["metadatas"] and len(res["metadatas"]) > 0:
                meta = res["metadatas"][0]
                meta["use_count"] = meta.get("use_count", 0) + 1
                meta["last_used"] = time.time()
                self.collection.update(ids=[doc_id], metadatas=[meta])
        except Exception as e:
            logger.error(f"[Sticker] 更新使用次数失败: {e}")

    # ====================== 实用工具方法 ======================
    def get_stats(self) -> Dict:
        """查看当前表情包统计"""
        total = self.collection.count()
        return {"total_stickers": total}

    async def batch_ingest_from_list(self, image_refs: List[str], chat_id: str = "global", owner: str = "admin"):
        """批量导入（慢慢打样时使用）"""
        for ref in image_refs:
            await self.ingest_sticker(ref, chat_id, owner)
            await asyncio.sleep(0.5)  # 避免API限流