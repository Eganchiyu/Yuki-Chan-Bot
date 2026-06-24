# YukiV6 项目架构文档

## 一、项目概述

**Project Yuki** 是一个基于 QQ 平台的 AI 虚拟助手，核心能力包括：
- 多群聊异步消息处理
- RAG 长期记忆系统
- 精力值/活跃度/生物钟行为模拟
- 表情包动态学习与 RLHF
- 小女仆自治系统（子代理）
- 简化 LLM 客户端（含主备故障转移）
- Function Call 工具链调用
- 工具调用前拟人化等待与执行日志观测

---

## 二、目录结构总览

```
YukiV6/
├── main.py                    # 主程序入口：初始化、启动流程
├── config.py                  # 配置管理：YAML 配置读写
├── init.py                    # 初始化工具：群组状态加载
├── setup.py                   # 一键安装/配置脚本
│
├── core/                      # 核心业务逻辑
│   ├── brain.py               # 状态管理：精力、活跃度、消息缓冲
│   ├── engine.py              # 主引擎：LLM 决策、工具链调用、回复生成
│   ├── session_pipeline.py    # 按 chat_id 串行运行的持久会话管道
│   ├── toolchain.py           # Function Call 注册、状态、延迟执行和结果封装
│   ├── tools.py               # 标准工具集合、schema 与 handler
│   ├── history_manager.py     # 历史记录管理
│   ├── maid.py                # 小女仆子代理系统
│   └── prompts.py             # 提示词模板管理
│
├── modules/                   # 功能模块
│   ├── QQNapcatListen/        # QQ 消息监听
│   │   └── listen_main.py     # WebSocket 监听、消息缓冲
│   ├── QQNapcatSend/          # QQ 消息发送（已迁移至 network）
│   ├── memory/                # 记忆系统
│   │   └── rag.py             # RAG 向量检索引擎
│   ├── message/               # 消息处理
│   │   ├── CQParser.py        # CQ 码解析器
│   │   ├── CQProtocol.py      # CQ 协议工具
│   │   └── GetMeta.py         # 元数据提取
│   ├── stickers/              # 表情包管理
│   │   └── manager.py         # 表情包学习与 RLHF
│   └── vision/                # 视觉处理
│       ├── processor.py       # 图像理解（VLM）
│       ├── cache.py           # 缓存管理
│       └── utils.py           # 工具函数
│
├── network/                   # 网络通信层
│   ├── ws_connection.py       # WebSocket 连接管理
│   └── ws_sender.py           # 消息发送器
│
├── utils/                     # 工具函数
│   ├── logger.py              # 日志系统
│   ├── llm_client.py          # LLM 客户端（含主备故障转移）
│   └── download_model.py      # 模型下载工具
│
├── scripts/                   # 脚本工具
│   ├── 01_api_test_tools/     # API 测试工具
│   ├── 02_energy_tools/       # 精力值可视化工具
│   ├── 03_RAG_Tools/          # RAG 记忆管理工具
│   ├── 04_meme_cache_tools/   # 表情包缓存工具
│   ├── 05_config_test_tools/  # 配置测试工具
│   └── 06_sticker_manager/    # 表情包管理工具
│
├── tests/                     # 测试文件
├── docs/                      # 文档目录
├── data/                      # 数据目录（运行时生成）
├── models/                    # 本地模型目录
└── yuki_memory/               # 向量数据库目录
```

---

## 三、核心模块详解

### 3.1 main.py - 主程序入口

**职责**：
- 初始化所有组件（`initialize_components()`）
- 创建并注入 `SessionPipeline`
- 选择运行模式（私聊/群聊）
- 启动消息监听

**关键组件**：
- `SessionPipeline`: 按 `chat_id` 串行运行的会话泵
- `main_process()`: 兼容旧调用路径的会话泵代理入口

**数据流**：
```
输入适配层 → message_buffer → SessionPipeline → YukiEngine → ToolChain/Maid →
上下文回写 → 消息发送 → 检查同 chat_id 新消息 → 下一轮处理
```

---

### 3.2 core/session_pipeline.py - 持久会话管道

**类**：`SessionPipeline`

**职责**：
- 按 `chat_id` 保证同一会话串行处理
- 管理防抖、消息合并、上下文加载、回复决策、记忆检索、发送与保存
- 在当前轮结束后继续消费运行中新增的消息，避免消息流分叉

**核心原则**：
```
一个 chat_id 同一时间只允许一个会话管道运行。
工具调用、小女仆回调和新消息都必须回流到同一 session 上下文。
```

---

### 3.3 core/brain.py - 状态管理

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
- `boost_activity()`: 提升活跃度
- `decay_heartbeat()`: 活跃度衰减心跳
- `update_energy()`: 更新精力值
- `consume_energy()`: 消耗精力值

---

### 3.4 core/engine.py - 主引擎

**类**：`YukiEngine`

**职责**：
- LLM 决策与响应处理
- 工具链多轮调用与结果回流
- 工具调用期间新消息合并
- 指令标签解析（`[DELEGATE_TO_MAID]`, `[MEME]`）
- 日记归档触发

**关键方法**：
- `api_reply()`: 调用 LLM 生成回复
- `_chat_with_tools()`: 执行多轮工具链决策
- `decide_to_reply()`: 决策是否回复
- `do_summarize()`: 日记归档

**工具链上下文原则**：
```
工具调用是 Yuki 的决策过程。
工具结果、工具期间新增消息和 Yuki 可见中间回复都会写入当前 session。
```

---

### 3.4 core/history_manager.py - 历史记录管理

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

### 3.5 core/toolchain.py 与 core/tools.py - Function Call 工具链

**职责**：
- `FunctionRegistry` 负责注册 `ToolSpec` 并向 LLM 提供 schema
- `ToolCallManager` 负责解析模型返回的 `tool_calls`、顺序执行工具、封装 OpenAI tool 消息
- `ToolContext` 在多轮工具调用期间携带 `chat_id`、运行模式、当前历史、用户输入与最小运行时依赖
- `core/tools.py` 通过 `TOOL_SPECS` 统一声明日记查询、定时任务、小女仆委托、主人私聊、浏览器搜索、QQ 文件发送、外部内容注入等标准工具

**执行策略**：
- 工具调用按顺序执行，避免共享状态并发写入
- 工具调用前读取 `cfg.TOOL_CALL_DELAY_SECONDS`，默认等待 1.2 秒，降低连续工具调用的机械感
- 记录模型请求的工具名、工具参数、执行耗时和成功状态，便于排查工具链问题
- 工具结果统一转换为 JSON 字符串，作为 `role=tool` 消息回传给模型继续推理

**配置项**：
- `cfg.timing.tool_call_delay_seconds` / `cfg.TOOL_CALL_DELAY_SECONDS`：工具调用前等待时间，单位秒

---

### 3.6 core/maid.py - 小女仆系统

**职责**：
- 子代理任务执行
- 多步骤任务分解
- 异步任务队列处理

**工作流程**：
```
任务入队 → 任务分解 → 逐步执行 → 结果反馈
```

---

### 3.7 modules/memory/rag.py - RAG 记忆系统

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
- `save_diary()`: 保存日记（含去重）
- `search_diaries()`: 语义检索日记
- `extract_keywords()`: 关键词提取

---

### 3.8 modules/QQNapcatListen/listen_main.py - 输入适配层

**职责**：
- WebSocket 消息监听
- 群聊开关控制（`/关闭`, `/开启`）
- QQ 消息标准化并 feed 到 `SessionPipeline`
- RLHF 正反馈捕捉
- 帮助指令拦截

**关键函数**：
- `configure_runtime()`: 注入运行时组件，避免反向导入 `main.py`
- `napcat_listen()`: 主监听循环
- `start_background_tasks()`: 启动后台任务
- `handle_group_switch()`: 处理群聊开关
- `feed_message()`: 将标准化消息放入会话缓冲并唤醒会话泵

---

### 3.9 network/ - 网络通信层

#### ws_connection.py - WebSocket 连接

**类**：`BotConnector`

**职责**：
- WebSocket 连接管理
- 自动重连机制
- 响应 Future 管理

**特性**：
- 连接池复用
- 心跳检测（ping/pong）
- 自动重连

#### ws_sender.py - 消息发送器

**类**：`MessageSender`

**职责**：
- 消息发送（文本、图片、语音）
- 失败重试机制
- CQ 码构建

**支持的发送类型**：
- `send()`: 文本消息
- `send_local_image()`: 本地图片
- `send_local_voice()`: 本地语音
- `send_ai_voice()`: AI 语音

---

### 3.10 utils/llm_client.py - LLM 客户端

**职责**：
- 发送 OpenAI 兼容格式的对话补全请求
- 主备故障转移（熔断 → 切换备用 → 120 秒自动恢复）
- 全局 aiohttp Session TCP 连接复用
- 平台 URL 解析与参数适配

**关键函数**：
- `chat_completion()`: 核心 HTTP 调用
- `llm_chat()`: 默认对话接口（含主备故障转移）
- `vision_chat()`: 视觉模型对话接口
- `close_global_session()`: 资源清理

**支持的平台**：
- DeepSeek (`https://api.deepseek.com/v1`)
- DashScope (`https://dashscope.aliyuncs.com/compatible-mode/v1`)
- YTea (`https://api.ytea.top/v1`)
- OpenAI (`https://api.openai.com/v1`)
- 自定义平台（通过配置文件指定 URL）

---

### 3.11 config.py - 配置管理

**职责**：
- YAML 配置文件读写
- 配置属性映射
- 配置热重载
- 配置自动保存

**配置层级**：
```
config.yaml (用户配置)
    ↓
config.py (属性映射)
    ↓
cfg (全局单例)
```

**关键配置项**：
- API 配置（LLM、Vision）
- 模型配置
- 连接配置
- 精力值系统配置
- 注意力系统配置
- 路径配置
- 时间/超时配置（含工具调用前等待时间）

---

## 四、数据流图

### 4.1 消息处理主流程

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
│  manage_buffer()                                                │
│  ├── RLHF 正反馈捕捉                                           │
│  ├── 防抖等待                                                   │
│  └── 消息入队                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  main_process()                                                 │
│  ├── 消息合并                                                   │
│  ├── 视觉处理（VLM）                                            │
│  ├── CQ码解析                                                   │
│  ├── 上下文加载                                                 │
│  ├── 决策判断（是否回复）                                       │
│  ├── 记忆检索（RAG）                                            │
│  ├── LLM 生成回复                                               │
│  ├── 指令标签解析                                               │
│  │   ├── [DELEGATE_TO_MAID] → 小女仆队列                       │
│  │   └── [MEME] → 表情包搜索                            │
│  ├── 消息发送                                                   │
│  └── 历史保存                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Function Call 流程

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
│  执行 handler 函数                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  回传结果给模型                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、关键设计模式

### 5.1 单例模式

以下组件使用单例模式：
- `MemoryRAG`: RAG 记忆系统

```python
class MemoryRAG:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
```

### 5.2 回调模式

- `engine.process_callback`: 主处理回调
- `brain_callback`: 消息注入回调

### 5.3 任务队列模式

- `maid_task_queue`: 小女仆任务队列
- `message_buffer`: 消息缓冲队列

### 5.4 故障转移模式

- `llm_client.py` 内置主备故障转移逻辑

---

## 六、注意事项

### 6.1 全局变量依赖

`listen_main.py` 从 `main.py` 导入大量全局变量：
```python
from main import yuki, engine, sender, history_manager, logger, connector, group_active_state, main_process
```

**注意**：确保 `main.py` 中的全局变量在 `initialize_components()` 后正确初始化。

### 6.2 异步并发

- 使用 `asyncio.Lock()` 保护共享状态
- 使用 `asyncio.create_task()` 创建后台任务
- 注意避免死锁

### 6.3 配置热重载

- `MemoryRAG` 支持屏蔽词热重载
- LLM 客户端在每次调用时直接从 config 读取最新参数
- 其他配置需要重启生效

### 6.4 内存管理

- `group_activity` 使用衰减机制，低活跃度自动清理
- `message_buffer` 在处理后清空
- 向量数据库使用持久化存储

### 6.5 错误处理

- WebSocket 连接失败自动重连
- LLM 调用失败触发故障转移
- 消息发送失败自动重试

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

## 八、部署架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        服务器环境                                │
├─────────────────────────────────────────────────────────────────┤
│  NapCat (QQ Bot Framework)                                      │
│  ├── WebSocket Server (ws://localhost:3001)                     │
│  └── HTTP Server (http://localhost:3004)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  YukiV6 主程序                                                  │
│  ├── WebSocket Client (连接 NapCat)                             │
│  ├── WebUI Server (http://127.0.0.1:1314)                      │
│  └── 后台任务                                                   │
│      ├── 精力衰减心跳                                           │
│      ├── 日记检查                                               │
│      ├── 破冰监控                                               │
│      └── 小女仆工作线程                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  外部服务                                                       │
│  ├── DeepSeek API                                               │
│  ├── DashScope API (Vision)                                     │
│  └── ChromaDB (本地)                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

**文档版本**：v1.0  
**最后更新**：2026-06-01  
**维护人员**：项目开发团队
