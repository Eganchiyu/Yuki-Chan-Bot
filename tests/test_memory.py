"""记忆系统单元测试：RAG 召回打分、Chroma 快查、跨轮召回缓存 (RecallCacheStore) 与小本本 (NotebookStore)。"""
import datetime

import chromadb

from config import cfg
from core import session_pipeline as sp_mod
from core.maid import maid_tools
from core.notebook import NOTEBOOK_MAX_CHARS, NotebookStore
from core.recall_cache import RecallCacheStore
from core.session_pipeline import SessionPipeline
from modules.memory.rag import RECENCY_FLOOR, MemoryRAG


class _FakeModel:
    def encode(self, text):
        return type("V", (), {"tolist": lambda self: [0.1, 0.2, 0.3]})()


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def count(self):
        return len(self.docs)

    def query(self, query_embeddings=None, n_results=8, where=None):
        ranked = sorted(self.docs, key=lambda d: d[3])[:n_results]
        return {
            "ids": [[d[0] for d in ranked]],
            "documents": [[d[1] for d in ranked]],
            "metadatas": [[d[2] for d in ranked]],
            "distances": [[d[3] for d in ranked]],
        }

    def get(self, where_document=None, where=None, include=None, limit=None):
        hit = [d for d in self.docs if self._match(d[1], where_document)]
        return {
            "ids": [d[0] for d in hit],
            "documents": [d[1] for d in hit],
            "metadatas": [d[2] for d in hit],
        }

    @staticmethod
    def _match(content, where_document):
        if not where_document:
            return True
        if "$and" in where_document:
            return all(_FakeCollection._match(content, c) for c in where_document["$and"])
        if "$or" in where_document:
            return any(_FakeCollection._match(content, c) for c in where_document["$or"])
        return where_document.get("$contains", "") in content


def _make_rag(docs):
    rag = object.__new__(MemoryRAG)
    rag.collection = _FakeCollection(docs)
    rag.model = _FakeModel()
    rag.name_blacklist = []
    return rag


# ==================== RAG 召回打分与重排 ====================

def test_rag_scoring_boosts_and_decay():
    """纯语义分 relevance 不被加权污染；同群/发言者相对加成不反超高相关跨群记忆；时间衰减偏好近期。"""
    local_item = MemoryRAG._calculate_final_item(
        "Alice 和 Yuki 在本群聊讨论浏览器模式",
        {"chat_id": "10001"},
        0.2,
        [("浏览器", 0.8)],
        chat_id="10001",
        speaker_names=["Alice"],
    )
    other_item = MemoryRAG._calculate_final_item(
        "另一个群聊也讨论浏览器模式",
        {"chat_id": "20002"},
        0.9,
        [],
        chat_id="10001",
        speaker_names=["Alice"],
    )
    assert local_item["relevance"] == 0.2 and other_item["relevance"] == 0.9
    assert local_item["score"] > local_item["relevance"]
    assert other_item["score"] > local_item["score"]

    now = datetime.datetime(2026, 10, 25, 12, 0).timestamp()
    recent = MemoryRAG._calculate_final_item("【日记(2026-10-24 10:00)】：同一件事", {}, 0.6, [], now=now)
    old = MemoryRAG._calculate_final_item("【日记(2024-01-01 10:00)】：同一件事", {}, 0.6, [], now=now)
    undated = MemoryRAG._calculate_final_item("没有日期前缀的日记", {}, 0.6, [], now=now)
    meta_ts = MemoryRAG._calculate_final_item(
        "无日期前缀", {"timestamp": datetime.datetime(2025, 1, 1).timestamp()}, 0.6, [], now=now
    )
    assert recent["decay"] > 0.99
    assert RECENCY_FLOOR <= old["decay"] < recent["decay"]
    assert undated["decay"] == 1.0 and meta_ts["decay"] < 1.0
    assert recent["score"] > old["score"]


def test_keyword_coverage_and_search_diaries():
    """关键词覆盖度惩罚单虚词弱命中，且跨群高相关日记能正常召回。"""
    keywords = [("一起", 0.4), ("打游戏", 0.35), ("周末", 0.25)]
    assert MemoryRAG._keyword_coverage("【日记(2026-10-20)】：今天一起很累", keywords, 1.0) < (
        MemoryRAG._keyword_coverage("【日记(2026-10-20)】：周末打游戏", keywords, 1.0)
    )
    assert MemoryRAG._keyword_coverage("完全不相关", keywords, 1.0) == 0.0

    docs = [
        ("d1", "【日记(2026-10-24 10:00)】：周末和主人一起打游戏，好开心", {"chat_id": "10001"}, 0.10),
        ("d2", "【日记(2024-01-01 10:00)】：今天很累", {"chat_id": "10001"}, 0.95),
        ("d3", "【日记(2024-02-01 10:00)】：今天吃了面", {"chat_id": "10001"}, 0.96),
    ]
    results = _make_rag(docs).search_diaries("周末要不要一起打游戏", chat_id="10001", n_results=2)
    assert results and results[0]["content"].startswith("【日记(2026-10-24")
    assert all(0.0 <= r["relevance"] <= 1.0 for r in results)

    cross_docs = [
        ("d1", "【日记(2026-10-24 10:00)】：别的群聊讨论代码报错", {"chat_id": "20002"}, 0.10),
        ("d2", "【日记(2026-10-24 10:00)】：这个群聊聊了别的事", {"chat_id": "10001"}, 0.90),
    ]
    cross_res = _make_rag(cross_docs).search_diaries("代码报错", chat_id="10001", n_results=1)
    assert cross_res[0]["metadata"]["chat_id"] == "20002"


def test_search_diary_fast_uses_where_document(monkeypatch):
    """小女仆快速查日记使用 where_document 下推过滤，不走全表扫描。"""
    docs = [
        "【日记(2026-05-20 10:00)】：主人过生日",
        "【日记(2026-05-21 10:00)】：今天写代码",
        "【日记(2026-06-01 10:00)】：Nothing Special",
    ]
    collection = _FakeCollection([(f"id{i}", d, {}, 0.5) for i, d in enumerate(docs)])
    calls = []
    orig_get = collection.get

    def tracking_get(**kwargs):
        calls.append(kwargs)
        return orig_get(**kwargs)

    collection.get = tracking_get
    monkeypatch.setattr(
        chromadb,
        "PersistentClient",
        type("C", (), {"__init__": lambda self, path=None: None, "get_collection": lambda self, name: collection}),
    )

    by_date = maid_tools.search_diary_fast(date_str="2026-05")
    by_kw = maid_tools.search_diary_fast(keyword="nothing special")
    missing = maid_tools.search_diary_fast(keyword="不存在的词")

    assert "主人过生日" in by_date and "今天写代码" in by_date
    assert "Nothing Special" in by_kw
    assert "没有找到" in missing
    assert calls and all("where_document" in c for c in calls)


# ==================== 跨轮召回缓存 (RecallCacheStore) & 小本本 (NotebookStore) ====================

def test_recall_cache_persistence_and_pipeline_merge(tmp_path, monkeypatch):
    """RecallCacheStore 持久化最近两轮 top-1，且 SessionPipeline._merge_recent_recall 按预期去重与排序。"""
    cache_file = tmp_path / "recall_best.json"
    store = RecallCacheStore(path=str(cache_file))
    monkeypatch.setattr(sp_mod, "recall_cache_store", store)
    monkeypatch.setattr(cfg.rag, "inject_top_k", 3)

    pipeline = SessionPipeline.__new__(SessionPipeline)

    # 第 1 轮：无历史保留，直接取前 3 条，并把 top-1 (A) 存入缓存
    r1 = [{"content": "A", "score": 0.9}, {"content": "B", "score": 0.8}, {"content": "C", "score": 0.7}]
    out1 = pipeline._merge_recent_recall("chat1", r1)
    assert [x["content"] for x in out1] == ["A", "B", "C"]
    assert [x["content"] for x in store.get("chat1")] == ["A"]

    # 第 2 轮：带上一轮 top-1 (A)，新召回补齐 2 条 (D, E)，列表顺序为 新召回 + 保留条目
    r2 = [{"content": "D", "score": 0.95}, {"content": "E", "score": 0.85}, {"content": "F", "score": 0.75}]
    out2 = pipeline._merge_recent_recall("chat1", r2)
    assert [x["content"] for x in out2] == ["D", "E", "A"]

    # 重建实例验证落盘持久化：此时历史保留为 [A, D]（最多 2 条）
    reloaded = RecallCacheStore(path=str(cache_file))
    assert [x["content"] for x in reloaded.get("chat1")] == ["A", "D"]


def test_notebook_store_roundtrip_and_truncation(tmp_path):
    """NotebookStore 支持空文件默认、超长截断到 512 字以及损坏 JSON 容错。"""
    nb_path = tmp_path / "notebook.json"
    store = NotebookStore(path=str(nb_path))
    assert store.load() == ""

    saved = store.save("A" * (NOTEBOOK_MAX_CHARS + 50))
    assert len(saved) == NOTEBOOK_MAX_CHARS
    assert store.load() == "A" * NOTEBOOK_MAX_CHARS

    nb_path.write_text("{corrupted json", encoding="utf-8")
    assert store.load() == ""
