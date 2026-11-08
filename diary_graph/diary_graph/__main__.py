"""命令行入口：python -m diary_graph {build,serve}"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import socketserver
import sys
import time
from pathlib import Path

from .config import DEFAULT_DB, DEFAULT_EXTRA_STOP, DEFAULT_OUT, ROOT, BuildOptions
from .extract import KeywordExtractor
from .graph import index_node_docs, stats_markdown
from .graph import analyze, build_graph
from .loader import load_diaries
from .render import render

CACHE_NAME = "keywords_cache.json"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _lexicon_fingerprint(top_k: int, extra_stop=None) -> str:
    """词典/停用词/别名任一改动都应让缓存失效。"""
    h = hashlib.md5(f"topk={top_k}".encode())
    files = [ROOT / "custom_dict.txt", ROOT / "stopwords.txt", ROOT / "aliases.txt"]
    if extra_stop:
        files.append(Path(extra_stop))
    for f in files:
        p = Path(f)
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()[:16]


def _extract_all(diaries, opts: BuildOptions, cache_path: Path, extra_stop=None):
    extractor = KeywordExtractor(ROOT, extra_stop=extra_stop)
    fingerprint = _lexicon_fingerprint(opts.top_k, extra_stop)
    cache: dict[str, dict] = {}
    if opts.use_cache and cache_path.exists():
        try:
            blob = json.loads(cache_path.read_text(encoding="utf-8"))
            if blob.get("fingerprint") == fingerprint:
                cache = blob.get("items", {})
        except (json.JSONDecodeError, AttributeError):
            cache = {}

    keywords: list[list[str]] = []
    hits = 0
    t0 = time.time()
    for i, diary in enumerate(diaries, 1):
        digest = hashlib.md5(diary.text.encode("utf-8")).hexdigest()[:12]
        entry = cache.get(diary.id)
        if entry and entry.get("h") == digest:
            keywords.append(entry["kw"])
            hits += 1
        else:
            kw = extractor.extract(diary.text, top_k=opts.top_k)
            keywords.append(kw)
            cache[diary.id] = {"h": digest, "kw": kw}
        if i % 500 == 0:
            _log(f"  关键词抽取 {i}/{len(diaries)}（缓存命中 {hits}）…")
    _log(f"关键词抽取完成，用时 {time.time() - t0:.1f}s，缓存命中 {hits}/{len(diaries)}")

    if opts.use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"fingerprint": fingerprint, "items": cache}, ensure_ascii=False),
            encoding="utf-8")
    return keywords


def cmd_build(args: argparse.Namespace) -> int:
    opts = BuildOptions(
        db=Path(args.db), out_dir=Path(args.out), collection=args.collection,
        limit=args.limit, top_k=args.top_k, halflife_days=args.halflife,
        min_weight=args.min_weight, max_nodes=args.max_nodes,
        max_docs_per_node=args.max_docs, snippet_len=args.snippet_len,
        use_cache=not args.no_cache,
    )
    _log(f"读取记忆库: {opts.db}（collection={opts.collection}）")
    diaries = load_diaries(opts.db, opts.collection, limit=opts.limit or None)
    if not diaries:
        _log("没有读到任何日记，检查 --db / --collection")
        return 1
    _log(f"日记 {len(diaries)} 篇，时间范围 {diaries[0].date} ~ {diaries[-1].date}")

    keywords = _extract_all(diaries, opts, opts.out_dir / CACHE_NAME,
                            extra_stop=args.extra_stop)
    entries = [(kw, d.timestamp) for d, kw in zip(diaries, keywords)]

    _log(f"建图: 半衰期 {opts.halflife_days:g} 天，剪枝阈值 {opts.min_weight}，最多保留 {opts.max_nodes or '不限'} 节点")
    G = build_graph(entries, halflife_days=opts.halflife_days,
                    min_weight=opts.min_weight, max_nodes=opts.max_nodes)
    if G.number_of_nodes() == 0:
        _log("剪枝后图为空，请降低 --min-weight 或提高 --max-nodes")
        return 1

    _log(f"图规模 {G.number_of_nodes()} 节点 / {G.number_of_edges()} 边，计算簇与桥接…")
    bundle = analyze(G, resolution=args.resolution)
    bundle.node_docs = index_node_docs(
        diaries, keywords, set(G.nodes()), max_per_node=opts.max_docs_per_node,
        snippet_len=opts.snippet_len)

    html_path = render(bundle, opts.out_dir / "mind_map.html",
                       title=f"Yuki 日记图谱（{len(diaries)} 篇）")
    md_path = opts.out_dir / "graph_stats.md"
    md_path.write_text(stats_markdown(bundle.stats), encoding="utf-8")
    (opts.out_dir / "graph_stats.json").write_text(
        json.dumps(bundle.stats, ensure_ascii=False, indent=2), encoding="utf-8")

    _log(f"完成:\n  {html_path}\n  {md_path}")
    print(f"{bundle.stats['nodes']}\t{bundle.stats['edges']}\t{bundle.stats['communities']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    root = Path(args.dir).resolve()
    if not root.exists():
        _log(f"目录不存在: {root}，先跑 build")
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        _log(f"服务中: http://127.0.0.1:{args.port}/mind_map.html  （Ctrl-C 结束）")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            _log("已停止")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m diary_graph",
        description="Yuki 日记共现图谱：建图 + 物理仿真可视化（离线单文件 HTML）")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="抽取关键词、建图、输出 HTML 与统计")
    b.add_argument("--db", default=str(DEFAULT_DB), help="chroma.sqlite3 路径")
    b.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    b.add_argument("--collection", default="diaries")
    b.add_argument("--limit", type=int, default=0, help="只用最新 N 篇（0=全部）")
    b.add_argument("--top-k", type=int, default=8, help="每篇关键词数")
    b.add_argument("--halflife", type=float, default=365.0,
                   help="时间衰减半衰期（天），<=0 关闭")
    b.add_argument("--min-weight", type=float, default=1.0, help="边权重剪枝阈值")
    b.add_argument("--max-nodes", type=int, default=900,
                   help="保留加权度最高的 N 个概念（0=不限）")
    b.add_argument("--max-docs", type=int, default=8, help="每个概念最多挂几篇日记")
    b.add_argument("--snippet-len", type=int, default=260, help="日记片段长度")
    b.add_argument("--extra-stop", default=str(DEFAULT_EXTRA_STOP),
                   help="额外屏蔽词文件（默认复用主项目 blacklist.txt）")
    b.add_argument("--resolution", type=float, default=1.0,
                   help="Louvain 分辨率，越大簇越细")
    b.add_argument("--no-cache", action="store_true", help="忽略关键词缓存")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="本地 http 服务打开生成的图谱")
    s.add_argument("--port", type=int, default=8778)
    s.add_argument("--dir", default=str(DEFAULT_OUT))
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
