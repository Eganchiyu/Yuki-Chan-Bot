# Yuki Context Debug WebUI 开发计划

## 1. 项目目标

构建一个美观、实时、只读优先的 Debug WebUI，用于观察 YukiV6 主程序当前状态，以及每轮回复时传给 LLM 的完整构建上下文。

核心目标：

1. 实时显示 Yuki 当前运行状态。
2. 实时显示各群聊 session 状态。
3. 展示 Yuki 的完整 prompt 构建结果，包括：
   - system 人设；
   - Yuki-Memory 结构化上下文；
   - 旧 RAG 回忆；
   - 工具链约束；
   - 最近对话；
   - 当前输入。
4. 展示记忆召回细节，包括旧 `MemoryRAG` 与新 `YukiMemory` 的召回结果。
5. 用于 debug，不改变机器人运行行为。
6. 第一版只读；后续再考虑手动触发整理、导出上下文、开关配置等能力。

---

## 2. 设计原则

### 2.1 只读优先

第一版 WebUI 不应该写入数据库、不修改 session、不触发发送消息。

允许读取：

```text
chat_history.json
日志文件
YukiState 快照
SessionPipeline debug 快照
MemoryRAG/YukiMemory 检索结果
构建好的 LLM messages
```

禁止第一版实现：

```text
发送 QQ 消息
修改记忆
删除记忆
修改配置
强制触发回复
强制触发整理
```

### 2.2 渐进式接入

先做旁路 debug 能力，再逐步集成到主程序。

推荐顺序：

```text
静态快照 API
→ 实时轮询 WebUI
→ 接入 SessionPipeline debug snapshot
→ 接入完整 prompt messages 捕获
→ 增加历史上下文回放
→ 增加人工诊断工具
```

### 2.3 不阻塞主流程

Debug WebUI 不能影响 Yuki 回复速度。

要求：

- 捕获上下文时使用轻量 snapshot；
- WebUI 读取 snapshot，不直接阻塞 pipeline；
- 大文本展示在前端折叠/懒加载；
- 后端 API 有超时和异常兜底。

### 2.4 隐私与安全

WebUI 默认只监听：

```text
127.0.0.1
```

禁止默认暴露公网。

敏感字段处理：

- API Key 必须脱敏；
- NapCat token 必须脱敏；
- 私聊内容可以显示，但需明确这是本地 debug 页面；
- 后续如开放远程访问，必须加认证。

---

## 3. 推荐技术方案

### 3.1 第一版技术栈

后端：

```text
Python 标准库 ThreadingHTTPServer 或 aiohttp
```

前端：

```text
单文件 HTML + CSS + 原生 JS
```

理由：

- 当前项目已经有 `live_memory_dashboard.py`，可复用思路；
- 不引入新依赖；
- 便于其他 AI 快速实现；
- 适合本地 debug 页面。

### 3.2 后续增强技术栈

如果后续需要更复杂交互，可升级为：

```text
FastAPI + WebSocket + React/Vite
```

但第一版不建议引入，避免增加部署复杂度。

---

## 4. 建议文件结构

新增文件：

```text
modules/debug/
├── __init__.py
├── context_snapshot.py       # 上下文快照模型与管理器
├── webui_server.py           # Debug WebUI 后端服务
└── serializers.py            # 脱敏与格式化工具

scripts/debug_tools/
└── start_context_debug_webui.py
```

也可以第一版先只做：

```text
scripts/debug_tools/context_debug_webui.py
```

但推荐模块化，后续方便接入主程序。

---

## 5. 核心数据模型

### 5.1 ContextSnapshot

建议结构：

```python
@dataclass
class ContextSnapshot:
    snapshot_id: str
    chat_id: str
    mode: str
    created_at: str
    stage: str
    combined_text: str
    current_time_str: str
    message_count: int
    should_reply: Optional[bool]
    relevant_diaries: list
    structured_memory_context: dict
    built_messages: list
    token_estimate: dict
    tool_context: dict
    latency: dict
    errors: list
```

字段说明：

| 字段 | 说明 |
|------|------|
| `snapshot_id` | 每轮构建的唯一 ID |
| `chat_id` | 群聊/私聊 ID |
| `mode` | group/private |
| `created_at` | 快照创建时间 |
| `stage` | 当前阶段，如 retrieved/built/sent |
| `combined_text` | 本轮合并后的输入 |
| `current_time_str` | 当前时间字符串 |
| `message_count` | 当前 session 消息数 |
| `should_reply` | 是否决定回复 |
| `relevant_diaries` | 旧 RAG 回忆 |
| `structured_memory_context` | 新 YukiMemory 结构化上下文 |
| `built_messages` | 最终传给 LLM 的 messages |
| `token_estimate` | token 粗估 |
| `tool_context` | 工具链状态 |
| `latency` | 各阶段耗时 |
| `errors` | 捕获错误 |

---

## 6. Debug 数据采集点

### 6.1 SessionPipeline 采集点

文件：

```text
core/session_pipeline.py
```

建议在以下阶段更新 snapshot：

```text
prepare_message_batch
normalize_incoming_content
prepare_chat_context
decide_reply_action
retrieve_memories
generate_reply
finalize_conversation
```

第一版重点采集：

```python
context["combined_text"]
context["history_dict"][chat_id]
context["relevant_diaries"]
context["structured_memory_context"]
```

### 6.2 Engine 采集点

文件：

```text
core/engine.py
```

方法：

```python
YukiEngine.api_reply()
```

在调用：

```python
combined_API_message = await build_chat_context(...)
```

之后记录：

```python
built_messages = combined_API_message
```

这是 WebUI 展示“完整构建上下文”的核心数据。

### 6.3 Prompt 构建采集点

文件：

```text
core/prompts.py
```

方法：

```python
build_chat_context()
build_structured_memory_prompt()
```

可以不在这里写全局状态，只在 Engine 拿返回后的 messages 即可。

---

## 7. Snapshot 管理器设计

### 7.1 ContextSnapshotStore

建议文件：

```text
modules/debug/context_snapshot.py
```

职责：

1. 保存最近 N 个快照；
2. 按 chat_id 查询最新快照；
3. 按 snapshot_id 查询详情；
4. 提供线程安全读写；
5. 自动脱敏。

建议接口：

```python
class ContextSnapshotStore:
    def put(self, snapshot: dict) -> str: ...
    def update(self, snapshot_id: str, **fields): ...
    def latest(self, chat_id: str | None = None) -> dict | None: ...
    def list_recent(self, limit: int = 50, chat_id: str | None = None) -> list[dict]: ...
    def get(self, snapshot_id: str) -> dict | None: ...
```

建议内存保存即可：

```text
collections.deque(maxlen=200)
```

第一版不需要持久化。

---

## 8. WebUI 页面设计

整体风格：

```text
深色玻璃拟态
卡片布局
渐变状态灯
可折叠 JSON/Prompt 面板
实时刷新
```

### 8.1 顶部状态栏

展示：

```text
Yuki Context Debug WebUI
运行状态：online/offline
刷新时间
当前活跃 chat_id
最近 snapshot 时间
```

### 8.2 左侧：会话列表

展示最近活跃会话：

```text
chat_id
mode
最后输入摘要
session 消息数
是否回复
最后构建耗时
```

支持点击切换会话。

### 8.3 中间：完整构建上下文

按构建顺序展示：

```text
1. System Prompt
2. Yuki-Memory 结构化上下文
3. 旧 RAG 回忆
4. 工具链约束
5. 破冰指令（如有）
6. 最近对话
7. 当前输入
```

每段显示：

```text
role
字符数
token 粗估
内容
```

要求：

- 每个 message 可折叠；
- system/user/assistant/tool 用不同颜色；
- 支持复制单条 message；
- 支持复制完整 messages JSON。

### 8.4 右侧：记忆召回面板

分三块：

```text
旧 RAG 回忆
Yuki-Memory profiles
Yuki-Memory facts
Yuki-Memory summaries
```

每条显示：

```text
score
memory type
subject
importance
source/candidate_id
content
```

### 8.5 下方：Pipeline 阶段时间线

展示：

```text
prepare_message_batch
normalize_incoming_content
prepare_chat_context
decide_reply_action
retrieve_memories
generate_reply
send_reply
finalize_conversation
```

每阶段显示：

```text
状态：pending/running/done/error
耗时
错误信息
```

### 8.6 Debug 工具栏

第一版只读按钮：

```text
刷新
暂停自动刷新
复制当前上下文
导出当前 snapshot JSON
切换紧凑/详细模式
```

后续可选按钮：

```text
手动触发 dry-run 整理
手动查询记忆
对比旧 RAG / 新 YukiMemory
```

---

## 9. 后端 API 设计

### 9.1 页面

```http
GET /
```

返回 WebUI HTML。

### 9.2 全局状态

```http
GET /api/status
```

返回：

```json
{
  "ok": true,
  "generated_at": "...",
  "snapshot_count": 10,
  "active_chats": ["1057020972"],
  "latest_snapshot_id": "..."
}
```

### 9.3 最近快照列表

```http
GET /api/snapshots?limit=50&chat_id=1057020972
```

返回简略列表。

### 9.4 快照详情

```http
GET /api/snapshots/<snapshot_id>
```

返回完整 snapshot。

### 9.5 最新快照

```http
GET /api/latest?chat_id=1057020972
```

返回指定 chat_id 最新 snapshot。

### 9.6 健康检查

```http
GET /api/health
```

返回：

```json
{"ok": true}
```

---

## 10. Token 粗估方案

第一版不引入 tokenizer，使用粗估：

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)
```

统计字段：

```json
{
  "total_chars": 12000,
  "estimated_tokens": 6000,
  "by_role": {
    "system": 3200,
    "user": 1800,
    "assistant": 1000
  }
}
```

后续可接入模型 tokenizer。

---

## 11. 脱敏规则

必须脱敏：

```text
sk- 开头 API Key
tp- 开头 API Key
Bearer token
NapCat token
可能的 authorization header
```

建议实现：

```python
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{12,}",
    r"tp-[A-Za-z0-9_-]{12,}",
    r"Bearer\s+[A-Za-z0-9._-]+",
]
```

替换为：

```text
<REDACTED>
```

---

## 12. 开发步骤

### 阶段 A：只读 WebUI 骨架

新增：

```text
modules/debug/context_snapshot.py
modules/debug/webui_server.py
scripts/debug_tools/start_context_debug_webui.py
```

完成：

- 启动本地 WebUI；
- `/api/health`；
- `/api/status`；
- 页面美观展示空状态。

验收：

```text
python scripts/debug_tools/start_context_debug_webui.py
打开 http://127.0.0.1:8777/
能看到页面
```

### 阶段 B：接入 SnapshotStore

完成：

- 实现 `ContextSnapshotStore`；
- 支持 put/update/latest/list/get；
- WebUI 展示最近 snapshot 列表。

验收：

```text
手动写入测试 snapshot
WebUI 能实时显示
```

### 阶段 C：接入主流程上下文捕获

修改：

```text
core/session_pipeline.py
core/engine.py
```

完成：

- 在 `retrieve_memories()` 后记录记忆召回；
- 在 `api_reply()` 构建 messages 后记录完整 `combined_API_message`；
- 不影响回复流程。

验收：

```text
机器人收到消息后，WebUI 显示最新 prompt messages
```

### 阶段 D：完善 UI 展示

完成：

- 左侧会话列表；
- 中间完整上下文；
- 右侧记忆召回；
- 下方 pipeline 时间线；
- 复制 JSON；
- 自动刷新/暂停刷新。

验收：

```text
能清晰看到每条 role/message
能区分结构化记忆和旧 RAG 回忆
能复制完整上下文 JSON
```

### 阶段 E：安全和性能

完成：

- 脱敏；
- snapshot 数量限制；
- 大文本折叠；
- API 异常兜底；
- 只监听 127.0.0.1。

验收：

```text
API Key 不出现在页面
WebUI 不影响主程序回复
```

---

## 13. 主流程接入建议

推荐不要让 WebUI 直接依赖 `SessionPipeline` 内部对象，而是新增全局 debug store。

建议：

```python
# modules/debug/context_snapshot.py
context_snapshot_store = ContextSnapshotStore()
```

在主流程中只做轻量写入：

```python
context_snapshot_store.put({...})
context_snapshot_store.update(snapshot_id, built_messages=combined_API_message)
```

WebUI 只读：

```python
context_snapshot_store.latest(chat_id)
```

这样耦合最低。

---

## 14. 与现有实时看板的关系

当前已有：

```text
scripts/03_RAG_Tools/live_memory_dashboard.py
```

它用于显示离线 backfill 进度。

新 WebUI 用途不同：

```text
Context Debug WebUI：显示主程序实时上下文构建
Live Memory Dashboard：显示离线候选提取进度
```

可以复用它的：

- 单文件 HTML 设计风格；
- ThreadingHTTPServer 方式；
- `/api/stats` 风格接口；
- 深色卡片 UI。

但建议不要直接混在同一个脚本里。

---

## 15. 验收标准

第一版完成标准：

- [ ] WebUI 可本地启动。
- [ ] 页面美观，有实时刷新。
- [ ] 能显示最近 snapshot 列表。
- [ ] 能显示某个 chat_id 的完整 LLM messages。
- [ ] 能显示旧 RAG 回忆。
- [ ] 能显示 Yuki-Memory 结构化上下文。
- [ ] 能显示 message role、字符数、token 粗估。
- [ ] 能复制完整上下文 JSON。
- [ ] API Key/token 已脱敏。
- [ ] 主程序没有因为 WebUI 异常而崩溃。

---

## 16. 不要做的事情

1. 不要在第一版实现写数据库。
2. 不要让 WebUI 发送 QQ 消息。
3. 不要让 WebUI 修改配置。
4. 不要暴露公网监听。
5. 不要在 prompt 中显示未脱敏 API Key。
6. 不要为了 WebUI 改变 Yuki 回复逻辑。
7. 不要引入大型前端框架，除非第一版已经稳定。
8. 不要把 WebUI 和离线 backfill 看板强行合并。

---

## 17. 推荐给实现 AI 的任务描述

请基于本计划实现 Yuki Context Debug WebUI，要求：

1. 新增 `modules/debug/context_snapshot.py`，实现内存快照存储。
2. 新增 `modules/debug/webui_server.py`，实现本地只读 WebUI 和 API。
3. 新增 `scripts/debug_tools/start_context_debug_webui.py`，可单独启动 WebUI。
4. 在 `core/session_pipeline.py` 和 `core/engine.py` 中以最小侵入方式写入 snapshot。
5. WebUI 展示完整构建上下文、旧 RAG 回忆、新 YukiMemory 结构化上下文、阶段耗时和 token 粗估。
6. 保持只读，不改变主程序行为。
7. 完成 `py_compile` 验证，并更新 changelog。

---

## 18. 当前优先级

建议优先做：

```text
阶段 A → 阶段 B → 阶段 C
```

也就是先让 WebUI 能启动、能显示 snapshot，再接主流程完整上下文。

不要一开始就做复杂控制台、配置修改或消息发送。
