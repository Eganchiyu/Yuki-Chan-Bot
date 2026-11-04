# QQ 空间说说发布工具归档

## 1. 这段代码是干什么的
`tools_qzone.py`（原 `core/tools/tools_qzone.py` / `core/tools/_archived/tools_qzone.py`）封装了 Yuki 主动发布 QQ 空间说说（动态）的 Function Call 工具 `publish_qzone_mood_tool`：
- 支持纯文本说说或附带多张图片（自动通过 `_resolve_image_path` 解析 `[img:XXX]` / `[shot:N]` 索引为本地真实路径）。
- 底层调用 `modules.qzone.publish_mood(context.sender, content, visible, image_paths)` 发布动态。
- 发布成功后会自动通知 `modules.qzone.monitor.notify_new_post` 记录新说说及其触发时的最近 5 条群聊消息上下文，便于后续空间评论监控关联背景。

## 2. 原来的埋点在哪里
- **工具实现路径**：`core/tools/tools_qzone.py`（后移入 `core/tools/_archived/tools_qzone.py`）
- **工具注册埋点**：`core/tools/tools.py` 的 `TOOL_SPECS` 列表及 `core/tools/__init__.py`。
- **下游依赖模块**：
  - `core/tools/tools_common.py` 中的 `_resolve_image_path`、`logger`
  - `modules/qzone/__init__.py`（`publish_mood`）與 `modules/qzone/monitor.py`（`notify_new_post`）

## 3. 怎样接入
1. 将 `tools_qzone.py` 复制回 `core/tools/tools_qzone.py`：
   ```bash
   cp _archive/qzone_tool/tools_qzone.py core/tools/tools_qzone.py
   ```
2. 检查文件头部的相对导入（位于 `core/tools/` 下时使用 `from .tools_common import _resolve_image_path, logger`）。
3. 在 `core/tools/tools.py` 中导入并注册到 `TOOL_SPECS`：
   ```python
   from .tools_qzone import publish_qzone_mood_tool

   # 在 TOOL_SPECS 中追加：
   ToolSpec(
       name="publish_qzone_mood",
       description="发布一条 QQ 空间说说（动态），支持纯文字或附带图片（可使用 [img:XXX] 或本地路径）。",
       parameters={
           "type": "object",
           "properties": {
               "content": {"type": "string", "description": "说说正文内容"},
               "visible": {"type": "integer", "description": "可见范围：1=所有人可见(默认)", "default": 1},
               "image_paths": {
                   "type": "array",
                   "items": {"type": "string"},
                   "description": "配图路径或 [img:XXX] 索引列表（可选）",
               },
           },
           "required": ["content"],
       },
       handler=publish_qzone_mood_tool,
   ),
   ```
