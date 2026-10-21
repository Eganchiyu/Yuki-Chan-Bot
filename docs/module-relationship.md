# YukiV6 模块关系与依赖文档

本文档详细描述 YukiV6 项目各模块间的依赖关系、数据流和接口，旨在帮助 LLM Agent 快速理解项目结构并进行开发。

---

## 一、项目整体架构

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         入口层 (Entry)                           │
│  main.py - 组装组件、启动监听、资源清理                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ 配置层        │  │ 初始化层      │  │   业务逻辑层      │
│ config.py    │  │ init.py      │  │   core/ modules/ │
│ 配置中心      │  │ 状态持久化    │  │                  │
└──────────────┘  └──────────────┘  └──────────────────┘
        ▲                                    │
        │                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      网络层 (Network)                            │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ BotConnector     │◄───│ MessageSender   │                     │
│  │ (ws_connection)  │    │ (ws_sender)     │                     │
│  │ WebSocket 连接   │    │ 消息发送/文件下载 │                     │
│  └─────────────────┘    └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                       工具层 (Utils)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ logger.py    │  │ llm_client.py│  │ download_model.py│       │
│  │ 日志系统      │  │ LLM 对话客户端│  │ 嵌入模型下载      │       │
│  └──────────────┘  └──────────────┘  └──────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 模块依赖关系图

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    main.py                         │
                    │  组装组件 → 创建 SessionPipeline → 启动监听          │
                    └──────────────────────┬─────────────────────────────┘
                                           │
                    ┌──────────────────────▼─────────────────────────────┐
                    │              QQNapcatListen/                       │
                    │         (消息监听入口)                              │
                    └──────────────────────┬─────────────────────────────┘
                                           │
                    ┌──────────────────────▼─────────────────────────────┐
                    │              message/                              │
                    │    CQParser ← CQProtocol ← GetMeta                │
                    │         (消息解析与协议处理)                        │
                    └──────────────────────┬─────────────────────────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────────────────────┐
        │                                  │                                  │
        ▼                                  ▼                                  ▼
┌───────────────┐              ┌───────────────────┐              ┌───────────────────┐
│   memory/     │              │    vision/        │              │   yuki_memory/    │
│   (旧 RAG)    │              │   (视觉识别)      │              │   (新记忆系统)    │
└───────┬───────┘              └─────────┬─────────┘              └─────────┬─────────┘
        │                                │                                  │
        │                                ▼                                  │
        │                      ┌───────────────────┐                        │
        │                      │    stickers/      │                        │
        │                      │  (表情包管理)     │                        │
        │                      └───────────────────┘                        │
        │                                                                   │
        └───────────────────────────┬───────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────────────┐
                    │              core/                     │
                    │   engine.py, brain.py, session_pipeline│
                    │         (核心业务逻辑)                 │
                    └───────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────────────┐
                    │              debug/                    │
                    │   context_snapshot.py, webui_server.py │
                    │         (调试监控)                     │
                    └───────────────────────────────────────┘
```

---

## 二、核心模块详解

### 2.1 入口层

#### main.py - 主程序入口

**职责**：
- 初始化所有组件
- 创建并注入 SessionPipeline
- 启动消息监听
- 资源清理

**依赖**：
- `config` - 配置中心
- `init` - 状态持久化
- `core.brain` - 状态管理
- `core.engine` - 主引擎
- `core.history_manager` - 历史记录
- `core.session_pipeline` - 会话管道
- `modules.memory.rag` - RAG 记忆
- `modules.yuki_memory.retriever` - 结构化记忆检索
- `modules.stickers.manager` - 表情包管理
- `modules.message.CQParser` - 消息解析
- `modules.vision.processor` - 视觉处理
- `modules.QQNapcatListen.listen_main` - 消息监听
- `network.ws_connection` - WebSocket 连接
- `network.ws_sender` - 消息发送
- `utils.logger` - 日志系统
- `utils.llm_client` - LLM 客户端

**启动流程**：
```python
1. setup_logging()              # 初始化日志
2. load_group_state()           # 加载群聊状态
3. initialize_components()      # 初始化所有组件
4. SessionPipeline              # 创建会话管道
5. configure_runtime()          # 配置运行时参数
6. warmup_groups()              # 预热群组
7. napcat_listen(mode)          # 启动消息监听
8. atexit → _do_cleanup()       # 退出时清理资源
```

---

### 2.2 配置层

#### config.py - 配置中心

**职责**：
- YAML 配置文件读写
- 配置属性映射
- 配置热重载
- 配置自动保存

**配置层级**：
```
Config
├── robot_name, master_name, max_message_length, debug
├── api: APIConfig          (llm_base_url, backup_base_url, image_process_url, keys...)
├── model: ModelConfig      (llm, backup, vision, disable_thinking)
├── connection: ConnectionConfig  (napcat_ws_url, napcat_ws_token, max_retries)
├── target: TargetConfig    (qq, groups, whitelist)
├── diary: DiaryConfig      (idle_seconds, min_turns, max_length)
├── rag: RAGConfig          (retrieval_top_k, keep_last_dialogue)
├── energy: EnergyConfig    (initial, max, recovery_per_min, cost_per_reply, min_active)
├── attention: AttentionConfig  (sensitivity, decay_level, sigmoid_centre, sigmoid_alpha, keywords)
├── paths: PathsConfig      (vector_db, embed_model, history_file, log_file, cache_dir, cache_file)
└── timing: TimingConfig    (debounce_time, tool_call_delay_seconds, request_timeout)
```

**全局单例**：`cfg = load_config()`（模块末尾）

---

#### init.py - 初始化工具

**职责**：
- 群聊状态持久化加载/保存
- 启动前配置检查

**主要函数**：
- `load_group_state()` - 从 `data/group_state.json` 加载群聊状态
- `save_group_state(state)` - 保存群聊状态到 JSON
- `check_config()` - 启动前检查配置文件、黑名单、嵌入模型是否存在

---

### 2.3 核心业务层 (core/)

#### core/brain.py - 状态管理

**类**：`YukiState`

**职责**：
- 精力值系统管理
- 活跃度感知与衰减
- 消息缓冲区管理
- 小女仆任务队列

**关键属性**：
```python
energy: Dict[str, float]           # 精力值
group_activity: Dict[str, float]   # 活跃度
message_buffer: Dict[str, list]    # 消息缓冲区
maid_task_queue: asyncio.Queue     # 小女仆任务队列
```

**关键方法**：
- `boost_activity(chat_id, amount)` - 提升活跃度
- `decay_heartbeat()` - 活跃度衰减心跳
- `update_energy(chat_id, delta)` - 更新精力值
- `consume_energy(chat_id, amount)` - 消耗精力值

---

#### core/engine.py - 主引擎

**类**：`YukiEngine`

**职责**：
- LLM 决策与响应处理
- 工具链多轮调用与结果回流
- 工具调用期间新消息合并
- 指令标签解析（`[DELEGATE_TO_MAID]`, `[MEME_SEARCH]`）
- 日记归档触发

**关键方法**：
- `api_reply()` - 调用 LLM 生成回复
- `_chat_with_tools()` - 执行多轮工具链决策
- `decide_to_reply()` - 决策是否回复
- `do_summarize()` - 日记归档

**依赖**：
- `core.brain.YukiState` - 状态管理
- `core.history_manager.HistoryManager` - 历史记录
- `core.toolchain.FunctionRegistry` - 工具注册
- `core.toolchain.ToolCallManager` - 工具调用
- `modules.memory.rag.MemoryRAG` - RAG 记忆
- `network.ws_sender.MessageSender` - 消息发送
- `utils.llm_client` - LLM 客户端

---

#### core/session_pipeline.py - 会话管道

**类**：`SessionPipeline`

**职责**：
- 按 `chat_id` 保证同一会话串行处理
- 管理防抖、消息合并、上下文加载、回复决策、记忆检索、发送与保存
- 在当前轮结束后继续消费运行中新增的消息

**核心原则**：
```
一个 chat_id 同一时间只允许一个会话管道运行。
工具调用、小女仆回调和新消息都必须回流到同一 session 上下文。
```

---

#### core/toolchain.py - Function Call 工具链

**类**：
- `FunctionRegistry` - 工具注册中心
- `ToolCallManager` - 工具调用执行器
- `ToolContext` - 工具调用上下文
- `ToolResult` - 工具执行结果

**职责**：
- `FunctionRegistry` 负责注册 `ToolSpec` 并向 LLM 提供 schema
- `ToolCallManager` 负责解析模型返回的 `tool_calls`、顺序执行工具、封装 OpenAI tool 消息
- `ToolContext` 在多轮工具调用期间携带 `chat_id`、运行模式、当前历史、用户输入与最小运行时依赖

**执行策略**：
- 工具调用按顺序执行，避免共享状态并发写入
- 工具调用前读取 `cfg.TOOL_CALL_DELAY_SECONDS`，默认等待 1.2 秒
- 记录模型请求的工具名、工具参数、执行耗时和成功状态

---

#### core/tools.py - 标准工具集合

**职责**：
- 定义 7 个标准工具的 Schema 和 Handler
- 统一声明日记查询、定时任务、小女仆委托、主人私聊、浏览器搜索、QQ 文件发送、外部内容注入

**标准工具**：
| 工具名 | 描述 |
|--------|------|
| `search_diary` | 查询 Yuki 的日记/记忆 |
| `manage_timer_task` | 创建、取消或列出定时任务 |
| `delegate_to_maid` | 将重型任务委托给小女仆处理 |
| `send_master_private` | 向主人私聊发送私密信息 |
| `browser_search` | 生成网络搜索入口 |
| `send_qq_file` | 发送图片或语音文件 |
| `inject_external_content` | 向当前对话注入外部系统提供的动态内容 |

---

#### core/maid.py - 小女仆系统

**职责**：
- 子代理任务执行
- 多步骤任务分解
- 异步任务队列处理
- 自主编程与技能进化

**工作流程**：
```
任务入队 → 任务分解 → 逐步执行 → 结果反馈
```

---

#### core/history_manager.py - 历史记录管理

**职责**：
- 对话历史的持久化存储
- 按群聊隔离的历史记录
- 日志文件写入

**存储格式**：
```json
{
  "chat_id": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "...", "time": "..."},
    {"role": "assistant", "content": "...", "time": "..."}
  ]
}
```

---

#### core/prompts.py - 提示词管理

**职责**：
- 系统提示词构建
- 破冰提示词生成
- 视觉识别提示词

---

### 2.4 功能模块层 (modules/)

#### modules/memory/rag.py - RAG 记忆系统

**类**：`MemoryRAG`（单例）

**职责**：
- 向量数据库管理（ChromaDB）
- 嵌入模型加载（text2vec-base-chinese）
- 日记存储与检索
- 关键词提取（jieba）
- 屏蔽词管理

**技术栈**：
- 向量数据库：ChromaDB
- 嵌入模型：text2vec-base-chinese
- 分词：jieba

**关键方法**：
- `save_diary(content, date_str)` - 保存日记（含去重）
- `search_diaries(query, top_k)` - 语义检索日记
- `search_memory(query, top_k)` - 混合检索：当前群聊 + 手动录入
- `extract_keywords(text, top_k)` - 关键词提取

---

#### modules/yuki_memory/ - 新一代结构化记忆系统

**职责**：
- 替代旧 RAG 系统的结构化记忆存储
- 支持多类型记忆（事实、偏好、关系、画像等）
- 多层压缩整理

**主要类**：
- `MemoryRecord` - 标准化记忆记录模型
- `YukiMemoryStore` - 向量存储层
- `YukiMemoryRetriever` - 结构化上下文检索适配层
- `MultiLayerMemoryConsolidator` - 多轮多层次压缩整理器
- `LegacyDiaryMigrator` - 旧日记备份迁移工具

**支持的记忆类型**：
`raw`, `summary`, `fact`, `preference`, `profile`, `relationship`, `todo`, `event`, `snapshot`

---

#### modules/message/ - 消息解析与协议处理

**职责**：
- 处理 QQ 的 CQ 码（一种消息格式协议）
- 解析 @、回复、图片等特殊消息

**主要类**：
- `CQProtocol` - CQ 码翻译器（纯文本替换）
- `CQCodeParser` - CQ 码解析器（协调网络请求）
- `MetaGetter` - 通过 NapCat API 获取元数据

---

#### modules/stickers/ - 表情包智能管理模块

**职责**：
- 管理表情包的入库、检索、重排
- 实现"积热冷却"算法防止表情包发散使用

**主要类**：`StickerManager`

**关键方法**：
- `ingest_sticker()` - 自动学习一张表情包入库
- `get_suitable_sticker()` - 检索、重排并选择最佳表情包
- `add_preference()` - 正反馈偏好加成

---

#### modules/vision/ - 视觉识别与图像处理模块

**职责**：
- 处理图片消息的识别、压缩、缓存
- 调用视觉模型理解表情包含义

**主要类**：
- `MemeProcessor` - 图像处理器核心
- `MemeCache` - 表情包识别结果缓存

---

#### modules/debug/ - 调试与监控模块

**职责**：
- 提供运行时上下文快照
- WebUI 调试界面

**主要类**：
- `ContextSnapshotStore` - 线程安全的内存快照存储
- `ContextDebugRequestHandler` - HTTP 请求处理器

---

### 2.5 网络层 (network/)

#### network/ws_connection.py - WebSocket 连接管理

**类**：`BotConnector`

**职责**：
- WebSocket 连接管理
- 自动重连机制
- 响应 Future 管理

**特性**：
- 连接池复用
- 心跳检测（ping/pong）
- 自动重连

---

#### network/ws_sender.py - 消息发送

**类**：`MessageSender`

**职责**：
- 消息发送（文本、图片、语音）
- 失败重试机制
- CQ 码构建

**支持的发送类型**：
- `send()` - 文本消息
- `send_local_image()` - 本地图片
- `send_local_file()` - 本地文件
- `send_local_voice()` - 本地语音
- `send_ai_voice()` - AI 语音
- `send_poke()` - 戳一戳

---

### 2.6 工具层 (utils/)

#### utils/logger.py - 日志系统

**职责**：
- 统一的日志配置
- 控制台彩色输出
- 文件持久化
- 日志归档

**核心组件**：
- `PrettyFormatter` - 文件日志格式
- `ColoredConsoleFormatter` - 控制台日志格式
- `setup_logging()` - 初始化全局日志配置
- `get_logger()` - 获取 logger 实例

---

#### utils/llm_client.py - LLM 客户端

**职责**：
- 统一的 LLM 对话接口
- 支持主备故障转移
- 全局连接池复用
- 平台参数适配

**关键函数**：
- `chat_completion_raw()` - 底层请求，返回原始 message dict
- `chat_completion()` - 底层请求，返回纯文本
- `llm_chat_raw()` - 高层接口，含主备故障转移，返回原始 message
- `llm_chat()` - 高层接口，含主备故障转移，返回纯文本
- `vision_chat()` - 视觉模型专用接口

**故障转移逻辑**：主线路失败 → 熔断 → 切换备用线路 → 120 秒后尝试恢复主线路

---

#### utils/download_model.py - 嵌入模型下载

**职责**：
- 下载并保存 RAG 系统使用的语义嵌入模型（`text2vec-base-chinese`）

---

## 三、数据流详解

### 3.1 消息处理主流程

```
┌─────────────────────────────────────────────────────────────────┐
│                         消息进入                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  napcat_listen()                                                │
│  ├── WebSocket 监听                                             │
│  ├── 群聊开关检查                                               │
│  └── 消息格式化                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  feed_message()                                                 │
│  ├── RLHF 正反馈捕捉                                           │
│  ├── 防抖等待                                                   │
│  └── 消息入队                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  SessionPipeline.process_loop()                                 │
│  ├── 消息合并                                                   │
│  ├── 视觉处理（VLM）                                            │
│  ├── CQ码解析                                                   │
│  ├── 上下文加载                                                 │
│  ├── 决策判断（是否回复）                                       │
│  ├── 记忆检索（RAG）                                            │
│  ├── LLM 生成回复                                               │
│  ├── 指令标签解析                                               │
│  │   ├── [DELEGATE_TO_MAID] → 小女仆队列                       │
│  │   └── [MEME_SEARCH] → 表情包搜索                            │
│  ├── 消息发送                                                   │
│  └── 历史保存                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Function Call 流程

```
┌─────────────────────────────────────────────────────────────────┐
│  FunctionRegistry                                               │
│  ├── 注册 tools schema                                          │
│  ├── 注册 handler 函数                                          │
│  └── 提供 tools 列表                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LLM 请求（带 tools 参数）                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模型返回 tool_calls                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ToolCallManager.execute_tool_call()                            │
│  ├── 解析参数                                                   │
│  ├── 执行 handler 函数                                          │
│  └── 封装结果                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  回传结果给模型                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 记忆检索流程

```
┌─────────────────────────────────────────────────────────────────┐
│  用户输入                                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  SessionPipeline.retrieve_memories()                            │
│  ├── 调用 YukiMemoryRetriever.retrieve()                        │
│  │   ├── 搜索 profile (画像)                                    │
│  │   ├── 搜索 fact/preference (事实/偏好)                        │
│  │   ├── 搜索 summary (摘要)                                    │
│  │   └── 失败时回退旧 RAG                                        │
│  └── 调用 MemoryRAG.search_diaries()                            │
│      ├── 语义向量检索                                           │
│      └── 关键词检索                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  build_structured_memory_prompt()                               │
│  ├── 注入结构化长期记忆                                         │
│  └── 注入旧 RAG 回忆                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LLM 上下文                                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、关键设计模式

### 4.1 单例模式

以下组件使用单例模式：
- `MemoryRAG` - RAG 记忆系统
- `YukiMemoryStore` - 结构化记忆存储

```python
class MemoryRAG:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
```

### 4.2 回调模式

- `engine.process_callback` - 主处理回调
- `brain_callback` - 消息注入回调

### 4.3 任务队列模式

- `maid_task_queue` - 小女仆任务队列
- `message_buffer` - 消息缓冲队列

### 4.4 故障转移模式

- `llm_client.py` 内置主备故障转移逻辑
- WebSocket 连接失败自动重连

### 4.5 管道模式

- `SessionPipeline` 按 `chat_id` 串行运行的会话管道
- `MultiLayerMemoryConsolidator` 多层压缩整理管道

---

## 五、模块接口速查表

### 5.1 核心模块接口

| 模块 | 类/函数 | 主要方法 | 职责 |
|------|---------|----------|------|
| `core.brain` | `YukiState` | `boost_activity()`, `consume_energy()` | 状态管理 |
| `core.engine` | `YukiEngine` | `api_reply()`, `decide_to_reply()` | 决策引擎 |
| `core.session_pipeline` | `SessionPipeline` | `enqueue_message()`, `process_loop()` | 会话管道 |
| `core.toolchain` | `FunctionRegistry` | `register()`, `get_tools()` | 工具注册 |
| `core.toolchain` | `ToolCallManager` | `execute_tool_call()` | 工具执行 |
| `core.maid` | `MaidAgent` | `delegate_task()` | 小女仆系统 |
| `core.history_manager` | `HistoryManager` | `load()`, `save()` | 历史记录 |
| `core.prompts` | - | `build_system_prompt()` | 提示词管理 |

### 5.2 功能模块接口

| 模块 | 类/函数 | 主要方法 | 职责 |
|------|---------|----------|------|
| `modules.memory.rag` | `MemoryRAG` | `save_diary()`, `search_diaries()` | RAG 记忆 |
| `modules.yuki_memory.store` | `YukiMemoryStore` | `save()`, `search()` | 结构化记忆 |
| `modules.yuki_memory.retriever` | `YukiMemoryRetriever` | `retrieve()` | 记忆检索 |
| `modules.yuki_memory.consolidator` | `MultiLayerMemoryConsolidator` | `consolidate()` | 记忆整理 |
| `modules.message.CQParser` | `CQCodeParser` | `parse_all_cq_codes()` | 消息解析 |
| `modules.message.CQProtocol` | `CQProtocol` | `replace_other_CQ_codes()` | CQ 码处理 |
| `modules.stickers.manager` | `StickerManager` | `ingest_sticker()`, `get_suitable_sticker()` | 表情包管理 |
| `modules.vision.processor` | `MemeProcessor` | `understand_from_url()` | 视觉处理 |
| `modules.vision.cache` | `MemeCache` | `get()`, `set()` | 缓存管理 |
| `modules.debug.context_snapshot` | `ContextSnapshotStore` | `save_snapshot()` | 调试快照 |

### 5.3 网络层接口

| 模块 | 类/函数 | 主要方法 | 职责 |
|------|---------|----------|------|
| `network.ws_connection` | `BotConnector` | `ensure_connection()`, `listen()`, `send_request()` | WebSocket 连接 |
| `network.ws_sender` | `MessageSender` | `send()`, `send_local_image()`, `send_poke()` | 消息发送 |

### 5.4 工具层接口

| 模块 | 类/函数 | 主要方法 | 职责 |
|------|---------|----------|------|
| `utils.logger` | - | `setup_logging()`, `get_logger()` | 日志系统 |
| `utils.llm_client` | - | `llm_chat()`, `vision_chat()` | LLM 客户端 |
| `config` | `Config` | `load_config()`, `sync_config()` | 配置管理 |
| `init` | - | `load_group_state()`, `save_group_state()` | 状态持久化 |

---

## 六、开发指南

### 6.1 新增功能模块

1. **确定模块位置**：根据功能类型选择 `core/`、`modules/` 或 `utils/`
2. **遵循命名规范**：文件名使用小写字母和下划线
3. **定义清晰接口**：导出类和函数，避免暴露内部实现
4. **添加依赖声明**：在文件开头导入所需模块
5. **更新文档**：同步更新 `docs/architecture.md` 和 `docs/changelog.md`

### 6.2 修改现有模块

1. **理解模块职责**：阅读模块文档和代码注释
2. **检查依赖关系**：确认修改不会影响其他模块
3. **保持接口兼容**：避免破坏性变更
4. **添加测试**：为核心功能添加单元测试
5. **更新文档**：同步更新相关文档

### 6.3 调试技巧

1. **使用 Debug WebUI**：设置环境变量 `YUKI_CONTEXT_DEBUG_WEBUI=1` 启动调试界面
2. **查看日志**：日志文件位于 `data/yuki_log.txt`
3. **使用测试脚本**：`scripts/` 目录下有各种测试工具
4. **检查配置**：确保 `configs/config.yaml` 配置正确

---

## 七、技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| 异步框架 | asyncio |
| WebSocket | websockets |
| 向量数据库 | ChromaDB |
| 嵌入模型 | sentence-transformers |
| 分词 | jieba |
| 视觉模型 | Qwen-VL (DashScope) |
| LLM | DeepSeek / OpenAI 兼容 |
| 配置管理 | PyYAML |
| WebUI | Gradio |

---

## 八、注意事项

### 8.1 全局变量依赖

`listen_main.py` 通过 `configure_runtime()` 注入运行时组件，避免反向导入 `main.py`。

### 8.2 异步并发

- 使用 `asyncio.Lock()` 保护共享状态
- 使用 `asyncio.create_task()` 创建后台任务
- 注意避免死锁

### 8.3 配置热重载

- `MemoryRAG` 支持屏蔽词热重载
- LLM 客户端在每次调用时直接从 config 读取最新参数
- 其他配置需要重启生效

### 8.4 内存管理

- `group_activity` 使用衰减机制，低活跃度自动清理
- `message_buffer` 在处理后清空
- 向量数据库使用持久化存储

### 8.5 错误处理

- WebSocket 连接失败自动重连
- LLM 调用失败触发故障转移
- 消息发送失败自动重试

---

**文档版本**：v1.0  
**最后更新**：2026-06-16  
**维护人员**：项目开发团队
