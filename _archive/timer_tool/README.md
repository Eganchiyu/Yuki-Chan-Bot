# 精确定时任务工具归档

## 1. 这段代码是干什么的
`tools_timer.py`（原 `core/tools/tools_timer.py` / `core/tools/_archived/tools_timer.py`）为 Yuki 提供会话级的精确定时提醒能力：
- `manage_timer_task_tool(context, title=None, due_time=None, delay_seconds=None, action="create", task_id=None, message=None)`：
  - 支持绝对时间（`due_time`，如 `YYYY-MM-DD HH:MM:SS`）或相对秒数（`delay_seconds`）创建定时任务（`action="create"`）。
  - 支持列出当前会话定时任务（`action="list"`）和按 `task_id` 或 `title` 取消任务（`action="cancel"`）。
- `_timer_wake_worker(context, task_id, delay_seconds)`：后台异步 `asyncio.sleep(delay_seconds)`，到点后向原会话注入一条 `{"content": "【定时任务到点】...", "is_timer_event": True}` 消息，并调用 `process_callback(chat_id, mode, message_obj=..., debounce_flag=False, force_reply=True)` 唤醒 Yuki 主动发言。

## 2. 原来的埋点在哪里
- **工具实现路径**：`core/tools/tools_timer.py`（后移入 `core/tools/_archived/tools_timer.py`）
- **工具注册埋点**：`core/tools/tools.py` 的 `TOOL_SPECS` 列表。
- **运行时状态挂载点**：
  - 任务字典与协程句柄存储在 `context.yuki.maid_current_tasks["__timer_tasks__"]` 和 `context.yuki.maid_current_tasks["__timer_handles__"]`。
  - 唤醒回调通过 `context.metadata.get("process_callback")`（由 `EngineReplyService.chat_with_tools` 注入 `main.main_process`）触发主会话管线。
  - `core/reply_watch.py` 与 `core/session_pipeline.py` 中对 `is_timer_event` 做了识别（定时事件不视为真人消息、不触发自动回复订阅）。

## 3. 怎样接入
1. 将文件复制回 `core/tools/tools_timer.py`：
   ```bash
   cp _archive/timer_tool/tools_timer.py core/tools/tools_timer.py
   ```
2. 将文件内的 `from ..tools_common import logger` 改为 `from .tools_common import logger`。
3. 在 `core/tools/tools.py` 中导入并注册到 `TOOL_SPECS`：
   ```python
   from .tools_timer import manage_timer_task_tool

   # 在 TOOL_SPECS 中追加：
   ToolSpec(
       name="manage_timer_task",
       description="创建、查询或取消当前会话的定时提醒任务，到点后会自动唤醒你发言。",
       parameters={
           "type": "object",
           "properties": {
               "action": {"type": "string", "enum": ["create", "list", "cancel"], "default": "create"},
               "title": {"type": "string", "description": "定时任务标题"},
               "due_time": {"type": "string", "description": "触发时间，格式 YYYY-MM-DD HH:MM:SS"},
               "delay_seconds": {"type": "number", "description": "相对延迟秒数（与 due_time 二选一）"},
               "task_id": {"type": "string", "description": "取消任务时的任务 ID"},
               "message": {"type": "string", "description": "到点时的提醒内容"},
           },
       },
       handler=manage_timer_task_tool,
   ),
   ```
