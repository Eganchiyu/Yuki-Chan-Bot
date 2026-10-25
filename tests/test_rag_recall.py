"""日记召回打分/重排的单元测试（不依赖真实向量库与 embedding 模型）。"""
import datetime
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from modules.memory.rag import (  # noqa: E402
    RECENCY_FLOOR,
    MemoryRAG,
)


class _FakeModel:
    def encode(self, text):
        return _FakeVector()


class _FakeVector:
    def tolist(self):
        return [0.1, 0.2, 0.3]


class _FakeCollection:
    """极简 Chroma collection：只支持 count/query/get，where_document 只实现 $contains。"""

    def __init__(self, docs):
        # docs: [(id, content, metadata, distance)]
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
            return all(_FakeCollection._match(content, cond) for cond in where_document["$and"])
        if "$or" in where_document:
            return any(_FakeCollection._match(content, cond) for cond in where_document["$or"])
        needle = where_document.get("$contains", "")
        return needle in content


def _make_rag(docs):
    rag = object.__new__(MemoryRAG)
    rag.collection = _FakeCollection(docs)
    rag.model = _FakeModel()
    rag.name_blacklist = []
    return rag


def test_relevance_not_polluted_by_boosts():
    item = MemoryRAG._calculate_final_item(
        "【日记(2026-10-20 10:00)】：小雨和 Yuki 打游戏",
        {"chat_id": "10001"},
        0.42,
        [("打游戏", 0.8)],
        chat_id="10001",
        speaker_names=["小雨"],
    )
    assert item["relevance"] == 0.42
    assert item["score"] > item["relevance"]
    assert item["decay"] == 1.0 or item["decay"] < 1.0


def test_recency_decay_prefers_recent_diary():
    now = datetime.datetime(2026, 10, 25, 12, 0).timestamp()
    recent = MemoryRAG._calculate_final_item("【日记(2026-10-24 10:00)】：同一件事", {}, 0.6, [], now=now)
    old = MemoryRAG._calculate_final_item("【日记(2024-01-01 10:00)】：同一件事", {}, 0.6, [], now=now)
    undated = MemoryRAG._calculate_final_item("没有日期前缀的日记", {}, 0.6, [], now=now)

    assert recent["decay"] > 0.99
    assert RECENCY_FLOOR <= old["decay"] < recent["decay"]
    assert undated["decay"] == 1.0
    assert recent["score"] > old["score"]


def test_recency_decay_uses_metadata_timestamp_fallback():
    now = datetime.datetime(2026, 10, 25, 12, 0).timestamp()
    old_ts = datetime.datetime(2025, 1, 1).timestamp()
    item = MemoryRAG._calculate_final_item("无日期前缀", {"timestamp": old_ts}, 0.6, [], now=now)
    assert item["decay"] < 1.0


def test_keyword_coverage_scales_down_weak_single_hit():
    keywords = [("一起", 0.4), ("打游戏", 0.35), ("周末", 0.25)]
    total = 1.0
    weak = MemoryRAG._keyword_coverage("【日记(2026-10-20)】：今天一起很累", keywords, total)
    strong = MemoryRAG._keyword_coverage("【日记(2026-10-20)】：周末打游戏", keywords, total)

    assert weak < strong
    assert MemoryRAG._keyword_coverage("完全不相关", keywords, total) == 0.0


def test_search_diaries_ignores_stopword_only_keyword_pool_hit():
    docs = [
        # 语义最相关
        ("d1", "【日记(2026-10-24 10:00)】：周末和主人一起打游戏，好开心", {"chat_id": "10001"}, 0.10),
        # 只命中虚词"今天"，且是同群老日记
        ("d2", "【日记(2024-01-01 10:00)】：今天很累", {"chat_id": "10001"}, 0.95),
        ("d3", "【日记(2024-02-01 10:00)】：今天吃了面", {"chat_id": "10001"}, 0.96),
    ]
    rag = _make_rag(docs)
    results = rag.search_diaries("周末要不要一起打游戏", chat_id="10001", n_results=2)

    assert results
    assert results[0]["content"].startswith("【日记(2026-10-24")
    assert all("relevance" in r for r in results)
    assert all(0.0 <= r["relevance"] <= 1.0 for r in results)


def test_search_diaries_keeps_other_chat_recall_when_more_relevant():
    docs = [
        ("d1", "【日记(2026-10-24 10:00)】：别的群聊讨论代码报错", {"chat_id": "20002"}, 0.10),
        ("d2", "【日记(2026-10-24 10:00)】：这个群聊聊了别的事", {"chat_id": "10001"}, 0.90),
    ]
    rag = _make_rag(docs)
    results = rag.search_diaries("代码报错", chat_id="10001", n_results=1)
    assert results[0]["metadata"]["chat_id"] == "20002"


def test_search_diary_fast_uses_where_document_instead_of_full_scan():
    import chromadb
    from core.maid import maid_tools

    docs = [
        "【日记(2026-05-20 10:00)】：主人过生日",
        "【日记(2026-05-21 10:00)】：今天写代码",
        "【日记(2026-06-01 10:00)】：Nothing Special",
    ]
    collection = _FakeCollection([(f"id{i}", d, {}, 0.5) for i, d in enumerate(docs)])
    calls = []

    class _Client:
        def __init__(self, path=None):
            pass

        def get_collection(self, name):
            return collection

    original_get = collection.get

    def tracking_get(**kwargs):
        calls.append(kwargs)
        return original_get(**kwargs)

    collection.get = tracking_get
    original_client = chromadb.PersistentClient
    chromadb.PersistentClient = _Client
    try:
        by_date = maid_tools.search_diary_fast(date_str="2026-05")
        by_keyword = maid_tools.search_diary_fast(keyword="nothing special")
        missing = maid_tools.search_diary_fast(keyword="不存在的词")
    finally:
        chromadb.PersistentClient = original_client

    assert "主人过生日" in by_date and "今天写代码" in by_date
    assert "Nothing Special" in by_keyword
    assert "没有找到" in missing
    # 每次查询都带 where_document，说明没有走全表拉取
    assert calls and all("where_document" in c for c in calls)


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")
