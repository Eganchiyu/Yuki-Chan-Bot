# Yuki-Memory 开发日志与运行手册

## 1. 当前开发重点

当前重点是把 YukiV6 的记忆系统从旧 `MemoryRAG` 逐步迁移到 `Yuki-Memory`，同时保持主程序可回退、可验证、不中断运行。

本阶段目标：

1. 完成旧 `diaries` 记忆的 summary 迁移。
2. 完成旧日记到结构化候选的离线提取。
3. 审核、过滤并导入低风险结构化记忆。
4. 让主程序上下文构建同时使用：
   - 旧 `MemoryRAG.search_diaries()` 回忆；
   - 新 `YukiMemoryStore` 的 profile/fact/summary 分层召回。
5. 后续再把高频旧日记总结替换为每日/半日多层压缩整理。

---

## 2. 数据库策略

当前采用：

```text
同一个 Chroma 持久化目录
├── diaries      # 旧 MemoryRAG collection
└── yuki_memory  # 新 Yuki-Memory collection
```

原因：

- 备份和部署路径统一；
- 旧逻辑完全保留，不污染旧 collection；
- 新逻辑可以独立检索、导入、回滚；
- 主程序可同时查新旧记忆，失败时回退旧逻辑。

不要删除旧 `diaries` collection。旧库目前仍是生产回退来源。

---

## 3. 当前状态快照

### 3.1 旧快照

旧导出：

```text
data/memory_exports/diaries_backup_20260608_234723.json
```

统计：

```text
总数：3244
主群聊 1057020972：1955
其余群聊：1289
```

旧导出已完成全量候选提取。主群聊 error 文件包含历史失败尝试，因此 error 行数可能大于最终失败条数。

### 3.2 新快照

新导出：

```text
data/memory_exports/diaries_backup_20260614_193344.json
```

统计：

```text
总数：3533
相比旧快照新增：289
```

新增分布：

```text
1057020972: +158
818038143:  +57
495881825:  +38
1034986009: +36
```

已执行 summary 增量迁移：

```text
成功迁移：289
跳过已有：3244
yuki_memory 当前 count：3533
```

结构化候选增量提取仍在运行中，命令 ID：

```text
549fdf59-0979-45c5-92a4-164274a44216
```

---

## 4. 已实现模块说明

### 4.1 `modules/yuki_memory/models.py`

核心类：

```python
MemoryRecord
```

用途：Yuki-Memory 的标准记忆记录模型。

关键字段：

| 字段 | 说明 |
|------|------|
| `memory_id` | 记忆 ID |
| `type` | 记忆类型：summary/fact/preference/profile/relationship/todo/event/snapshot 等 |
| `content` | 记忆正文 |
| `chat_id` | 所属群聊或会话 |
| `subject` | 主体，如人物、项目、群聊 |
| `status` | active/candidate/superseded/archived/rejected |
| `confidence` | 置信度 |
| `importance` | 重要性 1-5 |
| `source` | 来源 |
| `source_ids` | 原始来源 ID |
| `supersedes` | 被替代旧记忆 ID |
| `metadata` | 扩展元数据 |

常用方法：

```python
record.to_metadata()
MemoryRecord.from_chroma(memory_id, content, metadata)
```

---

### 4.2 `modules/yuki_memory/store.py`

核心类：

```python
YukiMemoryStore
```

用途：封装 `yuki_memory` collection 的保存和检索。

常用方法：

```python
store.save(record)
store.save_summary(...)
store.search(query, chat_id=None, memory_types=None, top_k=8, status="active")
store.search_summaries(query, chat_id=None, top_k=8)
store.search_facts(query, chat_id=None, top_k=8)
store.search_profiles(query, chat_id=None, top_k=8)
store.get_latest_snapshot(chat_id=None, snapshot_type=None)
store.supersede(old_id, new_record)
```

`search_facts()` 当前包含：

```text
fact
preference
relationship
todo
event
```

---

### 4.3 `modules/yuki_memory/migrator.py`

核心类：

```python
LegacyDiaryMigrator
```

用途：把旧 `diaries` 导出的备份转换为 `MemoryRecord(type="summary")`。

核心方法：

```python
LegacyDiaryMigrator.load_backup(input_path)
LegacyDiaryMigrator.to_memory_record(legacy_record)
LegacyDiaryMigrator.migrate_records(...)
```

配套脚本：

```text
scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py
```

---

### 4.4 `modules/yuki_memory/retriever.py`

核心类：

```python
YukiMemoryRetriever
```

用途：主流程结构化上下文检索适配层。

入口：

```python
retriever.retrieve(query, chat_id=chat_id)
```

返回结构：

```python
{
    "enabled": True,
    "profiles": [...],
    "facts": [...],
    "summaries": [...],
    "errors": [],
}
```

特点：

- 分层召回 profile/fact/summary；
- 自动去重；
- 失败时返回空结构，不影响旧 RAG；
- 主程序上下文构建已经接入。

---

### 4.5 `modules/yuki_memory/consolidator.py`

核心类：

```python
MultiLayerMemoryConsolidator
```

用途：未来替代高频旧日记的多层压缩整理器。

处理路径：

```text
原始对话
→ 粗样本筛选
→ 重叠 buffer 摘要
→ 结构化候选提取
→ 短日记生成
→ 可选写入 yuki_memory
```

核心方法：

```python
await consolidator.consolidate(chat_id, messages, save=False)
consolidator.save_result(result)
```

配套脚本：

```text
scripts/03_RAG_Tools/consolidate_runtime_memory.py
```

默认不写库，传 `--save` 才写入。

---

## 5. 主程序上下文构建现状

### 5.1 当前调用链

```text
NapCat 消息
→ SessionPipeline.enqueue_message()
→ SessionPipeline.process_loop()
→ SessionPipeline.run_once()
→ prepare_message_batch()
→ normalize_incoming_content()
→ prepare_chat_context()
→ decide_reply_action()
→ retrieve_memories()
→ generate_reply()
→ YukiEngine.api_reply()
→ build_chat_context()
→ LLM 回复
```

### 5.2 记忆检索位置

文件：

```text
core/session_pipeline.py
```

方法：

```python
SessionPipeline.retrieve_memories()
```

当前逻辑：

```text
1. 调用旧 MemoryRAG.search_diaries()
2. 调用新 YukiMemoryRetriever.retrieve()
3. 把 relevant_diaries 和 structured_memory_context 一起传给 Engine
```

### 5.3 Prompt 构建位置

文件：

```text
core/prompts.py
```

方法：

```python
build_chat_context(...)
build_structured_memory_prompt(...)
```

当前 prompt 顺序：

```text
system 人设
→ Yuki-Memory 结构化上下文
→ 旧 RAG【回忆】
→ 工具链约束
→ 破冰指令（可选）
→ 最近对话
→ 当前时间 + 当前输入
```

这意味着新记忆已经直接参与上下文构建，但旧回忆仍保留作为回退。

---

## 6. 离线处理操作指南

### 6.1 导出旧 diaries

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/export_memory.py" --output-dir "data/memory_exports"
```

输出：

```text
diaries_backup_<timestamp>.json
diaries_stats_<timestamp>.json
```

### 6.2 迁移 summary 到 yuki_memory

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py" --input "data/memory_exports/diaries_backup_<timestamp>.json" --resume
```

说明：

- `--resume` 会跳过已经存在的 `memory_id`；
- 可安全对新导出文件重复执行；
- 不会修改旧 `diaries` collection。

### 6.3 提取结构化候选

单群聊示例：

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/backfill_memory_candidates.py" `
  --input "data/memory_exports/diaries_backup_<timestamp>.json" `
  --base-url "<LLM_BASE_URL>" `
  --api-key "<LLM_API_KEY>" `
  --model "<MODEL>" `
  --chat-id <CHAT_ID> `
  --order newest `
  --batch-size 50 `
  --retries 2 `
  --output "data/memory_exports/mimo_<CHAT_ID>_candidates.jsonl" `
  --error-output "data/memory_exports/mimo_<CHAT_ID>_errors.jsonl" `
  --report "data/memory_exports/mimo_<CHAT_ID>_report.json" `
  --resume `
  --max-consecutive-failures 5
```

注意：

- 不要把 API Key 写进文档或提交；
- `--resume` 根据候选 JSONL 中的 `source_diary_id` 去重；
- 对新导出文件继续 append 到原候选文件即可补新增日记。

### 6.4 审核候选

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/review_memory_candidates.py" `
  --input data/memory_exports/mimo_*_candidates.jsonl `
  --approved-output "data/memory_exports/memory_candidates_approved_full.jsonl" `
  --needs-review-output "data/memory_exports/memory_candidates_needs_review_full.jsonl" `
  --rejected-output "data/memory_exports/memory_candidates_rejected_full.jsonl" `
  --report "data/memory_exports/memory_candidates_review_report_full.json"
```

审核重点：

```text
profile_candidate
todo
medium risk
importance >= 3 的 rejected
relationship/preference 是否误删
```

### 6.5 导入 dry-run

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/import_memory_candidates.py" `
  --input "data/memory_exports/memory_candidates_approved_full.jsonl" `
  --dry-run `
  --report "data/memory_exports/import_memory_candidates_dry_run_report.json" `
  --preview-output "data/memory_exports/import_memory_candidates_preview.jsonl"
```

通过标准：

```text
failed = 0
profile_candidate 默认跳过
fact/preference/relationship/event/todo 可正常转换
```

### 6.6 真实导入

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/import_memory_candidates.py" `
  --input "data/memory_exports/memory_candidates_approved_full.jsonl" `
  --report "data/memory_exports/import_memory_candidates_report.json"
```

第一轮不要加 `--include-profile`。

---

## 7. 运行时多层整理操作指南

旁路 dry-run：

```powershell
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/consolidate_runtime_memory.py" `
  --chat-id <CHAT_ID> `
  --limit 80 `
  --output "data/memory_exports/runtime_consolidation_test.json" `
  --base-url "<LLM_BASE_URL>" `
  --api-key "<LLM_API_KEY>" `
  --model "<MODEL>"
```

写入 yuki_memory：

```powershell
# 仅在 dry-run 质量确认后使用
& "D:\Dev\Env\MiniForge\envs\ai_env\python.exe" "scripts/03_RAG_Tools/consolidate_runtime_memory.py" `
  --chat-id <CHAT_ID> `
  --limit 120 `
  --save
```

当前建议：只 dry-run，不接管旧 `do_summarize()`。

---

## 8. 当前风险与注意事项

1. 新结构化记忆上下文已接入主流程，但结构化候选还没真实导入前，主要召回 summary。
2. 旧 RAG 仍然保留，主程序不会因为新检索失败而失去记忆。
3. `profile_candidate` 不要直接导入稳定 profile。
4. `event` 需要严格过滤，低重要性 event 容易污染召回。
5. API Key 不要写入文档、提交记录和日志归档。
6. 增量提取运行期间，不要手动编辑正在 append 的 JSONL 文件。
7. 看板仍使用旧 stats 文件时，可能不能反映新快照总数，需要启动时指定新 stats 文件。

---

## 9. 接下来计划

### 近期

1. 等增量候选提取完成。
2. 检查 4 个增量 report。
3. 收紧审核规则，尤其是低价值 event 和 importance=1。
4. 跑全量 review。
5. 抽查 needs_review/rejected。
6. 执行 import dry-run。
7. 真实导入低风险 approved。
8. 用主流程结构化上下文做召回 smoke test。

### 中期

1. 增加配置开关，控制结构化上下文是否参与 prompt。
2. 实现每日/半日 runtime consolidation 调度器。
3. 拉长 session context，减少频繁裁剪。
4. 实现 cache-friendly prompt builder。
5. 做 profile/snapshot 生成器。

### 长期

1. 实现 supersedes 演化链自动更新。
2. 实现 subject alias / 人物归一。
3. 实现低价值记忆衰减和归档。
4. 旧 `MemoryRAG` 降级为兼容工具或只读回退。

---

## 10. 当前开发重点一句话

当前不是删除旧记忆系统，而是让 Yuki-Memory 先以结构化上下文形式参与回复，待历史结构化记忆审核导入稳定后，再逐步替换旧日记写入和旧 RAG 召回。
