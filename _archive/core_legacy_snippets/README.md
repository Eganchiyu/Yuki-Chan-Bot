# 核心模块零散未挂载代码与旧兼容方法归档

## 1. 这段代码是干什么的
在 `core/` 演进与模块解耦过程中，部分早期实验实现、外部注入接口和拆分过渡期的私有兼容方法已不再被任何生产路径调用。本目录按所属模块分类保存这些代码片段：

| 归档文件 | 原所属文件 | 包含内容与用途说明 |
|---|---|---|
| `brain_snippets.py` | `core/brain.py` | ① `UserMapping.get_all`：返回群聊内全部昵称→QQ 映射（原仅供已下线的 `resolve_user_tool` 调试返回）<br>② `self.maid_executor = ThreadPoolExecutor(max_workers=2)`：早期同步小女仆线程池残留（现已改为异步队列 + 宿主 Harness）<br>③ `get_smooth_time_weight_cosine_v1`：初代双峰余弦生物钟算法注释块（已被分段基准+三峰高斯模型替代）<br>④ `YukiState.get_smooth_time_weight_test`：生物钟测试包装函数 |
| `history_manager_snippets.py` | `core/history_manager.py` | ① `HistoryManager.session_exists(chat_id)`：判断会话是否存在的未调用辅助方法<br>② `HistoryManager.inject_whisper(chat_id, message)`：向指定会话注入 `【主人对Yuki的悄悄话】` 系统提示的外部接口（早期工具/脚本入口，现无调用点） |
| `engine_compat_snippets.py` | `core/engine/engine.py` | `YukiEngine` 拆分为 `EngineReplyService` 与 `EngineDiaryService` 时留下的 5 个旧私有方法转发器（`_clean_visible_reply`、`_merge_pending_messages`、`_send_tool_thought`、`_chat_with_tools`、`_summarize_idle_session`）及未使用的 `self.maid = None` 属性 |
| `toolchain_snippets.py` | `core/toolchain.py` | `ToolCallManager.start_session` 与 `finish_session` 两个空实现（no-op）生命周期兼容钩子 |

## 2. 原来的埋点在哪里
- **`core/brain.py`**：`UserMapping` 类尾部、`YukiState.__init__` 第 101 行、`YukiState` 底部第 223–251 行与第 289–291 行。
- **`core/history_manager.py`**：`HistoryManager` 类第 110–113 行（`session_exists`）与第 199–216 行（`inject_whisper`）。
- **`core/engine/engine.py`**：`YukiEngine.__init__` 第 22 行（`self.maid = None`）与类底部第 77–99 行。
- **`core/toolchain.py` & `core/engine/engine_reply.py`**：`ToolCallManager` 第 186–190 行定义，并在 `EngineReplyService.chat_with_tools` 进入/退出 `try...finally` 时调用。

## 3. 怎样接入
- 若需恢复某项方法（如 `HistoryManager.inject_whisper` 或 `UserMapping.get_all`），直接将对应文件中的函数粘回原所属类定义内即可，无额外外部依赖。
- 若外部脚本或旧测试依赖 `YukiEngine._chat_with_tools` 等私有入口，可将 `engine_compat_snippets.py` 中的方法合入 `core/engine/engine.py` 的 `YukiEngine` 类（或直接改为调用 `engine.reply_service.<method>` / `engine.diary_service.<method>`）。
