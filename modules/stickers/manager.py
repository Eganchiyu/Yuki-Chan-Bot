# modules/stickers/manager.py
import asyncio
import base64
import json
import time
import os
import math
import random
from typing import List, Dict, Optional, Any
import chromadb
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    import jieba
    import jieba.analyse
from sentence_transformers import SentenceTransformer

from config import cfg
from modules.vision.processor import MemeProcessor
from utils.logger import get_logger

logger = get_logger("stickers")

# ================== Prompt ==================
STICKER_ANALYSIS_PROMPT = """
你是一个专业的QQ表情包语义专家。请严格按照JSON格式分析下面这张表情包，只输出合法JSON，不要任何额外文字。

{
  "description": "一句话核心描述（15-25字，包含动作、表情、意图）",
  "emotion": "主要情绪（必须从以下选择一个）：撒娇、吐槽、无语、生气、开心、委屈、调情、震惊、摸鱼、高冷、抽象、群内梗、中性",
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
    def __init__(self):
        from providers.registry import ProviderRegistry
        self.registry = ProviderRegistry()
        self.vl_processor = MemeProcessor()
        self.model = SentenceTransformer(cfg.EMBED_MODEL)

        self.client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="stickers",
            metadata={"hnsw:space": "cosine"}
        )
        # === 👇 新增：并发防重锁与状态集合 ===
        self._db_lock = asyncio.Lock()
        self.processing_files = set()
        jieba.load_userdict("blacklist.txt") if os.path.exists("blacklist.txt") else None
        logger.info(f"[StickerManager] 初始化完成 | 当前表情包数量: {self.collection.count()}")

    # ====================== 工具函数 ======================

    async def _localize_image(self, image_ref: str) -> str:
        """
        纯粹的本地化工具：将网络或本地图片转为本地军火库标准路径。
        绝不调用大模型，极致榨取 IO 性能。
        """
        try:
            if image_ref.startswith("http://") or image_ref.startswith("https://"):
                # 网络图片：异步下载到内存
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_ref, timeout=15) as resp:
                        if resp.status != 200:
                            raise Exception(f"HTTP {resp.status}")
                        content = await resp.read()
                path = image_ref  # 仅作变量占位提取后缀用
            else:
                # 本地图片：处理 file:/// 等前缀并读取
                if image_ref.startswith("file:///"):
                    path = image_ref[8:]
                elif image_ref.startswith("file://"):
                    path = image_ref[7:]
                else:
                    path = image_ref

                if os.name == 'nt' and path.startswith('/') and len(path) > 2 and path[2] == ':':
                    path = path[1:]
                path = os.path.abspath(path)

                with open(path, "rb") as f:
                    content = f.read()

            # 只负责将其保存为 MD5 唯一名字
            return self.vl_processor.save_to_local_sticker_library(content, path)

        except Exception as e:
            logger.error(f"[StickerManager] 图片获取与本地化异常: {e}")
            return ""

    async def structured_analysis(self, image_ref: str) -> Dict[str, Any]:
        """使用 Base64 进行结构化分析（修正：调用独立的视觉 API 通道）"""
        prompt_text = STICKER_ANALYSIS_PROMPT

        try:
            if image_ref.startswith("file:///"):
                local_path = image_ref[8:]
            elif image_ref.startswith("file://"):
                local_path = image_ref[7:]
            else:
                local_path = image_ref

            if os.name == 'nt' and local_path.startswith('/') and local_path[2] == ':':
                local_path = local_path[1:]

            local_path = os.path.abspath(local_path)

            if not os.path.exists(local_path):
                raise FileNotFoundError(f"无法读取文件进行分析，路径不存在: {local_path}")

            with open(local_path, "rb") as f:
                img_data = f.read()
                b64_str = base64.b64encode(img_data).decode('utf-8')

            payload = {
                "model": cfg.VISION_MODEL,
                "messages": [
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
                ],
                "max_tokens": 400,
                "temperature": 0.3
            }

            headers = {
                "Authorization": f"Bearer {cfg.IMAGE_PROCESS_API_KEY}",
                "Content-Type": "application/json"
            }

            import aiohttp
            # 这里直接走专门的图像处理通道，不走文本 LLM 的通道
            async with aiohttp.ClientSession(timeout=cfg.REQUEST_TIMEOUT) as session:
                async with session.post(cfg.IMAGE_PROCESS_API_URL, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw = data["choices"][0]["message"]["content"]
                    else:
                        error_text = await resp.text()
                        raise Exception(f"Vision API HTTP {resp.status}: {error_text}")

            # 清洗结果
            cleaned = raw.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

                # 修复 NoneType Bug：确保无论如何都有一个 return 兜底
            return json.loads(cleaned)

        except Exception as e:
            logger.error(f"[Sticker] 结构化分析失败: {e}")
            return {"description": "识别失败", "emotion": "中性", "tags": [], "usage_scenarios": []}

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
        prompt = EMOTION_JUDGE_PROMPT.format(yuki_message=yuki_message)

        provider = self.registry.get("default")
        raw = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=cfg.LLM_MODEL,
            temperature=0.0,
            max_tokens=20
        )

        return raw.strip() or "中性"

        # ====================== 核心算法：重排与状态管理 ======================

    def _rank_and_explore(self, candidates: List[Dict]) -> List[Dict]:
        """融合排名 + 积热冷却算法（V2终极版）"""
        if not candidates:
            return []

        current_time = time.time()

        for cand in candidates:
            # 1. 语义基础分 (来自 RAG 的余弦相似度，权重最高)
            semantic_score = cand.get("score_vector", 0.0) * 5.0

            # 2. 新鲜度奖励 (指数衰减)
            create_time = cand.get("create_time", current_time)
            days_since_creation = (current_time - create_time) / (24 * 3600)
            freshness_bonus = math.exp(-0.1 * days_since_creation)

            # 3. 积热冷却惩罚 (防发散与真正遗忘机制)
            last_heat = cand.get("heat", 0.0)
            last_used_time = cand.get("last_used_time", current_time)
            days_since_last_used = (current_time - last_used_time) / (24 * 3600)

            # 冷却因子：三天不用，热度衰减显著
            current_heat = last_heat * math.exp(-0.3 * days_since_last_used)
            penalty = 1.2 * current_heat

            # 暂存当前残余热度，供后续选中时升温使用
            cand["current_heat"] = current_heat

            # 4. 正反馈偏好加成 (群友越爱看，发得越多)
            pref_bonus = 0.8 * cand.get("preference", 0)

            # 5. 随机游走噪声 (人类灵魂)
            noise = random.uniform(0, 0.2)

            # 综合打分
            cand["final_score"] = semantic_score + freshness_bonus - penalty + pref_bonus + noise

        # 降序排列，取 Top 8
        candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return candidates[:8]

    def _update_meme_status(self, doc_id: str, current_heat: float):
        """发送表情包后，执行积热升温与时间刷新"""
        try:
            res = self.collection.get(ids=[doc_id], include=["metadatas"])
            if res["metadatas"] and len(res["metadatas"]) > 0:
                meta = res["metadatas"][0]
                meta["heat"] = current_heat + 1.0  # 核心：残余热度 + 1
                meta["last_used_time"] = time.time()  # 刷新 CD 时间
                meta["use_count"] = meta.get("use_count", 0) + 1  # 仅作数据统计用
                self.collection.update(ids=[doc_id], metadatas=[meta])
        except Exception as e:
            logger.error(f"[Sticker] 更新表情积热状态失败: {e}")

    def add_preference(self, doc_id: str):
        """群友产生正反馈时调用：好感度 +1"""
        try:
            res = self.collection.get(ids=[doc_id], include=["metadatas"])
            if res["metadatas"] and len(res["metadatas"]) > 0:
                meta = res["metadatas"][0]
                meta["preference"] = meta.get("preference", 0) + 1
                self.collection.update(ids=[doc_id], metadatas=[meta])
                logger.info(f"[Sticker] 收到正反馈！表情包 {doc_id} 偏好度升至 {meta['preference']}")
        except Exception as e:
            logger.error(f"[Sticker] 增加偏好度失败: {e}")

        # ====================== 主流程：入库与检索 ======================

    async def ingest_sticker(self, image_ref: str, chat_id: str = "global", owner: str = "admin") -> str:
        """主流程：自动学习一张表情包，存入向量库"""
        logger.info(f"[Sticker] 尝试学习表情包 → {image_ref[:80]}...")

        # Step 1: 极速本地化下载与哈希命名
        local_file_ref = await self._localize_image(image_ref)

        if not local_file_ref or not os.path.exists(local_file_ref):
            logger.warning(f"[Sticker] 获取本地文件失败，放弃入库。")
            return "failed"

        async with self._db_lock:
            if local_file_ref in self.processing_files:
                logger.info(f"[Sticker] 🛑 并发拦截：该表情包正在被其他协程分析中，跳过重复消耗。")
                return "processing"

            existing = self.collection.get(where={"image_ref": local_file_ref})
            if existing and existing['ids']:
                logger.info(f"[Sticker] 🛑 查重拦截：该表情包已在军火库中，跳过打标与入库消耗。")
                return existing['ids'][0]

            self.processing_files.add(local_file_ref)

        try:
            # Step 2: 调用大模型进行结构化分析
            analysis = await self.structured_analysis(local_file_ref)
            embed_text = self._build_embed_text(analysis)
            embedding = self._embed_text(embed_text)

            doc_id = f"sticker_{int(time.time())}_{hash(image_ref) % 100000:05d}"
            current_time = time.time()
            metadata = {
                "chat_id": str(chat_id),
                "owner": owner,
                "emotion": analysis["emotion"],
                "description": analysis["description"],
                "tags": json.dumps(analysis.get("tags", []), ensure_ascii=False),
                "usage_scenarios": json.dumps(analysis.get("usage_scenarios", []), ensure_ascii=False),
                "image_ref": local_file_ref,
                "create_time": current_time,
                "last_used_time": current_time,
                "heat": 0.0,
                "preference": 0,
                "use_count": 0
            }

            self.collection.add(
                documents=[embed_text],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id]
            )

            logger.info(f"[Sticker] ✅ 成功学会新表情 | 本地路径: {local_file_ref} | 情绪: {analysis['emotion']}")
            return doc_id

        finally:
            async with self._db_lock:
                if local_file_ref in self.processing_files:
                    self.processing_files.remove(local_file_ref)

    async def manual_batch_ingest_from_json(self, json_path: str, chat_id: str = "global", owner: str = "admin"):
        """从本地 JSON 文件手动批量打标并入库，彻底绕过大模型识别"""
        if not os.path.exists(json_path):
            logger.error(f"[Sticker] 找不到打标文件 {json_path}")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            try:
                stickers_data = json.load(f)
            except Exception as e:
                logger.error(f"[Sticker] JSON 解析失败: {e}")
                return

        for item in stickers_data:
            image_path = item.get("image_path")
            if not image_path:
                continue

            logger.info(f"[Sticker] 正在手动录入: {image_path}")

            # 本地化
            local_file_ref = await self._localize_image(image_path)
            if not local_file_ref or not os.path.exists(local_file_ref):
                logger.warning(f"[Sticker] 获取本地文件失败，跳过: {image_path}")
                continue

            async with self._db_lock:
                # 查重
                existing = self.collection.get(where={"image_ref": local_file_ref})
                if existing and existing['ids']:
                    logger.info(f"[Sticker] 🛑 查重拦截：该表情包已在军火库中，跳过 {image_path}")
                    continue

                # 提取手动数据并直接向量化
                embed_text = self._build_embed_text(item)
                embedding = self._embed_text(embed_text)

                doc_id = f"sticker_{int(time.time())}_{hash(image_path) % 100000:05d}"
                current_time = time.time()

                metadata = {
                    "chat_id": str(chat_id),
                    "owner": owner,
                    "emotion": item.get("emotion", "中性"),
                    "description": item.get("description", "无描述"),
                    "tags": json.dumps(item.get("tags", []), ensure_ascii=False),
                    "usage_scenarios": json.dumps(item.get("usage_scenarios", []), ensure_ascii=False),
                    "image_ref": local_file_ref,
                    "create_time": current_time,
                    "last_used_time": current_time,
                    "heat": 0.0,
                    "preference": 0,
                    "use_count": 0
                }

                self.collection.add(
                    documents=[embed_text],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
                logger.info(f"[Sticker] ✅ 成功手动录入表情包: {item.get('description')}")

    async def get_suitable_sticker(self, yuki_message: str, chat_id: str, top_k: int = 10) -> Optional[Dict]:
        """主流程：检索、重排并决定发送的表情包"""
        if not yuki_message.strip():
            return None

        logger.info(f"[Sticker] 开始为消息检索表情包: {yuki_message[:60]}...")

        emotion_tag = await self._judge_emotion(yuki_message)
        query_text = f"{yuki_message} | 情绪：{emotion_tag}"

        # 1. 召回层 (Recall)：双池检索提取 Top 20 候选
        candidates = await self._dual_pool_retrieve(query_text, chat_id, top_k=top_k * 2)
        if not candidates:
            return None

        # 2. 排序层 (Rank)：积热重排算法
        ranked = self._rank_and_explore(candidates)
        if not ranked:
            return None

        # 3. 决断与状态刷新
        best = ranked[0]
        self._update_meme_status(best["id"], best.get("current_heat", 0.0))

        logger.info(
            f"[Sticker] 选中表情 → 情绪:{best['emotion']} | 描述:{best['description'][:40]} | 偏好度:{best.get('preference', 0)}")
        return best

    async def _dual_pool_retrieve(self, query_text: str, chat_id: str, top_k: int = 20) -> List[Dict]:
        """双池召回：向量语义池 + 关键词补漏池"""
        query_emb = self._embed_text(query_text)

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

        keywords = jieba.analyse.extract_tags(query_text, topK=12)
        for cand in candidates:
            matched = sum(1 for kw in keywords if kw in (cand.get("embed_text", "") + " " + str(cand.get("tags", ""))))
            cand["score_keyword"] = matched * 0.3

        return candidates

        # ====================== 实用工具方法 ======================

    def get_stats(self) -> Dict:
        """查看当前表情包统计"""
        total = self.collection.count()
        return {"total_stickers": total}

    async def batch_ingest_from_list(self, image_refs: List[str], chat_id: str = "global", owner: str = "admin"):
        """批量导入（自动模式）"""
        for ref in image_refs:
            await self.ingest_sticker(ref, chat_id, owner)
            await asyncio.sleep(0.5)


# ====================== 数据库管理终端 ======================

if __name__ == "__main__":
    import sys
    from pathlib import Path


    async def view_sticker_database():
        # 1. 初始化（自动读取 cfg 路径）
        dummy_llm = ApiCall(cfg.LLM_API_KEY, cfg.LLM_BASE_URL)
        manager = StickerManager(dummy_llm)

        while True:  # 增加循环，删完图后自动刷新列表
            print(f"\n{'=' * 20} 📦 Yuki 表情包军火库全量审计 {'=' * 20}")
            print(f"数据库路径: {os.path.abspath(cfg.VECTOR_DB_PATH)}")

            # 2. 提取全量数据
            data = manager.collection.get(include=["metadatas", "documents"])

            if not data or not data['ids']:
                print("目前库里空空如也，快去水群存点图或手动导入吧！")
                count = 0
                items = []
            else:
                count = len(data['ids'])
                print(f"当前存库总量: {count} 张")
                print("-" * 120)

                # 3. 结构化处理以便排序预览
                items = []
                for i in range(count):
                    meta = data['metadatas'][i]
                    items.append({
                        "id": data['ids'][i],
                        "emotion": meta.get("emotion", "未知"),
                        "pref": meta.get("preference", 0),
                        "heat": round(meta.get("heat", 0.0), 2),
                        "used": meta.get("use_count", 0),
                        "desc": meta.get("description", "无描述"),
                        "path": meta.get("image_ref", "路径丢失")
                    })

                # 排序：好感度优先，热度次之
                items.sort(key=lambda x: (x['pref'], x['heat']), reverse=True)

                # 4. 打印表头
                head = f"{'索引':<4} | {'情绪':<6} | {'好感度':<6} | {'当前积热':<6} | {'使用次数':<6} | {'完整描述'}"
                print(head)
                print("-" * 120)

                for idx, item in enumerate(items, 1):
                    # 取消截断，直接展示全量文本
                    full_desc = item['desc']

                    # 使用 Emoji 增加可读性
                    print(
                        f"{idx:<4} | {item['emotion']:<6} | ❤️  {item['pref']:<4} | 🔥 {item['heat']:<6} | 🔁 {item['used']:<6} | {full_desc}")

                print("-" * 120)

            print(f"{'=' * 25} 审计结束 | 输入 'i' 导入手动打标JSON | 输入 'q' 退出 {'=' * 25}")

            cmd = input("\n输入命令 (数字查看详情/删除, 'i' 导入JSON, 'q' 退出): ").strip().lower()

            if cmd == 'q' or cmd == 'exit':
                break
            elif cmd == 'i':
                json_path = input("请输入要导入的 JSON 文件路径 (默认 manual_stickers.json): ").strip()
                if not json_path:
                    json_path = "manual_stickers.json"
                print(f"开始从 {json_path} 批量导入...")
                await manager.manual_batch_ingest_from_json(json_path)
                print("\n⏳ 正在刷新列表...")
                await asyncio.sleep(1.5)
            elif cmd.isdigit() and items:
                i = int(cmd) - 1
                if 0 <= i < len(items):
                    target = items[i]
                    print(f"\n📂 详细信息:")
                    print(f"  - 内部 ID: {target['id']}")
                    print(f"  - 本地路径: {target['path']}")
                    print(f"  - 完整描述: {target['desc']}")

                    del_cmd = input(f"\n⚠️ 是否要将该表情包从 Yuki 的记忆和硬盘中彻底删除？(y/N): ").strip().lower()
                    if del_cmd == 'y':
                        try:
                            # 1. 从 ChromaDB 中删除记录
                            manager.collection.delete(ids=[target['id']])
                            print(f"✅ 数据库记录已清除。")

                            # 2. 同步销毁本地物理文件
                            if os.path.exists(target['path']):
                                os.remove(target['path'])
                                print(f"✅ 本地图片文件已同步销毁。")
                            else:
                                print(f"⚠️ 找不到本地图片，可能此前已被手动删除。")

                            print("\n⏳ 正在刷新列表...")
                            await asyncio.sleep(1.5)
                        except Exception as e:
                            print(f"❌ 删除失败: {e}")
                else:
                    print("❌ 索引超出范围。")
            else:
                print("❌ 无效的输入。")


    # 运行
    try:
        asyncio.run(view_sticker_database())
    except KeyboardInterrupt:
        print("\n已退出管理器。")
