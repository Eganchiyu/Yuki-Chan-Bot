# 浏览器交互聚焦模式：部署点位、剥离清单与复原手册

归档日期：2026-11-01
归档源码：`_archive/modules/browser_interaction/`、`_archive/core/tools/tools_browser.py`
设计稿：`_archive/docs/browser-interaction-mode-plan.md`
测试快照：`_archive/tests/test_modes.py.original`

> 剥离原因：该模式的**唯一输出通道是 Live2D 的 `broadcast()`**，Live2D 下线后它没有可用出口，因此一并归档。

---

## 一、当初部署在哪些点位

| 文件 | 位置 | 作用 |
|---|---|---|
| `core/modes.py` | `BrowserInteractionMode` 类（`mode_id="browser_interaction"`, `session_id="mode:browser"`, `tool_group="browser_interaction"`, `is_focus_mode=True`）+ `ModeManager._specs` 注册 | 模式声明，全局唯一聚焦模式 |
| `core/prompts.py` | `get_yuki_setting_browser_interaction()` | 浏览器模式专属 system prompt（浏览器场景、输出规则、互斥规则） |
| `core/brain.py` | `YukiState.get_setting()` 里 `if mode == "browser_interaction": return get_yuki_setting_browser_interaction()` + 顶部 import | 按 mode 选 prompt |
| `core/session_pipeline.py` | `decide_reply_action()` 强制回复集合含 `"browser_interaction"`；`send_answer()` 的 broadcast 分支 | 跳过潜水判定 + 输出走桌宠 |
| `core/engine/engine_reply.py` | `send_tool_thought()` 的 broadcast 分支；工具执行后 `if mode == "browser_interaction": await self.yuki.mode_manager.record_step(...)` | 阶段性文本走桌宠 + 自动记录模式步骤 |
| `core/tools/_archived/tools_browser.py` | `enter_browser_interaction_tool(context, goal)` | 进入模式的入口工具（**此前已从主模型卸载**，只在 `_archived` 里待命） |
| `core/tools/_archived/__init__.py` | import + `__all__` 导出 `enter_browser_interaction_tool` | 归档包导出 |
| `modules/browser_interaction/tools.py` | `browser_scan_placeholder_tool` / `browser_record_step_tool` / `browser_complete_tool` + `BROWSER_TOOL_SPECS` | 模式级工具组（占位实现） |
| `core/engine/engine.py` | 两行注释掉的 `BROWSER_TOOL_SPECS` / `mode_specs=` 引用 | 模式级工具注册的历史残留 |
| `tests/test_modes.py` | 5 个测试：工具文本不走 QQ sender、聚焦模式互斥、进入模式建 session+回调、占位工具完成后回源会话、模式级工具组隔离 | 覆盖率最高的模式测试 |
| `README.md` | 功能列表「浏览器交互模式」、目录树 `browser_interaction/` 与 `tools_browser.py`、开发计划勾选 | 文档 |

模块内部结构：

```
modules/browser_interaction/
├── __init__.py    # 导出 BROWSER_TOOL_SPECS
└── tools.py       # 3 个占位工具：scan / record_step / complete
```

**关键机制**：进入模式 → `ModeManager.enter_mode()` 建 `FocusModeState`（`session_id="mode:browser"`）→ 通过 `process_callback` 起一个 `mode="browser_interaction"` 的管线会话 → 该会话的回复走 Live2D 气泡 → 工具 `browser_complete` 收尾时把结果回发来源 QQ 会话。

---

## 二、这次剥离做了什么

1. 删除 `modules/browser_interaction/`（已归档）。
2. `core/modes.py`：删除 `BrowserInteractionMode` 类与 `_specs` 中该项。**`ModeManager` / `ModeSpec` / `FocusModeState` 通用框架保留**（`core/prompts.py` 的 `mode_manager.render_prompt_status()` 注入仍在用）。
3. `core/prompts.py`：删除 `get_yuki_setting_browser_interaction()`；群聊提示词「即使你正在浏览器交互等聚焦模式中……」改为中性描述。
4. `core/brain.py`：删除 `browser_interaction` 分支与 import。
5. `core/session_pipeline.py`：强制回复集合与 broadcast 分支去掉 `browser_interaction`。
6. `core/engine/engine_reply.py`：去掉 broadcast 分支与 `record_step` 分支。
7. `core/tools/_archived/tools_browser.py` → `_archive/core/tools/tools_browser.py`；`_archived/__init__.py` 去除导出。
8. `core/engine/engine.py`：删掉两行注释残留。
9. `tests/test_modes.py`：重写为 2 个测试（「已无聚焦模式可注册」+ RAG 打分），原文件整体快照在 `_archive/tests/test_modes.py.original`。
10. `docs/browser-interaction-mode-plan.md` → `_archive/docs/`。
11. `README.md`：功能列表、目录树、开发计划勾选去掉该模式。

---

## 三、怎么加回去

### 前置条件

浏览器模式的输出通道依赖 Live2D WS。**要么先按 `live2d-archive.md` 恢复桌宠**，要么把 `send_answer()`/`send_tool_thought()` 里它的分支改成走 QQ `sender.send()`。

### 步骤

```bash
cd /home/asumi/Yuki

# 1) 目录与文件回归
rsync -a _archive/modules/browser_interaction/ modules/browser_interaction/
cp _archive/core/tools/tools_browser.py core/tools/_archived/tools_browser.py
cp _archive/docs/browser-interaction-mode-plan.md docs/
cp _archive/tests/test_modes.py.original tests/test_modes.py   # 若要连旧测试一起恢复
```

2) **`core/modes.py`** 加回模式类并注册：

```python
class BrowserInteractionMode:
    """浏览器交互聚焦模式包装。"""
    spec = ModeSpec(
        mode_id="browser_interaction",
        display_name="BrowserInteractionMode",
        session_id="mode:browser",
        tool_group="browser_interaction",
        is_focus_mode=True,
    )
# 并在 ModeManager.__init__ 的 _specs 里补：
#     BrowserInteractionMode.spec.mode_id: BrowserInteractionMode.spec,
```

3) **`core/prompts.py`** 加回 prompt 函数（原文见 `_archive/docs/removal.diff` 中 `core/prompts.py` 段），并在 `core/brain.py` 恢复：

```python
from core.prompts import ..., get_yuki_setting_browser_interaction
...
        if mode == "browser_interaction":
            return get_yuki_setting_browser_interaction()
```

4) **`core/tools/_archived/__init__.py`** 恢复导出：

```python
from .tools_browser import enter_browser_interaction_tool
__all__ = ["enter_browser_interaction_tool", ...]
```

5) **让主模型能再次进入模式**：`enter_browser_interaction` 此前已从 `TOOL_SPECS` 卸载，恢复它需要在 `core/tools/` 里重新注册一个 `ToolSpec`（handler 直接用归档里的 `enter_browser_interaction_tool`）。只恢复代码不注册工具时，该模式没有任何入口，只能手动调 `ModeManager.enter_mode()`。

6) **模式级工具注册**（可选）：`ToolRegistryProvider(mode_specs={"browser_interaction": BROWSER_TOOL_SPECS})`，参考 `_archive/tests/test_modes.py.original` 里的 `test_tool_registry_provider_uses_browser_tool_group_only_in_browser_mode`。

7) **输出与步骤记录**：按 `live2d-archive.md` 的方案 B 恢复 broadcast 分支；`engine_reply.py` 里加回：

```python
                    if mode == "browser_interaction":
                        await self.yuki.mode_manager.record_step(
                            f"调用工具 {tool_result_message.get('name')}"
                        )
```

8) **测试**：`cp _archive/tests/test_modes.py.original tests/test_modes.py` 后跑 `pytest tests/test_modes.py`（需要带项目的 Python 环境）。

---

## 四、这份代码怎么用

### 进入/退出模式（不依赖 LLM，手工验证）

```python
from core.modes import ModeManager

mgr = ModeManager()
ok, state, reason = await mgr.enter_mode(
    "browser_interaction", origin_chat_id="10001", origin_mode="group", goal="看网页"
)
# ok=True, state.session_id == "mode:browser"
await mgr.record_step("打开了 about:blank")
await mgr.complete_mode(summary="验证完成")   # 退出，回源会话发「【浏览器模式完成】...」
```

同一时间只允许一个聚焦模式：重复 `enter_mode` 返回 `(False, 当前状态, "focus_mode_busy")`。

### 三个占位工具

| 工具 | 参数 | 行为 |
|---|---|---|
| `browser_scan_placeholder` | 无 | 断言当前在浏览器模式，记一条步骤，返回 `mock_page`（`about:blank`） |
| `browser_record_step` | `step` | 记录一条进展，返回 `brief()` 摘要 |
| `browser_complete` | `summary` | 结束模式，向 `origin_mode`/`origin_chat_id` 发「【浏览器模式完成】{summary}」，并写入来源会话历史（`mode_return=True`） |

**注意**：这些都是占位实现，没有真实浏览器驱动。要做真浏览器控制，替换 `browser_scan_placeholder_tool` 的实现即可，模式框架不用动。

### 设计意图（想重新做时看这里）

`_archive/docs/browser-interaction-mode-plan.md` 里有完整方案：聚焦模式作为独立会话存在、与来源群聊记忆隔离但可返回、`origin_chat_id` 追溯、以及「浏览器模式不应伪装成 desktop_pet 会话」的边界约定（原文 307-311 行）。
