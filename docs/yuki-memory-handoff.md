# Yuki-Memory 全量重构交接文档

> 本文档用于交接给后续 LLM / 开发者继续实现。请先完整阅读本文档，再进行代码修改。

---

## 0. 当前任务背景

YukiV6 当前已有一套基础记忆系统：

- 短期上下文：`data/chat_history.json` + `HistoryManager`
- 长期记忆：`modules/memory/rag.py` 中的 ChromaDB 日记库
- 日记总结：`core/engine.py::do_summarize()`
- 回复前检索：`core/session_pipeline.py::retrieve_memories()` 调用 `MemoryRAG.search_diaries()`
- Prompt 注入：`core/prompts.py::build_chat_context()` 把检索到的日记作为 `【回忆】` system 消息插入

但现在用户已经明确提出：

> 不再只是小修 RAG，而是要把现有 memory 模块整体改造成新的 `yuki-memory`。旧系统和新系统唯一的历史连接点是已经导出的 3244 条旧日记。

用户的新目标是：

1. 上下文可以保留得更长。
2. 不再频繁整理和裁剪上下文。
3. 每天只整理 / 释放 1-2 次。
4. Prompt 构建要尽量提高 token cache 命中率。
5. 旧的 `modules/memory/rag.py` 未来应降级为兼容层或迁移工具。
6. 新的主记忆系统应命名 / 定位为 `yuki-memory`。
7. 旧的 3244 条日记应作为新系统的唯一历史连接源。

---

## 1. 当前分支与已完成工作

当前开发分支：

```text
feature/yuki-memory-lite
```

已经完成的文件改动：

| 文件 | 状态 | 说明 |
|---|---|---|
| `modules/memory/rag.py` | 已修改 | 新增 `save_memory()` 和标准 metadata 构造函数；`save_diary()` 改为 `summary` 包装 |
| `scripts/03_RAG_Tools/export_memory.py` | 已重写 | 支持导出全量日记并生成统计 |
| `scripts/03_RAG_Tools/backfill_memory_candidates.py` | 已新增 | 支持从旧日记备份中离线提取结构化记忆候选 |
| `tests/test_yuki_memory_lite.py` | 已新增 | 覆盖 metadata、导出统计、候选清洗、JSON 解析 |
| `docs/changelog.md` | 已更新 | 已记录本轮新增内容 |

注意：这些只是“第一阶段脚手架”，不是完整 yuki-memory 主流程。

---

## 2. 当前数据导出结果

已经成功导出旧日记库。

导出文件：

```text
data/memory_exports/diaries_backup_20260608_234723.json
data/memory_exports/diaries_stats_20260608_234723.json
```

统计结果：

```json
{
  "total": 3244,
  "empty_count": 0,
  "duplicate_count": 0,
  "average_length": 259.36,
  "max_length": 842,
  "min_length": 60,
  "time_range": {
    "earliest": "2026-04-22T19:38:30.532695",
    "latest": "2026-06-08T23:39:14.011338"
  },
  "by_chat_id": {
    "1057020972": 1955,
    "1034986009": 657,
    "620127376": 125,
    "1056258919": 122,
    "818038143": 98,
    "495881825": 94,
    "782427668": 75,
    "742134223": 66,
    "620230095": 29,
    "1085409165": 10,
    "1057868210": 10,
    "2962538973": 2,
    "737337230": 1
  },
  "by_type": {
    "summary": 3244
  },
  "by_status": {
    "legacy": 3244
  },
  "missing_standard_fields": {
    "type": 3244,
    "status": 3244,
    "confidence": 3244,
    "importance": 3244
  }
}
```

结论：

- 当前旧日记数据质量很好：无空内容、无重复。
- 全部都是 legacy summary，没有标准 metadata。
- 适合将其作为 yuki-memory 新系统的历史种子。
- 不应直接在旧 `diaries` collection 上继续堆功能，建议新建 `yuki_memory` collection。

---

## 3. 当前代码结构关键位置

### 3.1 旧 RAG 记忆模块

```text
modules/memory/rag.py
```

关键类：

```python
class MemoryRAG:
```

当前职责：

- 初始化 ChromaDB collection `diaries`
- 加载 embedding 模型
- 保存日记
- 检索日记
- 清理重复日记

已新增接口：

```python
MemoryRAG._build_memory_metadata(...)
MemoryRAG.save_memory(...)
MemoryRAG.save_diary(...)
```

`save_memory()` 当前写入 metadata：

```json
{
  "type": "summary",
  "status": "active",
  "confidence": 1.0,
  "importance": 3,
  "timestamp": 1780000000,
  "created_at": 1780000000,
  "updated_at": 1780000000,
  "access_count": 0,
  "chat_id": "...",
  "people": "...",
  "emotion": "...",
  "subject": "...",
  "supersedes": "...",
  "source_ids": "[...]"
}
```

但注意：这只是旧模块上的兼容增强，不是最终 yuki-memory 架构。

---

### 3.2 当前主流程

```text
core/session_pipeline.py
```

关键方法：

```python
prepare_chat_context()
decide_reply_action()
retrieve_memories()
generate_reply()
finalize_conversation()
```

当前记忆检索：

```python
relevant_diaries = self.memory_rag.search_diaries(
    combined_text,
    chat_id=chat_id,
    top_k=dynamic_top_k,
)
```

位置：

```text
core/session_pipeline.py::retrieve_memories()
```

当前保存上下文并触发总结：

```python
if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
    summarized_list = await self.engine.do_summarize(chat_id, history_dict[chat_id])
```

位置：

```text
core/session_pipeline.py::finalize_conversation()
```

这是未来要替换的核心逻辑之一。

---

### 3.3 当前日记总结

```text
core/engine.py
```

关键方法：

```python
YukiEngine.do_summarize()
YukiEngine.idle_diary_checker()
```

当前逻辑：

```text
历史过长 / 空闲触发
  → LLM 总结为一篇日记
  → rag.save_diary()
  → 只保留最近 cfg.KEEP_LAST_DIALOGUE 条上下文
```

这与用户新目标冲突，因为用户希望：

```text
上下文保留很长
一天只整理/释放 1-2 次
不要频繁总结和裁剪
```

因此未来要将 `do_summarize()` 降级为旧逻辑或迁移为 `daily_consolidate()`。

---

### 3.4 当前 Prompt 构建

```text
core/prompts.py
```

关键函数：

```python
build_chat_context(...)
```

当前结构：

```text
system prompt
【回忆】日记 1
【回忆】日记 2
...
工具链约束
破冰指令（可选）
最近 cfg.KEEP_LAST_DIALOGUE 条对话
当前时间 + 当前输入
```

问题：

- 每次插入的回忆数量不同。
- 回忆内容随当前输入变化。
- 当前时间进入 prompt。
- 最近上下文很短。
- system 前缀变化较多，不利于 token cache 命中。

未来需要改为 cache-friendly prompt 构建。

---

## 4. 用户最终效果需求

这是最重要的部分。后续实现必须以此为准。

### 4.1 记忆系统目标

最终要实现：

```text
Yuki-Memory：一个替代现有 MemoryRAG 的分层长期记忆系统。
```

它要支持：

1. L1 RAW 原始痕迹
2. L2 FACT 原子事实
3. L3 PROFILE / IDENTITY 用户或群画像
4. L4 SUMMARY 会话 / 日 / 半日摘要
5. Snapshot 稳定上下文快照
6. Supersedes 演化链
7. 记忆置信度、重要性、状态管理
8. 长上下文保留
9. 每日低频整理
10. 高 token cache 命中 prompt 构建

---

### 4.2 上下文目标

用户明确希望：

```text
上下文可以长一点。
```

最终效果：

- 不再只保留最近 10 条。
- 单个群聊 session 可保留较长窗口。
- 建议初始目标：

```yaml
memory:
  session_context:
    max_messages: 120
    max_chars: 24000
    preserve_hours: 24
```

这表示：

- 最多保留最近 120 条 session 消息。
- 或最多约 24000 字符。
- 当天上下文尽量保留，不频繁释放。

实际参数可按模型上下文长度调整。

---

### 4.3 整理频率目标

用户明确希望：

```text
一天就整理和释放 1-2 次。
```

最终效果：

- 废弃“空闲 120 秒就写日记”的核心策略。
- 废弃“超过 40 条就强制总结并裁剪”的核心策略。
- 改为：

```text
每日固定时间整理
或半日固定时间整理
或上下文极端超限时紧急整理
```

建议配置：

```yaml
memory:
  consolidation:
    enabled: true
    times:
      - "04:00"
      - "16:00"
    emergency_max_messages: 180
    emergency_max_chars: 36000
```

含义：

- 默认每天 04:00 和 16:00 整理。
- 只有超过紧急阈值才额外整理。

---

### 4.4 Token cache 命中目标

用户明确希望：

```text
保证 token 命中缓存要保持高度命中。
```

最终 prompt 必须拆为三段：

```text
稳定前缀区 stable prefix
动态上下文区 dynamic context
当前输入区 current turn
```

#### 稳定前缀区

一天只变 1-2 次，尽可能固定顺序和内容。

包括：

```text
基础 system prompt
长期用户画像 snapshot
长期群画像 snapshot
当天/半日 memory snapshot
工具链约束
```

#### 动态上下文区

每轮可能变化，但放在 prompt 后半段。

包括：

```text
最近长 session 消息
少量必要检索结果
工具链上下文
```

#### 当前输入区

永远放最后。

包括：

```text
当前时间
当前用户消息
当前模式信息
```

关键原则：

- 不要把当前时间放在 system prompt 前部。
- 不要把每轮 RAG 检索结果放在稳定前缀前部。
- 不要每轮重排长期画像。
- snapshot 一天最多更新 1-2 次。
- profile/snapshot 的格式和顺序必须稳定。

---

### 4.5 旧日记的角色

旧 3244 条日记不是未来主库，而是新系统初始化数据源。

最终关系：

```text
旧 diaries collection
  → 只读备份 / legacy source
  → 迁移到 yuki_memory collection
  → 旧模块逐步退役
```

旧日记迁移后应成为：

```text
L4 SUMMARY
source = legacy_diary
status = active
confidence = 1.0
importance = 3
```

不要删除旧导出文件。

---

## 5. 目标架构设计

### 5.1 新模块目录

建议新增：

```text
modules/yuki_memory/
  __init__.py
  models.py
  store.py
  migrator.py
  extractor.py
  scheduler.py
  context.py
  prompt_builder.py
```

第一阶段至少实现：

```text
modules/yuki_memory/__init__.py
modules/yuki_memory/models.py
modules/yuki_memory/store.py
modules/yuki_memory/migrator.py
```

---

### 5.2 MemoryRecord 数据结构

建议在 `modules/yuki_memory/models.py` 中定义：

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRecord:
    memory_id: str
    type: str
    content: str
    scope: str = "group"
    chat_id: str | None = None
    subject: str | None = None
    status: str = "active"
    confidence: float = 1.0
    importance: int = 3
    source: str = "unknown"
    source_ids: list[str] = field(default_factory=list)
    supersedes: str | None = None
    created_at: float | None = None
    updated_at: float | None = None
    access_count: int = 0
    last_accessed: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

支持的 `type`：

| type | 含义 |
|---|---|
| `raw` | 原始消息痕迹 |
| `summary` | 日记 / 日摘要 / 半日摘要 |
| `fact` | 原子事实 |
| `preference` | 偏好 |
| `profile` | 用户或群画像 |
| `relationship` | 人际关系 |
| `todo` | 待办 / 承诺 |
| `event` | 事件 |
| `snapshot` | 稳定上下文快照 |

支持的 `status`：

| status | 含义 |
|---|---|
| `active` | 当前有效 |
| `candidate` | 候选，未确认 |
| `superseded` | 被新记忆替代 |
| `archived` | 归档，不主动召回 |
| `rejected` | 拒绝或判定污染 |

---

### 5.3 YukiMemoryStore

建议在 `modules/yuki_memory/store.py` 中实现：

```python
class YukiMemoryStore:
    def __init__(self):
        ...

    def save(self, record: MemoryRecord) -> str:
        ...

    def save_summary(...):
        ...

    def search(self, query: str, chat_id=None, memory_types=None, top_k=8):
        ...

    def search_summaries(...):
        ...

    def search_facts(...):
        ...

    def search_profiles(...):
        ...

    def get_latest_snapshot(chat_id, snapshot_type):
        ...

    def mark_accessed(memory_ids):
        ...

    def supersede(old_id, new_record):
        ...
```

建议第一版继续使用：

```text
ChromaDB PersistentClient
collection = yuki_memory
```

不要一开始拆多个 collection，避免复杂度过高。

---

### 5.4 新 collection metadata

每条 Chroma 记录 metadata 应至少包含：

```json
{
  "type": "summary",
  "scope": "group",
  "chat_id": "1057020972",
  "subject": "群聊",
  "status": "active",
  "confidence": 1.0,
  "importance": 3,
  "source": "legacy_diary",
  "source_ids": "[\"old_diary_id\"]",
  "supersedes": "",
  "created_at": 1780000000,
  "updated_at": 1780000000,
  "access_count": 0,
  "last_accessed": 0
}
```

Chroma metadata 对复杂对象支持有限，list/dict 应 JSON 字符串化。

---

## 6. 分阶段实现路线

### 阶段 A：建立 yuki_memory 新库骨架

目标：建立新模块，不接入主流程。

需要新增：

```text
modules/yuki_memory/__init__.py
modules/yuki_memory/models.py
modules/yuki_memory/store.py
modules/yuki_memory/migrator.py
```

验收标准：

- 可以初始化 `YukiMemoryStore()`。
- 可以保存一条 `summary`。
- 可以搜索一条 `summary`。
- 不影响旧 `MemoryRAG`。

测试建议：

```text
tests/test_yuki_memory_store.py
```

---

### 阶段 B：迁移 3244 条旧日记到新库

目标：把旧日记导入新 collection `yuki_memory`。

输入：

```text
data/memory_exports/diaries_backup_20260608_234723.json
```

新增脚本：

```text
scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py
```

行为：

```text
读取备份 JSON
每条旧日记生成 MemoryRecord(type="summary")
source="legacy_diary"
source_ids=[旧 id]
chat_id=旧 metadata.chat_id
created_at=旧 metadata.timestamp
confidence=1.0
importance=3
写入 yuki_memory collection
```

必须支持：

```text
--dry-run
--limit
--resume
--reset-test-collection 或 --collection-name
```

验收标准：

- dry-run 能显示将迁移多少条。
- limit 10 可成功迁移 10 条。
- 全量迁移后 count = 3244。
- 旧 `diaries` collection 不被修改。

---

### 阶段 C：旧日记离线提取 L2/L3 候选

已有脚本：

```text
scripts/03_RAG_Tools/backfill_memory_candidates.py
```

需要增强：

1. 支持按 `chat_id` 过滤。
2. 支持随机抽样。
3. 支持最近优先 / 最早优先。
4. 支持 batch 处理。
5. 输出统计报告。
6. 支持失败重试次数。
7. 支持写入错误 JSONL。

输出：

```text
data/memory_exports/memory_candidates_*.jsonl
```

不要直接入库。

---

### 阶段 D：候选审核和去重

新增脚本：

```text
scripts/03_RAG_Tools/review_memory_candidates.py
```

功能：

```text
读取 candidates JSONL
过滤 error != null
过滤 confidence < 0.65
过滤 risk = high
按 type + subject 聚合
按 content 去重
输出统计
输出 approved_candidates.jsonl
输出 rejected_candidates.jsonl
输出 review_report.json
```

第一版可以先用简单规则：

```text
相同 type + subject + content 完全相同 → 去重
confidence >= 0.85 且 risk=low → approved
0.65 <= confidence < 0.85 → pending
risk=high → rejected
```

后续再做向量相似聚类。

---

### 阶段 E：导入 L2/L3 结构化记忆

新增脚本：

```text
scripts/03_RAG_Tools/import_memory_candidates.py
```

导入规则：

```text
只导入 approved_candidates.jsonl
profile_candidate 不直接导入 profile
profile_candidate 先作为 candidate 或 pending
fact/preference/relationship/event/todo 可以入库
```

入库 metadata：

```text
source = legacy_extraction
source_ids = [source_diary_id]
status = active 或 candidate
```

验收标准：

- 能导入 10 条测试候选。
- 能按 type 搜索。
- 不影响旧日记 summary。

---

### 阶段 F：长上下文 Session 改造

目标：替换当前 `KEEP_LAST_DIALOGUE=10` 和 `DIARY_MAX_LENGTH=40` 的短上下文策略。

当前配置位置：

```text
configs/config.yaml
```

当前配置：

```yaml
diary:
  idle_seconds: 120
  min_turns: 20
  max_length: 40

rag:
  retrieval_top_k: 20
  keep_last_dialogue: 10
```

建议新增配置：

```yaml
memory:
  session_context:
    max_messages: 120
    max_chars: 24000
    preserve_hours: 24
  consolidation:
    enabled: true
    times:
      - "04:00"
      - "16:00"
    emergency_max_messages: 180
    emergency_max_chars: 36000
  retrieval:
    summary_top_k: 3
    fact_top_k: 5
    profile_top_k: 5
    inject_legacy_summary: false
```

需要同步修改：

```text
config.py
configs/config.yaml
tests/test_config.py
```

---

### 阶段 G：每日 / 半日整理器

新增：

```text
modules/yuki_memory/scheduler.py
```

或在 `core/engine.py` 中新增后台任务，但推荐放在 yuki_memory 模块。

职责：

```text
每天 1-2 次读取长 session
生成 daily_summary / halfday_summary
抽取 facts / profile candidates
生成 snapshot
释放旧 session
```

替代旧逻辑：

```text
YukiEngine.idle_diary_checker()
YukiEngine.do_summarize()
```

第一版可以保留旧逻辑，但默认禁用高频触发。

---

### 阶段 H：Cache-friendly Prompt Builder

新增：

```text
modules/yuki_memory/prompt_builder.py
```

或改造：

```text
core/prompts.py::build_chat_context()
```

最终 Prompt 顺序：

```text
1. Stable Prefix
   - 基础人设
   - 工具链约束
   - 用户/群长期画像 snapshot
   - 当日/半日 snapshot

2. Dynamic Context
   - 长 session 最近消息
   - 必要的 facts / summaries 检索结果
   - 工具链上下文

3. Current Turn
   - 当前时间
   - 当前输入
```

关键要求：

- 稳定 prefix 一天最多变 1-2 次。
- 当前时间永远放后面。
- 检索结果不要插在 system prompt 前部。
- 长期画像排序稳定，例如按 `subject + type + updated_at`。
- snapshot 内容格式稳定。

---

### 阶段 I：主流程接入 YukiMemory

修改：

```text
main.py
core/session_pipeline.py
core/engine.py
core/prompts.py
```

目标：

```text
memory_rag = MemoryRAG()
```

逐步替换为：

```text
yuki_memory = YukiMemoryStore()
```

但不要一次性删除 `MemoryRAG`。

推荐过渡方式：

```python
class YukiMemoryAdapter:
    def search_diaries(...):
        return yuki_memory.search_summaries(...)
```

这样先保持旧接口兼容，再逐步重构调用方。

---

## 7. 重要技术注意事项

### 7.1 Conda 环境问题

在当前 Trae PowerShell 中：

```powershell
conda activate ai_env
```

没有真正切换 Python，仍然使用 base：

```text
D:\Dev\Env\MiniForge\python.exe
```

正确运行方式：

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/export_memory.py"
```

`conda run -n ai_env ...` 会因为 Windows GBK 编码报错。

后续运行项目脚本建议直接使用：

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "脚本路径.py"
```

---

### 7.2 Chroma / SentenceTransformer 警告

导出时出现：

```text
You try to use a model that was created with version 5.2.3, however, your version is 2.7.0.
```

这是 sentence-transformers 模型版本警告。导出成功，目前不阻塞。

---

### 7.3 Git 状态异常

当前 `git status --short` 显示大量 `A` 文件，像是仓库处于初始 staged/索引异常状态。

后续不要随便 `git add .`。

只应添加本次相关文件，例如：

```powershell
git add modules/memory/rag.py scripts/03_RAG_Tools/export_memory.py scripts/03_RAG_Tools/backfill_memory_candidates.py tests/test_yuki_memory_lite.py docs/changelog.md docs/yuki-memory-handoff.md
```

如果新增 yuki_memory 模块，只添加对应文件。

---

## 8. 已验证内容

已通过语法检查：

```powershell
python -m py_compile modules/memory/rag.py scripts/03_RAG_Tools/export_memory.py scripts/03_RAG_Tools/backfill_memory_candidates.py tests/test_yuki_memory_lite.py
```

已通过测试：

```powershell
python -m pytest tests/test_yuki_memory_lite.py tests/test_config.py
```

结果：

```text
45 passed
```

曾尝试运行：

```powershell
python -m pytest tests/test_config.py tests/test_llm_client.py tests/test_maid_search_diary.py
```

其中 `tests/test_llm_client.py` 的 3 个 async 测试失败，原因是测试环境缺少 async pytest 插件，不是本轮改动导致。

---

## 9. 下一个 LLM 的建议执行顺序

请按以下顺序继续，避免过度重构：

### 第 1 步：创建 yuki_memory 模块骨架

新增：

```text
modules/yuki_memory/__init__.py
modules/yuki_memory/models.py
modules/yuki_memory/store.py
modules/yuki_memory/migrator.py
```

实现最小可用：

```text
MemoryRecord
YukiMemoryStore.save()
YukiMemoryStore.search()
LegacyDiaryMigrator.load_backup()
```

---

### 第 2 步：新增迁移脚本

新增：

```text
scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py
```

支持：

```text
--input data/memory_exports/diaries_backup_20260608_234723.json
--collection yuki_memory
--dry-run
--limit
--resume
```

先 dry-run，再 limit 10，最后全量。

---

### 第 3 步：新增测试

新增：

```text
tests/test_yuki_memory_store.py
tests/test_yuki_memory_migrator.py
```

测试不应依赖真实 Chroma，可使用 stub 或临时目录。

---

### 第 4 步：迁移旧日记到新库

运行：

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py" --input "data/memory_exports/diaries_backup_20260608_234723.json" --limit 10
```

验证没问题后再全量。

---

### 第 5 步：实现兼容搜索

让 `YukiMemoryStore.search_summaries()` 返回格式兼容旧 `search_diaries()`：

```python
[
    {
        "content": "...",
        "metadata": {...},
        "score": 0.9,
        "debug": "..."
    }
]
```

这样后续可以逐步替换 `SessionPipeline.retrieve_memories()`。

---

### 第 6 步：再考虑主流程替换

不要在还没完成新库迁移前改主流程。

主流程替换顺序应为：

```text
1. 新库 summary search 可用
2. SessionPipeline 可切换到 YukiMemoryStore.search_summaries()
3. Prompt 仍保持旧格式
4. 验证回复不崩
5. 再做长上下文和 cache-friendly prompt
```

---

## 10. 最终完成标准

整个 yuki-memory 重构最终完成时，应满足以下标准。

### 10.1 数据层完成标准

- 旧 3244 条日记已导入 `yuki_memory` collection。
- 每条旧日记都有标准 metadata。
- 可以按 `type=summary` 检索。
- 可以按 `chat_id` 过滤。
- 可以按 `status=active` 过滤。
- 旧 `diaries` collection 不再是主流程依赖。

---

### 10.2 L1-L4 完成标准

| 层级 | 完成标准 |
|---|---|
| L1 RAW | 原始消息可以按天/群归档，且不因上下文裁剪丢失 |
| L2 FACT | 可以从旧日记/新对话中提取事实候选，经审核或规则入库 |
| L3 PROFILE | 可以由多条事实合并为稳定用户/群画像，不从单条日记过度推断 |
| L4 SUMMARY | 可以生成日/半日 summary，并作为 summary 记忆入库 |

---

### 10.3 上下文完成标准

- 单群上下文不再固定只保留 10 条。
- 可按 `max_messages` / `max_chars` 保留长上下文。
- 只有每日整理或紧急超限时才释放上下文。
- 整理前后的上下文行为可追踪。

---

### 10.4 Token cache 完成标准

Prompt 构建满足：

- system persona 稳定。
- profile snapshot 稳定。
- daily snapshot 稳定。
- 当前时间放后部。
- 检索结果放后部。
- 稳定前缀一天最多更新 1-2 次。

最终 prompt 大致结构：

```text
[稳定 system persona]
[稳定工具链约束]
[稳定长期画像 snapshot]
[稳定当日/半日 snapshot]
---
[长 session 最近上下文]
[少量动态检索记忆]
---
[当前时间]
[当前用户输入]
```

---

### 10.5 行为完成标准

- Yuki 能记住更长当天上下文。
- Yuki 不会频繁“写日记后忘掉刚才的长话题”。
- Yuki 能基于旧 3244 条日记检索过去事件。
- Yuki 能逐步从旧日记中形成事实和偏好。
- Yuki 不会把玩笑、临时情绪、角色扮演误当长期事实。
- Yuki 的回复不会因为注入过多旧记忆而变得啰嗦或爱翻旧账。

---

## 11. 不要做的事情

后续 LLM 必须避免：

1. 不要直接删除旧 `diaries` collection。
2. 不要直接把 LLM 提取的所有 candidate 写入生产记忆。
3. 不要一次性大改 `SessionPipeline`、`Engine`、`Prompt` 三处核心流程。
4. 不要把 `profile_candidate` 直接当作稳定 profile。
5. 不要把当前时间插入 prompt 前部。
6. 不要每轮重写 stable snapshot。
7. 不要 `git add .`。
8. 不要提交 `.env`、`api_config.txt`、私密配置、缓存大文件。
9. 不要在没有测试的情况下替换主流程。

---

## 12. 推荐的下一条开发指令

如果下一个 LLM 要开始实际实现，建议直接执行以下任务：

```text
请基于 docs/yuki-memory-handoff.md，先实现 modules/yuki_memory 的最小骨架：
1. models.py 中定义 MemoryRecord；
2. store.py 中实现 YukiMemoryStore，使用 Chroma collection=yuki_memory，支持 save/search/search_summaries；
3. migrator.py 中实现从 diaries_backup_20260608_234723.json 读取旧日记并转换为 MemoryRecord(type=summary)；
4. 新增 scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py，支持 --dry-run、--limit、--resume；
5. 新增基础测试，不接入主流程。
```

这是最安全的下一步。

---

## 13. 参考文件清单

后续开发必须重点阅读：

```text
docs/yuki-memory-handoff.md
docs/Hy-Memory技术文档.md
data/memory_exports/diaries_stats_20260608_234723.json
scripts/03_RAG_Tools/backfill_memory_candidates.py
scripts/03_RAG_Tools/export_memory.py
modules/memory/rag.py
core/session_pipeline.py
core/engine.py
core/prompts.py
config.py
configs/config.yaml
tests/test_yuki_memory_lite.py
```

---

## 14. 当前状态一句话总结

当前已经完成旧日记导出和 yuki-memory 第一批工具脚手架；下一步不应继续强化旧 RAG，而应新建 `modules/yuki_memory`，把 3244 条旧日记迁移为新系统的 `summary` 层，然后再逐步实现 FACT、PROFILE、长上下文、每日整理和 cache-friendly prompt。
