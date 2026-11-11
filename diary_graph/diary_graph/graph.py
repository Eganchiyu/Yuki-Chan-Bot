"""共现建图 + 时间衰减 + 显著性剪枝 + 骨架提取 + 图分析指标。"""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import networkx as nx

from .loader import Diary

_PREFIX = re.compile(r"^\s*【日记\([^)）]*\)】[：:]?\s*")


@dataclass
class GraphBundle:
    graph: nx.Graph
    communities: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, dict] = field(default_factory=dict)
    node_docs: dict[str, list[dict]] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def _decay(days_ago: float, halflife_days: float) -> float:
    if halflife_days <= 0:
        return 1.0
    return math.pow(2.0, -max(days_ago, 0.0) / halflife_days)


def _pmi(co: float, df_u: float, df_v: float, n_docs: int) -> float:
    """点互信息：共现是否比"随机同框"更显著。<=0 说明这条边没有逻辑。"""
    if co <= 0 or df_u <= 0 or df_v <= 0 or n_docs <= 0:
        return float("-inf")
    return math.log((co * n_docs) / (df_u * df_v))


def build_graph(
    entries: list[tuple[list[str], float]],
    *,
    now: float | None = None,
    halflife_days: float = 365.0,
    min_weight: float = 0.0,
    min_pmi: float = 0.0,
    keep_per_node: int = 5,
    max_nodes: int = 0,
) -> nx.Graph:
    """entries = [(关键词列表, 日记时间戳)]，返回剪枝 + 骨架化后的无向加权图。

    边属性：weight = 时间衰减后的共现强度，count = 原始共现篇数。
    """
    if now is None:
        now = max((ts for _, ts in entries), default=0.0)
    now = max(now, max((ts for _, ts in entries), default=0.0))

    G = nx.Graph()
    df: Counter[str] = Counter()          # 词出现于多少篇日记（用于 PMI）
    for kws, ts in entries:
        uniq = list(dict.fromkeys(k for k in kws if k))
        if not uniq:
            continue
        df.update(uniq)
        if len(uniq) < 2:
            G.add_nodes_from(uniq)
            continue
        w = _decay((now - ts) / 86400.0, halflife_days)
        for u, v in itertools.combinations(uniq, 2):
            if G.has_edge(u, v):
                G[u][v]["weight"] += w
                G[u][v]["count"] += 1
            else:
                G.add_edge(u, v, weight=w, count=1)

    n_docs = len(entries)

    # 1) 显著性剪枝：共现不高于随机同框的边直接丢掉
    if min_pmi > float("-inf"):
        drop = [(u, v) for u, v, d in G.edges(data=True)
                if _pmi(d["count"], df[u], df[v], n_docs) < min_pmi]
        G.remove_edges_from(drop)

    # 2) 强度剪枝
    if min_weight > 0:
        G.remove_edges_from([(u, v) for u, v, d in G.edges(data=True)
                             if d["weight"] < min_weight])
    G.remove_nodes_from([n for n, d in G.degree() if d == 0])
    if G.number_of_edges() == 0:
        return G

    # 3) 局部骨架：每个节点只留最强的 N 条边，打破"局部全连接"的致密团块
    if keep_per_node and keep_per_node > 0:
        keep: set[tuple[str, str]] = set()
        for n in G.nodes():
            edges = sorted(G.edges(n, data=True),
                           key=lambda e: e[2]["weight"], reverse=True)
            for u, v, _ in edges[:keep_per_node]:
                keep.add((u, v) if u <= v else (v, u))
        node_set = set(G.nodes())
        keep = {(u, v) for u, v in keep if u in node_set and v in node_set}
        G = G.edge_subgraph(keep).copy()
        G.remove_nodes_from([n for n, d in G.degree() if d == 0])
    if G.number_of_edges() == 0:
        return G

    # 4) 控制规模：只保留加权度最高的 N 个概念
    if max_nodes and G.number_of_nodes() > max_nodes:
        keep_top = sorted(G.degree(weight="weight"), key=lambda x: x[1], reverse=True)
        G = G.subgraph([n for n, _ in keep_top[:max_nodes]]).copy()
        G.remove_nodes_from([n for n, d in G.degree() if d == 0])
    return G


def analyze(G: nx.Graph, seed: int = 42, betweenness_samples: int = 400,
            resolution: float = 1.0) -> GraphBundle:
    """社区划分 + 度/加权度/桥接度/介数中心性。"""
    stats: dict = {}
    if G.number_of_nodes() == 0:
        return GraphBundle(graph=G, stats={"nodes": 0, "edges": 0})

    communities = nx.community.louvain_communities(
        G, weight="weight", seed=seed, resolution=resolution)
    comm_of: dict[str, int] = {}
    for cid, members in enumerate(sorted(communities, key=len, reverse=True)):
        for n in members:
            comm_of[n] = cid

    n_nodes = G.number_of_nodes()
    if n_nodes > 2000:
        k = min(betweenness_samples, n_nodes)
        betweenness = nx.betweenness_centrality(G, k=k, seed=seed)
    else:
        betweenness = nx.betweenness_centrality(G)

    degree = dict(G.degree())
    wdegree = dict(G.degree(weight="weight"))
    clustering = nx.clustering(G, weight=None)

    metrics: dict[str, dict] = {}
    for n in G.nodes():
        neighbor_comms = {comm_of.get(nb, -1) for nb in G.neighbors(n)}
        metrics[n] = {
            "degree": degree[n],
            "weighted_degree": round(wdegree[n], 3),
            "betweenness": round(betweenness.get(n, 0.0), 6),
            # 桥接：邻居里出现了多少个不同簇，越多越像"跨领域十字路口"
            "bridging": len(neighbor_comms - {comm_of.get(n, -1)}),
            "clustering": round(clustering.get(n, 0.0), 3),
            "community": comm_of.get(n, -1),
        }

    stats.update({
        "nodes": n_nodes,
        "edges": G.number_of_edges(),
        "components": nx.number_connected_components(G),
        "largest_component": max(len(c) for c in nx.connected_components(G)),
        "communities": len(communities),
        "avg_degree": round(2 * G.number_of_edges() / n_nodes, 2),
        "density": round(nx.density(G), 6),
        "top_degree": sorted(wdegree.items(), key=lambda x: x[1], reverse=True)[:25],
        "top_betweenness": sorted(
            ((n, m["betweenness"]) for n, m in metrics.items()),
            key=lambda x: x[1], reverse=True)[:25],
        "top_bridging": sorted(
            ((n, m["bridging"], m["degree"]) for n, m in metrics.items()),
            key=lambda x: (x[1], x[2]), reverse=True)[:25],
        "community_sizes": Counter(comm_of.values()).most_common(20),
    })
    return GraphBundle(graph=G, communities=comm_of, metrics=metrics, stats=stats)


def index_node_docs(diaries: list[Diary], keywords: list[list[str]],
                    keep_nodes: set[str], max_per_node: int = 12,
                    snippet_len: int = 260) -> dict[str, list[dict]]:
    """节点 -> 相关日记片段（供前端点节点查看内容）。"""
    node_docs: dict[str, list[dict]] = defaultdict(list)
    for diary, kws in zip(diaries, keywords):
        for k in kws:
            if k not in keep_nodes:
                continue
            bucket = node_docs[k]
            if len(bucket) >= max_per_node:
                continue
            text = _PREFIX.sub("", diary.text)
            bucket.append({
                "id": diary.id,
                "date": diary.date,
                "text": text if len(text) <= snippet_len else text[:snippet_len] + "…",
            })
    return dict(node_docs)


def stats_markdown(stats: dict) -> str:
    lines = [
        "# 日记图谱统计",
        "",
        f"- 节点数: {stats.get('nodes', 0)}",
        f"- 边数: {stats.get('edges', 0)}",
        f"- 簇数(Louvain): {stats.get('communities', 0)}",
        f"- 连通分量: {stats.get('components', 0)}（最大 {stats.get('largest_component', 0)}）",
        f"- 平均度: {stats.get('avg_degree', 0)}　密度: {stats.get('density', 0)}",
        "",
        "## 核心话题（加权度 Top）",
        "",
        *[f"- {n}  `{w}`" for n, w in stats.get("top_degree", [])],
        "",
        "## 桥梁话题（跨簇邻居数 Top）",
        "",
        *[f"- {n}  跨 {b} 簇 / 度 {d}" for n, b, d in stats.get("top_bridging", [])],
        "",
        "## 介数中心性 Top",
        "",
        *[f"- {n}  `{b}`" for n, b in stats.get("top_betweenness", [])],
        "",
        "## 簇规模 Top",
        "",
        *[f"- 簇 {cid}: {size}" for cid, size in stats.get("community_sizes", [])],
    ]
    return "\n".join(lines) + "\n"
