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
- `sender: NapCatGateway` - NapCat 接入层实例（`network/napcat.py`，收发同一对象）
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

CQ 码解析与消息元数据查询已并入 NapCat 接入层（见 6.1 `NapCatGateway`）：
`parse_cq_codes()` 负责 @ 与回复替换，`get_member_info()` / `get_msg()` 负责
群成员与消息元数据，`smart_truncate()` 等纯函数负责文本归一化。

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

### 6.1 NapCatGateway - NapCat 接入层

**位置**：`network/napcat.py`（原 `ws_connection.py` + `ws_sender.py` 已合并至此）

**类**：`NapCatGateway`

**职责**：连接管理、帧路由、出站动作、CQ 协议与群/成员/消息查询。
边界只到传输 + 协议，不 import `core/` / `modules/`。

#### 构造函数

```python
def __init__(self, ws_url=None, ws_token=None)
```

**参数**：
- `ws_url: str` - WebSocket 地址，缺省取 `cfg.NAPCAT_WS_URL`
- `ws_token: Optional[str]` - 认证 Token，缺省取 `cfg.NAPCAT_WS_TOKEN`

#### 并发模型

一个常驻 `_reader()` 协程独占读端：`echo` 命中挂起请求则唤醒对应 `call()`；
带 `post_type` 的帧投进事件队列供 `listen()` 消费；其它帧丢弃。
因此出站不依赖有人消费事件流，API 响应也不会混进事件流。

#### 公共方法

##### `async call(action, params, timeout=5.0) -> dict | None`

通用动作原语：发送 OneBot 动作并等待其响应，超时/异常返回 `None`。

##### `async listen() -> AsyncIterator[dict]`

入站事件流（响应帧不会出现在这里）。只应由一个消费者迭代。

##### `async send(chat_id, message, mode="private") -> None`

发送文本或 CQ 码；发完即返回，不等响应（流式回复走这里）。

##### `async send_local_image(chat_id, local_path, mode="private") -> None`

##### `async send_local_file(chat_id, local_path, mode="private") -> None`

##### `async send_local_voice(chat_id, local_path, mode="group") -> None`

##### `async send_poke(user_id, group_id) -> dict`

戳一戳（仅群聊），返回 NapCat 响应字典。

##### `async download_file(file_id, filename=None) -> dict`

按 `file_id` 取回文件并落到 `workspace/`，返回
`{"success", "file_path", "filename", "error"}`。

##### `async get_member_info(group_id, user_id) -> dict | None`

群成员信息（含群名片），带进程内缓存。

##### `async get_member_name(group_id, user_id) -> str`

群名片优先，其次昵称；`all` 返回「全体成员」。

##### `async get_msg(message_id) -> dict | None`

##### `async get_forward_messages(forward_id) -> tuple[list, dict | None]`

合并转发内容，兼容三套参数名并做了响应归一化。

##### `async get_group_meta(group_id) -> dict`

群名与群备注。

##### `async get_cookies(domain="user.qzone.qq.com") -> dict | None`

##### `async get_login_info() -> dict | None`

##### `async parse_cq_codes(text, group_id) -> str`

把 @ 与回复 CQ 码替换成可读文本。

##### `async close() -> None`

**模块级纯函数**：`smart_truncate()`、`replace_other_cq_codes()`、
`extract_at_uids()`、`replace_at_placeholder()`、`extract_reply_ids()`、
`replace_reply_placeholder()`、`mentions_self()`。

**运行计数**：`gateway.stats`（frames / events / dropped / reconnects /
calls / call_failures）。

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

### 8.1 发送消息与调用动作

```python
from network.napcat import NapCatGateway

gateway = NapCatGateway()                     # 缺省读 cfg.NAPCAT_WS_URL / TOKEN
await gateway.send("123456789", "Hello!", mode="group")
await gateway.send_local_image("123456789", "/path/pic.png", mode="group")

resp = await gateway.call("get_msg", {"message_id": 12345})   # 通用动作原语

# 入站：常驻 reader 已在网关内部运行，这里只消费事件
async for event in gateway.listen():
    ...
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
