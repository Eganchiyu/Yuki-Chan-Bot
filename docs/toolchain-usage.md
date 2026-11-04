# Function Call 工具链指南

本文档基于 `core/toolchain.py`、`core/tool_markup.py`、`core/tools/` 与 `core/engine/engine_reply.py` 的最新实现整理。

---

## 一、核心组件

| 文件 / 类 | 职责 |
|---|---|
| `core/toolchain.py::ToolSpec` | 工具唯一声明源：`name`、`description`、`parameters`、`handler`、`persist_result`（默认 `True`） |
| `core/toolchain.py::FunctionRegistry` | 注册与导出 OpenAI 兼容 tools schema（`get_tools()` / `get_handler()` / `get_spec()`） |
| `core/toolchain.py::ToolCallManager` | 顺序执行 `tool_calls`、调用前拟人化延迟（`cfg.TOOL_CALL_DELAY_SECONDS`，默认 1.2s）、JSON 截断自纠反馈 |
| `core/toolchain.py::ToolContext` | 携带 `chat_id`、`mode`、`session`、`combined_text`、`runtime`（`sender`、`yuki_state`、`image_store`）与 `metadata` |
| `core/toolchain.py::ToolResult` | 统一返回结构（`success`、`content`、`data`、`error`），序列化为 `role=tool` 消息 |
| `core/tool_markup.py` | 将模型误写进正文的 `<｜DSML｜invoke>`、`<tool_call>`、`<function=名>` 还原为标准 `tool_calls` 执行，并在发送前兜底剥离 |
| `core/tools/tools.py` | 汇总 `TOOL_SPECS`（主模型当前挂载的 12 个工具） |

---

## 二、多轮调用与特殊控制流

主流程位于 `core/engine/engine_reply.py::EngineReplyService.chat_with_tools()`（最多 `max_rounds=4` 轮）：

1. **阶段性文本实时发送**：工具轮次中模型附带的可见文本（若同批不含 `skip`）会经 `clean_visible_reply()` 清洗后立即发出，并以 `is_tool_thought=True`、`sent_realtime=True` 记入上下文。
2. **工具期间新消息合并**：每轮工具执行后，调用 `_merge_pending_messages()` 把同一 `chat_id` 新入队的消息合并进当前上下文（同样经过图片预取与归一化）。
3. **非持久化工具结果 (`persist_result=False`)**：
   - 如 `update_notebook`、`skip`，其 `role=tool` 结果仅在本轮 `messages` 内可见，**不会**写回 `chat_history.json`，避免污染长期对话历史。
4. **主动跳过回复 (`skip` 工具与 `SKIP_REPLY_MARKER`)**：
   - 群聊中模型调用 `skip` 时，`skip_reply_tool` 返回 `data={"skip_reply": True}`；
   - `ToolCallManager` 置 `context.metadata["skip_reply"] = True` 并中断同批后续工具，且不发送同轮伴随的阶段文本；
   - `EngineReplyService` 直接返回 `(SKIP_REPLY_MARKER, SKIP_REPLY_MARKER)`；
   - `SessionPipeline.generate_reply()` 收到标记后调用 `_prune_skipped_round()`，恢复到本轮进入前的历史快照（仅保留工具期间新到的用户消息），本轮不发送任何消息、不留任何 skip 痕迹。
5. **清洗致空兜底**：若本轮执行过工具，但最终回复被 `<layout>` 等标记清洗为空，发送 `工作中......`（`WORKING_NOTICE`），不触发空回复重试。
6. **参数截断自纠**：若模型因 `finish_reason=length` 导致 `arguments` JSON 截断，`ToolCallManager` 返回明确提示「参数被输出长度限制截断，请压缩到 500 字以内重新调用」并附上 `arguments_tail`。`MAID_GOAL_BREVITY_HINT` 仅拼接在 `delegate_to_maid` 描述末尾。

---

## 三、现役标准工具清单（12 个）

| 工具名 | 所在文件 | `persist_result` | 功能说明 |
|---|---|---|---|
| `delegate_to_maid` | `tools_maid.py` | `True` | 经 `MaidCapabilityBoundary.judge()` 校验后将任务放入 `maid_task_queue`，交由宿主 DSH 后台执行 |
| `search_diary` | `tools_diary.py` | `True` | 按 `date_str` / `keyword` 检索日记（随机抽最多 8 条）；均不填时随机翻看 8 条日记 |
| `update_notebook` | `tools_notebook.py` | `False` | 覆盖更新全局小本本 `data/notebook.json`（上限 512 字），内容在 `build_chat_context` 中作为潜意识注入 |
| `skip` | `tools_skip.py` | `False` | 群聊中主动保持安静、跳过本轮回复且不留历史痕迹（私聊调用会直接报错拒绝） |
| `send_master_private` | `tools_message.py` | `True` | 向主人主号（`cfg.TARGET_QQ`）发送私聊通知并同步写入主人私聊历史 |
| `poke` | `tools_message.py` | `True` | 群聊戳一戳指定用户（支持传 `target` 昵称自动解析或直接传 `user_id`） |
| `send_qq_file` | `tools_message.py` | `True` | 发送本地图片/语音/文件，支持 `[img:XXX]` 与 `[shot:X]` 索引，严禁模型手写 CQ 码 |
| `capture_group_snapshot` | `tools_snapshot.py` | `True` | 将当前群最近聊天渲染成带头像气泡的 PNG 截图，永久存入 `data/shot_memory/` |
| `search_group_snapshots` | `tools_snapshot.py` | `True` | 按关键词或随机翻看本群历史截屏（最多 5 条），预热为 `[shot:1]`~`[shot:5]` 供 `send_qq_file` 发送 |
| `parse_rich_message` | `tools_rich.py` | `True` | 解析合并转发（支持 `start`/`count` 分页与 `max_depth` 嵌套展开）、小程序、JSON/XML 卡片 |
| `download_file` | `tools_media.py` | `True` | 按消息中的 `[文件:file_id=xxx]` 下载群/私聊文件到 `workspace/` |
| `generate_image` | `tools_media.py` | `True` | 文生图 / 参考图编辑（最多 4 张参考图，内置 Yuki 与主人固定人设图路径说明），落盘到 `output/` |

---

## 四、已归档工具（不在主模型挂载）

以下工具已从 `core/tools/tools.py` 卸载并归档至 `_archive/`（每个目录均含 `README.md` 说明复原方法）：

- `_archive/ncm_tools/`：`ncm_search`、`ncm_download` 与 `ncm_login.py`（网易云搜歌/下载）
- `_archive/qzone_tool/`：`publish_qzone_mood`（发说说；底层 `modules/qzone/publisher.py` 仍在）
- `_archive/search_tools/`：`amap_search`（高德地图）、`browser_search`（Tavily 搜索）
- `_archive/master_status/`：`get_master_status`（主人桌面空闲与前台窗口检测）
- `_archive/timer_tool/`：`manage_timer_task`（会话级定时提醒）
- `_archive/user_resolve_tool/`：`resolve_user`（昵称查 QQ 号）

---

## 五、如何新增或修改工具

1. **实现 Handler**：在 `core/tools/tools_*.py` 中编写 `async def my_tool(context: ToolContext, ...) -> ToolResult`。阻塞 I/O 用 `asyncio.to_thread()` 包装，业务错误返回 `ToolResult.failure(content, error_code)` 而非抛异常。
2. **注册 Spec**：在 `core/tools/tools.py` 的 `TOOL_SPECS` 中追加 `ToolSpec(...)`（并同步在 `core/tools/__init__.py` 导出 handler）。若工具输出无需留存在持久化历史中，设 `persist_result=False`。
3. **验证测试**：运行 `~/miniconda3/envs/yuki/bin/python -m pytest tests/test_toolchain.py -q`。
