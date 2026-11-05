# 聚焦模式（Focus Mode）设计范式

本文档总结了以「手机聚焦模式（`core/phone_focus.py`）」为标杆沉淀出的**按需展开工具集 + 退出覆写上下文**设计范式。未来在扩展**浏览器自动化（Browser Focus）**、**Bilibili 漫游（Bili Focus）**、**游戏/桌面操控**等重度多步工具时，均可直接遵循本范式实现。

---

## 一、为什么需要聚焦模式？（四大核心痛点与解法）

当 Yuki 拥有越来越多「亲手操作」某套复杂外部系统的能力时，传统把所有工具平铺在全局 `TOOL_SPECS` 的做法会遇到四个瓶颈：

| 痛点 | 传统平铺做法的后果 | 聚焦模式（Focus Mode）的解法 |
|---|---|---|
| **1. 常态 Token 税过高** | 复杂工具（如 `phone_action` + `phone_macro`）仅 Schema 说明就占 800~1200+ Tokens，哪怕在群里日常闲聊，每一轮请求都在白白消耗上下文。 | **渐进式披露（Progressive Disclosure）**：常态下隐藏复杂工具，只暴露一个 50 字以内的极简入口工具 `<domain>_start(goal)`。 |
| **2. 工具过多导致分心** | 挂载 15~25 个工具时，模型在连续点击/翻页过程中容易误调 `search_diary`、`update_notebook` 等无关日常工具。 | **工作台收敛（Workspace Isolation）**：一旦进入聚焦模式，立即收起查日记、写小本本、画图、小女仆等无关工具，只保留当前领域的专精工具 + 群聊基础互动（如 `skip` / 发图）。 |
| **3. 过程数据撑爆上下文** | 点一次外卖要 6~10 步，每步返回的 DOM / 控件树 / 截图动辄几千字，操作完后群聊历史被技术垃圾刷屏，把前面的群友聊天挤出窗口。 | **退出即覆写（Exit & Summarize）**：新增 `<domain>_finish(summary)` 工具。退出时将聚焦期间的所有工具调用链、中间思考、临时截图一键抹除，替换为一条以 **`role="user"`** 身份注入的简短总结（如 `【手机操作总结】...`）。 |
| **4. 闭关操作与群聊脱节** | 如果做成独立子 Agent 后台跑，Yuki 在操作期间就无法实时带人设和群友互动（比如边看外卖边问群友“你要微辣还是中辣？”）。 | **群聊流内并发（In-Flow Concurrency）**：主模型本人在流内操作。聚焦状态跨轮保持，工作期间群友插话按原顺序注入并永久保留；退出覆写时只删“工具工作痕迹”，不删任何一句群聊对话。 |

---

## 二、聚焦模式的生命周期与状态流转

```text
                  ┌──────────────────────────────────────────┐
                  │              常态模式 (Default)            │
                  │  暴露：日常群聊工具 + 极简 <domain>_start   │
                  │  隐藏：<domain>_action / _macro / _finish │
                  └────────────────────┬─────────────────────┘
                                       │
                        1. 模型调用 <domain>_start(goal)
                      （自动执行首屏 inspect 并返回领域概览）
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │            聚焦模式 (Focus Mode)           │
                  │  展开：<domain>_action / _macro / _finish │
                  │  保留：skip / send_master_private / 发文件 │
                  │  收起：日记 / 小本本 / 画图 / 小女仆等       │
                  └──────┬─────────────────────────────┬─────┘
                         │                             │
          2a. 显式调用 <domain>_finish(summary)   2b. 连续闲置 > 5 轮未调该领域工具
                         │                             │ (基于已记录的 trace 自动生成总结)
                         └──────────────┬──────────────┘
                                        ▼
                  ┌──────────────────────────────────────────┐
                  │         上下文原地覆写 (Context Rewrite)    │
                  │  1. 删除聚焦期间所有 tool 输出与阶段思考    │
                  │  2. 按原时间顺序保留期间所有群友消息与发言   │
                  │  3. 以 USER 身份注入：【XX操作总结】summary │
                  │  4. 切回常态 ToolSpec 空间                 │
                  └──────────────────────────────────────────┘
```

### 关键设计细节

1. **当轮无缝切换 ToolSpec**：
   在 `EngineReplyService.chat_with_tools` 的 `for _ in range(max_rounds):` 循环内，**每一次向 LLM 发起请求前**都会实时查询当前 `chat_id` 的聚焦状态。因此：
   - 第 1 步调用 `phone_start` 后，无需等到下一条用户消息，**同轮第 2 步**请求 LLM 时 `tools` 参数就已经切换成了聚焦工具集；
   - 第 K 步调用 `phone_finish` 后，**同轮第 K+1 步**请求 LLM 生成对群友的最终回复时，`tools` 已经恢复为常态工具集，且 `tool_messages` 里的几万字控件树已被替换成了那条简短的 USER 总结。
2. **为什么总结要以 `USER` 身份注入？**
   - OpenAI / DeepSeek 兼容接口对 `role="tool"` 和 `assistant(tool_calls)` 有严格的成对校验（删掉 `tool` 消息而留着 `tool_calls` 会报 400 错误，反过来也一样）。
   - 将整个工作过程折叠为一条 `{"role": "user", "content": "【手机操作总结】..."}` 消息，既彻底规避了 `tool_calls` 配对约束，又符合 Yuki 提示词中系统事件/环境反馈以 `user` 消息注入的惯例，同时在日记过滤或后续对话中一目了然。
3. **工作期间群友插话的严格保序**：
   - 假设时间线为：
     1. `[user] 阿澄: 帮我点个汉堡`
     2. `[assistant(tool_thought)] 我拿手机看看~` (`phone_focus_work=True`)
     3. `[tool: phone_start]` 控件树... (`phone_focus_work=True`)
     4. `[user] 群友B: 顺便看看有没有可乐`（工具执行间隙通过 `merge_pending_messages` 插进来的新消息，**不带** `phone_focus_work`）
     5. `[tool: phone_action]` 控件树... (`phone_focus_work=True`)
     6. 调用 `phone_finish(summary="帮阿澄在美团点了汉堡，并确认有冰可乐")`
   - 覆写后的上下文为：
     1. `[user] 阿澄: 帮我点个汉堡`
     2. `[user] 群友B: 顺便看看有没有可乐`
     3. `[user] 【手机操作总结】帮阿澄在美团点了汉堡，并确认有冰可乐`
     4. `[assistant] 点好啦！顺便帮B看了一眼，店里有冰可乐卖~`
   - 中间的技术过程全部蒸发，而群聊的时间线与插话顺序分毫不差。
4. **连续闲置 > 5 轮自动退出兜底**：
   - 若模型在跨轮互动中操作完后直接和群友聊起了别的、忘了显式调用 `<domain>_finish`，管理器在每轮结束（`after_turn`）时累加 `idle_turns`（只要当轮用过该领域工具就清零）。
   - 一旦 `idle_turns > 5`（即连续 6 轮未碰该领域工具），自动触发 `exit_and_summarize`，用聚焦期间每步自动记录的 `trace` 轨迹合成一条 USER 总结覆盖工作记录，防止永久卡在聚焦模式。

---

## 三、开发新聚焦模式的标准模板（Checklist）

以后若要新增例如 **浏览器聚焦模式（`browser`）** 或 **Bilibili 聚焦模式（`bili`）**，只需按以下 4 步实现：

### 第 1 步：定义三件套工具（`<domain>_start` / `<domain>_action`... / `<domain>_finish`）

1. **`<domain>_start(goal="")`**（常态下唯一暴露的入口）：
   - 描述控制在 2 句话以内；
   - 执行时：调用 `focus_manager.enter(context.chat_id, goal)`，**顺带执行一次首屏观察**（如手机的 `inspect`、浏览器的当前标签页概览、B站首页/热搜概览），避免模型进模式后还要多花一轮调观察工具。
2. **领域核心工具（如 `<domain>_action`、`<domain>_macro`）**：
   - 拥有完整的参数枚举与详细说明，仅在聚焦模式开启时暴露；
   - 每次执行成功时调用 `focus_manager.record_step(context.chat_id, step_desc, note)` 记录一行简短轨迹（供超时自动退出兜底生成总结）。
3. **`<domain>_finish(summary="...")`**（退出工具）：
   - 必填参数 `summary`；
   - 执行时：调用 `focus_manager.exit_and_summarize(...)` 清理历史并写入 `context.metadata["<domain>_finish_summary"] = final_summary`，返回 `data={"no_persist": True}`。

### 第 2 步：在 `FunctionRegistry.get_tools` 中配置视图映射

在 `core/phone_focus.py`（或通用化的 `core/focus_manager.py`）中维护每个聚焦模式的两个集合：

- `HIDDEN_IN_DEFAULT`：常态下隐藏的重型工具名（如 `{"phone_action", "phone_macro", "phone_finish"}`）；
- `FOCUS_ALLOWED_TOOLS`：该聚焦模式下允许暴露的工具白名单（领域工具 + `{"skip", "send_master_private", "send_qq_file"}`）。

### 第 3 步：给工作过程消息打上 `_focus_work` 标记

在 `EngineReplyService.chat_with_tools` 中：
- 聚焦期间产生的 `is_tool_thought=True` 的阶段性 `assistant` 消息，以及该领域的 `role="tool"` 消息，在 `history.append_session_message(...)` 时带上 `phone_focus_work=True`（或通用的 `focus_work="<domain>"`）。
- 普通群友发来的 `role="user"` 消息和每轮最终的 `role="assistant"` 回复**不打该标记**，从而在退出清理时被100%保留。

### 第 4 步：双端清理与 USER 总结注入

退出聚焦模式时，同时清理两处：
1. **持久化历史（`HistoryManager`）**：过滤掉带 `focus_work` 的 `tool` 与 `is_tool_thought` 消息，追加 `{"role": "user", "content": "【XX操作总结】...", "is_focus_summary": True}`。
2. **当轮内存消息（`tool_messages`）**：通过 `rewrite_in_memory_tool_messages` 移除当轮该领域的 `assistant(tool_calls)` + `role="tool"` + `【工具截图】` 消息对，在末尾追加同一条 `role="user"` 总结，确保当轮后续请求既不报 400 配对错误，又能立刻释放上下文窗口。

---

## 四、参考实现代码位置

- **聚焦状态机与上下文覆写器**：`core/phone_focus.py`（`PhoneFocusManager`、`phone_start_tool`、`phone_finish_tool`）
- **动态 ToolSpec 过滤**：`core/toolchain.py::FunctionRegistry.get_tools(phone_focus=...)`
- **多轮对话循环内的动态切换与内存覆写**：`core/engine/engine_reply.py::EngineReplyService.chat_with_tools` 与 `_after_turn`
- **单元测试参考**：`tests/test_tool_phone_macro.py` 末尾的 `test_registry_get_tools_switches_between_default_and_phone_focus`、`test_phone_focus_enter_and_finish_overwrites_work_records_preserving_chat`、`test_phone_focus_auto_exits_after_more_than_five_idle_turns`
