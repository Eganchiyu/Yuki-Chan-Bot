# diary_graph — Yuki 日记概念图谱

外部独立程序组：把 Yuki 的 6000+ 篇日记做成**关键词共现图**，输出一个离线单文件 HTML，
用 vis-network（forceAtlas2Based 物理仿真）呈现"概念星系"，点节点即可看相关日记原文片段。

本分支只做「建图 + 可视化」。话题随机游走 / 自主对抗选目标是后续分支的事。

## 数据来源

直接只读 `../yuki_memory/chroma.sqlite3` 的 `embeddings` / `embedding_metadata` 表
（collection `diaries`），**不依赖 chromadb 包**，也不会加载嵌入模型。

## 安装

```bash
cd diary_graph
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 使用

```bash
# 全量建图（默认：全 6485 篇、每篇 8 个关键词、半衰期 365 天、最多 900 节点）
.venv/bin/python -m diary_graph build

# 打开可视化
.venv/bin/python -m diary_graph serve --port 8778
# 浏览器访问 http://127.0.0.1:8778/mind_map.html
```

产物都在 `output/`：

| 文件 | 说明 |
| --- | --- |
| `mind_map.html` | 单文件可视化（内联 vis-network，离线可用），点节点弹出该概念的相关日记 |
| `graph_stats.md` / `.json` | 核心话题、桥梁话题、介数中心性、簇规模 |
| `keywords_cache.json` | 关键词缓存（词典/停用词/别名改动会自动失效） |

## 四阶段流水线

1. **抽取**（`extract.py`）：`jieba` + 自定义词典（`custom_dict.txt`，Yuki 领域词）+ 别名归一（`aliases.txt`）
   + 词性过滤（n/nr/ns/nt/nz/vn/v/eng）+ TF-IDF Top-K + 停用词（`stopwords.txt`，另叠加主项目 `blacklist.txt`）。
2. **建图**（`graph.py`）：同一篇日记的 Top-K 关键词两两连边，无向加权。
3. **优化**：时间衰减 `weight += 2^(-days_ago/半衰期)`；`--min-weight` 剪弱边；清孤岛；`--max-nodes` 按加权度截断。
4. **可视化**（`render.py`）：节点大小 ∝ 度，颜色 = Louvain 簇，边宽/透明度 ∝ 共现权重；
   支持搜索定位、冻结/继续布局、复位视角、点击看日记片段。

## 常用调参

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| `--top-k` | 8 | 每篇取几个关键词，越大图越噪 |
| `--halflife` | 365 | 时间衰减半衰期（天）；`<=0` 关闭衰减 |
| `--min-weight` | 1.0 | 边权重下限，调高图形更干净、簇更碎 |
| `--max-nodes` | 900 | 只保留加权度最高的概念，前端渲染性能相关 |
| `--resolution` | 1.0 | Louvain 分辨率，调大簇更细 |
| `--extra-stop` | `../blacklist.txt` | 额外屏蔽词文件；想屏蔽某些群友名/口头禅就往这里加 |
| `--limit` | 0 | 只用最新 N 篇 |

示例：想看更干净的"话题"而非"人名星系"：

```bash
.venv/bin/python -m diary_graph build --min-weight 3 --max-nodes 800 --resolution 1.3
```

## 已知局限

- jieba 的 `nr` 词性并不可靠（会把"蔚蓝档案""安卓"标成人名），所以没有做自动去人名；
  高频群友名（Momo、白姐姐…）会成为超级枢纽节点，需要就手工加进 `--extra-stop` 文件。
- 全量剪枝后约 2500 节点 / 12000 边，前端一次渲染 1200 节点较流畅，更多会卡。
- 节点相关日记只内嵌片段（默认 260 字、每节点 8 篇）以控制 HTML 体积（约 7MB）。
