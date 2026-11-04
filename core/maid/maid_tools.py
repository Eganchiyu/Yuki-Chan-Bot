import random
import re

DIARY_PREVIEW_MAX = 8


def search_diary_fast(date_str=None, keyword=None):
    """按日期/关键词检索日记；无参数时随机翻看。命中结果同样随机抽取，不按时间顺序。"""
    try:
        import chromadb
        from config import cfg

        # 绕过 RAG，直接连接配置中的向量数据库目录
        client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)

        # 2. 获取 Collection（不加载任何 Embedding 模型）
        collection = client.get_collection(name="diaries")

        # 3. 过滤交给向量库底层（where_document），不再把全表拉进内存
        conditions = []
        if date_str:
            # 日记正文固定以 【日记(YYYY-MM-DD HH:MM)】 开头，日期前缀可直接用 $contains 粗筛
            conditions.append({"$contains": f"【日记({date_str}"})
        if keyword:
            # Chroma 的 $contains 区分大小写：常见大小写形态各查一次取并集，
            # 最终精确判定仍由下面的 lower() 比对负责。
            keyword_variants = {
                keyword,
                keyword.lower(),
                keyword.upper(),
                keyword.title(),
                keyword.capitalize(),
            }
            keyword_conditions = [{"$contains": kw} for kw in sorted(keyword_variants)]
            conditions.append(
                keyword_conditions[0] if len(keyword_conditions) == 1 else {"$or": keyword_conditions}
            )

        if conditions:
            where_document = conditions[0] if len(conditions) == 1 else {"$and": conditions}
            results = collection.get(where_document=where_document, include=["documents"])
        else:
            # 无日期无关键词：随机翻看日记本
            results = collection.get(include=["documents"])
        candidates = results.get("documents") or []

        if not candidates:
            return "没有找到匹配的日记。" if conditions else "记忆库目前是空的。"

        # 4. 候选集已经很小，再用正则做精确校验（保持原日期语义）
        date_pattern = re.compile(rf"【日记\({re.escape(date_str)}.*?\)】") if date_str else None
        keyword_lower = keyword.lower() if keyword else None
        matched_docs = []
        for doc in candidates:
            if date_pattern and not date_pattern.search(doc):
                continue
            if keyword_lower is not None and keyword_lower not in doc.lower():
                continue
            matched_docs.append(doc)

        if not matched_docs:
            return "没有找到匹配的日记。"

        # 5. 随机抽取，避免总是返回最早写入的那几条
        picked = random.sample(matched_docs, min(DIARY_PREVIEW_MAX, len(matched_docs)))
        if conditions:
            header = f"成功找到 {len(matched_docs)} 条记录（随机抽取 {len(picked)} 条展示）：\n"
        else:
            header = f"随机翻看日记本（共 {len(matched_docs)} 条，随机抽取 {len(picked)} 条）：\n"
        res_str = header
        for i, d in enumerate(picked):
            preview = d.replace("\n", " ")
            res_str += f"[{i+1}] {preview}...\n"

        return res_str

    except Exception as e:
        return f"搜索异常: {str(e)}"
