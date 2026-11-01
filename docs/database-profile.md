# Yuki 记忆库画像（chroma.sqlite3）

> 生成时间：2026-11-01 12:10（只读体检，**未做任何增删改**）
> 数据来源：`/home/asumi/Yuki/yuki_memory/chroma.sqlite3`（容器内 rw bind 挂载的同一份文件）

## 0. 一句话结论

- 三个 collection：`diaries` 6285 条（现役）、`stickers` 66 条（现役）、`yuki_memory` 7830 条（**已弃用的结构化记忆，仍在库里，没被删**）。
- 你记得的「几千条失败品」= `yuki_memory` 里的 4297 条 `fact / preference / relationship / event` 候选记忆，加上 3533 条日记摘要副本，共 7830 条，`status` 全是 `active`。
- 该 collection 最后写入时间为 **2026-06-14**，此后完全静默；**当前代码里没有任何地方读写它**（只有 `diaries` / `stickers` 被 `get_or_create_collection`），属于孤儿数据，占约 23 MB 向量 + 库内行。

## 1. 物理布局

```
yuki_memory/                                   105 MB
├── chroma.sqlite3                              60 MB   ← 元数据 + 全文索引 + 队列（本体）
├── 42868517-…-471a3545980a/                    22 MB   ← diaries 的 HNSW 向量索引
├── 67437597-…-4d68948e2e01/                    23 MB   ← yuki_memory 的 HNSW 向量索引（弃用仍在）
├── 52885bff-…-0314a4d61019/                   340 KB   ← stickers 的 HNSW
└── f989647f-…-d2-f851a838b0da/                328 KB   ← 另一段（历史残留/元数据）
```

同名路径在 `backups/` 下还有副本：
`backups/yuki_memory/<YYYYMMDD_HHMMSS>/` 是自进化重启前的 rsync 硬链接增量快照（`deploy/supervisor.py::snapshot_memory`，保留最近若干份）；
`backups/chroma_before_diary_fix_20261031_0145.sqlite3` 是 10-31 单条日记修复前的人工整库备份。

## 2. 引擎与持久化安全

| 项目 | 值 |
| --- | --- |
| 库格式 | chromadb 1.5.9（schema v2，`migrations` 表 18 条迁移） |
| 引擎 | SQLite，`journal_mode=delete`、`synchronous=FULL(2)`、页大小 4096、15478 页 |
| 向量维度 | 768（`models/text2vec-base-chinese`） |
| 距离 | cosine，HNSW `ef_construction=100 / max_neighbors=16`（`yuki_memory` 那套是 28 线程，其余 8 线程） |
| 写入路径 | 容器内 `yuki_memory` 是 **rw bind mount**，直接落宿主 `/dev/sda2`(ext4)，无 overlay、无退出时同步 |
| 断电影响 | `synchronous=FULL` → 每次事务提交都 fsync；最坏只丢「正在写的那一个事务」，已提交日记不会丢，库不会损坏 |

## 3. 表结构画像

```
collections ──┬──< segments ──┬──< embeddings ──< embedding_metadata        每条记录 = 一行 embedding + N 行 key/value
              │               │                 └< embedding_metadata_array  （数组型 metadata）
              │               └── max_seq_id   每个段的递增序列水位
              │
              └── collection_metadata / segment_metadata                   collection/段级别的配置

embedding_fulltext_search (+ _config/_content/_data/_docsize/_idx)       FTS5 全文索引（#document 走这里）
embeddings_queue (+ _queue_config)                                        写入队列/日志（崩溃恢复用）
maintenance_log / migrations / acquire_write / databases / tenants        引擎内部（锁、迁移、库归属）
```

每个 collection 固定对应 **两个 segment**：`urn:chroma:segment/vector/hnsw-local-persisted`（向量，落在同名 uuid 目录）和 `urn:chroma:segment/metadata/sqlite`（行 + metadata，落在 `chroma.sqlite3`）。`embeddings` 表按 metadata 段统计即等于业务记录数。

## 4. 三个 collection

### 4.1 `diaries`（现役，核心记忆）

- 记录数 **6285**，`embedding_id` 前缀：`diary_*` 3286 条 + `mem_summary_*` 2999 条（两代命名并存）。
- metadata 键：`chroma:document`、`chat_id`、`timestamp` 全员都有；`type`/`status`/`importance`/`confidence`/`created_at`/`updated_at`/`access_count` 只在新格式 2999 条上有（旧格式 3286 条没有）。
- 取值：`type=summary`（2999），`status=active`（2999），`importance=3`，`confidence=1.0`，`access_count=0`。
- 文档内自带日期的分布（比 metadata 时间戳更能代表真实时间）：

  | 月份 | 条数 |
  | --- | --- |
  | 2026-03 | 388 |
  | 2026-04 | 767 |
  | 2026-05 | 1344 |
  | 2026-06 | 1747 |
  | 2026-07 | 642 |
  | 2026-08 | 427 |
  | 2026-09 | 481 |
  | 2026-10 | 198 |
  | 2026-11 | 4 |
  | 无日期标记 | 287 |

  即「3 月一直到 11 月」的完整跨度都在，其中 `[熔炼记忆]` 287 条、`【日记(...)】` 5945 条、纯文本 51 条、其他 2 条。
- 体量：最长 842 字，平均 201 字。完全重复的文档只有 2 组（涉及 4 条），基本干净。
- 按群分布（top）：`1057020972` 3702、`1034986009` 1039、`818038143` 550、`495881825` 354、`742134223` 129…
- 代码入口：`modules/memory/rag.py`（`search_diaries` / `add` / `clean_duplicate_diaries`）。

### 4.2 `stickers`（现役，表情包）

- 66 条，`embedding_id` 形如 `sticker_<unixts>_<rand>`。
- metadata：`description`、`emotion`、`tags`、`usage_scenarios`、`image_ref`、`owner`、`chat_id`、`preference`、`heat`、`use_count`、`create_time`、`last_used_time`。
- 代码入口：`modules/stickers/manager.py`。

### 4.3 `yuki_memory`（**已弃用**，结构化记忆实验）

- 记录数 **7830**，`embedding_id` 前缀能直接看出两批货：

  | 前缀 | 条数 | 含义 |
  | --- | --- | --- |
  | `legacy_diary_*` | 3310 | 早期日记原样搬进来的副本 |
  | `legacy_mem_summary_*` | 223 | 早期日记摘要副本 |
  | `ymem_fact_cand_*` | 2045 | 抽取出的「事实」 |
  | `ymem_preference_*` | 941 | 「偏好」 |
  | `ymem_relationship_*` | 791 | 「关系」 |
  | `ymem_event_cand_*` | 397 | 「事件」 |

- metadata 两套：全员 15 个键（`type/status/scope/source/subject/supersedes/source_ids/importance/confidence/...`），其中 4297 条候选记忆额外带 `candidate_id/candidate_type/evidence/review_status/review_reason/risk/time_scope/source_diary_id`。
- 取值：`type` = summary 3533 / fact 2168 / preference 941 / relationship 791 / event 397；`source` = `legacy_diary` 3533 + `llm_candidate_backfill` 4297；`status` 全 `active`；`scope` 全 `group`；`review_status` 全 `approved`；`risk` 全 `low`。
- `time_scope`：long_term 2312 / short_term 914 / past 805 / unknown 254 / future 12。
- 时间范围 `created_at`：**2026-04-22 19:38 → 2026-06-14 19:22**（按月 3400 / 2927 / 1503），之后再无写入。
- `subject` 分布（top）：群聊 3547、Yuki 925、主人 458、yuki 428、主人哥哥 329、YukiV6 244…
- 代码引用：**零**。全仓只有目录名 `yuki_memory/` 和 `maid_charter.py` 的敏感词表提到这个字样，没有任何 `get_collection("yuki_memory")`。

## 5. 「失败品该删掉了吗」核查结论

不是「已经被删掉」，而是「还在，只是没人用了」：

| 你的预期 | 实际 |
| --- | --- |
| 结构化记忆（fact/preference/relationship/event）已被删除 | 仍在，4297 条，`status` 全 `active`、`review_status` 全 `approved` |
| 只剩 diary 和表情包两个字段/集合 | 多了整个 `yuki_memory` collection（7830 行 + 23 MB HNSW 索引） |

补充证据：库里/备份里 7 份历史快照对照（`backups/yuki_memory/*/chroma.sqlite3`）：

| 快照 | diaries | stickers | yuki_memory |
| --- | --- | --- | --- |
| 2026-10-24 14:55 | 6171 | 66 | 7830 |
| 2026-10-27 17:40 | 6197 | 66 | 7830 |
| 2026-10-28 12:46 | 6206 | 66 | 7830 |
| 2026-10-29 00:09 | 6216 | 66 | 7830 |
| 2026-10-31 02:10 | 6267 | 66 | 7830 |
| 现在（11-01 12:06） | 6285 | 66 | 7830 |

即：`diaries` 一直在长，`yuki_memory` 从 6-14 起就冻在 7830，**没有人删过它**。

顺带解开一个疑点：之前小女仆汇报「日记总数 14164」，与现在的 6285 对不上——`6267 + 66 + 7830 = 14163`（10-31 那天），也就是她数的是**整库三张 collection 的总行数**，不是日记数。

## 6. 建议（都还没执行，等你决定）

1. **留档再动**：真要清理，先 `rsync -a yuki_memory/ backups/yuki_memory_prune_$(date +%Y%m%d_%H%M%S)/`，确认可回滚再删。
2. **删除方式**：走 chromadb API（`client.delete_collection("yuki_memory")`）而不是 `DELETE FROM`，否则 HNSW 目录和 FTS 表会留垃圾；删完记得让 `67437597-…` 这个 23 MB 的向量目录一起走。
3. **先冻结再删**：先在代码里确认没有隐式引用（目前确认是无引用），再删；`maid_charter.py` 第 91 条把 `yuki_memory/` 列为不可再生资产，删之前最好同步那条描述，免得小女仆判定违规。
4. `diaries` 若想收敛旧格式记录，`modules/memory/rag.py::clean_duplicate_diaries(dry_run=True)` 可以先出报告不落刀（目前全库只有 2 组重复，收益很小）。

## 7. 复现这份体检

```bash
# 只读打开，随便查
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('file:/home/asumi/Yuki/yuki_memory/chroma.sqlite3?mode=ro', uri=True)
for name in ("diaries", "stickers", "yuki_memory"):
    seg = c.execute(
        "select id from segments where collection=(select id from collections where name=?) "
        "and scope='METADATA'", (name,)).fetchone()[0]
    print(name, c.execute("select count(*) from embeddings where segment_id=?", (seg,)).fetchone()[0])
PY
```

> 注意：容器在跑时**不要**用非 chromadb 的方式改这个文件；体检一律用 `mode=ro` 连接。
