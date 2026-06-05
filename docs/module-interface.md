# YukiV6 模块接口文档

本文档描述 YukiV6 各模块的公共方法签名和使用示例。

---

## 一、核心模块

### 1.1 YukiEngine - 决策引擎

**位置**：`core/engine.py`

**类**：`YukiEngine`

**职责**：LLM 决策与响应处理、工具链多轮调用、指令标签解析。

#### 构造函数

```python
def __init__(self, yuki, sender, history_manager, memory_rag)
```

**参数**：
- `yuki: YukiState` - 状态管理实例
- `sender: MessageSender` - 消息发送器
- `history_manager: HistoryManager` - 历史记录管理器
- `memory_rag: MemoryRAG` - RAG 记忆系统实例

#### 公共方法

##### `async api_reply(chat_id, mode, user_text, system_prompt, history) -> str`

调用 LLM 生成回复。

**参数**：
- `chat_id: str` - 会话 ID
- `mode: str` - 运行模式（"group" 或 "private"）
- `user_text: str` - 用户输入文本
- `system_prompt: str` - 系统提示词
- `history: list` - 对话历史

**返回**：`str` - LLM 回复内容

**示例**：
```python
reply = await engine.api_reply(
    chat_id="group_123",
    mode="group",
    user_text="你好",
    system_prompt="你是 Yuki",
    history=[]
)
```

##### `async decide_to_reply(chat_id, mode, user_text) -> bool`

决策是否回复。

**参数**：
- `chat_id: str` - 会话 ID
- `mode: str` - 运行模式
- `user_text: str` - 用户输入文本

**返回**：`bool` - 是否回复

##### `async do_summarize(chat_id, mode) -> None`

触发日记归档。

**参数**：
- `chat_id: str` - 会话 ID
- `mode: str` - 运行模式

**返回**：无

---

### 1.2 YukiState - 状态管理

**位置**：`core/brain.py`

**类**：`YukiState`

**职责**：精力值系统管理、活跃度感知与衰减、消息缓冲区管理。

#### 属性

- `energy: Dict[str, float]` - 精力值
- `group_activity: Dict[str, float]` - 活跃度
- `message_buffer: Dict[str, list]` - 消息缓冲区
- `maid_task_queue: asyncio.Queue` - 小女仆任务队列

#### 公共方法

##### `boost_activity(chat_id, amount=1.0) -> None`

提升活跃度。

**参数**：
- `chat_id: str` - 会话 ID
- `amount: float` - 提升量，默认 1.0

**返回**：无

##### `async decay_heartbeat() -> None`

活跃度衰减心跳。

**参数**：无

**返回**：无

##### `update_energy(chat_id, delta) -> None`

更新精力值。

**参数**：
- `chat_id: str` - 会话 ID
- `delta: float` - 变化量（正数为恢复，负数为消耗）

**返回**：无

##### `consume_energy(chat_id, amount) -> bool`

消耗精力值。

**参数**：
- `chat_id: str` - 会话 ID
- `amount: float` - 消耗量

**返回**：`bool` - 是否成功消耗（精力值是否足够）

---

### 1.3 FunctionRegistry - Function Call 注册中心

**位置**：`core/toolchain.py`

**类**：`FunctionRegistry`

**职责**：管理 Function Call 工具的注册、注销和查询。

#### 公共方法

##### `register(schema, handler) -> None`

注册一个 function tool。

**参数**：
- `schema: dict` - 工具 schema 定义
- `handler: Callable[..., Awaitable[ToolResult]]` - 异步处理函数

**返回**：无

##### `unregister(name) -> None`

注销一个 function tool。

**参数**：
- `name: str` - 工具名称

**返回**：无

##### `get_tools() -> list`

获取所有已注册的 tools 列表。

**返回**：`list[dict]` - 工具 schema 列表

##### `get_handler(name) -> Callable`

获取指定 function 的执行函数。

**参数**：
- `name: str` - 工具名称

**返回**：`Callable[..., Awaitable[ToolResult]]` 或 `None`

---

### 1.4 ToolCallManager - 工具调用执行器

**位置**：`core/toolchain.py`

**类**：`ToolCallManager`

**职责**：负责工具调用的参数解析、执行状态管理和结果标准化。

#### 构造函数

```python
def __init__(self, registry, max_rounds=4)
```

**参数**：
- `registry: FunctionRegistry` - FunctionRegistry 实例
- `max_rounds: int` - 最大工具调用轮数，默认 4

#### 公共方法

##### `start_session(chat_id, user_text) -> None`

记录一次工具调用会话。

**参数**：
- `chat_id: str` - 会话 ID
- `user_text: str` - 用户输入文本

**返回**：无

##### `finish_session(chat_id) -> None`

结束一次工具调用会话。

**参数**：
- `chat_id: str` - 会话 ID

**返回**：无

##### `async execute_tool_call(tool_call, context) -> dict`

执行单个 tool call，并返回 OpenAI tool 消息。

**参数**：
- `tool_call: dict` - 工具调用信息
- `context: ToolContext` - 工具调用上下文

**返回**：`dict` - OpenAI tool 消息格式

---

## 二、记忆模块

### 2.1 MemoryRAG - RAG 记忆系统

**位置**：`modules/memory/rag.py`

**类**：`MemoryRAG`（单例）

**职责**：向量数据库管理、嵌入模型加载、日记存储与检索。

#### 公共方法

##### `save_diary(content, date_str=None) -> bool`

保存日记（含去重）。

**参数**：
- `content: str` - 日记内容
- `date_str: Optional[str]` - 日期字符串，默认当前日期

**返回**：`bool` - 是否成功保存

##### `search_diaries(query, top_k=20) -> list`

语义检索日记。

**参数**：
- `query: str` - 查询文本
- `top_k: int` - 返回结果数量，默认 20

**返回**：`list[dict]` - 检索结果列表

##### `extract_keywords(text, top_k=5) -> list`

关键词提取。

**参数**：
- `text: str` - 输入文本
- `top_k: int` - 返回关键词数量，默认 5

**返回**：`list[str]` - 关键词列表

---

## 三、消息模块

### 3.1 CQParser - CQ 码解析器

**位置**：`modules/message/CQParser.py`

**类**：`CQParser`

**职责**：解析 CQ 码，提取文本、图片、@、回复等信息。

#### 公共方法

##### `parse(message) -> dict`

解析消息。

**参数**：
- `message: str` - 原始消息

**返回**：`dict` - 解析结果，包含 `text`、`images`、`at_list`、`reply_id` 等字段

##### `extract_text(message) -> str`

提取纯文本。

**参数**：
- `message: str` - 原始消息

**返回**：`str` - 纯文本内容

---

### 3.2 GetMeta - 元数据提取

**位置**：`modules/message/GetMeta.py`

**类**：`GetMeta`

**职责**：提取消息元数据。

#### 公共方法

##### `get_sender_info(event) -> dict`

提取发送者信息。

**参数**：
- `event: dict` - 事件数据

**返回**：`dict` - 发送者信息，包含 `user_id`、`nickname`、`card` 等字段

---

## 四、视觉模块

### 4.1 VisionProcessor - 视觉处理

**位置**：`modules/vision/processor.py`

**类**：`VisionProcessor`

**职责**：图像理解（VLM）、表情包识别。

#### 公共方法

##### `async process_image(image_path, prompt=None) -> str`

处理图像。

**参数**：
- `image_path: str` - 图像路径
- `prompt: Optional[str]` - 提示词

**返回**：`str` - 图像描述

---

## 五、表情包模块

### 5.1 StickerManager - 表情包管理

**位置**：`modules/stickers/manager.py`

**类**：`StickerManager`

**职责**：表情包学习与 RLHF、正反馈捕捉。

#### 公共方法

##### `async search_sticker(query, top_k=5) -> list`

搜索表情包。

**参数**：
- `query: str` - 查询文本
- `top_k: int` - 返回结果数量，默认 5

**返回**：`list[dict]` - 表情包列表

##### `async add_sticker(image_path, description) -> bool`

添加表情包。

**参数**：
- `image_path: str` - 图像路径
- `description: str` - 描述

**返回**：`bool` - 是否成功添加

---

## 六、网络模块

### 6.1 BotConnector - WebSocket 连接

**位置**：`network/ws_connection.py`

**类**：`BotConnector`

**职责**：WebSocket 连接管理、自动重连机制。

#### 构造函数

```python
def __init__(self, ws_url, token=None)
```

**参数**：
- `ws_url: str` - WebSocket 地址
- `token: Optional[str]` - 认证 Token

#### 公共方法

##### `async connect() -> None`

连接 WebSocket。

**返回**：无

##### `async disconnect() -> None`

断开 WebSocket。

**返回**：无

##### `async send_request(action, params) -> dict`

发送请求。

**参数**：
- `action: str` - 操作类型
- `params: dict` - 参数

**返回**：`dict` - 响应数据

---

### 6.2 MessageSender - 消息发送器

**位置**：`network/ws_sender.py`

**类**：`MessageSender`

**职责**：消息发送（文本、图片、语音）。

#### 公共方法

##### `async send(target, message, mode="group") -> bool`

发送文本消息。

**参数**：
- `target: str` - 目标 ID
- `message: str` - 消息内容
- `mode: str` - 发送模式（"group" 或 "private"）

**返回**：`bool` - 是否成功发送

##### `async send_local_image(target, image_path, mode="group") -> bool`

发送本地图片。

**参数**：
- `target: str` - 目标 ID
- `image_path: str` - 图片路径
- `mode: str` - 发送模式

**返回**：`bool` - 是否成功发送

##### `async send_local_voice(target, voice_path, mode="group") -> bool`

发送本地语音。

**参数**：
- `target: str` - 目标 ID
- `voice_path: str` - 语音路径
- `mode: str` - 发送模式

**返回**：`bool` - 是否成功发送

---

## 七、配置模块

### 7.1 Config - 配置管理

**位置**：`config.py`

**类**：`Config`

**职责**：YAML 配置文件读写、配置属性映射、配置热重载。

#### 公共方法

##### `reload() -> None`

重新加载配置文件。

**返回**：无

##### `get(section, key, default=None) -> Any`

获取配置项。

**参数**：
- `section: str` - 配置节
- `key: str` - 配置键
- `default: Any` - 默认值

**返回**：配置值

##### `save() -> None`

保存配置到文件。

**返回**：无

---

## 八、使用示例

### 8.1 发送消息

```python
from network.ws_sender import MessageSender

sender = MessageSender(connector)
await sender.send("123456789", "Hello!", mode="group")
```

### 8.2 调用 LLM

```python
from utils.llm_client import llm_chat

messages = [
    {"role": "system", "content": "你是 Yuki"},
    {"role": "user", "content": "你好"}
]
response = await llm_chat(messages)
reply = response["choices"][0]["message"]["content"]
```

### 8.3 搜索记忆

```python
from modules.memory.rag import MemoryRAG

rag = MemoryRAG()
results = rag.search_diaries("今天天气", top_k=10)
for result in results:
    print(result["content"])
```

### 8.4 注册工具

```python
from core.toolchain import FunctionRegistry, ToolResult, ToolContext

registry = FunctionRegistry()

async def my_tool(context: ToolContext, param1: str) -> ToolResult:
    # 工具逻辑
    return ToolResult(name="my_tool", success=True, content="执行成功")

registry.register({
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "我的工具",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string"}
            },
            "required": ["param1"]
        }
    }
}, my_tool)
```

---

**文档版本**：v1.0  
**最后更新**：2026-06-04  
**维护人员**：项目开发团队
