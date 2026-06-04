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

---

## 二、目录结构总览

```
YukiV6/
├── main.py                    # 主程序入口：初始化、启动流程
├── config.py                  # 配置管理：YAML 配置读写
├── init.py                    # 初始化工具：群组状态加载
├── webui.py                   # WebUI 管理面板
├── setup.py                   # 一键安装/配置脚本
│
├── core/                      # 核心业务逻辑
│   ├── brain.py               # 状态管理：精力、活跃度、欲望演算
│   ├── engine.py              # 主引擎：LLM 调用、消息处理
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
├── providers/                 # LLM Provider 层
│   ├── base.py                # Provider 基类
│   ├── registry.py            # Provider 注册中心（单例）
│   ├── fallback.py            # 故障转移 Provider
│   ├── openai_compatible.py   # OpenAI 兼容 Provider
│   ├── deepseek.py            # DeepSeek Provider
│   ├── dashscope.py           # 阿里灵积 Provider
│   └── ytea.py                # YTea Provider
│
├── utils/                     # 工具函数
│   ├── logger.py              # 日志系统
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
- 启动 WebUI 管理面板
- 选择运行模式（私聊/群聊）
- 启动消息监听

**关键组件**：
- `FunctionRegistry`: Function Call 注册中心
- `main_process()`: 核心消息处理函数

**数据流**：
```
消息进入 → 防抖缓冲 → 消息合并 → CQ码解析 → 视觉处理 → 
上下文加载 → 决策判断 → 记忆检索 → LLM 生成 → 消息发送
```

---

### 3.2 core/brain.py - 状态管理

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

### 3.3 core/engine.py - 主引擎

**类**：`YukiEngine`

**职责**：
- LLM 调用与响应处理
- 消息上下文构建
- 指令标签解析（`[DELEGATE_TO_MAID]`, `[MEME_SEARCH]`）
- 日记归档触发

**关键方法**：
- `api_reply()`: 调用 LLM 生成回复
- `decide_to_reply()`: 决策是否回复
- `do_summarize()`: 日记归档

**依赖**：
- `rag`: RAG 记忆系统
- `history_manager`: 历史记录管理
- `yuki_state`: 状态管理
- `sender`: 消息发送器

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

### 3.5 core/maid.py - 小女仆系统

**职责**：
- 子代理任务执行
- 多步骤任务分解
- 异步任务队列处理

**工作流程**：
```
任务入队 → 任务分解 → 逐步执行 → 结果反馈
```

---

### 3.6 modules/memory/rag.py - RAG 记忆系统

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

### 3.7 modules/QQNapcatListen/listen_main.py - 消息监听

**职责**：
- WebSocket 消息监听
- 群聊开关控制（`/关闭`, `/开启`）
- 消息防抖缓冲
- RLHF 正反馈捕捉
- 帮助指令拦截

**关键函数**：
- `napcat_listen()`: 主监听循环
- `start_background_tasks()`: 启动后台任务
- `handle_group_switch()`: 处理群聊开关
- `manage_buffer()`: 消息缓冲管理

---

### 3.8 network/ - 网络通信层

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

### 3.9 providers/ - LLM Provider 层

#### 架构设计

```
ProviderRegistry (单例)
    ├── DeepSeekProvider
    ├── DashScopeProvider
    ├── OpenAICompatibleProvider
    └── FallbackProvider (故障转移)
```

#### registry.py - Provider 注册中心

**类**：`ProviderRegistry`（单例）

**职责**：
- 自动发现 Provider 模块
- Provider 生命周期管理
- 配置热重载

**特性**：
- 自动扫描 providers 包下的所有模块
- 读取 `PLATFORM_NAME` 完成注册
- 支持配置热重载

#### base.py - Provider 基类

**抽象方法**：
- `chat()`: 对话补全
- `close()`: 关闭连接

#### fallback.py - 故障转移 Provider

**职责**：
- 主 Provider 失败时自动切换
- 多 Provider 轮询
- 错误日志记录

---

### 3.10 config.py - 配置管理

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
│  │   └── [MEME_SEARCH] → 表情包搜索                            │
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
- `ProviderRegistry`: Provider 注册中心

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

- `FallbackProvider`: Provider 故障自动切换

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

- `ProviderRegistry` 支持配置热重载
- `MemoryRAG` 支持屏蔽词热重载
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
