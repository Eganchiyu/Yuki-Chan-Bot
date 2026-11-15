# Yuki 自主轮架构（Autonomous Sandbox）现态说明

> 单一事实源：本文只描述**当前代码实际行为**（P0–P7 已落地）。历史愿景稿与施工规划已归档删除（git 历史可查）。
> 代码总量约 3.8k 行：`core/modes/`（模式层，553 行）+ `modules/autonomous/`（沙盒层，3.2k 行）。
> 默认全关：`autonomous.enabled=false`、`enabled_groups=[]`，只有被 `/自主轮 开` 的群才会用。

---

## 一、范式：模式化多主循环

每群同一时刻只有**一种模式**；`chat` 模式就是原来的 `SessionPipeline`，非聊天模式（`debate` / `workshop`）各有一套瘦主循环。

| 模式 | 主循环实现 | 能发群消息 | 写 `chat_history.json` | 收真人入站 | 允许子聚焦 | 触发日记总结 |
| --- | --- | --- | --- | --- | --- | --- |
| `chat` | `SessionPipeline.run_once`（8 阶段）+ `EngineReplyService` | 是 | 是 | 是 | 是 | 是 |
| `debate` | `modules/autonomous/inner_debate.py::InnerDebate.run` | 否 | 否 | 否（入缓冲） | 否 | 否 |
| `workshop` | `modules/autonomous/workshop.py::Workshop.run` | 否 | 否 | 否（入缓冲） | 是（phone / art） | 否 |

两条硬规则：

1. **每群同一时刻只有一种模式**：`ModeRouter._states[chat_id] = ModeState(mode, run_id, started_at, session_id, instance)`。
2. **全局同一时刻只有一个非聊天模式**（唯一体性）：`ModeRouter._global_run` 互斥；其它群此时收到消息只入 `yuki.message_buffer` 并登记「缺席」。

`focus`（phone / art）**不是模式**而是模式内子态：`chat` 与 `workshop` 都能进，`debate` 不能。

---

## 二、触发逻辑

### 2.1 三种触发途径

| 途径 | 入口 | 触发条件 |
| --- | --- | --- |
| 手动 | `listen_main.handle_autonomous_command` → `AutonomousCoordinator.start_run(trigger="manual")` | 主人在白名单群发 `/深思` |
| 冷场自动 | `engine_monitor.idle_diary_checker`（30s 一轮）→ `AutoTriggerCheck` | 见 §2.3 |
| 重启兜底 | `main.py` 启动时 `sweep_stale_runs()` | 上次进程留下 `active_mode` 残留 |

### 2.2 群级准入（唯一判定：`AutonomousCoordinator.is_group_enabled`）

优先级从高到低：

```
gid ∈ TARGET_GROUPS（若配置了，否则一律不许）
  > 运行时覆盖 data/autonomous_state.json:group_overrides[gid]
  > cfg.autonomous.enabled 且 gid ∈ cfg.autonomous.enabled_groups
```

- 运行时覆盖由 `/自主轮 开|关` 写入，**重启后仍生效**，且 `开` 能越过 `enabled=false`（主人当场的显式授权）。
- 自动触发还额外要求 `auto_trigger_enabled=true`。
- `gate_reason()` 是给 `/工坊状态` 与异常文案用的可读解释。

### 2.3 自动触发的全部前置条件（`auto_trigger_check`）

全部满足才触发：

1. `autonomous.enabled` 且 `auto_trigger_enabled`；
2. `router.is_idle()`（没有别的群在跑非聊天模式）；
3. 不在 `quiet_hours`（默认 `[1, 7]`，支持跨零点写法如 `[22, 6]`）；
4. 距 `last_run_at` 超过 `cooldown_minutes`（默认 120）；
5. 今日自动次数 < `daily_max_runs`（默认 3，持久化、重启不清零）；
6. 候选群（`enabled_group_ids()` = 白名单 ∩ `TARGET_GROUPS`，叠加运行时覆盖）里有满足下列条件的群：
   - 静默 ≥ `min_group_idle_minutes`（默认 45）；
   - 精力比例 ≥ `min_energy`（默认 0.6）；
7. 取候选里「静默最久 → 精力最高」的第一个。

触发后 `bump_auto_runs()` 记账，`start_run(trigger="auto", notify_master=False)`。

### 2.4 `start_run` 的即时拒绝

已在该群跑 / 全局被别的群占用 / 准入不通过 / 群处于休眠（`group_active_state[gid]=False`）——最后一条在指令层就拒，提示先 `/开启`。

---

## 三、代码运行逻辑（一次 run 的完整链路）

```
listen_main.handle_autonomous_command('/深思')
  └─ coordinator.start_run(gid)            # 只建 task，立刻回执
       └─ asyncio.create_task(_run(gid))
```

### 3.1 `_run` 主流程（`coordinator.py`）

```
_chat_label()            # group_name_cache 惰性拉群名（失败回落「群 <gid>」）
SandboxState(run_id)     # 运行期共享状态（投票/复盘/日志/产物）
transcript_for(state)    # logs/autonomous/<run_id>.jsonl
state_store.set_active_mode(gid, 'debate', run_id)
reply_watch.resolve(gid) # 独处期间不需要「等回音」追击

try:
  A. debate 阶段
     router.enter(gid,'debate',instance=DebateMode) → _run_mode(mode)
        └─ asyncio.wait_for(mode.run(), max_wall_seconds)
     router.exit(gid, run_id)

  B. 分支判定
     stopped ∈ {force,timeout,empty} → 记 last_error，静默收尾（session 标 paused）
     verdict == 'do_nothing'        → 零痕迹退出
     ── 否则进入复盘（不是模式，是 coordinator 内部步骤）

  C. reflection 阶段（state.phase='reflection'）
     _reflect()：单工具环 conclude_reflection，最多 3 次（零工具则追问）
     action == abandon / 没落盘 → 零痕迹退出
     ── 否则写 L1 备忘录 + L2 工作日记（若填了）+ 小本本 plans 区

  D. 分流
     action == memo_only → L4 今日工作记忆(status=随想) → 结束
     action == start_work
         _ensure_work_session()  # 继承 paused/active 会话，否则新建 sess_YYYYMMDD_NN
         router.enter(gid,'workshop') → _run_mode(WorkshopMode)
         router.exit
         L4 今日工作记忆(status=可续)

finally:
  router.exit() 兜底 + focus_manager.abort(gid) + state_store.clear_active_mode()
  _runs.pop(gid)
  transcript.finish(outcome)
  notify_master（仅 manual 且 summary 非空 → 私聊汇报）
  _after_run(episode=…)
```

### 3.2 `_after_run`

```
router.dispatch_catchups()        # 冻结期有新消息的群各补一次台
if not episode: return            # do_nothing / abandon / 中断：不拉高欲望、不破冰
yuki.mark_high_spirits(gid)       # 25 分钟高涨 + 3 轮连发配额
若该群缓冲区为空 → engine.process_callback(ice_break=True) 主动破冰
```

### 3.3 debate 主循环（`inner_debate.py`）

```
seeds = DiarySeedSampler.sample(chat_id)   # 2 条近 7 天本群 + 1 条 30 天前旧日记
for step in 1..debate_max_rounds:
    stop_check() ? break
    role = 'A' if step 奇数 else 'B'
    messages = [system: 共有底色 + 该念头附加引导,
                user:   日记契机 + 交锋记录/锚点 + 压力旁白 + 轮到谁]
    msg = llm_chat_raw(tools=只读接地工具+inner_vote, max_tokens=debate_max_tokens)
    calls = 原生 tool_calls 或 tool_markup 还原
    calls 非空 → execute(calls)（投票写进 SandboxState.votes）
    turns.append({role, content})
    SandboxState.consensus() ? → 收敛退出
    每 debate_compress_every 步 → 旧交锋压成锚点卡（sub-LLM；失败回落代码截断）
满轮 → verdict='undecided'，只把最近 6 轮交给复盘
```

- **收敛条件**：连续两步 `agree_to_end=True` **且** `verdict` 完全一致（`SandboxState.consensus()`）。
- **可见工具**：`search_diary`、`search_group_snapshots`、`list_recent_work_sessions`、`inspect_work_session`、`inner_vote`（只读接地 + 投票）。
- **三段式压力旁白**（纯代码，不花 token）：第 4 步未检索过→提醒去翻日记；第 11 步→推演落地细节；第 `max(23, 0.7*上限)` 步→催收敛。

### 3.4 reflection 步骤（`coordinator._reflect`）

- 单独 registry：只有 `conclude_reflection`；`AdaptorHistory` 承接内存历史。
- 输入：`reflection_system()`（本尊人格 + 三向指引）+ `reflection_user_block()`（交锋共识/最后 6 轮摘要 + 倾向）。
- 最多 3 次；模型不调工具就追加 `NUDGE_TEXT` 追问；仍未落盘 → 按 abandon 处理。

### 3.5 workshop 主循环（`workshop.py`）

```
resume_hint = 上次会话的 512 字日志（有就注入）
for step in 1..:
    stop_check() ? break
    _drain_inner_events()                  # 小女仆汇报并入上下文
    budget_left <= 0 ? visible={'work_finish'} : visible=focus_view()|pinned
    msg = llm_chat_raw(tools=visible, max_tokens=1200)
    calls 为空 → zero_streak+1；≤ zero_tool_max_retries 则追问，否则熔断
    calls 非空 → execute → 拼接结果 → 附加截图 → 预算提醒
    state.finished (work_finish 被调用) ? break
```

- **工具可见性**：`ToolView.resolve(registry, focus_manager, chat_id).visible | pinned`，`pinned = {inspect_work_session, list_recent_work_sessions, write_work_diary, work_finish}`；子聚焦（phone/art）期间 `work_finish` 仍在，绝不会被锁死。
- **预算**：`workshop_max_tool_calls`（默认 60）；到 55 次起在工具结果尾部追加系统提醒；用完只剩 `work_finish`。
- **零工具熔断**：`zero_tool_max_retries`（默认 2）次追问后直接收尾，用最近几轮文本拼一份兜底日志、`status=paused`。
- **内部事件**：`maid_worker` 的汇报只写历史、不传 `message_obj`，路由从历史尾部认出 `is_maid_report` 并投给 `WorkshopMode.on_inner_event` → 下一轮开头并入上下文（不发群）。

### 3.6 入站路由（`core/modes/pipeline.py`）

`ModeAwarePipeline.enqueue_message` 是全项目唯一路由点：

```
router.is_idle()        → super().enqueue_message(...)   # chat 模式零行为变化
router.route(chat_id):
  ROUTE_MODE   → 系统注入（maid_report/ catchup）→ router.deliver_inner_event，
                 被消费就返回；真人消息 → _buffer_incoming + mark_frozen + on_input
  ROUTE_FROZEN → _buffer_incoming + mark_frozen（唯一体性冻结）
```

- 冻结仍发生在 `yuki.message_buffer`，顺带维护 `last_msg_time`、`reply_watch.resolve`、图片预取。
- `is_catchup` / `is_maid_report` 走 `IncomingMessage.is_system_injected`，**不算真人到达**、不解除回复订阅、不计入日记轮次（`core/history_filter.is_dialogue_message`）。

### 3.7 回群补台（`catchup.py`）

```
handle_catchup(chat_id):
  群休眠 → 跳过注入（消息留在缓冲区，/开启 后随下一条消息处理）
  pop_buffer() → 过滤系统注入 → 无真人消息则结束
  digest:
    ≤ catchup_summarize_threshold(12) → 代码直拼「HH:MM 名字: 内容」
    更多 → sub-LLM 压 ≤200 字（digest_model 空则主模型，temperature=0.3）
    失败 → 回落直拼最近 20 条
  超 catchup_max_messages(80) 只留最近 80 条并标注省略
  生成 is_catchup 合成消息 → super().enqueue_message(force_reply=True)
```

### 3.8 心情高涨与被动连发（回群后）

- `YukiState.mark_high_spirits(gid)`：`high_spirits_until[gid]=now+25min`、`high_spirits_remaining_turns[gid]=3`。
- `EngineDecisionService.decide_to_reply`：高涨时 `reply_score += high_spirits_desire_bonus*100`（默认 +45），低精力拒绝分支留 `15% MAX_ENERGY` 底线。
- `SessionPipeline._maybe_subscribe_reply`：高涨且还有配额时，注册 `high_spirits_followup_window`（默认 12s，可低于 reply_watch 的 30s 下限）的被动窗口；到期无人回 → `event_builder` 注入「想再说几句」并扣 1 轮配额。
- `prompts.build_chat_context` 注入【心情高涨】引导 + 【今日独处工作记忆】+ 小本本双区。

---

## 四、状态机

### 4.1 模式与阶段

```
                    ┌───────────── /深思 或 冷场自动 ─────────────┐
                    ▼                                            │
chat ────────► debate ──投票 start_work──► reflection ──► workshop ─┘（work_finish）
  ▲                │                          │
  │                ├─ do_nothing ──────────────┤
  │                ├─ 中断(force/timeout/empty)┤
  │                └─ 满轮 undecided ──────────┘
  └──────────────── abandon / memo_only / 熔断 / 墙钟超时 / /强制放行
```

- `active_mode`（`data/autonomous_state.json`）记录 `{chat_id, mode, run_id, session_id, started_at}`，正常结束一定清空；进程异常退出留下的残留在启动时由 `sweep_stale_runs()` 清成 paused。
- `SandboxState.phase`：`debate` → `reflection` → `workshop`。
- `/强制放行` = `router.force_release()` → `Mode.request_stop(reason)` → 循环在下一步开头跳出（`stopped='force'`），现场按配置存 paused。

### 4.2 工作会话（L3）状态

`work_sessions/<sid>.json.status`：`active` → `paused`（work_finish paused / 墙钟超时 / 零工具熔断 / 重启残留）→ `completed`（work_finish completed）。`_ensure_work_session()` 优先接续最近 `active|paused` 的会话。

### 4.3 三个「零痕迹」出口

| 出口 | 触发 | 后果 |
| --- | --- | --- |
| do_nothing | debate 连续两步投 do_nothing | 不写 L1–L5、不动小本本、不激活高涨、不破冰 |
| abandon | 复盘选 abandon 或复盘没落盘 | 同上 |
| 中断 | force / timeout / empty / 异常 | 同上，只把 L3 会话标 paused（若已建） |

`chat_history.json` 在以上三种情况下**零记录**（全程只写 `AdaptorHistory`）。

### 4.4 冻结与补台状态

`FrozenChat(chat_id, since, messages, last_at)`：只统计真人消息（`_counts_as_missed`）。退出时 `dispatch_catchups()` 取 `pending_catchups()`（`messages>0`）逐个补台并清空登记。

---

## 五、文件路径地图

### 5.1 模式层 `core/modes/`（553 行）

| 文件 | 职责 |
| --- | --- |
| `core/modes/base.py` | `ModeCapabilities`（can_send / writes_chat_history / accepts_human_input / allow_sub_focus / triggers_diary / accepts_inner_event）+ `Mode` 基类（`run` / `on_input` / `on_inner_event` / `request_stop` / `stop_requested`） |
| `core/modes/router.py` | `ModeRouter`：`ModeState`、`FrozenChat`、`ROUTE_CHAT/MODE/FROZEN`、`enter/exit/force_release`、`mark_frozen/pending_catchups/dispatch_catchups`、`deliver_inner_event`；模块级单例 `router` |
| `core/modes/pipeline.py` | `ModeAwarePipeline(SessionPipeline)`：`enqueue_message` 唯一路由点、`handle_catchup`、`catchup_mode()`（按主人私聊/私聊/群聊选模式） |

### 5.2 沙盒层 `modules/autonomous/`（3.2k 行）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `coordinator.py` | 591 | `AutonomousCoordinator`：准入、`start_run`、`_run` 主流程、`_reflect`、`_ensure_work_session`、`_after_run`（补台/高涨/破冰）、`auto_trigger_check`、`_pick_candidate`、`sweep_stale_runs`、`status_text` |
| `storage.py` | 665 | L1 memo（`MemoStore`）、L2 `WorkDiaryStore`、L3 `WorkSessionStore`、L4 `DailyWorkMemoryStore`、`AutonomousStateStore`、`GroupNameCache`、`DiarySeedSampler`、`init_data_dir()`、容量常量（512/1000/400/800） |
| `tools.py` | 441 | `SandboxState`（votes/reflection/work_log/artifacts/transcript）+ 6 个 `ToolSpec` + `build_registry()` + L1/L2/L4 落盘辅助 |
| `sandbox_loop.py` | 256 | `SilentSender`（发送只进 outbox）、`AdaptorHistory`、`SandboxLoop`（`call_model` / `extract_calls` / `execute_calls` / `focus_view()` + `pinned`）、`SandboxDeps`、`build_tool_context`、`run_step_with_timeout` |
| `inner_debate.py` | 244 | `InnerDebate`、`DebateResult`、`DEBATE_VISIBLE`、`RETRIEVAL_TOOLS`、锚点压缩 |
| `workshop.py` | 288 | `Workshop`、`WorkshopOutcome`、预算/零工具熔断/内部事件/兜底日志 |
| `mode_impl.py` | 129 | `DebateMode` / `WorkshopMode`（`Mode` 实现）、`make_mode_factory` |
| `prompts.py` | 187 | 共有独处底色、念头 A/B 引导、压力旁白、复盘提示词、工坊提示词（只读复用 `core.prompts.get_base_setting()`） |
| `catchup.py` | 136 | `build_digest`、`build_catchup_event`、时间/人名格式化 |
| `inspect.py` | 138 | WebUI 快照 `autonomous_snapshot()` |
| `transcript.py` | 147 | `RunTranscript`：逐轮记录到 `logs/autonomous/<run_id>.jsonl` |
| `__init__.py` | 36 | 导出 storage 单例与惰性 `AutonomousCoordinator` |

### 5.3 被改动的既有文件（只加极小钩子）

| 文件 | 改动 |
| --- | --- |
| `main.py` | 用 `ModeAwarePipeline` 装配、`init_data_dir()`、`AutonomousCoordinator` 注入 `pipeline.autonomous` 与 `engine.autonomous`、`sweep_stale_runs()` |
| `core/session_pipeline.py` | 抽出 `_buffer_incoming()`；`IncomingMessage.is_catchup/is_maid_report/is_system_injected`；补台强制回复；`_maybe_subscribe_reply` 高涨短窗口 + `_high_spirits_event_builder` |
| `core/history_filter.py` | 补台 / 小女仆汇报不计入聊天轮次 |
| `core/brain.py` | `high_spirits_until` / `high_spirits_remaining_turns`（按 chat_id）+ 四个方法 |
| `core/engine/engine_decision.py` | 高涨加分与 15% 精力底线 |
| `core/engine/engine_monitor.py` | 30s 巡检挂 `auto_trigger_check()`；自主轮期间跳过日记巡检与破冰 |
| `core/engine/engine.py` | `self.autonomous` 挂点 + 传给 monitor |
| `core/reply_watch.py` | `subscribe/auto_subscribe` 可选 `min_timeout_seconds` / `event_builder` |
| `core/notebook.py` | 双区（daily ≤350 / plans ≤160）、`load_zones/save_zone/render`、旧 `content` 兼容 |
| `core/prompts.py` | 小本本双区渲染、今日工作记忆槽位、心情高涨槽位 |
| `core/tools/tools_notebook.py` + `tools.py` | `update_notebook(zone=...)` |
| `core/maid/maid_tools.py` | 日记归属标注用群名缓存 `group_name_cache.label()` |
| `core/phone_driver.py` | 全局 `ADB_LOCK`，所有 `adb()` 子命令串行 |
| `modules/QQNapcatListen/listen_main.py` | `handle_autonomous_command`（`/深思` `/工坊状态` `/强制放行` `/自主轮 开|关`）、休眠群拒绝 `/深思`、`_set_group_active` 留痕日志 |
| `modules/debug/webui_server.py` | `GET /api/autonomous` |
| `config.py` / `configs/config.yaml` | `AutonomousConfig`（24 项，`autonomous` 段） |
| `deploy/verify.sh` | 校验容器给 `output/ temp_images/ workspace/` 加 tmpfs、`output/assets` 只读挂载 |

### 5.4 数据文件

| 层级 | 路径 | 说明 |
| --- | --- | --- |
| L1 | `yuki_memory/chroma.sqlite3`（diaries 集合） | 前缀 `【自主随想(YYYY-MM-DD)】`/`【工作记录(...)】`，`metadata.type="autonomous_memo"`，只追加 |
| L2 | `data/work_diary.jsonl` | 一条一行：`{ts,date,session_id,title,kind,chat_id,content}`（≤400 字） |
| L3 | `data/work_sessions/<sid>.json` + `index.jsonl` | `status/work_log(≤512)/artifacts/title/kind/chat_id`；索引带 `log_head`(80 字) |
| L4 | `data/daily_work_memory.json` + `daily_work_memory_archive/<date>.json` | `entries` 渲染成 `text`（≤1000 字）；18h TTL；次日 04:00 归档 |
| L5 | `data/notebook.json` | `{version:2, daily, plans, content}`；`content` 为旧字段兼容 |
| 运行状态 | `data/autonomous_state.json` | `daily{date,auto_runs}` / `last_run_at` / `cooldowns` / `group_overrides` / `active_mode` |
| 群名 | `data/group_names.json` | `{gid: 群名}` 惰性缓存 |
| 逐轮记录 | `logs/autonomous/<run_id>.jsonl` | `run_start/debate_step/vote/phase/reflection/workshop_step/workshop_finish/run_finish` |
| 运行日志 | `logs/yuki.log` | `[Autonomous]/[Modes]/[Debate]/[Workshop]/[Catchup]/[Switch]` 前缀，DEBUG 级 |

### 5.5 测试

| 文件 | 项数 | 覆盖 |
| --- | --- | --- |
| `tests/test_mode_router.py` | 12 | 三态路由、唯一体性互斥、空闲透传、冻结与补台、内部事件、强制放行、补台不算真人、休眠群跳过补台 |
| `tests/test_autonomous_sandbox.py` | 30 | 投票收敛/轮数上限/上下文压缩/强制停止、准入与运行时覆盖、do_nothing 零痕迹、memo_only 落盘、工坊 60 步裁剪与零工具熔断、512 字截断与续作、子聚焦保留 work_finish、补台直拼/摘要/回落、高涨加分与短窗口、L4 TTL 与归档、自动触发配额、sweep、逐轮记录、全链路 start_work |

全量：`docker exec yuki python -m pytest tests -q` → **229 passed**；`deploy/verify.sh` 5 门 ALL_GATES_PASSED。

---

## 六、配置项（`configs/config.yaml` → `autonomous:`）

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `enabled` | `false`（线上已置 true） | 自动触发总开关；关闭时仍允许 `/自主轮 开` 的群手动 `/深思` |
| `enabled_groups` | `[]` | 白名单（与 `TARGET_GROUPS` 取交集） |
| `auto_trigger_enabled` | `false` | 冷场自动触发开关 |
| `min_group_idle_minutes` | `45` | 静默阈值 |
| `min_energy` | `0.60` | 精力比例下限 |
| `quiet_hours` | `[1, 7]` | 深夜禁触发（支持跨零点） |
| `cooldown_minutes` | `120` | 两次自动轮间隔 |
| `daily_max_runs` | `3` | 每日自动次数（持久化） |
| `max_wall_seconds` | `900` | 单次非聊天模式最长占用 |
| `debate_max_rounds` | `32` | 交锋上限 |
| `debate_max_tokens` | `600` | 每步输出上限 |
| `debate_compress_every` | `8` | 压缩间隔（保留最近 6 步原文） |
| `workshop_max_tool_calls` | `60` | 工坊工具预算 |
| `zero_tool_max_retries` | `2` | 零工具追问容忍 |
| `step_timeout_seconds` | `180` | 单步（LLM+工具）超时 |
| `catchup_enabled` | `true` | 回群补台开关 |
| `catchup_max_messages` | `80` | 补台纳入上限 |
| `catchup_summarize_threshold` | `12` | 超过则走 sub-LLM |
| `digest_model` | `""` | 补台/压缩模型，空=主模型 |
| `diary_local_ratio` | `0.7` | 日记检索本群占比（软比例，实现于 `search_diary_fast`） |
| `daily_memory_ttl_hours` | `18` | L4 有效期 |
| `high_spirits_turns` | `3` | 回群连发配额 |
| `high_spirits_minutes` | `25` | 高涨持续 |
| `high_spirits_desire_bonus` | `0.45` | 欲望加成（换算成 +45 分） |
| `high_spirits_followup_window` | `12` | 被动回音窗口秒数 |

---

## 七、指令与观测

| 指令（master 限定） | 作用 |
| --- | --- |
| `/深思` | 在本群手动跑一次自主轮；休眠群/未开启/已占用会被拒并说明原因 |
| `/自主轮 开` / `/自主轮 关` | 运行时开关，写 `group_overrides`，优先级高于配置，重启后仍生效 |
| `/工坊状态` | 当前模式与墙钟、暂停中的会话 + 512 字日志头、今日配额、上次结束时间、上次异常 |
| `/强制放行` | 逃生阀：请求当前模式尽快收尾，立即恢复群聊 |

观测：

```bash
curl -s http://127.0.0.1:8777/api/autonomous | jq          # 模式/阶段/冻结/配额/L2-L5 快照
tail -f logs/yuki.log | grep -E "\[(Autonomous|Modes|Debate|Workshop|Catchup|Switch)\]"
ls logs/autonomous/ && jq -c . logs/autonomous/<run_id>.jsonl | head
cat data/autonomous_state.json && cat data/daily_work_memory.json
```

---

## 八、已知限制与注意事项

1. **群休眠 = 她不在线**：`/深思` 在休眠群会被拒（提示 `/开启`）；补台也跳过休眠群（消息留在缓冲区），所以排查「不回话」先看 `/查询` 的「模式」。
2. `do_nothing` / `abandon` / 中断是**零痕迹**出口：她本人在之后的对话里不会记得这次独处（日志与 transcript 里有，但不进上下文）。
3. 沙盒内不发群消息：`SilentSender` 把发送全部拦进 `outbox`；产物靠 `work_finish` 的 `artifacts` 记录，回群后由心情高涨阶段自然分享。
4. 唯一体性是**全局**的：一个群在独处时其它群一律冻结（只补台）。主人私聊同样会被冻结。
5. `debate` 不接内部事件（小女仆汇报只在 workshop 消费）。
6. 墙钟超时会强制收尾并把 L3 会话标 `paused`；工作日志可能是兜底拼的，需要人看一眼是否合理。
7. 代码与配置都在容器只读挂载里：改完必须重启容器才生效。
