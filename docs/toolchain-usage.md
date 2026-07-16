# Toolchain 用法与调用流程说明

本文档基于 `core/toolchain.py`、`core/tools.py` 和当前项目调用点整理，说明 YukiV6 Function Call 工具链的职责、使用方式和扩展规范。

---

## 一、模块定位

工具链由两个核心文件组成：

| 文件 | 职责 |
|------|------|
| `core/toolchain.py` | 提供 `ToolSpec`、工具注册中心、工具调用上下文、运行时依赖、工具执行器和标准结果封装 |
| `core/tools.py` | 定义标准工具 handler，并通过 `TOOL_SPECS` 统一声明 schema 与 handler |

当前工具链由 `core/engine.py` 接入：

1. `YukiEngine.__init__()` 初始化 `FunctionRegistry`。
2. 使用 `TOOL_SPECS` 批量注册工具。
3. 初始化 `ToolCallManager`。
4. `_chat_with_tools()` 在 LLM 请求中传入 tools。
5. 模型返回 `tool_calls` 后，由 `ToolCallManager` 顺序执行工具。
6. 工具结果以 OpenAI tool message 格式写回上下文，继续下一轮 LLM 对话。

---

## 二、核心对象

### 2.1 ToolResult

`ToolResult` 是所有工具 handler 的标准返回结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | `bool` | 是否执行成功 |
| `content` | `str` | 面向模型或用户的主要结果描述 |
| `data` | `Any` | 可选结构化数据 |
| `error` | `str` | 可选错误码或错误详情 |
| `name` | `str` | 工具名称，可省略，由执行器自动补齐 |

`to_message_content()` 会将结果序列化为 JSON 字符串，作为 OpenAI tool message 的 `content` 返回给模型。

---

### 2.2 ToolRuntime 与 ToolContext

`ToolContext` 保存一次工具调用期间所需的上下文信息。工具不再直接访问完整 `YukiEngine`，而是通过 `ToolRuntime` 获取最小运行时依赖。

| 字段 | 类型 | 说明 |
|------|------|------|
| `chat_id` | `str` | 当前会话 ID |
| `mode` | `str` | 当前消息模式，例如 group/private |
| `history_dict` | `dict` | 当前会话历史字典 |
| `combined_text` | `str` | 当前合并后的用户输入 |
| `runtime` | `ToolRuntime` | 工具运行时依赖 |
| `metadata` | `dict` | 可选扩展元数据 |

> `metadata` 中的 `history_manager` 键可用于工具跨会话写入历史记录。

`ToolRuntime` 当前包含：

| 字段 | 说明 |
|------|------|
| `sender` | 消息发送器 |
| `yuki_state` | Yuki 状态对象 |

handler 可通过 `context.sender` 和 `context.yuki` 访问对应依赖，避免耦合完整 Engine。

---

### 2.3 ToolSpec

`ToolSpec` 是单个工具的唯一声明源，统一维护工具名、描述、参数 schema 和 handler。

```python
ToolSpec(
    name="example",
    description="示例工具。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "需要处理的文本"},
        },
        "required": ["text"],
    },
    handler=example_tool,
)
```

`ToolSpec.to_schema()` 会自动生成 OpenAI 兼容 function schema。

---

### 2.4 FunctionRegistry

`FunctionRegistry` 负责维护 `ToolSpec` 注册关系。

| 方法 | 说明 |
|------|------|
| `register(spec)` | 注册单个工具 |
| `unregister(name)` | 注销单个工具 |
| `get_tools()` | 返回所有已注册 schema，供 LLM 请求使用 |
| `get_handler(name)` | 根据工具名获取 handler |
| `list_functions()` | 返回已注册工具名称列表 |
| `scan_and_register(tool_specs)` | 清空旧注册后批量注册 |

当前注册入口位于 `YukiEngine.__init__()`：

```python
self.tool_registry = FunctionRegistry()
self.tool_registry.scan_and_register(TOOL_SPECS)
self.tool_manager = ToolCallManager(self.tool_registry)
```

---

### 2.5 ToolCallManager

`ToolCallManager` 负责执行模型返回的 tool call。

关键职责：

- 解析模型返回的 `function.arguments` JSON。
- 根据工具名从 `FunctionRegistry` 获取 handler。
- 调用 handler 并捕获异常。
- 自动补齐 `ToolResult.name`。
- 将 `ToolResult` 转换为 OpenAI tool message。
- 记录工具调用参数、成功状态与耗时日志。
- 控制单轮工具调用按顺序执行，避免共享状态并发写入。

执行时会读取 `cfg.timing.tool_call_delay_seconds`，在真正调用 handler 前等待一小段时间，用于降低连续工具调用的机械感。默认值为 `1.2` 秒。

---

## 三、当前调用流程

工具链主流程集中在 `YukiEngine._chat_with_tools()`。

```text
用户消息进入 api_reply()
        ↓
build_chat_context() 构造 LLM messages
        ↓
_chat_with_tools() 创建 ToolContext
        ↓
llm_chat_raw(..., tools=registry.get_tools(), tool_choice="auto")
        ↓
模型决定是否返回 tool_calls
        ↓
无 tool_calls：直接返回可见回复
有 tool_calls：写入 assistant/tool 上下文
        ↓
ToolCallManager.execute_tool_calls()
        ↓
逐个解析参数、执行 handler、返回 tool message
        ↓
将 tool message 追加进 messages，继续下一轮 LLM 调用
        ↓
达到最终回复或 max_rounds 后 fallback 普通 LLM 回复
```

补充行为：

- 工具调用轮次中模型返回的可见文本会通过 `_clean_visible_reply()` 清理后立即调用 sender 发送，不再积累到最终回复中统一释放。
- 已实时发送的阶段性文本会以 `is_tool_thought=True`、`sent_realtime=True` 写入 session，便于后续上下文追踪。
- 最终没有 `tool_calls` 的模型回复仍作为正式回复返回，由 `SessionPipeline.send_reply()` 走原有文本、表情包或语音发送流程。
- 工具结果会以 `role=tool` 写入当前 session。
- 工具调用期间同一会话新增消息会通过 `_merge_pending_messages()` 合并进当前上下文，避免消息流分叉。
- `ToolCallManager.max_rounds` 默认是 `4`，超过轮数后会使用当前消息上下文再请求一次普通 LLM 回复。

---

## 四、标准工具清单

当前 `core/tools.py` 注册了以下工具：

| 工具名 | handler | 功能 |
|--------|---------|------|
| `search_diary` | `search_diary_tool` | 查询 Yuki 日记/记忆，支持日期与关键词 |
| `delegate_to_maid` | `delegate_to_maid_tool` | 将重型任务委托给小女仆，支持后台队列或 inline 执行 |
| `send_qq_file` | `send_qq_file_tool` | 发送本地图片、语音或普通文件，支持 [img:XXX] 索引 |
| `resolve_user` | `resolve_user_tool` | 根据用户昵称解析 QQ 号 |
| `poke` | `poke_tool` | 戳一戳指定用户 |
| `download_file` | `download_file_tool` | 下载群聊/私聊中的文件到本地 |
| `publish_qzone_mood` | `publish_qzone_mood_tool` | 发布 QQ 空间说说，支持纯文本和带图 |
| `generate_image` | `generate_image_tool` | 调用图像生成模型生成图片 |

---

## 五、标准工具行为说明

### 5.1 search_diary

- 参数：`date_str`、`keyword` 二选一或同时提供。
- 行为：使用 `asyncio.to_thread()` 调用 `search_diary_fast()`，避免阻塞事件循环。
- 失败条件：日期和关键词都为空时返回 `missing_date_or_keyword`。

### 5.2 delegate_to_maid

- 参数：`goal` 必填，`run_inline` 可选。
- 调用前先使用 `MaidCapabilityBoundary.judge()` 进行能力边界判定。
- `run_inline=True` 时直接等待 `maid_evolution_loop()` 结果。
- 默认后台模式会构造 maid task 并放入 `context.yuki.maid_task_queue`。

### 5.3 send_qq_file

- 参数：`file_path` 必填，`file_type` 支持 `image`、`voice` 或 `file`。
- 行为：根据类型调用 sender 的本地图片、语音或文件发送接口。支持 `[img:XXX]` 索引。

### 5.6 resolve_user

- 参数：`nickname` 必填。
- 行为：根据用户昵称在当前群聊中查找匹配的 QQ 号。

### 5.7 poke

- 参数：`target_qq` 必填。
- 行为：戳一戳指定用户。

### 5.8 download_file

- 参数：`file_url` 必填，`save_path` 可选。
- 行为：下载群聊/私聊中的文件到本地。

### 5.9 publish_qzone_mood

- 参数：`content` 必填，`images` 可选。
- 行为：发布 QQ 空间说说，支持纯文本和带图。

### 5.10 generate_image

- 参数：`prompt` 必填。
- 行为：调用图像生成模型生成图片。

---

## 六、新增工具的推荐步骤

新增工具时，只需要编写 handler，并在 `TOOL_SPECS` 中添加一条声明。

### 6.1 编写 handler

handler 必须是异步函数，首参为 `context`，返回 `ToolResult`。

```python
async def example_tool(context, text):
    if not text:
        return ToolResult(success=False, content="缺少文本内容", error="missing_text")
    return ToolResult(success=True, content=f"已处理：{text}")
```

### 6.2 添加 ToolSpec

在 `TOOL_SPECS` 中添加工具声明。

```python
ToolSpec(
    name="example",
    description="示例工具。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "需要处理的文本"},
        },
        "required": ["text"],
    },
    handler=example_tool,
)
```

启动时 `scan_and_register(TOOL_SPECS)` 会自动注册所有工具。

---

## 七、错误处理与返回规范

工具链内部已统一处理以下异常：

| 场景 | 返回内容 |
|------|----------|
| 工具未注册 | `success=False`，`error="handler_not_found"` |
| 参数不是合法 JSON | `success=False`，`content="工具参数不是合法 JSON"` |
| 参数不符合 handler 签名 | `success=False`，`content="工具参数不符合接口要求"` |
| handler 执行异常 | `success=False`，`content="工具执行异常"` |

handler 内部应优先返回结构化 `ToolResult`，不要直接抛出可预期的业务错误。例如缺少参数、能力边界拒绝、目标资源不存在等，应返回 `success=False` 和稳定的 `error` 错误码。

---

## 八、设计注意事项

1. **保持 handler 异步**：阻塞型函数使用 `asyncio.to_thread()` 包装。
2. **优先维护 `TOOL_SPECS`**：`TOOL_SCHEMAS` 和 `TOOL_HANDLERS` 仅保留兼容旧引用，不再作为主要维护入口。
3. **避免访问完整 Engine**：工具通过 `context.sender`、`context.yuki` 等最小依赖访问运行时。
4. **避免并发写共享状态**：当前 `execute_tool_calls()` 是顺序执行，不建议在 handler 内自行并发写 `history_dict`、`maid_current_tasks` 等共享结构。
5. **schema 与 handler 参数保持一致**：schema 的 `required` 和 handler 必填参数不一致会导致 `TypeError`。
6. **工具输出应简洁**：`content` 会回填给模型，避免输出过长或包含敏感信息。
7. **配置等待时间**：如需调整工具调用前等待，可修改 `timing.tool_call_delay_seconds` 对应配置。

---

## 九、与旧能力的关系

当前 `api_reply()` 仍保留两类标签式兼容逻辑：

- `[DELEGATE_TO_MAID:...]`：旧式小女仆委托标签。
- `[MEME:...]`：旧式表情包搜索标签。

Function Call 工具链是新的标准调用入口，但这些标签逻辑仍在最终回复阶段解析，用于兼容历史提示词或模型输出习惯。

---

## 十、排查建议

| 问题 | 排查方向 |
|------|----------|
| 模型没有调用工具 | 检查 `tools=self.tool_registry.get_tools()` 是否传入、schema 描述是否清晰、模型是否支持 tool_calls |
| 返回工具未注册 | 检查工具是否已加入 `TOOL_SPECS` |
| 参数错误 | 检查 schema `required` 与 handler 参数签名是否一致 |
| 工具调用后没有继续回复 | 检查 tool message 是否被追加到 `tool_messages`，以及 LLM API 是否支持 OpenAI tool message 格式 |
| 状态未写入 | 检查 handler 是否通过 `context.yuki` 或 `context.history_dict` 访问了正确对象 |
| 调用速度过慢 | 检查 `timing.tool_call_delay_seconds` 配置和 handler 内部是否存在阻塞操作 |

---

## 十一、关联文件

- `core/toolchain.py`：工具链基础设施。
- `core/tools.py`：标准工具集合。
- `core/engine.py`：工具链接入与多轮对话流程。
- `utils/llm_client.py`：LLM 原始 message 返回接口。
- `config.py`：工具调用等待时间配置。
- `tests/test_toolchain.py`：工具链最小 smoke test。
