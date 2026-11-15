# 自主沙盒（Autonomous Sandbox v1）可行性评估与开发规划

> 上游设计基准：`docs/Autonomous Sandbox.md`
> 本文档只回答两件事：**能不能落地**、**按什么顺序落地**。
> 结论先行：**可以实现**，且不需要改动主循环 `engine_reply.py` 的既有热路径；
> 但设计文档里有 6 处与当前代码事实不符，必须按本文档的口径修正后再动手。

---

## 一、可行性结论

### 1.1 可以直接复用的底座（已核实到函数级）

| 能力 | 位置 | 复用方式 |
| --- | --- | --- |
| 生物钟 / 精力 / 活跃度 | `core/brain.py` `YukiState.{update_energy,get_smooth_time_weight,group_activity,last_message_time}` | 触发条件判定，零改动 |
| 冷场巡检循环 | `core/engine/engine_monitor.py` `idle_diary_checker`（30s 一轮） | 在同一个循环体里挂 `autonomous_trigger_check()` |
| 工具声明/执行/参数容错 | `core/toolchain.py` `ToolSpec` `FunctionRegistry` `ToolCallManager`（已含 JSON 截断提示、超时、skip_reply） | 沙盒自建 registry，`max_rounds=60` |
| 文本形式工具调用还原 | `core/tool_markup.py` `extract_text_tool_calls` | 沙盒循环里照抄 `engine_reply._extract_calls` 的处理 |
| 日记只读检索 | `modules/memory/rag.py` `search_diaries` / `core/maid/maid_tools.py` `search_diary_fast`（走 chromadb `where_document`，**不加载 embedding 模型**） | 直接给工具用；冷启动采样只读 `collection.get(where={"timestamp": ...})` |
| 日记追加写入 | `modules/memory/rag.py` `save_diary` → `save_memory`（内部 `self.model.encode`） | 只追加，不改表结构；metadata 追加 `type="autonomous_memo"` |
| 聚焦模式范式 | `core/focus/{domain,manager,view}.py` | 借用概念；**不注册**到全局 `focus_manager`（理由见 2.1） |
| 等回音追击 | `core/reply_watch.py` `subscribe/_dispatch` | Phase 4 被动多轮复用，需加可选下限参数（见 2.4） |
| LLM 主备切换/空回复重试 | `utils/llm_client.py` `llm_chat_raw(**tools)` | 沙盒循环的唯一出口 |

### 1.2 必须新建的部分（设计文档 `modules/autonomous/` 五文件，方向正确）

设计文档的模块拆分基本可用，只补一个文件：

```text
modules/autonomous/
├── __init__.py
├── coordinator.py     # 四阶段状态机 + 抢占事件 + 冷却/日配额 + 虚拟 chat 路由
├── sandbox_loop.py    # 【新增】独立 LLM 工具循环（沙盒版 chat_with_tools，约 180 行）
├── inner_debate.py    # Phase 1 双念头 + 双向投票 + 三段式压力调度
├── workshop.py        # Phase 3 工坊（60 步上限、零工具追问、熔断）
├── prompts.py         # 各阶段 system prompt（只读引用 get_base_setting，剥 layout/MEME）
├── storage.py         # L2/L3/L4/L1 落盘 + 日记采样 + 小本本双区适配
└── tools.py           # inner_vote / conclude_reflection / list_recent_work_sessions /
                       # inspect_work_session / write_work_diary / work_finish
```

`engine_reply.py` 为什么不能直接拿来跑沙盒：它硬绑 `self.history`（真实会话 +
`replace_session` 覆写）与 `self.sender`（`send_tool_thought` 会把阶段性思考
**实时发送到群**），任一处漏配就是把内心独白发进群里。而设计铁律 1 恰好禁止这件事。
所以沙盒必须有自己的瘦循环：`llm_chat_raw` + `ToolCallManager` + 内存消息流 + 静默 sender。

---

## 二、设计文档与代码事实的 6 处偏差（必须先修正口径）

### 2.1 `ToolView` 不读 `ToolContext.metadata`，"在 domain.py 检查 is_autonomous_work"不可行

`core/focus/view.py::ToolView.resolve(registry, manager, chat_id)` 只由
`registry.list_functions()` 与 `focus_manager.active(chat_id)` 推导，拿不到 `ToolContext`。
而且默认视图会**保留 `entry_tool`**，如果沙盒工具注册进主 registry，群聊模型就会看到
`autonomous_start` 并可能自己去点。

修正方案（更简单、无侵入）：**沙盒工具不注册进主 `FunctionRegistry`**，只在沙盒自建的
registry 里存在。沙盒的工具视图自己算：

```python
visible = (set(main_registry.list_functions()) - AUTONOMY_HIDDEN - AUTONOMY_DOMAIN_TOOLS) | AUTONOMY_TOOLS
```

`work_finish` 恒在集合里，天然不会被任何子聚焦域屏蔽，`core/focus/domain.py` 无需改动。

### 2.2 `reply_watch.MIN_TIMEOUT_SECONDS = 30`，做不出 10~15 秒窗口

`subscribe()` 把 timeout 夹到 `>= 30s`（`core/reply_watch.py:20,74`）。
Phase 4 要求"发出第一条后 10~15 秒安静就补一句"。
修正：`subscribe(..., min_timeout_seconds=MIN_TIMEOUT_SECONDS)` / `auto_subscribe(..., min_timeout_seconds=...)`，
只在 high_spirits 路径传 `10.0`，**默认行为不变**，`test_reply_*` 不受影响。

### 2.3 chat_id 到底填什么：工具语义要求真实群 ID，隔离不能靠它

清点后确认：`search_group_snapshots` / `capture_group_snapshot` / `send_qq_file` / `poke` /
`delegate_to_maid` 全部读 `context.chat_id`。所以**沙盒的 `ToolContext.chat_id` 必须是真实目标群 ID**，
否则"翻群聊截屏"这类能力直接失效。隔离改由 `runtime` 与 `metadata` 承担：

1. `ToolContext.chat_id = target_group_id`（工具语义正确，零包装）；
2. `metadata["autonomous"] = {"run_id", "session_id"}` 作为隔离标识；
3. `runtime.sender = SilentSender`：`send_qq_file` / `poke` / `send_master_private` 都只经过
   `context.sender`，于是**自动变成不真发**（T1 方案 B 免费获得，无需逐个包装）；
4. `delegate_to_maid` 是唯一需要包装的：沙盒版 handler 把 task 的 chat_id 改为虚拟
   `autonomous:<gid>` 再入队，`maid_worker` 汇报时 `engine.process_callback("autonomous:<gid>", ...)`
   会在 `main_process` 被前缀分流回沙盒（不再触发群回复）：

```python
if str(chat_id).startswith(AUTONOMOUS_CHAT_PREFIX):   # "autonomous:"
    return await autonomous_coordinator.on_inner_event(chat_id, text=...)
```

虚拟 chat_id 只出现在这条链路上；`data/chat_history.json` 永远不会出现该键。

### 2.4 `FocusManager.exit()` 依赖 `history.get_session/replace_session`

若 Phase 3 想嵌套 `phone_start` / `art_start`，`focus_manager` 的键是 `chat_id`，
`exit(history=...)` 会去真实 `HistoryManager` 里查这个键。
修正：给沙盒一个 20 行的 `SandboxHistoryAdapter`（只实现 `get_session` / `replace_session`，
读写沙盒内存消息流），进入子聚焦时传 `history=adapter`。
此项列为 P4 可选项，**v1 默认关闭嵌套聚焦**（见 §7 取舍 T3）。

### 2.5 基线测试已经是红的（与本需求无关，但会干扰验收）

`docker exec yuki python -m pytest tests -q` 现状：**5 failed / 153 passed**，原因是历史漂移：
`BASE_KEEP_TOOLS` 后来加了 `search_diary`、registry 新增了 `art_*`，但
`test_tool_phone_macro` / `test_art_focus` 里仍写死旧集合；`test_focus_snapshot`、
`test_diary_filter` 同理。
计划：**P0 先修这 5 个测试**（只改断言，不改实现），否则新模块的"测试全绿"无法作为验收依据。

### 2.6 Phase 1 的"翻群聊截屏"必须显式绑定目标群

`search_group_snapshots` 的入参只有 `keyword` / `limit`，群 ID 取自 `context.chat_id`，
而 Phase 1 的上下文里没有真实群消息可依据。按 §2.3 的约定 `ToolContext.chat_id = target_group_id`
即可直接用；P1 只需在 prompt 里说明"你现在在 `<群名/群号>` 的独处空间"，避免模型乱猜群。

---

## 三、总体架构（落地后的数据流）

```text
EngineMonitorService.idle_diary_checker (30s)
        │  autonomous_trigger_check(): 静默≥45min ∧ 精力≥0.6 ∧ 非深夜 ∧ 冷却结束 ∧ 日配额未满
        ▼
AutonomousCoordinator.run(target_group, trigger="auto"|"manual")
        │  session_id = sess_YYYYMMDD_HHMMSS
        │  ★ asyncio.Event interrupt，由 SessionPipeline.enqueue_message 置位
        ▼
  Phase 1  inner_debate.run()
           messages: [system(内省底色+A/B 视角) , system(3 条采样日记), user(开场旁白)]
           loop ≤32: llm_chat_raw(tools=READONLY_TOOLS) → 执行 → 累积 → 每 8 步压缩
           收敛: 连续两步 inner_vote(agree_to_end=True) 且 verdict 相同
        ├ verdict=do_nothing ──────────────► 出口 1：清空内存，不落盘，直接 return
        ├ verdict=memo_only / start_work ──► Phase 2
        └ 满 32 轮 ────────────────────────► Phase 2（consensus_note = 最后 6 步摘要）
        ▼
  Phase 2  yuki_self_review.run()
           messages: [基础人设(剥离 layout/MEME), 契机, consensus_note]
           一次工具调用 conclude_reflection(action, title, memo_content, work_diary_entry, notebook_pointer)
        ├ abandon ──► 出口 2：不落盘（除 debug 日志），return
        ├ memo_only ──► L1 diaries + L2 work_diary + L4 daily_work_memory + L5 小本本下区
        └ start_work ──► 同上 + 建/续 L3 work_session → Phase 3
        ▼
  Phase 3  workshop.run(session_id)
           messages: [system(工坊 prompt + session_id + 上次 work_log)]
           tools = 主 registry 全量 ∪ 工坊专属；max_rounds=60
           零工具 → 注入追问（≤2 次）→ 熔断兜底 work_log(status=paused)
           55/60 步时工具结果尾部追加提醒；≥60 步强制只剩 work_finish
        ▼
  Phase 4  after_return(target_group)
           L4 daily_work_memory(≤1000 字) 常驻注入 build_chat_context
           YukiState.high_spirits_until / high_spirits_remaining_turns=3
           EngineDecisionService 欲望 +0.45；静默则立刻触发一次破冰
           首条发出后 reply_watch(min_timeout=10~15s) → 静默则再唤醒（每次 -1）
```

隔离保证：沙盒全程只在内存消息流里跑，唯一落盘是 L1~L5 五层记忆与 debug 轨迹；
`data/chat_history.json` 里不会出现 `autonomous:` 键（写之前断言）。

---

## 四、五层记忆的落地 schema

```python
# L3 data/work_sessions/<session_id>.json
{
  "session_id": "sess_20261115_01",
  "created_at": 1763200000.0, "updated_at": 1763203600.0,
  "status": "active",            # active | paused | completed | abandoned
  "title": "雪夜电台",
  "kind": "creative",            # creative | code | life | misc
  "work_log": "≤512 字",          # 干了什么 / 产物路径 / 下次从哪接
  "artifacts": ["workspace/novels/snow_radio_ch1.md"],
  "memo_ref": "mem_autonomous_memo_...",   # L1 doc_id
  "runs": ["sess_20261115_01", "sess_20261116_01"],  # 每次独处一个 run 记录
}
# L3 data/work_sessions/index.jsonl  每行 {"session_id","title","status","updated_at","log_head":80 字}

# L2 data/work_diary.jsonl
{"ts": 1763203600.0, "session_id": "...", "title": "...", "content": "150~400 字", "kind": "insight"}

# L4 data/daily_work_memory.json
{"date": "2026-11-15", "archived_at": null, "updated_at": ..., "text": "≤1000 字",
 "entries": [{"session_id":"...","status":"completed|paused","summary":"...","artifacts":[...]}]}
#   text 由 entries 渲染（代码拼接，非模型生成），04:00 后把昨天归档进 data/daily_work_memory_archive/<date>.json

# L5 data/notebook.json（向后兼容旧格式）
{"version": 2, "daily": "≤350 字", "plans": "≤160 字", "content": "<旧字段，读取时回落为 daily>"}
```

L1 写入固定前缀：`【自主随想(YYYY-MM-DD)】` / `【工作记录(YYYY-MM-DD)】`，
metadata `extra_metadata={"type": "autonomous_memo", "session_id": ..., "kind": ...}`
（`save_memory` 支持 `extra_metadata`，见 `rag.py:_build_memory_metadata`）。

---

## 五、配置项（`configs/config.yaml` + `config.py` 新增 `AutonomousConfig`）

沿用项目现有 `config_field(..., section="autonomous")` 风格，`cfg.autonomous.*` 访问。

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `false` | **先关**，手动 `/深思` 验证通过后再开自动 |
| `target_groups` | `[]` | 空 = 用 `cfg.TARGET_GROUPS[0]` |
| `auto_trigger_enabled` | `false` | 冷场自动触发开关（P5 才打开） |
| `min_group_idle_minutes` | `45` | 静默阈值 |
| `min_energy` | `0.60` | 精力下限 |
| `quiet_hours` | `[1, 7]` | 深夜禁止触发（配合生物钟） |
| `cooldown_minutes` | `120` | 两次自动轮次最小间隔 |
| `daily_max_runs` | `3` | 每日自动上限（持久化计数，重启不清零） |
| `debate_max_rounds` | `32` | Phase 1 上限 |
| `debate_max_tokens` | `600` | 每步输出上限（控 token） |
| `debate_compress_every` | `8` | 每 8 步把已用上下文压成锚点卡 |
| `workshop_max_tool_calls` | `60` | Phase 3 上限 |
| `zero_tool_max_retries` | `2` | 零工具追问容忍 |
| `step_timeout_seconds` | `180` | 单步（一次 LLM+该批工具）超时熔断 |
| `daily_memory_ttl_hours` | `18` | L4 有效期 |
| `high_spirits_turns` | `3` | 回归后连发配额 |
| `high_spirits_minutes` | `25` | 高涨持续 |
| `high_spirits_desire_bonus` | `0.45` | 欲望加成 |
| `high_spirits_followup_window` | `12` | 被动窗口（秒，允许 <30，走 2.2 的改动） |

---

## 六、分阶段实施计划（每阶段独立可验收、可回滚）

### P0 地基与基线修复（0.5 天）

1. `config.py`：新增 `AutonomousConfig` + `cfg.autonomous`；`python config.py sync` 生成 yaml 段。
2. 修 5 个漂移测试（只改断言）。
3. `modules/autonomous/storage.py` 骨架 + `data/` 目录初始化（含旧 notebook 迁移读取）。
4. 验收：`pytest tests -q` → **0 failed**；`cfg.autonomous.enabled is False`。

### P1 沙盒内核：循环 + 双念头 + 投票 + 双出口（2 天，`/深思` 手动跑通）

1. `sandbox_loop.py`：
   - `run_step(messages, tools, max_tokens) -> (content, calls)`；内部复用
     `extract_text_tool_calls`；
   - `SilentSender`：`send()` 只往 `self.sent` 记录并返回成功（子聚焦域/工具内部可能调用），
     `parse_cq_codes` 原样透传；
   - `ToolContext(chat_id=<真实 target_gid>, mode="autonomous",
     metadata={"autonomous": {"run_id": ..., "session_id": ...},
               "process_callback": None, "history_manager": adapter})`（见 §2.3）。
2. `storage.sample_diaries(n_recent=2, n_old=1)`：只读 `MemoryRAG().collection.get(...)`，
   按 `timestamp` 分桶随机（近 7 天 / 30 天以上），失败则降级为空并写日志，不阻塞。
3. `inner_debate.py`：三段式旁白注入（第 3 步未检索→提醒；11 步→排雷；23 步→收敛）；
   `inner_vote` 判定按**步序号**，同批多次投票只认最后一次；`agree_to_end` 单边为真则清零。
4. `prompts.py`：Phase 1 三个 prompt，A/B 通过 `system` 尾部"当前视角"切换（同一消息流，
   发言前缀 `【脑海里的直觉】/【冷静下来的念头】` 由 prompt 约束，代码只做校验与补齐）。
5. `listen_main.py`：`handle_group_switch` 增加 `/深思`、`/工坊状态`（master 限定，
   沿用现有 set + 提示文案风格）；`/深思` 异步起 coordinator，完成后
   `send_master_private` 发交锋摘要 + 备忘录全文。
6. 验收：连续 5 次 `/深思`，日志里能看到 a) 至少 3 次调用 `search_diary`；
   b) 出现 do_nothing 出口且 `data/` 无任何新文件；c) 36 轮上限内收敛；
   d) 全程 `data/chat_history.json` 无 `autonomous:` 键、群里零消息。

### P2 五层记忆落盘 + 小本本双区（1.5 天）

1. `core/notebook.py`：`load_zone(zone)` / `save_zone(zone, text)`；`load()` 回落
   `daily` 或旧 `content`；`update_notebook` 保持默认写 `daily`（旧调用语义不变）。
2. `core/prompts.build_chat_context`：小本本注入改为两区渲染（上区日常、下区
   `【长期路标】`），并在日记回忆之后新增 L4 槽位（§8 第 1 条）。
3. Phase 2 `conclude_reflection` 三向流转 + L1/L2/L4/L5 写入 + `work_sessions` 建档。
4. 验收：`memo_only` 后能 `search_diary` 命中自己的备忘录；`/工坊状态` 能列出
   active/paused 会话与 512 字日志尾部。

### P3 自主执行工坊（2 天）

1. `workshop.py`：60 步上限、55 步提醒、≥60 步强制只剩 `work_finish`、
   零工具追问（≤2 次）、连续零工具熔断兜底 `paused` 日志、`step_timeout` 熔断。
2. `tools.py`：`work_finish` 校验 ≤512 字（超长截断并回显"已精简到 512"），
   强制三要素（干了吗/产物路径/怎么接续）——只做软校验 + 提示，不硬拒。
3. `delegate_to_maid` 衔接：任务里带 `session_id` 写进 `tasks/dsh/*/request.json`
   之外的旁路文件 `data/work_sessions/<sid>.json.maid`（不改 maid 模块），
   maid 汇报经 §2.3 分流回到沙盒，若沙盒已结束则记进 L2 并在下次触发时提示。
4. 验收：两次 `/深思` 接续同一小说 → 第二次 `list_recent_work_sessions` 能看到上次
   session 且 `inspect_work_session` 返回 512 字日志；第三次能续写第二章。

### P4 真人抢占 + 子聚焦（可选）（1 天）

1. `SessionPipeline.enqueue_message`：真人入站时 `autonomous_coordinator.interrupt(chat_id)`；
   沙盒每个"步"边界检查 `interrupt.is_set()` → 保存断点 `status=paused` 退出。
2. 嵌套 `phone_start` / `art_start`：`SandboxHistoryAdapter` + 不注册 domain 的特殊处理；
   `work_finish` 恒在视图内（先算 `visible`，再 `|= {"work_finish"}`）。
3. 串行化：沙盒与群聊可能同时用 adb，加一把 `asyncio.Lock` 保护 phone 类重工具（或
   直接规定沙盒期间 `phone_start` 返回"现在不方便"）。
4. 验收：沙盒跑第 5 步时群里有人 @她 → 3 秒内沙盒挂起、正常回群、断点可续。

### P5 自动触发与冷场反哺（1.5 天）

1. `engine_monitor.autonomous_trigger_check()`：条件组合 + 冷却 + 日配额持久化
   （`data/autonomous_state.json`，按自然日重置，04:00 归档）。
2. `core/brain.py`：`high_spirits_until` / `high_spirits_remaining_turns` +
   `mark_high_spirits()/high_spirits_active()`。
3. `engine_decision`：`high_spirits` 时欲望 `+bonus`，并跳过 `energy < MIN_ACTIVE`
   的拒绝分支（但仍守 `energy > 0.15` 底线）。
4. `reply_watch`：`min_timeout_seconds` 参数（§2.2）+ `high_spirits_followup` 注册，
   扣减配额，刷屏 >3 条或精力耗尽即停。
5. 验收：把 `min_group_idle_minutes` 调成 2 分钟，手动制造冷场 → 自动进入沙盒 →
   回归后群里出现"分享语气"的 1~3 条消息，且不再继续刷。

### P6 观测与调优（1 天）

1. `modules/debug/webui_server.py` 加 `/api/autonomous`：当前阶段、轮次、token 估算、
   本次 run 的 A/B 对话流（内存 ring buffer）、五层记忆快照。
2. `docs/autonomous-sandbox-architecture.md` 定稿（把本文档 §2 的修正合并回设计文档）。
3. 一次性回归：`pytest tests -q` 全绿 + 新增 `tests/test_autonomous_sandbox.py`。

**总工期估算 9~10 个工作日**（单人、按现有代码风格）。

---

## 七、待机主拍板的取舍（会改变实现范围）

| # | 取舍 | 方案 A | 方案 B | 建议 |
| --- | --- | --- | --- | --- |
| T1 | Phase 3 能否直接往群里发消息/文件 | 允许（`send_qq_file`/`poke` 直接生效） | `SilentSender` 记录，回归群聊后才发 | **B**：半夜静默期突然往群里甩文件风险高；回归后由 Phase 4 自然分享 |
| T2 | 触发目标群 | 固定 `TARGET_GROUPS[0]` | `cfg.autonomous.target_groups` 可配多群，按静默最久的那个 | **B**（默认仍单群，行为可预期） |
| T3 | v1 是否含 phone/art 嵌套聚焦 | 含（+1 天，需 adapter 与 adb 互斥） | 先在工坊里只给 `bash`/`art_draw` 平铺，不下沉聚焦 | **B 起步，A 放 P4** |
| T4 | Phase 1 讨论上下文膨胀 | 全量 32 轮历史（token 爆炸，32 轮可达 ~120k） | 每 8 步压成"锚点卡"（保留日记引用、结论、待办），只留最近 6 步原文 | **B，必做** |

---

## 八、风险与对策

| 风险 | 触发场景 | 对策 |
| --- | --- | --- |
| 内心独白误发群 | 复用 `engine_reply` 或误注册沙盒工具 | 沙盒独立循环 + `SilentSender` + `/深思` 联调时群里零消息断言 |
| Token 费用失控 | 32 轮 + 60 步工具 | `debate_max_tokens=600`、8 步压缩、`daily_max_runs=3`、`step_timeout` |
| 与群聊抢 adb / 抢工具资源 | 沙盒与真实群聊并发 | 中断抢占 + phone 类重工具全局锁（P4） |
| Chroma 写入被并发破坏 | 日记写入与日常写日记并发 | 只用 `MemoryRAG.save_diary`（线程安全 + 24h 去重），不直接碰 sqlite |
| 人格漂移 | 长工具链稀释人设 | Phase 2/3 prompt 只读复用 `get_base_setting()`，剥 `<layout>`/`[MEME]`；禁改 `core/prompts.py` 人格正文 |
| 重启丢状态 | 容器重建（本项目高频操作） | 每阶段至少落一次 checkpoint；启动时 `sweep_stale_runs()` 把 `active` 却无对应内存 run 的会话改 `paused` |
| 模型把 `work_finish` 参数写超长 | 512 字限制 + 长 work_log | `ToolCallManager` 已有 `finish_reason=length` 提示；`work_finish` 再做一次截断兜底 |
| 测试无法离线 | RAG / chromadb 需要模型 | 沙盒模块构造函数注入 `rag`/`llm`/`sampler`，测试用 fake；`storage` 全走 tmp_path |

---

## 九、测试清单（`tests/test_autonomous_sandbox.py`，全离线）

1. `test_do_nothing_exit_leaves_no_trace`：A/B 连续 do_nothing → 无文件、无 L1 写入、无 high_spirits。
2. `test_vote_requires_two_consecutive_agree`：单边 agree 后对方 `agree_to_end=False` → 计数清零。
3. `test_debate_round_cap_and_consensus_from_last_6`：32 轮未收敛 → consensus_note 取最后 6 步。
4. `test_context_compression_every_8_steps`：第 24 步时消息数 <= 压缩阈值。
5. `test_zero_tool_retry_then_fuse`：连续 2 轮零工具 → 生成 `paused` 兜底日志并退出。
6. `test_workshop_60_call_cap_trims_tools_to_finish`：第 60 步 tools == {work_finish}。
7. `test_work_log_512_truncation`。
8. `test_session_resume_reads_512_log`：`inspect_work_session` 只返回 work_log。
9. `test_notebook_zone_backward_compat`：旧 `{"content": ...}` 能读成 daily。
10. `test_daily_work_memory_ttl_and_archive`：TTL 过期不注入；04:00 后归档。
11. `test_no_autonomous_key_in_chat_history`：跑完整流程后断言历史文件无虚拟 chat_id。
12. `test_maid_report_routed_to_coordinator`：`main_process("autonomous:1", ...)` 不进 pipeline。
