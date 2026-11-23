import random
import re

DIARY_PREVIEW_MAX = 8
# 软比例：本群占大部分（约 7 成），别的群少量（约 3 成）
DIARY_LOCAL_QUOTA = 6
DIARY_OTHER_QUOTA = 2

_CLIENT_CACHE: dict[tuple[object, str], object] = {}


def _get_diary_client(path: str):
    """复用 Chroma PersistentClient 实例；测试 monkeypatch PersistentClient 类时自动隔离。"""
    import chromadb

    cls = chromadb.PersistentClient
    key = (cls, str(path))
    client = _CLIENT_CACHE.get(key)
    if client is None:
        client = cls(path=path)
        _CLIENT_CACHE[key] = client
    return client


def _diary_labels(chat_id, chat_mode):
    """返回（本对话标签, 跨对话标签生成函数）。"""
    local_label = "[本对话]" if chat_mode == "private" else "[本群]"

    def other_label(cid):
        if not cid or cid in ("None", "manual_record"):
            return "[群:未标注]"
        try:
            from modules.autonomous.storage import group_name_cache

            return f"[群:{group_name_cache.label(cid)}]"
        except Exception:
            return f"[群:{cid}]"

    return local_label, other_label


def _pick_by_soft_ratio(local_docs, other_docs, max_items):
    """按软比例抽样：本群优先占多数，不足时用别的群补齐。"""
    picked_local = random.sample(local_docs, min(len(local_docs), DIARY_LOCAL_QUOTA))
    picked_other = random.sample(other_docs, min(len(other_docs), DIARY_OTHER_QUOTA))

    # 软补齐：某一侧不够时，空出的名额让给另一侧
    leftover_slots = max_items - len(picked_local) - len(picked_other)
    if leftover_slots > 0:
        rest_local = [d for d in local_docs if d not in picked_local]
        take_local = random.sample(rest_local, min(len(rest_local), leftover_slots))
        picked_local += take_local
        leftover_slots -= len(take_local)
    if leftover_slots > 0:
        rest_other = [d for d in other_docs if d not in picked_other]
        picked_other += random.sample(rest_other, min(len(rest_other), leftover_slots))

    random.shuffle(picked_local)
    random.shuffle(picked_other)
    return picked_local, picked_other


def search_diary_fast(date_str=None, keyword=None, chat_id=None, chat_mode=None):
    """按日期/关键词检索日记；无参数时随机翻看。

    结果标注归属（[本群]/[本对话] 与 [群:xxx]），并按软比例让本对话的日记占多数、
    别的群的占少数；本对话 0 命中时只用别的群并明确说明，全部 0 命中时直接说明没有记录。
    """
    try:
        from config import cfg

        # 绕过 RAG，直接连接配置中的向量数据库目录（复用客户端缓存）
        client = _get_diary_client(cfg.VECTOR_DB_PATH)

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

        include = ["documents", "metadatas"]
        cid_str = str(chat_id) if chat_id is not None else None
        local_label, other_label = _diary_labels(chat_id, chat_mode)

        if not conditions:
            # 无日期无关键词：先只拉轻量 metadatas + ids 完成软比例抽样，再按抽中的 8 个 id 取正文
            meta_results = collection.get(include=["metadatas"])
            all_ids = meta_results.get("ids") or []
            all_metas = meta_results.get("metadatas") or [None] * len(all_ids)
            inline_docs = meta_results.get("documents")
            if not all_ids and not inline_docs:
                return "记忆库目前是空的。"
            if all_ids:
                local_idx, other_idx = [], []
                for idx_i, meta in enumerate(all_metas):
                    doc_cid = (meta or {}).get("chat_id")
                    doc_cid = str(doc_cid) if doc_cid is not None else None
                    if cid_str is not None and doc_cid == cid_str:
                        local_idx.append(idx_i)
                    else:
                        other_idx.append(idx_i)
                picked_l_idx, picked_o_idx = _pick_by_soft_ratio(local_idx, other_idx, DIARY_PREVIEW_MAX)
                if inline_docs and len(inline_docs) == len(all_ids):
                    id_to_doc = dict(zip(all_ids, inline_docs))
                else:
                    target_ids = [all_ids[i] for i in (picked_l_idx + picked_o_idx)]
                    try:
                        doc_res = collection.get(ids=target_ids, include=["documents"])
                        id_to_doc = dict(zip(doc_res.get("ids") or [], doc_res.get("documents") or []))
                    except TypeError:
                        full_res = collection.get(include=include)
                        id_to_doc = dict(zip(full_res.get("ids") or all_ids, full_res.get("documents") or []))
                picked_local = [id_to_doc.get(all_ids[i], "") for i in picked_l_idx if id_to_doc.get(all_ids[i])]
                picked_other = [id_to_doc.get(all_ids[i], "") for i in picked_o_idx if id_to_doc.get(all_ids[i])]
                other_cids = {
                    id_to_doc.get(all_ids[i], ""): (
                        str((all_metas[i] or {}).get("chat_id"))
                        if (all_metas[i] or {}).get("chat_id") is not None
                        else None
                    )
                    for i in picked_o_idx
                }
                total_matched = len(all_ids)
                total_local = len(local_idx)
                total_other = len(other_idx)
            else:
                candidates = inline_docs or []
                total_matched = len(candidates)
                picked_local, picked_other = _pick_by_soft_ratio(candidates, [], DIARY_PREVIEW_MAX)
                total_local, total_other = len(candidates), 0
                other_cids = {}
        else:
            where_document = conditions[0] if len(conditions) == 1 else {"$and": conditions}
            results = collection.get(where_document=where_document, include=include)
            candidates = results.get("documents") or []
            metadatas = results.get("metadatas") or [None] * len(candidates)

            if not candidates:
                return "没有相关记录。"

            # 4. 候选集已经很小，再用正则做精确校验（保持原日期语义）
            date_pattern = re.compile(rf"【日记\({re.escape(date_str)}.*?\)】") if date_str else None
            keyword_lower = keyword.lower() if keyword else None
            matched = []
            for doc, meta in zip(candidates, metadatas):
                if date_pattern and not date_pattern.search(doc):
                    continue
                if keyword_lower is not None and keyword_lower not in doc.lower():
                    continue
                matched.append((doc, meta or {}))

            if not matched:
                return "没有相关记录。"

            local_docs, other_docs = [], []
            other_cids = {}
            for doc, meta in matched:
                doc_cid = meta.get("chat_id")
                doc_cid = str(doc_cid) if doc_cid is not None else None
                other_cids[doc] = doc_cid
                if cid_str is not None and doc_cid == cid_str:
                    local_docs.append(doc)
                else:
                    other_docs.append(doc)

            picked_local, picked_other = _pick_by_soft_ratio(local_docs, other_docs, DIARY_PREVIEW_MAX)
            total_matched = len(matched)
            total_local = len(local_docs)
            total_other = len(other_docs)

        # 5. 拼装输出
        header = []
        if cid_str is None:
            header.append(
                f"随机翻看日记本（共 {total_matched} 条，抽取 {len(picked_local) + len(picked_other)} 条）："
                if not conditions
                else f"成功找到 {total_matched} 条记录，抽取 {len(picked_local) + len(picked_other)} 条展示："
            )
        elif not total_local:
            scope = "本对话" if chat_mode == "private" else "本群"
            header.append(f"{scope}没有相关记录，以下是别的群的日记（共 {len(picked_other)} 条）：")
        elif conditions:
            header.append(
                f"成功找到 {total_matched} 条记录（本群 {total_local} 条 / 别的群 {total_other} 条），"
                f"抽取本群 {len(picked_local)} 条 + 别的群 {len(picked_other)} 条展示："
            )
        else:
            header.append(
                f"随机翻看日记本（共 {total_matched} 条，本群 {total_local} 条 / 别的群 {total_other} 条），"
                f"抽取本群 {len(picked_local)} 条 + 别的群 {len(picked_other)} 条："
            )

        res_str = "\n".join(header) + "\n"
        idx = 0
        for d in picked_local:
            idx += 1
            res_str += f"[{idx}] {local_label} {d.replace(chr(10), ' ')}...\n"
        for d in picked_other:
            idx += 1
            label = other_label(other_cids.get(d)) if cid_str is not None else "[未知归属]"
            res_str += f"[{idx}] {label} {d.replace(chr(10), ' ')}...\n"

        return res_str

    except Exception as e:
        return f"搜索异常: {str(e)}"
