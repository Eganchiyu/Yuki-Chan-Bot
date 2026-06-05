# YukiV6 API 接口文档

本文档描述 YukiV6 项目核心模块的公共 API 接口，包括参数、返回值和异常说明。

---

## 一、核心模块 API

### 1.1 FunctionRegistry - Function Call 注册中心

**位置**：`core/toolchain.py`

**类**：`FunctionRegistry`

**职责**：管理 Function Call 工具的注册、注销和查询。

#### 方法

##### `register(schema: dict, handler: Callable[..., Awaitable[ToolResult]])`
注册一个 function tool。

**参数**：
- `schema`: 工具 schema 定义，必须包含 `function.name` 字段
- `handler`: 异步处理函数，签名为 `async def handler(context: ToolContext, **kwargs) -> ToolResult`

**返回**：无

**异常**：无

##### `unregister(name: str)`
注销一个 function tool。

**参数**：
- `name`: 工具名称

**返回**：无

**异常**：无

##### `get_tools() -> list`
获取所有已注册的 tools 列表。

**参数**：无

**返回**：`list[dict]` - 工具 schema 列表

**异常**：无

##### `get_handler(name: str)`
获取指定 function 的执行函数。

**参数**：
- `name`: 工具名称

**返回**：`Callable[..., Awaitable[ToolResult]]` 或 `None`

**异常**：无

##### `list_functions() -> list`
列出所有已注册的 function 名称。

**参数**：无

**返回**：`list[str]` - 工具名称列表

**异常**：无

##### `scan_and_register(tools_list: list, handlers_dict: dict)`
批量扫描并注册 tools（先清空再扫描）。

**参数**：
- `tools_list`: 工具 schema 列表
- `handlers_dict`: 工具名称到处理函数的映射

**返回**：无

**异常**：无

---

### 1.2 ToolCallManager - 工具调用执行器

**位置**：`core/toolchain.py`

**类**：`ToolCallManager`

**职责**：负责工具调用的参数解析、执行状态管理和结果标准化。

#### 方法

##### `__init__(registry: FunctionRegistry, max_rounds: int = 4)`
初始化工具调用管理器。

**参数**：
- `registry`: FunctionRegistry 实例
- `max_rounds`: 最大工具调用轮数，默认 4

**返回**：无

**异常**：无

##### `start_session(chat_id: str, user_text: str)`
记录一次工具调用会话。

**参数**：
- `chat_id`: 会话 ID
- `user_text`: 用户输入文本

**返回**：无

**异常**：无

##### `finish_session(chat_id: str)`
结束一次工具调用会话。

**参数**：
- `chat_id`: 会话 ID

**返回**：无

**异常**：无

##### `async execute_tool_call(tool_call: dict, context: ToolContext) -> dict`
执行单个 tool call，并返回 OpenAI tool 消息。

**参数**：
- `tool_call`: 工具调用信息，包含 `function.name`、`function.arguments`、`id` 等字段
- `context`: 工具调用上下文

**返回**：`dict` - OpenAI tool 消息格式，包含 `role=tool`、`tool_call_id`、`name`、`content`

**异常**：
- `json.JSONDecodeError`: 工具参数不是合法 JSON
- `TypeError`: 工具参数不符合接口要求
- `Exception`: 工具执行异常

##### `async execute_tool_calls(tool_calls: list, context: ToolContext) -> list`
按顺序执行一轮工具调用，避免共享状态并发写入。

**参数**：
- `tool_calls`: 工具调用列表
- `context`: 工具调用上下文

**返回**：`list[dict]` - OpenAI tool 消息列表

**异常**：同 `execute_tool_call`

---

### 1.3 ToolContext - 工具调用上下文

**位置**：`core/toolchain.py`

**类**：`ToolContext`

**职责**：在多轮工具调用期间携带会话状态。

#### 属性

- `chat_id: str` - 会话 ID
- `mode: str` - 运行模式（"group" 或 "private"）
- `history_dict: dict` - 对话历史字典
- `combined_text: str` - 合并后的用户输入文本
- `engine: Any` - YukiEngine 实例引用
- `metadata: dict` - 附加元数据

---

### 1.4 ToolResult - 工具调用结果

**位置**：`core/toolchain.py`

**类**：`ToolResult`

**职责**：工具调用的标准结果封装。

#### 属性

- `name: str` - 工具名称
- `success: bool` - 是否成功
- `content: str` - 结果内容
- `data: Any` - 附加数据
- `error: str` - 错误信息

#### 方法

##### `to_message_content() -> str`
将结果转换为 JSON 字符串，用于 OpenAI tool 消息。

**参数**：无

**返回**：`str` - JSON 字符串

**异常**：无

---

## 二、标准工具 API

**位置**：`core/tools.py`

### 2.1 search_diary_tool

查询 Yuki 的日记/记忆，支持按日期和关键词检索。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `date_str: Optional[str]` - 日期，如 "2026-05-20" 或 "2026-05"
- `keyword: Optional[str]` - 需要匹配的关键词

**返回**：`ToolResult` - 查询结果

**异常**：无

### 2.2 manage_timer_task_tool

创建、取消或列出定时任务。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `title: str` - 任务标题
- `due_time: Optional[str]` - 到期时间
- `action: str` - 操作类型，可选 "create"、"cancel"、"list"，默认 "create"

**返回**：`ToolResult` - 操作结果

**异常**：无

### 2.3 delegate_to_maid_tool

调用小女仆处理重型任务。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `goal: str` - 任务目标
- `run_inline: bool` - 是否内联执行，默认 False

**返回**：`ToolResult` - 任务提交结果

**异常**：无

### 2.4 send_master_private_tool

向主人私聊发送私密信息。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `message: str` - 消息内容

**返回**：`ToolResult` - 发送结果

**异常**：无

### 2.5 browser_search_tool

提供网络搜索入口，当前返回可打开的搜索地址。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `query: str` - 搜索关键词

**返回**：`ToolResult` - 搜索 URL

**异常**：无

### 2.6 send_qq_file_tool

发送图片或语音文件。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `file_path: str` - 文件路径
- `file_type: str` - 文件类型，可选 "image" 或 "voice"，默认 "image"

**返回**：`ToolResult` - 发送结果

**异常**：无

### 2.7 inject_external_content_tool

外部内容注入入口，用于 WebUI 或多渠道输入适配。

**参数**：
- `context: ToolContext` - 工具调用上下文
- `content: str` - 注入内容
- `source: str` - 内容来源，默认 "external"

**返回**：`ToolResult` - 注入结果

**异常**：无

---

## 三、LLM 客户端 API

**位置**：`utils/llm_client.py`

### 3.1 chat_completion_raw

发送 OpenAI 兼容格式的对话补全请求。

**参数**：
- `base_url: str` - API 基础 URL
- `api_key: str` - API 密钥
- `messages: list` - 消息列表
- `model: str` - 模型名称
- `timeout: Optional[aiohttp.ClientTimeout]` - 超时配置
- `**kwargs` - 额外参数（temperature, max_tokens, response_format 等）

**返回**：`dict` - API 响应

**异常**：
- `aiohttp.ClientError`: 网络请求错误
- `asyncio.TimeoutError`: 请求超时
- `Exception`: 其他异常

### 3.2 llm_chat

默认对话接口（含主备故障转移）。

**参数**：
- `messages: list` - 消息列表
- `model: Optional[str]` - 模型名称，默认使用配置
- `**kwargs` - 额外参数

**返回**：`dict` - API 响应

**异常**：同 `chat_completion_raw`

### 3.3 vision_chat

视觉模型对话接口。

**参数**：
- `messages: list` - 消息列表
- `model: Optional[str]` - 模型名称，默认使用配置
- `**kwargs` - 额外参数

**返回**：`dict` - API 响应

**异常**：同 `chat_completion_raw`

### 3.4 close_global_session

关闭全局 aiohttp Session。

**参数**：无

**返回**：无

**异常**：无

---

## 四、配置管理 API

**位置**：`config.py`

### 4.1 cfg - 全局配置单例

**类型**：`Config`

**访问方式**：`from config import cfg`

**主要属性**：
- `robot_name: str` - 机器人名称
- `master_name: str` - 主人称呼
- `debug: bool` - 调试模式开关
- `api: APIConfig` - API 配置
- `model: ModelConfig` - 模型配置
- `connection: ConnectionConfig` - 连接配置
- `target: TargetConfig` - 目标配置
- `diary: DiaryConfig` - 日记配置
- `rag: RAGConfig` - RAG 配置
- `energy: EnergyConfig` - 精力值配置
- `attention: AttentionConfig` - 注意力配置
- `paths: PathsConfig` - 路径配置
- `timing: TimingConfig` - 时间配置

**主要方法**：

##### `reload()`
重新加载配置文件。

**参数**：无

**返回**：无

**异常**：无

##### `get(section: str, key: str, default: Any = None) -> Any`
获取配置项。

**参数**：
- `section`: 配置节
- `key`: 配置键
- `default`: 默认值

**返回**：配置值

**异常**：无

##### `save()`
保存配置到文件。

**参数**：无

**返回**：无

**异常**：无

---

**文档版本**：v1.0  
**最后更新**：2026-06-04  
**维护人员**：项目开发团队
