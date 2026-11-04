# 用户昵称解析 QQ 号工具归档

## 1. 这段代码是干什么的
`tools_resolve_user.py`（原注释保存在 `core/tools/tools.py` 末尾第 222–252 行）提供 `resolve_user_tool(context, name)` 工具：
- 根据群友昵称或群名片，查询 `context.yuki.user_mapping.resolve(context.chat_id, name)` 解析对应的 QQ 号。
- 解析失败时通过 `context.yuki.user_mapping.get_all(context.chat_id)` 返回当前群聊已知的全部昵称映射，辅助模型修正目标名称。
- 后来因为 `poke_tool`（戳一戳）已内置自动调用 `user_mapping.resolve()` 解析昵称，不再需要模型先单独调用一次 `resolve_user`，因此从 `TOOL_SPECS` 中注释下线。

## 2. 原来的埋点在哪里
- **原始位置**：`core/tools/tools.py` 底部注释块。
- **依赖埋点**：`core/brain.py` 中的 `YukiState.user_mapping`（`UserMapping.resolve` 与 `UserMapping.get_all`；若 `UserMapping.get_all` 一并归档，恢复本工具时需同步恢复 `UserMapping.get_all`，见 `_archive/core_legacy_snippets/`）。

## 3. 怎样接入
1. 将 `_archive/user_resolve_tool/tools_resolve_user.py` 复制到 `core/tools/tools_resolve_user.py`。
2. 确保 `core/brain.py` 的 `UserMapping` 类包含 `get_all(self, chat_id: str) -> dict` 方法。
3. 在 `core/tools/tools.py` 中导入 `RESOLVE_USER_SPEC`（或 `resolve_user_tool`）并加入 `TOOL_SPECS` 列表：
   ```python
   from .tools_resolve_user import RESOLVE_USER_SPEC

   # 加入 TOOL_SPECS：
   TOOL_SPECS.append(RESOLVE_USER_SPEC)
   ```
