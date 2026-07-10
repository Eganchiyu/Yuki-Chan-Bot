# Yuki-Memory 插件与接入指南

## 1. 定位

Yuki-Memory 是 YukiV6 的新长期记忆子系统，目标是替代旧 `MemoryRAG` 的“会话日记向量检索”模式，逐步升级为分层、结构化、可演化的长期记忆系统。

当前接入原则：

```text
新增能力优先旁路接入
旧逻辑保留为回退
数据导入先 dry-run 再真实写库
主流程逐步引流，不一次性替换
```

---

## 2. Collection 设计

当前使用同一 Chroma 持久化目录下的不同 collection：

```text
diaries      # 旧 MemoryRAG collection
yuki_memory  # 新 Yuki-Memory collection
```

### 为什么不新开物理数据库？

暂不新开物理数据库。原因：

1. 当前项目已有 `cfg.VECTOR_DB_PATH`，共用路径便于部署和备份。
2. Chroma collection 已经能完成逻辑隔离。
3. 旧系统和新系统可以并行运行。
4. 未来如需拆分，可以迁移 `yuki_memory` collection，而不用影响旧 `diaries`。

### 什么时候考虑新物理数据库？

只有在以下情况才需要：

- 新旧 embedding 模型完全不同，且索引规模很大；
- 需要独立备份/迁移 Yuki-Memory；
- 需要对 yuki_memory 做不同 Chroma 参数或服务化部署；
- 旧库要冻结为只读归档。

---

## 3. 模块结构

```text
modules/yuki_memory/
├── __init__.py
├── models.py          # MemoryRecord 标准模型
├── store.py           # Chroma 存储与检索封装
├── migrator.py        # 旧 diaries 备份迁移为 summary
├── retriever.py       # 主流程结构化上下文检索适配层
└── consolidator.py    # 运行时多层压缩整理器
```

---

## 4. 标准记忆模型

### 4.1 MemoryRecord

路径：

```text
modules/yuki_memory/models.py
```

使用：

```python
from modules.yuki_memory import MemoryRecord

record = MemoryRecord(
    memory_id="ymem_fact_example",
    type="fact",
    content="主人正在重构 Yuki-Memory。",
    chat_id="1057020972",
    subject="主人",
    confidence=0.95,
    importance=4,
    source="manual_test",
)
```

支持的类型：

```text
raw
summary
fact
preference
profile
relationship
todo
event
snapshot
```

支持的状态：

```text
active
candidate
superseded
archived
rejected
```

---

## 5. 存储接口

### 5.1 初始化

```python
from modules.yuki_memory import YukiMemoryStore

store = YukiMemoryStore(collection_name="yuki_memory")
```

默认使用：

```python
cfg.VECTOR_DB_PATH
cfg.EMBED_MODEL
```

### 5.2 保存记忆

```python
store.save(record)
```

### 5.3 保存 summary

```python
store.save_summary(
    content="今天主要讨论了 Yuki-Memory 的结构化接入。",
    chat_id="1057020972",
    subject="群聊",
    source="runtime_summary",
    importance=3,
)
```

### 5.4 检索记忆

通用检索：

```python
store.search(
    query="主人最近在做什么？",
    chat_id="1057020972",
    memory_types=["fact", "preference"],
    top_k=8,
)
```

分层检索：

```python
store.search_profiles(query, chat_id="1057020972", top_k=2)
store.search_facts(query, chat_id="1057020972", top_k=6)
store.search_summaries(query, chat_id="1057020972", top_k=4)
```

---

## 6. 主流程接入接口

### 6.1 YukiMemoryRetriever

路径：

```text
modules/yuki_memory/retriever.py
```

使用：

```python
from modules.yuki_memory import YukiMemoryRetriever

retriever = YukiMemoryRetriever(enabled=True)
context = retriever.retrieve(
    "主人最近在做什么？",
    chat_id="1057020972",
)
```

返回：

```python
{
    "enabled": True,
    "profiles": [...],
    "facts": [...],
    "summaries": [...],
    "errors": [],
}
```

如果检索失败：

```python
{
    "enabled": False,
    "profiles": [],
    "facts": [],
    "summaries": [],
    "errors": ["错误信息"],
}
```

主流程会继续使用旧 RAG，不会崩。

---

## 7. Prompt 接入接口

### 7.1 build_structured_memory_prompt

路径：

```text
core/prompts.py
```

使用：

```python
from core.prompts import build_structured_memory_prompt

text = build_structured_memory_prompt(structured_memory_context)
```

输出结构：

```text
【Yuki-Memory 结构化上下文】...

【长期画像/身份线索】
- [profile][主体][重要性:4] ...

【相关结构化记忆】
- [preference][主体][重要性:4] ...

【相关摘要回忆】
- [summary][重要性:3] ...
```

### 7.2 当前 build_chat_context 顺序

```text
system 人设
→ Yuki-Memory 结构化上下文
→ 旧 RAG【回忆】
→ 工具链约束
→ 破冰指令（可选）
→ 最近对话
→ 当前输入
```

---

## 8. 运行时整理接口

### 8.1 MultiLayerMemoryConsolidator

路径：

```text
modules/yuki_memory/consolidator.py
```

使用：

```python
from modules.yuki_memory import MultiLayerMemoryConsolidator

consolidator = MultiLayerMemoryConsolidator()
result = await consolidator.consolidate(
    chat_id="1057020972",
    messages=history_messages,
    save=False,
)
```

结果字段：

```python
result.raw_count
result.sample_count
result.buffer_summaries
result.candidates
result.diary
result.saved_ids
```

### 8.2 保存结果

```python
result = await consolidator.consolidate(chat_id, messages, save=True)
```

默认保存策略：

- 保存一条 `summary` 日记；
- 保存低风险结构化候选；
- `profile_candidate` 默认不入库；
- 低重要性 `event` 不入库。

---

## 9. 离线脚本清单

### 9.1 导出旧 diaries

```text
scripts/03_RAG_Tools/export_memory.py
```

### 9.2 迁移旧日记 summary

```text
scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py
```

### 9.3 离线提取结构化候选

```text
scripts/03_RAG_Tools/backfill_memory_candidates.py
```

### 9.4 审核候选

```text
scripts/03_RAG_Tools/review_memory_candidates.py
```

### 9.5 导入候选

```text
scripts/03_RAG_Tools/import_memory_candidates.py
```

### 9.6 运行时整理 dry-run

```text
scripts/03_RAG_Tools/consolidate_runtime_memory.py
```

---

## 10. 新插件/新模块接入建议

如果新插件需要读长期记忆，优先使用：

```python
YukiMemoryRetriever.retrieve()
```

如果需要底层精确检索，使用：

```python
YukiMemoryStore.search_facts()
YukiMemoryStore.search_summaries()
YukiMemoryStore.search_profiles()
```

如果插件需要写入长期记忆，优先写入 `MemoryRecord`：

```python
record = MemoryRecord(
    memory_id="...",
    type="fact",
    content="...",
    chat_id=chat_id,
    subject="...",
    source="plugin:<plugin_id>",
    confidence=0.9,
    importance=3,
)
store.save(record)
```

写入注意事项：

1. 不要把临时闲聊写为长期事实。
2. 不要把玩笑写为 profile。
3. 不要写高风险隐私。
4. `source` 必须能追溯插件来源。
5. 有原始消息 ID 时写入 `source_ids`。
6. 不确定内容使用 `status="candidate"`。

---

## 11. 推荐扩展点

### 11.1 新增每日整理调度器

建议文件：

```text
modules/yuki_memory/scheduler.py
```

职责：

```text
按 chat_id 收集当天 session
每日/半日触发 MultiLayerMemoryConsolidator
记录整理结果
整理后裁剪 session
```

### 11.2 新增画像生成器

建议文件：

```text
modules/yuki_memory/profile_builder.py
```

职责：

```text
读取 profile_candidate
人工/规则审核
生成稳定 profile 或 snapshot
```

### 11.3 新增上下文构建器

建议文件：

```text
modules/yuki_memory/context_builder.py
```

职责：

```text
结构化记忆排序
去重
分层 token budget
构建 cache-friendly memory context
```

---

## 12. 接入禁忌

1. 不要删除旧 `diaries` collection。
2. 不要直接把所有 candidate 导入 active。
3. 不要把 `profile_candidate` 直接当稳定 profile。
4. 不要让插件绕过 `MemoryRecord` 随便写 metadata。
5. 不要把 API Key 写进文档或仓库。
6. 不要在主流程中同步执行重型整理任务。
7. 不要在回复 prompt 中塞入过多旧日记。
8. 不要在未 dry-run 的情况下启用 `--save`。

---

## 13. 最小接入示例

```python
from modules.yuki_memory import YukiMemoryRetriever

retriever = YukiMemoryRetriever()
context = retriever.retrieve("最近 Yuki-Memory 做到哪了？", chat_id="1057020972")

if context["facts"] or context["summaries"]:
    print("已召回 Yuki-Memory 上下文")
else:
    print("无结构化上下文，可回退旧 RAG")
```

---

## 14. 当前接入状态

已完成：

- `YukiMemoryStore` 基础存储与检索；
- `YukiMemoryRetriever` 主流程适配层；
- `build_structured_memory_prompt()`；
- `SessionPipeline.retrieve_memories()` 新旧双检索；
- `YukiEngine.api_reply()` 透传结构化上下文；
- `MultiLayerMemoryConsolidator` 旁路整理器。

待完成：

- 全量候选 review；
- approved 结构化记忆 dry-run/import；
- 召回质量抽测；
- 每日/半日整理调度器；
- profile/snapshot 生成器；
- 配置开关与 token budget 控制。
