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
│   ├── tools/                 # 标准工具集合：按职责拆分的子服务与 TOOL_SPECS 装配
│   ├── history_manager.py     # 历史记录管理
│   ├── reply_format.py        # 回复标记格式容错（layout/MEME 归一化）
│   ├── maid.py                # 小女仆子代理系统
│   └── prompts.py             # 提示词模板管理
│
├── modules/                   # 功能模块
│   ├── QQNapcatListen/        # QQ 消息监听
│   │   └── listen_main.py     # NapCat 入站适配（事件 → 会话管线）
│   ├── QQNapcatSend/          # QQ 消息发送（已迁移至 network）
│   ├── memory/                # 记忆系统
│   │   └── rag.py             # RAG 向量检索引擎
│   ├── stickers/              # 表情包管理
│   │   └── manager.py         # 表情包学习与 RLHF
│   └── vision/                # 视觉处理
│       ├── processor.py       # 图片下载/压缩/转写（VLM）
│       ├── image_store.py     # 近期图片索引与原生视觉附件引用
│       ├── cache.py           # 缓存管理
│       └── utils.py           # 工具函数
│
├── network/                   # 网络通信层
│   └── napcat.py              # NapCat 接入层（连接/帧路由/CQ 协议/收发）
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

### 3.5 core/history_manager.py - 历史记录管理

**职责**：
- 对话历史的持久化存储
- 按群聊隔离的历史记录
- 日志文件写入
- 落盘前归一化回复标记（见 `core/reply_format.py`）

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

**回复标记修复**：
- `append_session_message()` 写入前调用 `normalize_reply_markup()`，只对 `assistant` 生效（用户原文不动），把 `[layout]...[/layout]`、`【MEME:...】` 等错格式统一成规范形式
- `preload()` 加载历史时批量修复既有错格式并原子落盘（`repair_reply_markup()` 为显式入口），断开「模型看到自己的错误示例 → 继续写错」的循环

---

### 3.5.1 core/reply_format.py - 回复标记格式容错

**职责**：统一处理模型偶发把内部标记括号写错的情况，避免思考内容外泄与表情包失效。

**标记规范**：
| 标记 | 规范形式 | 作用 |
|------|----------|------|
| 布局 | `<layout>盘算</layout>` | 内心思考，发送时剥离、写入历史时保留 |
| 表情包 | `[MEME:情绪]` | 发送阶段切分并检索表情包 |

**容错能力**：
- 括号变体：`[layout]`、`【layout】`、`［LAYOUT］`、`｛layout｝`、`<layout>` 等中英日全半角组合统一为 `<layout>` / `</layout>`，`[MEME]` 同理
- 混用括号：`[layout]...[/layout]`、`[layout]...</layout>`、`<layout>...[/layout]` 均按同一布局块剥离
- 未闭合开标签：从 `<layout>` 起整段视为内部思考丢弃，宁可少发一句也不外泄
- 空 MEME 标记（`[MEME]`、`【MEME:】`）直接丢弃

**对外入口**：
- `clean_visible_reply()`：发送前清洗，剥离布局、归一化 MEME（保留 `[MEME:x]` 供后续检索）
- `strip_meme_tags()`：只要纯文本时使用
- `normalize_reply_markup()`：写回历史前归一化，保留规范 layout
- `strip_layout_markup()` / `normalize_layout_tags()` / `normalize_meme_tags()`：细粒度操作

---

### 3.6 core/toolchain.py 与 core/tools/ - Function Call 工具链

**职责**：
- `FunctionRegistry` 负责注册 `ToolSpec` 并向 LLM 提供 schema
- `ToolCallManager` 负责解析模型返回的 `tool_calls`、顺序执行工具、封装 OpenAI tool 消息
- `ToolContext` 在多轮工具调用期间携带 `chat_id`、运行模式、当前历史、用户输入与最小运行时依赖
- `core/tools/` 按职责拆分标准工具子服务（状态、定时、日记、小女仆、消息、富文本、截屏、媒体、检索、空间、浏览器、网易云等），由 `core/tools/tools.py` 通过 `TOOL_SPECS` 统一装配声明，`core/tools/__init__.py` 保持 `core.tools` 旧引用路径兼容

**执行策略**：
- 工具调用按顺序执行，避免共享状态并发写入
- 工具调用前读取 `cfg.TOOL_CALL_DELAY_SECONDS`，默认等待 1.2 秒，降低连续工具调用的机械感
- 记录模型请求的工具名、工具参数、执行耗时和成功状态，便于排查工具链问题
- 工具结果统一转换为 JSON 字符串，作为 `role=tool` 消息回传给模型继续推理

**配置项**：
- `cfg.timing.tool_call_delay_seconds` / `cfg.TOOL_CALL_DELAY_SECONDS`：工具调用前等待时间，单位秒

---

### 3.7 core/maid.py - 小女仆系统

**职责**：
- 子代理任务执行
- 多步骤任务分解
- 异步任务队列处理

**工作流程**：
```
任务入队 → 任务分解 → 逐步执行 → 结果反馈
```

---

### 3.8 modules/memory/rag.py - RAG 记忆系统

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

### 3.10 modules/QQNapcatListen/listen_main.py - 入站适配层

**职责**：
- 把 NapCat 事件翻译成 `IncomingMessage` 并投给 `SessionPipeline`
- 群聊开关控制（`/关闭`, `/开启`）
- **双模路由**：群聊模式下同时接收主人私聊消息，路由为 `master_private` 模式
- 戳一戳：只处理戳到机器人自己的事件，按普通消息入队（不插队）
- 快速唤醒：命中机器人名字或 @ 到机器人时，跳过防抖并强制回复
- RLHF 正反馈捕捉
- 帮助指令拦截

**依赖**（只有两个，显式传参，无模块级全局）：
- `gateway`: `network.napcat.NapCatGateway`
- `pipeline`: `SessionPipeline`（已持有 yuki / engine / history_manager / group_active_state）

**关键函数**：
- `napcat_listen(gateway, pipeline, mode)`: 主事件循环
- `start_background_tasks()`: 启动后台任务（日记检查/破冰/精力衰减、可选监控）
- `handle_group_switch()`: 处理群聊开关
- `handle_poke_event()`: 处理戳一戳
- `feed_message()`: 将标准化消息放入会话缓冲并按需唤醒会话泵

---

### 3.11 network/napcat.py - NapCat 接入层

**类**：`NapCatGateway`（原来的 `BotConnector` + `MessageSender` 合并为一个对象）

**职责**：
- WebSocket 连接管理、token 拼接、断线重连（收敛为一处）
- 帧路由：`echo` 命中挂起请求 → 唤醒 `call()`；带 `post_type` 的帧 → 事件队列；
  其它 → 丢弃。因此 **出站不依赖有人消费事件流**，API 响应也不会混进事件流
- 出站动作：`send()` / `send_local_image()` / `send_local_file()` /
  `send_local_voice()` / `send_poke()` / `download_file()`
- 通用原语：`call(action, params, timeout)`（统一生成 echo 与超时）
- 查询：`get_member_info()`（进程内缓存）/ `get_member_name()` / `get_msg()` /
  `get_forward_messages()` / `get_group_meta()` / `get_cookies()` / `get_login_info()`
- CQ 协议：`parse_cq_codes()` 与一组纯函数（`smart_truncate`、
  `replace_other_cq_codes`、`extract_at_uids`、`mentions_self` 等）
- 运行计数：`stats`（frames/events/dropped/reconnects/calls/call_failures）

**边界**：只做传输 + 协议，不 import `core/` / `modules/` 的业务代码。

---

### 3.12 modules/vision/ - 图片理解与原生视觉

**职责**：
- 按 CQ 段 `sub_type` 区分普通图片与表情包
- 普通图片：开关开启时只下载登记为附件，交给主模型原生理解；关闭时走 VLM 转写
- 表情包：始终走外挂视觉模型转写（`[表情:描述]`），节省主模型视觉开销
- `ImageStore` 维护近期图片的短索引与唯一附件 ID，供 `[img:XXX]` 工具引用和模型图块复用

**关键配置**（`config.model`，默认全部关闭/保守）：
- `llm_native_vision_enabled`：主模型是否原生接收普通图片
- `backup_native_vision_enabled`：备用模型是否支持原生图片，否则降级为文本转写
- `native_vision_max_images` / `native_vision_history_turns`：单次张数与保留轮数
- `native_vision_max_size` / `native_vision_quality`：原生图片压缩参数

**数据流**：
```
普通图片 → 下载登记（轻量附件引用）→ 请求前渲染 imageUrl 图块 → 主模型
表情包   → VLM 转写 → [表情:描述] 纯文本 → 主模型
```

**边界**：聊天历史只持久化附件引用，不写入 Base64；索引过期或身份不匹配时按“图片已过期”处理，避免串图。

---

### 3.13 utils/llm_client.py - LLM 客户端

**职责**：
- 发送 OpenAI 兼容格式的对话补全请求
- 主备故障转移（熔断 → 切换备用 → 120 秒自动恢复）
- 空回复 / 请求失败的立即重试与降级文案
- 全局 aiohttp Session TCP 连接复用
- 平台 URL 解析与参数适配

**关键函数**：
- `chat_completion()`: 核心 HTTP 调用
- `llm_chat()`: 默认对话接口（含主备故障转移）
- `vision_chat()`: 视觉模型对话接口
- `close_global_session()`: 资源清理

**原生视觉降级**：主线路失败且备用模型不支持视觉时，`llm_chat_raw()` 通过 `fallback_messages_factory` 按需把图片附件转写为文本，再发往备用线路。

**空回复/失败重试**：`llm_chat_raw()` 在主备故障转移之外增加立即重试，次数由 `model.llm_max_retries`（默认 3，不含首次请求）控制。
- 判定为空：无 `tool_calls` 且文本内容为空（含纯空白；多模态块需至少一个非空文本）；带工具调用的空文本视为有效响应
- 出现过空回复后，后续重试在消息末尾追加一条 `role=user` 的「请不要输出空字符」（只加在临时副本上，不改动调用方 messages）
- `finish_reason=content_filter` 不做无意义重试，原样返回
- 重试耗尽后按原因返回降级文案：空回复 → 「输出了空字符」，请求失败 → 「暂时连接不上网络」

**支持的平台**：
- DeepSeek (`https://api.deepseek.com/v1`)
- DashScope (`https://dashscope.aliyuncs.com/compatible-mode/v1`)
- YTea (`https://api.ytea.top/v1`)
- OpenAI (`https://api.openai.com/v1`)
- 自定义平台（通过配置文件指定 URL）

---

### 3.14 config.py - 配置管理

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
│  ├── 视觉处理（普通图片原生输入 / 表情包 VLM 转写）              │
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
| 视觉模型 | Qwen-VL (DashScope)，表情包转写；主模型可按开关原生理解普通图片 |
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
│  ├── WebSocket Server (ws://127.0.0.1:3001，正向 WS，唯一在用)   │
│  ├── HTTP Server (未启用：onebot11 配置 httpServers 为空)        │
│  └── WebUI (http://localhost:6099)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  YukiV6 主程序                                                  │
│  ├── network/napcat.py (NapCatGateway：连接/帧路由/收发)         │
│  ├── WebUI Server (http://127.0.0.1:8777)                      │
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
