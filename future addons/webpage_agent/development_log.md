# 浏览器交互与多模式开发记录

## 2026-07-27

- 新增 `core.modes` 多模式基础框架，包含 `QQChatMode`、`BrowserInteractionMode`、`FocusModeState` 与 `ModeManager`。
- 将 QQ 群聊包装为默认主模式 `QQChatMode`，保留原有群聊处理链路。
- 新增浏览器交互占位模块 `modules/browser_interaction/`，当前只提供模式链路验证工具，不接入真实浏览器驱动。
- 新增默认工具 `enter_browser_interaction`，支持从群聊/私聊进入全局唯一浏览器聚焦模式，并创建 `mode:browser` 独立会话。
- 新增浏览器模式工具组：`browser_scan_placeholder`、`browser_record_step`、`browser_complete`。
- 浏览器模式完成时会向来源会话发送 `【浏览器模式完成】...` 返回说明，并写入来源会话历史。
- 新增 `ToolRegistryProvider`，支持按 mode 选择工具组；普通 QQChatMode 不暴露浏览器操作工具，浏览器模式只暴露浏览器工具组。
- 全局模式状态会注入 prompt：普通群聊收到新消息时能知道当前是否已有浏览器等聚焦模式运行，以及该会话是否为来源会话。
- 调整旧 RAG 日记召回：取消 `chat_id` 硬过滤，改为全局召回；对当前群聊日记给予绝对领先加分，对当前发言者姓名给予小幅加分。
- 新增 `tests/test_modes.py`，覆盖模式唯一锁、进入浏览器模式、来源返回、模式级工具隔离和 RAG 加权。
- 验证命令：`conda run -n ai_env python -m pytest tests/test_modes.py tests/test_toolchain.py -q`，结果 `16 passed`。
