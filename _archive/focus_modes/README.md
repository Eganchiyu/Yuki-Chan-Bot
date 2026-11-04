# 全局聚焦模式管理框架（Focus Modes）归档

## 1. 这段代码是干什么的
本目录归档了最初为「浏览器交互聚焦模式（`BrowserInteractionMode`）」等独占式交互模式设计的多模式管理框架与按模式切换工具集的提供器：
- `modes.py`（原 `core/modes.py`）：
  - `ModeSpec`：声明模式的 `mode_id`、`display_name`、`session_id`、`tool_group` 及是否为聚焦模式（`is_focus_mode`）。
  - `QQChatMode`：默认 QQ 群聊模式声明（`is_focus_mode=False`）。
  - `FocusModeState`：维护全局唯一聚焦模式的运行状态、来源会话（`origin_chat_id` / `origin_mode`）、目标 `goal` 与步骤列表 `steps`。
  - `ModeManager`：提供 `enter_mode`、`record_step`、`complete_mode` / `exit_mode` 及 `render_prompt_status`（生成注入 System Prompt 的【全局模式状态】说明）。
- `tool_registry_provider.py`（原位于 `core/toolchain.py` 的 `ToolRegistryProvider` 类）：
  - 按 `mode` 维护多套独立的 `FunctionRegistry`（例如在 `browser_interaction` 模式下切换为专属浏览器工具集，在普通模式下回退 `default_registry`）。

自 2026-11-01 `LiveYukiL2D` 与 `browser_interaction` 下线归档后，系统中不再有任何 `is_focus_mode=True` 的模式注册，`ModeManager` 始终处于空闲态，`ToolRegistryProvider` 也仅持有单一默认注册表，因此将其一并归档以精简核心链路。

## 2. 原来的埋点在哪里
- **`core/modes.py`** -> 被 `core/brain.py` 导入并在 `YukiState.__init__` 中挂载为 `self.mode_manager = ModeManager()`。
- **`core/prompts.py`** -> `build_chat_context()` 中通过 `mode_manager = getattr(yuki, "mode_manager", None)` 检查，若存在则调用 `mode_manager.render_prompt_status(...)` 注入【全局模式状态】システム消息。
- **`core/toolchain.py`** -> 定义 `ToolRegistryProvider`。
- **`core/engine/engine.py` & `core/engine/engine_reply.py`** -> `YukiEngine` 构造 `self.tool_registry_provider = ToolRegistryProvider(TOOL_SPECS)` 并传给 `EngineReplyService`，在 `chat_with_tools` 中按 `mode` 获取 `FunctionRegistry`。

## 3. 怎样接入
1. 将 `modes.py` 放回 `core/modes.py`：
   ```bash
   cp _archive/focus_modes/modes.py core/modes.py
   ```
2. 在 `core/brain.py` 中恢复挂载：
   ```python
   from core.modes import ModeManager
   # 在 YukiState.__init__ 中添加：
   self.mode_manager = ModeManager()
   ```
   （`core/prompts.py` 中的 `getattr(yuki, "mode_manager", None)` 会自动生效并注入模式状态。）
3. 若需要按模式隔离工具集，将 `tool_registry_provider.py` 中的 `ToolRegistryProvider` 合并回 `core/toolchain.py`，并在 `core/engine/engine.py` 中传入 `mode_specs={"<mode_id>": [...]}`。
