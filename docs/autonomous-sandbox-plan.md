# 自主沙盒（Autonomous Sandbox v1）可行性评估与开发规划

> 上游设计基准：`docs/Autonomous Sandbox.md`（保留为愿景与 prompt 素材来源）
> 本文档是**施工用**规划：能不能做、按什么范式做、动哪些文件、哪些口径必须修正。
> **v3（2026-11-15）**：范式改为**模式化多主循环**（机主提议），已并入三条决策：
> 唯一体性（全局单活跃非聊天模式）、群聊隔离 + 日记群归属检索、`/强制放行` 逃生阀。

**结论：可以实现。** 现有 `SessionPipeline` 作为 `chat` 模式原样保留，
新模式以「子类覆写入口 + 独立主循环」接入，`engine_reply.py` 热路径零改动。预计 11~12 人日。

---

## 一、可行性结论

### 1.1 关键事实：入站只有一个收口，所以模式可以做成路由

`enqueue_message` 是全项目唯一的外部入站入口，调用方只有四处：
`modules/QQNapcatListen/listen_main.py`、`modules/github_monitor/monitor.py`、
`core/reply_watch.py`（经 `main_process`）、`_archive/LiveYukiL2D/server.py`；
`main.py::main_process` 与 `tests/test_pipeline.py` 也走它。

因此模式化不需要动任何上层业务：**让 `SessionPipeline` 的一个子类在 `enqueue_message` 开头做路由**，
`chat` 模式原样 `super()`，非聊天模式把消息缓存起来或投给运行中的主循环即可。

### 1.2 可以直接复用的底座（已核实到函数级）

| 能力 | 位置 | 复用方式 |
| --- | --- | --- |
| 生物钟 / 精力 / 活跃度 | `core/brain.py` `YukiState.{update_energy,get_smooth_time_weight,group_activity,last_message_time}` | 触发判定，零改动 |
| 冷场巡检循环 | `core/engine/engine_monitor.py::idle_diary_checker`（30s） | 循环体里挂 `autonomous_trigger_check()` |
| 工具声明/执行/容错 | `core/toolchain.py` `ToolSpec` / `FunctionRegistry` / `ToolCallManager` | 辩论/工坊自建 registry，`max_rounds` 按模式给 |
| 文本形式工具调用还原 | `core/tool_markup.py::extract_text_tool_calls` | 新循环照抄 `engine_reply._extract_calls` |
| 日记只读检索 | `core/maid/maid_tools.py::search_diary_fast`（`where_document`，不加载 embedding 模型） | 改造为带群归属（§5） |
| 日记追加写入 | `modules/memory/rag.py::save_diary` → `save_memory` | 只追加，`extra_metadata.type="autonomous_memo"` |
| 群名获取 | `network/napcat.py::get_group_meta` | 缓存 `data/group_names.json` |
| 等回音追击 | `core/reply_watch.py` `subscribe/_dispatch` | Phase 4 被动多轮（需可选超时下限） |
| LLM 主备/重试 | `utils/llm_client.py::llm_chat_raw(**tools)` | 沙盒唯一 LLM 出口 |
| 聚焦域 | `core/focus/*`（phone / art） | 作为**模式内子态**复用，`FocusManager` 不改 |

### 1.3 新建：模式层 + 沙盒层

```text
core/modes/                     # 模式层（新范式的地基，与自主沙盒解耦，未来可加新模怷）
├── __init__.py
├── base.py                     # ModeCapabilities + Mode 抽象基类（run / on_input / on_exit）
├── router.py                   # ModeRouter：每群 current_mode + 全局单活跃非聊天模式 + 冻结/补台队列
└── pipeline.py                 # ModeAwarePipeline(SessionPipeline)：覆写 enqueue_message 做路由

modules/autonomous/             # 自主沙盒（依赖模式层，不反向依赖）
├── __init__.py
├── coordinator.py              # AutonomousCoordinator：chat→debate→workshop→chat 的调度与配额
├── sandbox_loop.py             # SandboxLoop：独立 LLM 工具循环 + SilentSender + AdaptorHistory
├── inner_debate.py             # debate 模式主循环（≤32 轮、双向投票、三段式压力、上下文压缩）
├── workshop.py                 # workshop 模式主循环（≤60 步、零工具追问、熔断）
├── catchup.py                  # 回群补台摘要生成与注入
├── prompts.py                  # 各模式 system prompt（只读复用 get_base_setting，剥 layout/MEME）
├── storage.py                  # L1~L5 落盘 + 日记采样 + 小本本双区 + 群名缓存
└── tools.py                    # inner_vote / conclude_reflection / *_work_session / work_finish
```

`engine_reply.py` 不能直接跑非聊天模式：它硬绑 `self.history`（真实会话 + `replace_session` 覆写）
与 `self.sender`（`send_tool_thought` 会把阶段性文本实时发群）。所以 debate/workshop 各有自己的瘦循环。

---

## 二、设计文档与代码事实的 7 处偏差（修正口径）

### 2.1 `ToolView` 不读 `ToolContext.metadata`

`core/focus/view.py::ToolView.resolve(registry, manager, chat_id)` 只吃 `registry.list_functions()`
与 `focus_manager.active(chat_id)`；且默认视图保留 `entry_tool`。
修正：**沙盒工具不注册进主 registry**，沙盒自建 registry 并自算视图：

```python
visible = (set(main_registry.list_functions()) - AUTONOMY_HIDDEN - AUTONOMY_DOMAIN_TOOLS) | AUTONOMY_TOOLS
```

`work_finish` 恒在集合内，子聚焦无法屏蔽；`core/focus/domain.py` 不需要改。

### 2.2 `reply_watch.MIN_TIMEOUT_SECONDS = 30`

`core/reply_watch.py:20,74` 把 timeout 夹到 ≥30s，做不出 10~15s 窗口。
修正：`subscribe/auto_subscribe` 加可选 `min_timeout_seconds`，仅高涨路径传 `10.0`，默认不变。

### 2.3 `chat_id` 恒为真实群号（不需要虚拟 chat_id 了）

`search_group_snapshots` / `capture_group_snapshot` / `send_qq_file` / `poke` / `delegate_to_maid`
全部读 `context.chat_id`。模式化后这一点反而变简单：

1. `ToolContext.chat_id = target_group_id`（工具语义天然正确，零包装）；
2. 隔离由**模式能力**承担：`can_send=False` → `runtime.sender = SilentSender`；
   `writes_chat_history=False` → 模式循环只写自己的内存流；
3. `delegate_to_maid` 也不需要改写目标：任务仍挂真实群号，`maid_worker` 汇报时
   `process_callback(chat_id, ...)` → 模式路由发现该群正在 workshop 模式 →
   **作为内部事件投递给运行中的主循环**（不再是"入 buffer"），既不丢也不发群。

> 遗留说明：`maid_worker` 会先 `history_manager.append_session_message(chat_id, "user", report, is_maid_report=True)`
> 把汇报写进群历史（在 `core/maid/maid_worker.py:31`）。这是既有行为，v1 接受：
> 该条带 `is_maid_report` 标记，补台摘要与日记总结按标记特殊处理即可，不改 worker。

### 2.4 `FocusManager.exit()` 依赖 `history.get_session/replace_session`

子聚焦（phone/art，T3 已定允许）退出时会去真实 `HistoryManager` 查键并覆写群历史。
修正：模式循环给一个 20 行 `AdaptorHistory`（`get_session`/`replace_session` 只读写模式内存流），
`focus_manager.exit(history=adaptor)`；模式结束一律 `focus_manager.abort(chat_id)` 兜底，
避免残留的 focus 状态影响 chat 模式的 `finalize_conversation` / `idle_diary_checker`。
另：phone 类重工具加全局 `asyncio.Lock`（模式锁只保证"没有第二个 Yuki"，防不住残留协程抢 adb）。

### 2.5 基线测试已经是红的

`docker exec yuki python -m pytest tests -q` 现状 **5 failed / 153 passed**（断言漂移：
`BASE_KEEP_TOOLS` 后来加了 `search_diary`、registry 新增 `art_*`）。
P0 只改断言修绿，否则新模式"测试全绿"没有意义。

### 2.6 Phase 1 的"翻群聊截屏"靠 `context.chat_id`

`search_group_snapshots` 入参只有 `keyword`/`limit`，群号取 `context.chat_id`。按 §2.3 填真实群号即可，
prompt 里点明"你在 `<群名>` 的独处空间"。

### 2.7 日记本来就有 `chat_id`，但检索完全不用它

`save_diary(content, chat_id=...)` 写进 metadata 的 `chat_id` 一直在库里（`rag.py:105-107`），
但 `search_diary_fast` / `search_diaries` 都没有群过滤，返回文本也不带群归属。
改造方案见 §5。

---

## 三、范式：模式化多主循环

### 3.1 三种模式

| 模式 | 主循环实现 | 能发消息 | 写 `chat_history.json` | 接受真人入站 | 允许子聚焦 | 触发日记总结 |
| --- | --- | --- | --- | --- | --- | --- |
| `chat` | 现有 `SessionPipeline.run_once`（8 阶段）+ `EngineReplyService.chat_with_tools` | 是 | 是 | 是（现有防抖/潜水决策） | 是 | 是 |
| `debate` | `inner_debate.run()` | 否 | 否 | 否 → 入缓冲 | 否 | 否 |
| `workshop` | `workshop.run()` | 否（T1） | 否 | 否 → 入缓冲/内部事件 | 是（phone / art） | 否 |

`focus`（phone/art）不是模式，仍是**模式内子态**：`chat` 与 `workshop` 都能进，`debate` 不能。
这样"聚焦模式"那套已验证的范式完全不用动。

### 3.2 两条硬规则

1. **每群同一时刻只有一种模式**：`ModeRouter._states[chat_id] = ModeState(mode, run_id, started_at)`。
2. **全局同一时刻只有一个非聊天模式**（唯一体性）：`ModeRouter._global_run` 互斥。
   别的群若在此期间收到消息 → 入缓冲、冻结、不回复；等本次 run 结束，按群各补一条补台摘要。

```text
模式流转（全局守卫：_global_run 只能被一个 chat 持有）

chat ──(/深思 或 冷场触发)──► debate ──(投票 start_work)──► workshop ──(work_finish)──► chat
  ▲                              │                           │
  │                              ├─(do_nothing)──────────────┤
  └──────────────────────────────┴─(abandon / 超时 / 熔断 / /强制放行)┘
                                  ↓ 每次回到 chat 都执行「补台」（§4）
```

### 3.3 实现点（三处，别扩散）

| 位置 | 改动 |
| --- | --- |
| `core/modes/pipeline.py` `ModeAwarePipeline.enqueue_message` | `router.route(chat_id, mode, message_obj, **kw)`：该群非 chat 模式 → 交模式；全局被别的 chat 占用 → 入 `yuki.message_buffer` 并标 `frozen_reason`；否则 `await super().enqueue_message(...)` |
| `core/modes/router.py::ModeRouter` | `enter/exit/force_release`、`_global_run` 互斥、冻结群登记、`deliver_inner_event()`（小女仆汇报 / 定时注入） |
| `main.py` | 用 `ModeAwarePipeline` 替换 `SessionPipeline` 实例化（`main_process` 一行不改，因为它只调 `enqueue_message`） |

`SessionPipeline` 本体只加两处**极小钩子**：`enqueue_message` 里识别 `is_catchup` 标记
（不计入"真人到达"、不触发 `reply_watch.resolve`）；`prepare_message_batch` 里把
`frozen` 期间的缓冲原样交给补台（`is_catchup` 事件不会被潜水决策拦掉，走 `force_reply`）。

### 3.4 `chat` 模式零行为变化的证明方式

`ModeAwarePipeline` 在 `router` 全空（无任何非 chat 模式、无冻结）时，`route()` 必须返回
`super().enqueue_message(...)`，且不建任何额外 task。
测试断言：`tests/test_pipeline.py` / `test_toolchain.py` / `test_vision.py` 全绿，
外加一条 `test_mode_router_noop_passthrough`（router 空 → 调用序列与父类一致）。

### 3.5 群级准入：默认一个群都不开

自主轮是"侵入性"能力（会让那个群短暂停摆），所以采用**白名单 + 默认全关**：

1. `autonomous.enabled: false`（总开关，默认关）；
2. `autonomous.enabled_groups: []`（默认空 → 没有任何群允许）；
3. 单群判定 `AutonomousCoordinator.is_group_enabled(gid)`，是**唯一**准入函数，
   同时被 `autonomous_trigger_check()`（自动）与 `/深思`（手动）调用：
   ```
   enabled and gid in enabled_groups（含运行时覆盖）
   ```
4. 运行时覆盖：`/自主轮 开|关`（master，群聊内）写 `data/autonomous_state.json`
   的 `group_overrides: {gid: true|false}`，**优先级高于配置**，重启后仍生效；
   `/工坊状态` 会显示本群当前是"已开启/未开启（来源：配置/运行时）"。
5. 未开启的群里执行 `/深思` → 回复"这个群没开自主轮哦，要用的话先 `/自主轮 开`"，
   不进入任何模式。
6. 自动触发时的候选群：白名单内按「静默最久 → 精力最高」排序取第一个；
   全局单活跃规则不变（同时只跑一个群）。
7. 白名单与 `cfg.TARGET_GROUPS` 的关系：必须同时属于 `TARGET_GROUPS`（不在目标群里的群本来就没人应），
   取交集。

> 这条同时把 T2（触发目标群）定死了：**不再有"默认主群"**，候选完全来自白名单。

## 四、回群补台（Catch-up）

### 4.1 冻结期间的消息

冻结仍发生在 `yuki.message_buffer[chat_id]`（`SessionPipeline.enqueue_message` 第 1 步照旧写入），
所以顺序、发送人、`last_message_time` 全部保留，无需额外数据库。

### 4.2 摘要生成（按量自动切）

| 缺席消息量 | 处理 |
| --- | --- |
| ≤ 12 条 | **代码直拼**（零 LLM）：`【你独处期间群里发生了什么】14:02 月白: … / 14:05 阿岚: …` |
| > 12 条 | **第三方 LLM 压成 ≤200 字**（`autonomous.digest_model` 空则用主模型，temperature 0.3；prompt 只要求客观列话题与人名，禁止角色扮演）；失败回落直拼（截断最近 20 条） |

超过 `autonomous.catchup_max_messages`（默认 80）只保留最近 80 条并标注"更早的省略"。

### 4.3 注入形态

```python
history.append_session_message(
    cid, "user",
    "【你刚才在独处，这会儿回到群里了】\n" + digest +
    "\n（这些是你不在的时候发生的事，可以自然接话，也可以只挑一句感兴趣的问。）",
    is_catchup=True,
)
process_callback(cid, "group", debounce_flag=False, force_reply=True)
```

- 只对"冻结期间真的有新消息"的群注入；一直安静的群不打扰。
- `is_catchup` 让 `history_filter.dialogue_length`、`reply_watch.is_human_incoming`、
  `engine_diary` 都按"系统补台"处理，不误判成群友发言。

---

## 五、群聊隔离与日记群归属检索（v1 必做）

### 5.1 结论：保持群聊隔离，不做一体化

日记共享但必须可归因：检索默认"本群为主、他群为辅"，并显式告诉模型来源。

### 5.2 检索改造（软比例）

新增统一入口 `DiarySearch.query(query, chat_id, n)`：

1. **打标**：每条结果前缀 `[本群]` / `[群:月白の小窝]` / `[早期·未标群]`（旧日记无 `chat_id`）。
2. **软比例**：本群占 `ceil(n * autonomous.diary_local_ratio)`（默认 0.7），余量给他群；
   本群名额不满顺延给他群。
3. **降级话术**（代码在返回文本前生成，保证模型一定看见）：
   - 本群 0 命中、他群有 → 末尾追加 `（本群没有相关记录，下面是你在其他群里留下的回忆。）`
   - 全部 0 → 直接返回 `没有相关记录。`
4. **群名**：`data/group_names.json` 惰性缓存，来源 `NapCatGateway.get_group_meta`，
   取不到显示 `群 1057020972`。
5. **Phase 1 冷启动采样**：同上规则 —— 2 条近 7 天本群日记 + 1 条 30 天以上任意群旧日记（标注来源群）。

### 5.3 影响面

`core/maid/maid_tools.py::search_diary_fast`（加 `chat_id`/`local_ratio`）、
`modules/memory/rag.py::search_diaries`（加 `chat_id_priority`，只调排序与名额）、
`core/tools/tools_diary.py::search_diary_tool`（传 `context.chat_id`）。
**不改** 已有 6485 篇日记内容，只做只读归因与展示层标注。

---

## 六、五层记忆 schema

```python
# L3 data/work_sessions/<session_id>.json
{
  "session_id":"sess_20261115_01","created_at":...,"updated_at":...,
  "status":"active",                 # active | paused | completed | abandoned
  "title":"雪夜电台","kind":"creative",   # creative | code | life | misc
  "work_log":"≤512 字",               # 干了什么 / 产物路径 / 下次从哪接
  "artifacts":["workspace/novels/snow_radio_ch1.md"],
  "chat_id":"1057020972","memo_ref":"mem_autonomous_memo_...",
  "runs":["sess_20261115_01","sess_20261116_01"],
}
# L3 data/work_sessions/index.jsonl  {"session_id","title","status","updated_at","log_head":80}

# L2 data/work_diary.jsonl
{"ts":...,"session_id":"...","title":"...","kind":"insight","content":"150~400 字"}

# L4 data/daily_work_memory.json（text 由 entries 代码渲染；04:00 归档到 daily_work_memory_archive/<date>.json）
{"date":"2026-11-15","archived_at":null,"updated_at":...,"text":"≤1000 字","entries":[...]}

# L5 data/notebook.json（向后兼容旧格式）
{"version":2,"daily":"≤350 字","plans":"≤160 字","content":"<旧字段，读取时回落为 daily>"}
```

L1 前缀 `【自主随想(YYYY-MM-DD)】` / `【工作记录(YYYY-MM-DD)】`，
`extra_metadata={"type":"autonomous_memo","session_id":...,"kind":...,"chat_id":...}`。

---

## 七、配置项（`config.py` 新增 `AutonomousConfig`，`section="autonomous"`）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `false` | 全局总开关，**默认关**；关时 `/深思` 直接拒绝 |
| `enabled_groups` | `[]` | **允许自主轮的群白名单，默认空 = 一个都不开**。只有列在这里的群才可能触发或接受 `/深思` |
| `auto_trigger_enabled` | `false` | 冷场自动触发（P6 才开）；只对白名单群生效 |
| `min_group_idle_minutes` | `45` | 静默阈值 |
| `min_energy` | `0.60` | 精力下限 |
| `quiet_hours` | `[1, 7]` | 深夜禁触发 |
| `cooldown_minutes` | `120` | 两次自动轮次最小间隔 |
| `daily_max_runs` | `3` | 日配额（持久化，重启不清零） |
| `max_wall_seconds` | `900` | 非聊天模式单次最长占用（超时强制暂停 + 全面放行） |
| `debate_max_rounds` | `32` | debate 上限 |
| `debate_max_tokens` | `600` | 每步输出上限 |
| `debate_compress_every` | `8` | 每 8 步压成锚点卡 |
| `workshop_max_tool_calls` | `60` | workshop 上限 |
| `zero_tool_max_retries` | `2` | 零工具追问容忍 |
| `step_timeout_seconds` | `180` | 单步（LLM + 该批工具）超时熔断 |
| `catchup_enabled` | `true` | 回群补台 |
| `catchup_max_messages` | `80` | 补台最多纳入消息数 |
| `catchup_summarize_threshold` | `12` | 超过则 sub-LLM 摘要 |
| `digest_model` | `""` | 补台摘要模型，空=主模型 |
| `diary_local_ratio` | `0.7` | 日记检索本群占比 |
| `daily_memory_ttl_hours` | `18` | L4 有效期 |
| `high_spirits_turns` | `3` | 回归后连发配额 |
| `high_spirits_minutes` | `25` | 高涨持续 |
| `high_spirits_desire_bonus` | `0.45` | 欲望加成 |
| `high_spirits_followup_window` | `12` | 被动窗口秒数（<30，走 §2.2） |

---

## 八、涉及文件清单（施工时逐项打勾）

### 8.1 新增文件

| 路径 | 作用 | 阶段 |
| --- | --- | --- |
| `core/modes/__init__.py` | 导出 `ModeRouter` / `ModeAwarePipeline` / `ModeCapabilities` | P1 |
| `core/modes/base.py` | `ModeCapabilities` 数据类 + `Mode` 基类（`run()` / `on_input()` / `on_inner_event()` / `on_exit()`） | P1 |
| `core/modes/router.py` | 每群 `ModeState`、`_global_run` 互斥、冻结登记、内部事件投递、`force_release()` | P1 |
| `core/modes/pipeline.py` | `ModeAwarePipeline(SessionPipeline)`：覆写 `enqueue_message` | P1 |
| `modules/autonomous/__init__.py` | 导出 `AutonomousCoordinator` 单例 | P2 |
| `modules/autonomous/sandbox_loop.py` | `SandboxLoop`（LLM 循环）+ `SilentSender` + `AdaptorHistory` + 视图计算 | P2 |
| `modules/autonomous/prompts.py` | 五个阶段 system prompt 组装 | P2 |
| `modules/autonomous/inner_debate.py` | debate 主循环（含投票、压力调度、压缩） | P2 |
| `modules/autonomous/tools.py` | `inner_vote` / `conclude_reflection` / `list_recent_work_sessions` / `inspect_work_session` / `write_work_diary` / `work_finish` | P2–P4 |
| `modules/autonomous/storage.py` | L2~L5 读写、日记采样、`group_names` 缓存、旧 notebook 迁移 | P0 |
| `modules/autonomous/workshop.py` | workshop 主循环与熔断 | P4 |
| `modules/autonomous/catchup.py` | 补台摘要与注入 | P6 |
| `modules/autonomous/coordinator.py` | 模式流转调度、配额、冷却、`sweep_stale_runs` | P2 |
| `tests/test_mode_router.py` | 路由/冻结/全局互斥/内部事件 | P1 |
| `tests/test_autonomous_sandbox.py` | 15 项离线测试（§12） | 随阶段 |
| `data/autonomous_state.json` | 日配额、冷却、`active_mode` 软标记、`group_overrides`（运行时群开关） | P0 |
| `data/work_diary.jsonl` | L2 | P3 |
| `data/work_sessions/{index.jsonl,<sid>.json}` | L3 | P3 |
| `data/daily_work_memory.json` + `daily_work_memory_archive/` | L4 | P3 |
| `data/group_names.json` | 群号→群名缓存 | P3 |

### 8.2 改动文件

| 文件 | 位置 | 改动 | 体量 |
| --- | --- | --- | --- |
| `config.py` | `ToolsConfig`（468 行）后新增 `AutonomousConfig`；`Config`（718 行）挂字段；底部 `SECTION_COMMENTS` 加 `autonomous` | 新配置节 | +80 行 |
| `configs/config.yaml` | 末尾 `autonomous:` 段 | 配置 | `config.py sync` 生成 |
| `main.py` | `session_pipeline = SessionPipeline(...)`（323 行）；`initialize_components`（30–72 行） | 换 `ModeAwarePipeline`；装配 coordinator 注入 components | +20 行 |
| `core/session_pipeline.py` | `enqueue_message`（202–266 行）、`prepare_message_batch`（317–360 行） | 识别 `is_catchup` / `is_maid_report`：不算真人到达、不被潜水决策拦、不计轮次 | +12 行 |
| `core/brain.py` | `YukiState.__init__`（76–101 行） | `high_spirits_until` / `high_spirits_remaining_turns` / `mark_high_spirits()` / `high_spirits_active()` / `consume_high_spirits_turn()` | +30 行 |
| `core/notebook.py` | 全文（53 行） | `load_zone/save_zone`、`daily`+`plans` 双区、旧 `content` 回落 | +40 行 |
| `core/prompts.py` | `build_chat_context`：日记段（192–197）、小本本段（205–215） | 小本本双区渲染、L4 今日工作记忆槽位、`high_spirits` 引导槽位 | +35 行 |
| `core/reply_watch.py` | `subscribe`（67 行）、`auto_subscribe`（215 行） | 可选 `min_timeout_seconds`（默认 30 不变） | +8 行 |
| `core/engine/engine_monitor.py` | `idle_diary_checker`（25–56 行） | 挂 `autonomous_trigger_check()`；非 chat 模式/冻结期间跳过日记总结与破冰 | +12 行 |
| `core/engine/engine_decision.py` | `decide_to_reply`（64–104 行） | `high_spirits` 欲望 `+bonus`，并跳过 `energy < MIN_ACTIVE` 拒绝分支（留 0.15 底线） | +12 行 |
| `modules/QQNapcatListen/listen_main.py` | `handle_group_switch`（335–378 行）、`handle_private_command`（381 行）、`start_background_tasks`（40–80 行） | 新增 `/深思`、`/工坊状态`、`/强制放行`、`/自主轮 开\|关`（master 限定，沿用现有 set + 文案风格）；启动 `sweep_stale_runs()` | +60 行 |
| `core/tools/tools_diary.py` | `search_diary_tool`（11–20 行） | 传 `context.chat_id`，走群归属检索，带 `[本群]` 前缀与降级话术 | +15 行 |
| `core/maid/maid_tools.py` | `search_diary_fast`（7–80 行） | `chat_id`/`local_ratio` 参数、软比例、群名标注、三段降级话术 | +50 行 |
| `modules/memory/rag.py` | `search_diaries`（225–347 行） | `chat_id_priority` 参数（只调排序与名额） | +30 行 |
| `core/tools/tools_notebook.py` + `core/tools/tools.py` | `update_notebook_tool`、`update_notebook` spec（239–254 行） | 可选 `zone`（`daily`/`plans`，默认 `daily`） | +15 行 |
| `modules/debug/webui_server.py` | 新增 `/api/autonomous` | 模式/阶段/轮次/token/A-B 对话流/五层记忆快照 | P7 |
| `tests/*`（5 个漂移文件） | 断言 | 只改断言不改实现 | P0 |

### 8.3 只读参考、**明确不改**

| 文件 | 为什么只读 |
| --- | --- |
| `core/engine/engine_reply.py` | chat 模式热路径，新循环不复用 |
| `core/toolchain.py` / `core/tool_markup.py` / `utils/llm_client.py` | 直接调用 |
| `core/focus/*` | 子聚焦原样复用；`work_finish` 由沙盒自算视图保证 |
| `core/history_manager.py` | 群历史不改；模式内存流通过 `AdaptorHistory` 接入 |
| `core/maid/maid_worker.py` | 汇报由路由器投递为内部事件，不改 worker |
| `core/phone_driver.py` / `phone_agent.py` / `phone_macro.py` | 子聚焦直接复用，只在外层加互斥锁 |
| `core/prompts.py` 人格正文（1–171 行） | 自进化准则第 1 条硬禁区 |
| `yuki_memory/chroma.sqlite3` | 只追加写入，不改表结构、不清理 |

---

## 九、分阶段实施计划

### P0 地基与基线修复（0.5 天）
`AutonomousConfig` + yaml 生成；修 5 个漂移测试；`storage.py` 骨架与 `data/` 初始化。
**验收**：`pytest tests -q` → 0 failed；`cfg.autonomous.enabled is False`。

### P1 模式层（1 天，chat 模式零行为变化）
`core/modes/`（base/router/pipeline）；`main.py` 换 `ModeAwarePipeline`。
**验收**：既有 `test_pipeline` / `test_toolchain` / `test_vision` / `test_napcat` 全绿；
`test_mode_router_noop_passthrough` 证明 router 空时调用序列与父类一致；
手写一个 `EchoMode` 假模式验证"该群进入假模式后入站被缓冲、其他群被冻结、退出后补台"。

### P2 沙盒内核：debate 模式 + `/深思`（2.5 天）
`SandboxLoop` / `SilentSender` / `AdaptorHistory` / `inner_debate` / `prompts` / `coordinator`；
`/深思` 跑完把交锋摘要 + 备忘录 `send_master_private` 给机主；`/强制放行` 打通。
**验收**（连续 5 次 `/深思`）：a) ≥3 次调用 `search_diary` 且带 `[本群]`；
b) ≥1 次 `do_nothing` 出口且 `data/` 无新文件；c) 辩论期间在群里发消息 → 零回复、消息进缓冲；
d) 32 轮内收敛；e) `data/chat_history.json` 无任何 debate 记录；f) `/强制放行` 5 秒内回 chat 模式。

### P3 日记群归属检索 + 五层记忆（2 天）
§5 检索改造；notebook 双区；`conclude_reflection` 三向流转；L1–L5 写入；群名缓存。
**验收**：`memo_only` 后 `search_diary` 命中自己的备忘录并带群标；`/工坊状态` 列出 active/paused
与 512 字日志尾；跨群检索出现"本群没有相关记录"。

### P4 workshop 模式（2 天）
60 步上限 / 55 步提醒 / ≥60 步只剩 `work_finish` / 零工具追问（≤2）/ 熔断兜底 / `step_timeout`；
`work_finish` 512 字软校验；小女仆委托与汇报回流。
**验收**：两次 `/深思` 接续同一小说 → 第二次 `inspect_work_session` 返回 512 字日志、第三次续写第二章；
maid 汇报在 workshop 内被读入而非发群。

### P5 子聚焦嵌套（1 天）
`AdaptorHistory` 接 `focus_manager.exit`；工具视图强制并入 `work_finish`；phone 类全局锁；
模式退出 `focus_manager.abort()` 兜底。
**验收**：workshop 内 `phone_start` → 两步 → `phone_finish` → 继续；全程群里零消息、chat_history 零记录。

### P6 补台 + 冷场反哺 + 自动触发（2 天）
`catchup.py`；`high_spirits` 三件套（brain / decision / reply_watch 窗口）；回归瞬间触发一次破冰；
`autonomous_trigger_check`（静默/精力/深夜/冷却/日配额持久化）；`sweep_stale_runs`。
**验收**：a) `enabled_groups` 为空时，任何冷场都不触发、`/深思` 被拒；
b) 只把 A 群加入白名单并把 `min_group_idle_minutes` 调成 2 分钟 → 只有 A 群触发，B 群冷场不触发；
c) `/自主轮 关` 后 A 群不再触发且重启后仍为关（运行时覆盖生效）；
d) 自动进 debate → 回群补台落地 → 1~3 条分享语气消息后自停；一天不超 3 次；重启配额不清零；深夜不触发。

### P7 观测与收尾（1 天）
WebUI `/api/autonomous`；把 §2 的 7 处修正合并回 `docs/autonomous-sandbox-architecture.md`；全量回归。

**总工期 11~12 人日。**

---

## 十、已定/待定取舍

| # | 取舍 | 结论 |
| --- | --- | --- |
| T1 | 沙盒内能否直接发群消息 | **已定：不发**（`SilentSender`；产物路径进工作日志，回群后由 Phase 4 分享） |
| T2 | 触发目标群 | **已定：无默认主群**，候选完全来自 `autonomous.enabled_groups`，按「静默最久 → 精力最高」取第一个 |
| T3 | 子聚焦（phone/art） | **已定：允许**（配 `AdaptorHistory` + 重工具互斥锁） |
| T4 | debate 上下文压缩 | **已定：必做**（每 8 步压锚点卡，只留最近 6 步原文） |
| T5 | 补台摘要方式 | **已定：按量自动切**（≤12 条直拼，>12 条 sub-LLM，失败回落） |
| T6 | 冻结期间主人私聊 | 待定。推荐**也冻结**（唯一体性优先），主人用 `/深思` `/工坊状态` `/强制放行` 操作 |
| T7 | 每次 run 的落盘上限 | 待定。推荐：每次 run 最多 1 篇 L1 + 1 条 L2，防刷库 |
| T8 | 模式作用域 | **已定：全局单活跃**（同时只有 1 个群可处于非 chat 模式，其他群冻结） |
| T9 | 逃生阀 | **已定：加 `/强制放行`**（断点存 `paused`，立即全面放行 + 补台） |
| T10 | 群级准入 | **已定：白名单 + 默认全关**；`enabled=false` + `enabled_groups=[]`；运行时 `/自主轮 开\|关` 覆盖，优先级高于配置 |

---

## 十一、风险与对策

| 风险 | 对策 |
| --- | --- |
| 冻结太久（60 步工具可跑 10 分钟+） | `max_wall_seconds=900` 强制暂停放行；补台保证她"知道刚才发生了什么"；`/强制放行` |
| 模式层拖慢/改坏 chat 路径 | P1 单独验收：router 空 → 完全透传；子类不改父类任何一行逻辑 |
| 漏挡新入站路径 | 路由只在 `ModeAwarePipeline.enqueue_message` 一处；测试断言"冻结期 `sender.send` 零调用" |
| 内心独白误发群 | 非 chat 模式独立循环 + `SilentSender` + 联调断言群里零消息、chat_history 零记录 |
| 与群聊抢 adb | 模式锁挡群聊；phone 类全局锁兜残留协程 |
| Token 费用 | `debate_max_tokens=600`、8 步压缩、`daily_max_runs=3`、`step_timeout` |
| Chroma 并发写 | 只用 `MemoryRAG.save_diary`（线程安全 + 24h 去重） |
| 人格漂移 | 各模式 prompt 只读复用 `get_base_setting()`，剥 `<layout>`/`[MEME]`；禁改人格正文 |
| 重启丢状态 | 每阶段落 checkpoint；`sweep_stale_runs()` 把残留 active 改 `paused` 并放行 |
| 日记跨群串味 | §5 软比例 + 群标 + 三档降级话术，测试覆盖 |

---

## 十二、测试清单（全离线）

**`tests/test_mode_router.py`**
1. `test_noop_passthrough`：router 空 → 调用序列与父类一致。
2. `test_non_chat_mode_buffers_input`：该群处于 debate → 入 buffer、不建 task。
3. `test_global_single_active_run`：A 群 debate 时 B 群入站 → 冻结；A 结束 → B 收到补台。
4. `test_inner_event_delivery`：workshop 模式下 `is_maid_report` → 投主循环而非 buffer。
5. `test_force_release`：`/强制放行` → 模式退出、断点 paused、全部放行。

**`tests/test_autonomous_sandbox.py`**
6. `test_do_nothing_exit_leaves_no_trace`。
7. `test_vote_requires_two_consecutive_agree`。
8. `test_debate_round_cap_and_consensus_from_last_6`。
9. `test_context_compression_every_8_steps`。
10. `test_zero_tool_retry_then_fuse`。
11. `test_workshop_60_call_cap_trims_tools_to_finish`。
12. `test_work_log_512_truncation` + `test_session_resume_reads_512_log`。
13. `test_notebook_zone_backward_compat` + `test_daily_work_memory_ttl_and_archive`。
14. `test_no_debate_trace_in_chat_history`。
15. `test_catchup_digest_direct_vs_llm`（≤12 直拼、>12 走 sub-LLM、失败回落）。
16. `test_diary_search_group_ratio_and_fallback`（7:3、本群 0 命中、全空三档）。
17. `test_group_gate_whitelist`：白名单空 → 不触发且 `/深思` 拒绝；白名单含 A → 只 A 触发；
    `/自主轮 关` 的运行时覆盖优先于配置，且落盘后重启仍生效。

---

## 十三、实现落地记录（P0–P7 已完成）

> 本节记录 v1 落地时的**实际口径**，与上文规划如有差异以此为准。代码入口：`core/modes/`（模式层）、`modules/autonomous/`（沙盒）。

### 13.1 文件与职责

| 文件 | 落地内容 |
| --- | --- |
| `core/modes/base.py` | `ModeCapabilities`（can_send / writes_chat_history / accepts_human_input / allow_sub_focus / triggers_diary / accepts_inner_event）+ `Mode` 基类（`run` / `on_input` / `on_inner_event` / `request_stop`） |
| `core/modes/router.py` | 每群 `ModeState`、`_global_run` 唯一体性、`ROUTE_CHAT/MODE/FROZEN` 三态路由、冻结登记（`FrozenChat.messages`）、`deliver_inner_event`、`force_release`、`dispatch_catchups` |
| `core/modes/pipeline.py` | `ModeAwarePipeline`：`enqueue_message` 唯一路由点；router 空闲时原样 `super()`；非 chat 模式只入缓冲；内部事件（小女仆汇报，含"只写历史不传 message_obj"的情形）投主循环；`handle_catchup` |
| `modules/autonomous/sandbox_loop.py` | `SilentSender`（发送全部落 outbox，绝不触网）、`AdaptorHistory`（只读写内存流）、`SandboxLoop`（自算工具视图 `focus_view() | pinned`）、`SandboxDeps` |
| `modules/autonomous/inner_debate.py` | 双念头交锋：≤`debate_max_rounds`、连续两步 agree+verdict 一致才收敛、三段式压力旁白、每 `debate_compress_every` 步压锚点卡（sub-LLM 失败回落代码截断）、满轮 `undecided` 交本尊 |
| `modules/autonomous/workshop.py` | ≤`workshop_max_tool_calls`；提前 5 次在工具结果尾部附预算提醒；耗尽后 tools 只留 `work_finish`；零工具追问 ≤`zero_tool_max_retries` 后熔断并写 paused 兜底日志；小女仆汇报在每轮开头并入上下文 |
| `modules/autonomous/coordinator.py` | 群级准入门禁（白名单 ∩ TARGET_GROUPS，运行时覆盖优先）、debate→reflect→workshop→chat、墙钟上限、`sweep_stale_runs`、`auto_trigger_check`、回群补台/心情高涨/破冰 |
| `modules/autonomous/storage.py` | L1 memo（`MemoryRAG.save_memory(extra_metadata.type=autonomous_memo)`）、L2 `work_diary.jsonl`、L3 `work_sessions/`、L4 `daily_work_memory.json`、`autonomous_state.json`、`group_names.json`、`DiarySeedSampler` |
| `modules/autonomous/tools.py` | 6 个沙盒工具（`inner_vote` / `conclude_reflection` / `list_recent_work_sessions` / `inspect_work_session` / `write_work_diary` / `work_finish`），只注册在沙盒自建 registry |
| `modules/autonomous/catchup.py` | 冻结期消息 → 摘要（≤12 条直拼 / 更多 sub-LLM ≤200 字 / 失败回落最近 20 条）→ `is_catchup` 事件 |
| `modules/autonomous/inspect.py` | WebUI `/api/autonomous` 快照（模式/阶段、配额、五层记忆摘要） |

### 13.2 与规划不同的三处

1. **补台注入走缓冲区**，不是直接写 `chat_history` + `process_callback`：冻结期间的消息由 `catchup.py` 从 `yuki.message_buffer` 取出并生成一条 `is_catchup` 合成消息，再交给父类 `enqueue_message` 正常跑一次回复。好处是不用处理"历史里已有一份、缓冲区又有一份"的重复上下文。
2. **心情高涨的被动窗口复用 `reply_watch`**，但通过新增的 `min_timeout_seconds` + `event_builder` 注入自定义事件（`source=yuki.high_spirits`），而不是让 `reply_watch` 认识"高涨"概念。
3. **`high_spirits_until` / `high_spirits_remaining_turns` 按 chat_id 记账**（dict），不再是单标量——同一时刻可能有多个群，全局标量会互相踩。

### 13.3 现在能用的指令（主人限定）

| 指令 | 作用 |
| --- | --- |
| `/深思` | 在当前群手动进入一次自主轮（白名单未开时会被拒并提示 `/自主轮 开`） |
| `/自主轮 开` / `/自主轮 关` | 运行时开关（写 `data/autonomous_state.json` 的 `group_overrides`，优先级高于配置，重启后仍生效） |
| `/工坊状态` | 当前模式/阶段、暂停中的工作会话与 512 字日志头、今日配额、上次结束时间 |
| `/强制放行` | 逃生阀：请求当前模式尽快收尾，立刻恢复群聊 |

### 13.4 上线开关（默认全关）

```yaml
autonomous:
  enabled: false          # 总开关
  enabled_groups: []      # 白名单；空 = 一个群都不开
  auto_trigger_enabled: false
```

`/深思` 与自动触发共用同一个准入函数 `AutonomousCoordinator.is_group_enabled()`：

```
cfg.autonomous.enabled
  and gid ∈ TARGET_GROUPS（若配置了）
  and (运行时覆盖 or gid ∈ enabled_groups)
```

### 13.5 验证与残余风险

- 离线：`tests/test_mode_router.py`（11 项）+ `tests/test_autonomous_sandbox.py`（25 项），`docker exec yuki python -m pytest tests -q` → 223 passed。
- 校验门：`deploy/verify.sh` 5 门全绿（顺带把 `output/`、`temp_images/`、`workspace/` 改为 tmpfs，`output/assets` 只读挂载，修正两个原先依赖可写代码树的 art 测试）。
- 残余风险：真实模型下的"防吹捧"效果、`work_finish` 是否会稳定调用、phone 子聚焦在沙盒里的稳定性，需要连续跑几次 `/深思` 才能验证（P2/P4 验收里的 5 次人工验收项）。
