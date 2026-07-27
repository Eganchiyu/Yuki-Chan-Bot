# Yuki 浏览器交互模式技术规划

## 1. 当前实现状态摘要

### 1.1 主链路现状

YukiV6 当前核心链路是：

```text
QQ / 桌宠输入 → SessionPipeline → YukiEngine → Function Call 工具链 → 回复发送 / 上下文回写
```

关键特征：

- `SessionPipeline` 已按 `chat_id` 串行处理会话，天然适合保持群聊上下文隔离。
- `ToolChain` 目前是全局工具注册：`YukiEngine` 初始化时将 `core.tools.TOOL_SPECS` 全量注册进 `FunctionRegistry`。
- 工具调用期间模型可以产生阶段性文本，`EngineReplyService.send_tool_thought()` 会直接发到当前会话：
  - 群聊模式发 QQ 群；
  - 私聊模式发私聊；
  - `desktop_pet` 模式广播给 Live2D 桌宠。
- 桌宠已经作为一种独立输入/输出模式存在，`LiveYukiL2D.server` 会把前端输入注入 `chat_id="desktop_pet"`、`mode="desktop_pet"` 的管线。
- 项目中已有早期 `future addons/webpage_agent/yuki_brain.py` 原型，说明“浏览器页面状态上报 + 命令轮询执行”路径可行，但尚未融入主 Yuki 架构。

### 1.2 与浏览器交互相关的现有基础

现有系统已经具备以下可复用能力：

- 工具链：可扩展浏览器操作工具，如扫描页面、点击、输入、滚动、跳转、获取截图。
- 会话管线：可用独立 `chat_id` 表示浏览器交互会话。
- 桌宠输出：适合承载浏览器交互时的实时讲话，不污染群聊。
- 主人状态工具：已有 `get_master_status` 能感知当前窗口，可作为浏览器触发策略的辅助信息。
- 群聊发言能力：现有 `MessageSender` 可按 `chat_id` 向群聊或私聊发送消息。

当前最大缺口不是浏览器操作本身，而是“模式管理”和“模式级工具组隔离”。如果直接把浏览器工具塞进全局 `TOOL_SPECS`，短期能跑，但长期会明显失控。

---

## 2. 需要解决的核心问题

### 2.1 窥屏触发和频率

浏览器窥屏不应该做成高频无脑轮询。原因很简单：页面状态变化频率很高，如果每次变化都进入 LLM，会让 Yuki 长时间被浏览器上下文占满，挤压群聊响应、记忆整理和桌宠对话。

更合理的触发来源分三类：

1. **主动模式触发**：主人在群聊、私聊或桌宠中要求“帮我看浏览器 / 操作网页 / 进入浏览器交互”。
2. **模式内事件触发**：进入浏览器交互模式后，由浏览器插件上报页面变化摘要，但只在关键事件触发推理。
3. **低频观察触发**：模式保持期间定时扫描浏览器状态，用于维持态势感知，而不是每次都说话。

推荐频率：

- 进入模式时立即完整扫描一次。
- URL / title / 可交互元素集合显著变化时触发一次。
- 用户点击、输入、导航后触发一次动作结果回报。
- 无操作时低频扫描，例如 10-30 秒一次，只更新状态，不一定触发 LLM。
- 连续页面变化应做防抖合并，复用 `SessionPipeline` 的防抖思想。

### 2.2 工具调用还是独立模式

这里不建议只做普通工具调用。浏览器交互不是一次性工具，它是一个持续聚焦任务：需要观察、计划、操作、等待结果、再观察。它的本质更接近一个“工作台模式”，而不是 `search_diary` 这种单次函数。

### 2.3 讲话应该发到哪里

浏览器交互模式下的默认讲话不应该发群聊。理由：浏览器操作过程通常是主人和 Yuki 的协作，不属于群聊公共上下文。如果把 ReAct 阶段性文本发群聊，会污染群聊历史，也会让群友看到大量无关操作过程。

推荐输出策略：

- 默认输出到桌宠，即 Live2D 气泡 / 语音 / 状态。
- 如果是从主人私聊进入，也可以同步输出到主人私聊，但桌宠仍是主通道。
- 群聊只在 Yuki 明确调用“向指定群聊发言”工具时发送。
- 浏览器模式下的工具组应提供 `send_group_message`，让 Yuki 可以主动把结果、通知或吐槽发到指定群聊。

### 2.4 是否需要群聊隔离

需要隔离，但不是简单复制现有群聊隔离。

推荐模型：

- 浏览器交互模式是一个全局焦点模式，因为浏览器实例通常是全局桌面资源。
- 进入浏览器模式时记录 `origin_chat_id` 和 `origin_mode`。
- 模式内历史写入独立会话，例如 `chat_id="mode:browser"`。
- 如果从某个群聊进入，则建立来源绑定：
  - `origin_chat_id=群号`
  - `origin_mode=group`
  - `return_target=该群聊`
- 浏览器模式内默认不读取其他群聊上下文，只读取：
  - 浏览器模式自身历史；
  - 主人私聊/桌宠近期上下文；
  - 必要时读取来源群聊最近消息。

这样既保持浏览器状态连续，又不会把浏览器过程塞进某个群聊历史。

---

## 3. 候选方案评估

### 3.1 方案 A：浏览器能力作为普通全局工具

做法：在 `core.tools.TOOL_SPECS` 中新增 `browser_scan`、`browser_click`、`browser_type`、`browser_scroll` 等工具，所有模式都能调用。

优点：

- 改动最少。
- 复用当前 Function Call 链路。
- 很快可以验证浏览器控制能力。

缺点：

- 工具会暴露给所有群聊、私聊和桌宠上下文，模型容易在普通聊天中误触发。
- 浏览器任务需要多轮 ReAct，全局工具没有“聚焦状态”，会导致上下文混乱。
- 阶段性文本会默认发到当前群聊，污染群聊体验。
- 无法自然扩展到后续 QQ 管理模式、游戏模式等模式化工具链。
- 退出、返回原群聊、指定输出目标等能力会被迫写成零散工具，架构会越来越补丁化。

结论：只适合作为极早期原型，不适合作为正式实现路径。

### 3.2 方案 B：新增独立浏览器 Agent，和 Yuki 主体弱连接

做法：沿用 `future addons/webpage_agent/yuki_brain.py` 的思想，单独启动一个浏览器 Agent 服务，自己维护状态、自己调用模型、自己执行浏览器操作，Yuki 只负责把任务转交给它。

优点：

- 与现有群聊主链路隔离，风险小。
- 浏览器 ReAct 可以自由设计，不受当前 `SessionPipeline` 限制。
- 便于快速验证复杂网页操作能力。

缺点：

- 会出现“双大脑”：浏览器 Agent 和 Yuki 主人格、记忆、上下文不一致。
- 工具调用结果难以自然回写 Yuki 历史和记忆。
- 桌宠讲话、群聊发言、返回原会话都需要额外桥接。
- 后续如果再做 QQ 管理模式、游戏模式，会复制多个 Agent，最终形成多套不可维护的状态机。

结论：适合作为浏览器驱动层原型，不适合作为最终产品架构。

### 3.3 方案 C：在 Yuki 主体内实现“可聚焦模式 + 模式级工具组”

做法：增加统一的 `ModeManager`，允许 Yuki 从群聊、私聊或桌宠进入某个聚焦模式。不同模式拥有不同 system prompt、工具组、输入源、输出策略和退出规则。浏览器交互作为第一个正式模式实现。

优点：

- 和用户设想一致，能自然扩展 QQ 管理模式、游戏模式等能力。
- 浏览器工具只在浏览器模式中暴露，避免普通群聊误触发。
- 模式可以拥有独立会话历史，浏览器 ReAct 不污染群聊。
- 默认输出到桌宠，同时保留“指定群聊发言”工具，输出路径清晰。
- 可以统一处理进入、退出、返回来源会话、模式抢占、模式空闲超时等问题。

缺点：

- 需要改造工具注册逻辑，从“全局工具列表”变成“按模式选择工具列表”。
- `YukiState.get_setting(mode)` 当前只区分 private/group/master_private，需要扩展模式 prompt。
- `SessionPipeline` 当前以 `chat_id + mode` 表示会话，需要补充“当前焦点模式”和“来源会话”的概念。

结论：这是最合理的正式路径。它不是最省事的方案，但它能一次性解决浏览器、QQ 管理、游戏等未来能力的共同架构问题，长期维护成本最低。

---

## 4. 最终推荐方案

推荐采用方案 C：**可聚焦模式 + 模式级工具组 + 浏览器交互模式**。

核心设计如下：

```text
普通群聊 / 私聊 / 桌宠
        ↓  enter_mode(browser_interaction)
ModeManager 设置当前焦点模式
        ↓
SessionPipeline 使用 mode:browser_interaction 会话
        ↓
EngineReplyService 按模式选择 Browser ToolRegistry
        ↓
浏览器观察 → ReAct → 浏览器操作 → 桌宠讲话 / 指定群聊发言
        ↓
exit_mode 返回 origin_chat_id / origin_mode
```

### 4.1 模式边界

新增模式：`browser_interaction`。

模式状态建议包含：

```python
@dataclass
class FocusModeState:
    mode: str
    session_id: str
    origin_chat_id: str
    origin_mode: str
    entered_at: float
    last_active_at: float
    metadata: dict
```

浏览器模式使用：

- `session_id = "mode:browser"`
- `mode = "browser_interaction"`
- `origin_chat_id = 进入模式的群聊 / 私聊 / desktop_pet`
- `metadata.browser_state = 当前 URL、标题、元素摘要、截图索引、最近动作结果`

### 4.2 工具组设计

普通群聊工具组继续保留现有工具：

- `search_diary`
- `delegate_to_maid`
- `send_qq_file`
- `poke`
- `publish_qzone_mood`
- `generate_image`
- 等现有工具

浏览器模式工具组新增：

| 工具 | 作用 |
|------|------|
| `browser_scan` | 获取当前页面摘要、URL、标题、可交互元素、可选截图 |
| `browser_click` | 点击指定元素或坐标 |
| `browser_type` | 向输入框输入文本 |
| `browser_scroll` | 滚动页面 |
| `browser_open` | 打开指定 URL |
| `browser_back` / `browser_forward` | 浏览器前进后退 |
| `browser_wait` | 等待页面变化或异步加载 |
| `browser_extract_text` | 提取当前页面正文或选区文本 |
| `send_group_message` | 向指定群聊发言 |
| `send_desktop_message` | 向桌宠说话，作为默认表达通道 |
| `exit_mode` | 退出浏览器模式并返回原会话 |

关键点：浏览器模式下不要复用全部 QQ 群聊工具，只暴露必要通信工具。否则模式边界会被破坏。

### 4.3 触发机制

进入模式的触发建议：

1. 主人明确要求：如“Yuki 看一下浏览器”“帮我操作这个网页”。
2. Yuki 在群聊或私聊中判断任务必须操作浏览器，调用 `enter_mode(mode="browser_interaction")`。
3. 桌宠端提供按钮或命令直接进入浏览器模式。

模式内观察触发：

- 进入模式立即 `browser_scan`。
- 浏览器插件发现 URL/title 改变时上报事件。
- Yuki 执行操作后等待结果并重新扫描。
- 空闲时低频扫描，只更新状态，不强制发言。

不推荐的触发：

- 全局持续截屏并持续喂给 LLM。
- 普通群聊每轮都自动读取浏览器。
- 所有页面 DOM 变化都触发模型推理。

### 4.4 讲话落点

推荐规则：

- 浏览器模式默认讲话到桌宠。
- 如果 `origin_mode == master_private`，可同步简短结果到主人私聊。
- 群聊发言必须通过 `send_group_message(chat_id, message)` 显式完成。
- ReAct 阶段性文本只给桌宠，不进入群聊。
- 浏览器工具结果写入 `mode:browser` 会话历史，不写入来源群聊；最终摘要可按需写回来源会话。

这能避免群聊被浏览器操作日志刷屏，同时保留 Yuki 主动“把浏览器看到的东西告诉群里”的能力。

---

## 5. 需要调整的现有架构点

### 5.1 `FunctionRegistry` 需要支持模式级工具

当前 `YukiEngine` 只有一个全局 `tool_registry`。建议改为：

```text
ToolRegistryProvider
├── default registry
├── browser_interaction registry
├── qq_management registry
└── game registry
```

`EngineReplyService.chat_with_tools()` 根据当前 `mode` 选择对应 registry，而不是固定使用 `self.tool_registry`。

### 5.2 `YukiState.get_setting(mode)` 需要扩展

当前未知模式会回落到群聊 prompt。浏览器模式必须有专用 prompt，否则模型会继续按群聊角色说话。

应新增：

- `get_yuki_setting_browser_interaction()`
- 模式行为说明：观察浏览器、先扫描后操作、默认对桌宠说话、必要时向指定群聊发言、可退出模式。

### 5.3 `SessionPipeline` 需要接受模式事件

建议新增一种内部消息来源：

```text
source = "browser"
chat_id = "mode:browser"
mode = "browser_interaction"
```

浏览器事件不直接进入群聊 `chat_id`，而是进入模式会话。

### 5.4 桌宠输出应成为浏览器模式默认通道

当前 `desktop_pet` 模式已经可通过 `broadcast({"type": "say"})` 讲话。浏览器模式可以复用同一输出方式，但不应把自身伪装成 `desktop_pet` 会话。

也就是说：

- `desktop_pet` 是输入/输出通道；
- `browser_interaction` 是焦点工作模式；
- 两者不应混为一谈。

---

## 6. 分阶段开发计划

### 阶段 1：抽象模式管理

目标：先让系统知道“当前是否处于某个聚焦模式”。

任务：

1. 新增 `core/mode_manager.py`。
2. 定义 `FocusModeState`。
3. 在 `YukiState` 或组件容器中挂载 `mode_manager`。
4. 实现：
   - `enter_mode(mode, origin_chat_id, origin_mode, metadata)`
   - `exit_mode()`
   - `get_current_mode()`
   - `is_focus_active()`
5. 增加基础工具：
   - `enter_focus_mode`
   - `exit_focus_mode`

依赖：无。

验收：Yuki 可从群聊/桌宠进入浏览器模式，并能记录来源会话。

### 阶段 2：实现模式级工具注册

目标：不同模式暴露不同工具组。

任务：

1. 新增 `ToolRegistryProvider` 或等价结构。
2. 拆分现有 `TOOL_SPECS` 为：
   - `DEFAULT_TOOL_SPECS`
   - `BROWSER_TOOL_SPECS`
3. 修改 `EngineReplyService.chat_with_tools()`，按 `mode` 选择 registry。
4. 调试上下文记录当前工具组名称和工具数量。

依赖：阶段 1。

验收：普通群聊看不到浏览器操作工具；浏览器模式能看到浏览器工具和退出工具。

### 阶段 3：接入浏览器驱动层

目标：实现浏览器观察和操作的最小闭环。

任务：

1. 新增 `modules/browser_interaction/`。
2. 实现浏览器服务端，接收插件上报：
   - URL
   - title
   - 页面正文摘要
   - 可交互元素列表
   - 可选截图路径或 base64
3. 实现命令队列，下发操作：
   - scan
   - click
   - type
   - scroll
   - open
   - wait
4. 将 `future addons/webpage_agent/yuki_brain.py` 的轮询模型迁移为正式模块。
5. 工具 handler 通过浏览器模块读状态、发命令、等待结果。

依赖：阶段 2。

验收：Yuki 在浏览器模式中可以扫描页面、点击按钮、输入文本、打开 URL，并看到动作结果。

### 阶段 4：浏览器模式 prompt 与输出策略

目标：让浏览器交互体验自然，不污染群聊。

任务：

1. 新增浏览器模式 system prompt。
2. 约束模型：
   - 先观察再行动；
   - 不确定元素时重新扫描；
   - 操作过程默认对桌宠说；
   - 只有需要公开结果时才调用群聊发言工具；
   - 完成任务后主动总结并退出或询问是否继续。
3. 实现 `send_desktop_message` 工具。
4. 实现 `send_group_message` 工具，允许指定 `chat_id`。
5. 调整 `send_tool_thought()`：浏览器模式阶段性文本默认发桌宠。

依赖：阶段 3。

验收：浏览器 ReAct 过程只在桌宠显示，群聊不被刷屏；Yuki 可以显式把结果发到指定群。

### 阶段 5：事件触发与频率控制

目标：让浏览器窥屏既及时又不吵。

任务：

1. 浏览器模块维护页面状态 hash。
2. URL/title/元素列表显著变化时生成事件。
3. 事件进入 `mode:browser` 缓冲区，复用防抖合并。
4. 空闲低频扫描只更新状态，不默认触发 LLM。
5. 动作后强制扫描一次，保证操作结果进入上下文。

依赖：阶段 4。

验收：页面变化可被 Yuki 感知；无意义 DOM 抖动不会持续触发回复。

### 阶段 6：模式返回与摘要回写

目标：完成浏览器模式和来源会话的闭环。

任务：

1. `exit_mode` 退出时生成浏览器任务摘要。
2. 摘要写入 `mode:browser` 历史。
3. 如果存在 `origin_chat_id`，可写入一条简短系统上下文到来源会话，例如“Yuki 刚完成一次浏览器操作：……”。
4. 如果用户要求发群聊，则通过 `send_group_message` 发正式结果。

依赖：阶段 5。

验收：退出浏览器模式后，Yuki 能回到原群聊/私聊语境，不丢失刚才浏览器任务的必要结论。

---

## 7. 最终判断

浏览器窥屏和操作不应该被设计成普通工具，而应该作为 Yuki 的第一个“聚焦模式”。

最关键的理由：

1. 浏览器交互是持续任务，不是单次查询。
2. 它需要独立观察频率、独立上下文、独立工具组。
3. 默认输出应走桌宠，而不是群聊。
4. 模式架构能复用到 QQ 管理模式、游戏模式等未来能力。
5. 群聊隔离仍然重要，但浏览器模式应是全局焦点会话，通过 `origin_chat_id` 与来源群聊建立弱绑定。

最终推荐实现口径：

```text
Yuki 可以从群聊/私聊/桌宠进入浏览器交互模式；
进入后切换到 mode:browser 独立会话；
浏览器模式拥有专属工具组；
ReAct 和过程发言默认显示在桌宠；
需要对外通知时显式调用指定群聊发言工具；
完成后通过 exit_mode 返回原会话。
```

这条路线比“直接加全局浏览器工具”更重一点，但它是后续多模式自主 Agent 架构的正确地基。