# Yuki 记忆库画像（chroma.sqlite3）

> 生成时间：2026-11-01 12:10（只读体检）
> 重写时间：2026-11-01 12:20（**已执行清理**：删除弃用的 `yuki_memory` collection 并 VACUUM）
> 对象：`/home/asumi/Yuki/yuki_memory/chroma.sqlite3`（容器内 rw bind mount 的同一份文件）

## 0. 一句话结论

- 现在只剩 **两个 collection**：`diaries` 6285 条（日记，核心记忆）、`stickers` 66 条（表情包）。
- 弃用的 `yuki_memory` collection（7830 条结构化记忆实验垃圾 + 其 23 MB HNSW 目录）**已于 2026-11-01 12:15 彻底删除**，VACUUM 后库从 60 MB 收到 33 MB，空闲页归零，文件内已扫不到任何 `ymem_*` / `legacy_*` / `review_status` 残留字符串。
- 删前完整快照在 `yuki_memory/_archive/20261101_121448/`（105 MB，`integrity_check = ok`），可整目录回滚。
- 上层目录 `yuki_memory/` 只是**向量库所在目录名**，与已被删除的 collection 同名纯属历史巧合；`config.py`、`deploy/supervisor.py` 里的 `yuki_memory` 字样都指目录，不涉及该 collection。

## 1. 物理布局

```
yuki_memory/                                   55 MB（不含 _archive）
├── chroma.sqlite3                              33 MB   ← 元数据 + 全文索引 + 队列（本体）
├── 42868517-…-471a3545980a/                    22 MB   ← diaries 的 HNSW 向量索引
├── 52885bff-…-0314a4d61019/                    340 KB  ← stickers 的 HNSW
├── f989647f-…-d2-f851a838b0da/                 328 KB  ← 孤儿目录（无对应 segment，历史残留，未动）
└── _archive/20261101_121448/                   105 MB  ← 清理前整目录备份（含旧 yuki_memory）
```

`backups/` 下的另一套副本：

- `backups/yuki_memory/<YYYYMMDD_HHMMSS>/`：自进化重启前的 rsync 硬链接增量快照（`deploy/supervisor.py::snapshot_memory`），当前保留 7 份（10-24 → 10-31）。**这些都还包含完整的旧 `yuki_memory` collection**，是第二重回滚手段。
- `backups/chroma_before_diary_fix_20261031_0145.sqlite3`：10-31 单条日记修复前的人工整库备份。

## 2. 引擎与持久化安全

| 项目 | 值 |
| --- | --- |
| 库格式 | chromadb 1.5.9（schema v2，`migrations` 表 18 条迁移） |
| 引擎 | SQLite，`journal_mode=delete`、`synchronous=FULL(2)`、页大小 4096、8294 页（VACUUM 后），`freelist_count=0` |
| 向量维度 | 768（`models/text2vec-base-chinese`） |
| 距离 | cosine，HNSW `ef_construction=100 / max_neighbors=16`（diaries/stickers 均 8 线程） |
| 写入路径 | 容器内 `yuki_memory` 是 **rw bind mount**，直接落宿主 `/dev/sda2`(ext4)，无 overlay、无退出时同步 |
| 断电影响 | `synchronous=FULL` → 每次事务提交都 fsync；最坏只丢「正在写的那一个事务」，已提交日记不会丢，库不会损坏 |
| 完整性 | `pragma integrity_check = ok`（清理后实测） |

## 3. 表结构画像

```
collections ──┬──< segments ──┬──< embeddings ──< embedding_metadata        每条记录 = 一行 embedding + N 行 key/value
              │               │                 └< embedding_metadata_array  （数组型 metadata，当前为空）
              │               └── max_seq_id   每个段的递增序列水位
              │
              └── collection_metadata / segment_metadata                   collection/段级别的配置

embedding_fulltext_search (+ _config/_content/_data/_docsize/_idx)       FTS5 全文索引（#document 走这里）
embeddings_queue (+ _queue_config)                                        写入队列/日志（崩溃恢复用）
maintenance_log / migrations / acquire_write / databases / tenants        引擎内部（锁、迁移、库归属）
```

要点：

- `embedding_metadata.id` 是 **整数** 外键，指向 `embeddings.id`，不是 `embedding_id` 字符串；按业务 id 查 metadata 要先 join。
- 每个 collection 固定对应 **两个 segment**：`urn:chroma:segment/vector/hnsw-local-persisted`（向量，落在同名 uuid 目录）和 `urn:chroma:segment/metadata/sqlite`（行 + metadata，落在 `chroma.sqlite3`）。
- 当前 segments 只有 4 条：`42868517`/`7e76ee61`（diaries）、`52885bff`/`fb885ff3`（stickers）。`f989647f` 目录**没有对应 segment 行**，是孤儿，chroma 不会读它。
- `embeddings_queue` 现存 968 行（10-22 至今的写前日志），只含 diaries/stickers 的写入，无已删数据残留。

## 4. 两个现役 collection

### 4.1 `diaries`（日记，核心记忆）

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

  即「3 月到 11 月」的完整跨度都在，其中 `[熔炼记忆]` 287 条、`【日记(...)】` 5945 条、纯文本/其他 53 条。
- 体量：最长 842 字，平均 200 字。完全重复的文档只有 2 组（涉及 4 条），基本干净。
- 按群分布（top）：`1057020972` 3702、`1034986009` 1039、`818038143` 550、`495881825` 354、`742134223` 129、`782427668` 126。
- 代码入口：`modules/memory/rag.py`（`search_diaries` / `add` / `clean_duplicate_diaries`）。

### 4.2 `stickers`（表情包）

- 66 条，`embedding_id` 形如 `sticker_<unixts>_<rand>`。
- metadata：`description`、`emotion`、`tags`、`usage_scenarios`、`image_ref`、`owner`、`chat_id`、`preference`、`heat`、`use_count`、`create_time`、`last_used_time`。
- 代码入口：`modules/stickers/manager.py`。

## 5. 已删除的 `yuki_memory` collection（清理记录）

### 5.1 它曾经是什么

2026-04-22 → 06-14 结构化记忆实验的产物，共 7830 条、`status` 全 `active`、`review_status` 全 `approved`，代码里零引用（无 `get_collection("yuki_memory")`）。构成：

| 前缀 | 条数 | 含义 |
| --- | --- | --- |
| `legacy_diary_*` | 3310 | 早期日记原样搬进来的副本 |
| `legacy_mem_summary_*` | 223 | 早期日记摘要副本 |
| `ymem_fact_cand_*` | 2045 | 抽取出的「事实」 |
| `ymem_preference_*` | 941 | 「偏好」 |
| `ymem_relationship_*` | 791 | 「关系」 |
| `ymem_event_cand_*` | 397 | 「事件」 |

用户口中的「几千条失败品」= 其中 4297 条 fact/preference/relationship/event 候选记忆 + 3533 条日记摘要副本。

### 5.2 实际做了什么（2026-11-01）

1. `12:14:48` 备份：`rsync -a --exclude _archive ./ _archive/20261101_121448/`（105 MB，备份库 `integrity_check=ok`）。
2. `12:15` 走 chromadb API 删除：容器镜像 `55597bd6a186`（chromadb 1.5.9）挂载同一目录执行 `client.delete_collection("yuki_memory")` —— 而不是 `DELETE FROM`，保证 segments / embeddings / embedding_metadata / FTS5 同步清干净。
3. 手工删除 API 未清理的 HNSW 剩余目录 `67437597-0315-4828-95a6-4d68948e2e01/`（23 MB）。
4. `VACUUM` 整库，回收 6597 个空闲页，把已删数据在页里的残影一并擦掉。

### 5.3 清理后的验证结果

| 检查项 | 结果 |
| --- | --- |
| `collections` 表 | 只剩 `diaries`、`stickers` |
| `segments` / `max_seq_id` | 各 4 条，无孤儿子段 |
| `embeddings` | 6351（6285 + 66），`embedding_metadata` 40706 行，FTS5 6351 行，全部对得上 |
| 独有 metadata 键（`scope`/`source`/`review_status`/`candidate_id`/`evidence`/`time_scope`/`source_diary_id`/`supersedes`…） | 计数全为 0 |
| 文件内字符串扫描（`ymem_fact`/`ymem_preference`/`review_status`/`legacy_diary`/`llm_candidate_backfill`…） | 全 0 命中 |
| `integrity_check` | ok |
| 文件体积 / 页数 / 空闲页 | 63,397,888 B → 33,972,224 B；15478 → 8294 页；freelist 6597 → 0 |
| 功能抽查（chromadb API） | `diaries.count()=6285`、`stickers.count()=66`，`get()` 正常返回日记正文与 metadata |

### 5.4 回滚方法

```bash
# 整目录回滚（容器先停）
docker stop yuki
rsync -a --delete /home/asumi/Yuki/yuki_memory/_archive/20261101_121448/ /home/asumi/Yuki/yuki_memory/
docker start yuki
```

`backups/yuki_memory/20261031_021058/`（清理前最后一份快照）同样含完整旧库，可作第二重回滚源。

## 6. 已知残留与建议

1. **孤儿 HNSW 目录 `f989647f-74e8-4bbd-bbd2-f851a838b0da/`（328 KB）**：`header.bin`+`data_level0.bin`+`length.bin` 指向一份极小的旧索引，DB 里没有对应 segment，chroma 不会读。留着无害，想清可以直接删目录（删前先确认没有 segment 行指向它）。
2. `_archive/20261101_121448/` 占 105 MB 且位于 `yuki_memory/` 内，会被 `supervisor.py::snapshot_memory` 的 rsync 快照一并复制。确认不再需要回滚后，建议把它移到 `backups/` 或删除，避免快照体积翻倍。
3. `core/maid/maid_charter.py` 第 91 条把 `yuki_memory/` 列为「不可再生资产」—— 指的是目录本身（仍存在），collection 删除不影响该条判定，但描述措辞可以顺手更正。
4. `diaries` 若想收敛旧格式记录，`modules/memory/rag.py::clean_duplicate_diaries(dry_run=True)` 可先出报告（目前全库只有 2 组重复，收益很小）。

## 7. 复现这份体检

```bash
# 只读打开，随便查（容器在跑也可以用 mode=ro）
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('file:/home/asumi/Yuki/yuki_memory/chroma.sqlite3?mode=ro', uri=True)
print("collections:", c.execute("select name from collections").fetchall())
for name, in c.execute("select name from collections"):
    seg = c.execute(
        "select id from segments where collection=(select id from collections where name=?) "
        "and scope='METADATA'", (name,)).fetchone()[0]
    print(name, c.execute("select count(*) from embeddings where segment_id=?", (seg,)).fetchone()[0])
print("integrity:", c.execute("pragma integrity_check").fetchone()[0])
print("pages:", c.execute("pragma page_count").fetchone()[0],
      "freelist:", c.execute("pragma freelist_count").fetchone()[0])
PY
```

> 注意：**不要**在容器运行时用非 chromadb 的方式改这个文件（读用 `mode=ro` 没问题）；写操作（删除 collection、VACUUM）必须停容器后进行，改完再 `docker start yuki`。
