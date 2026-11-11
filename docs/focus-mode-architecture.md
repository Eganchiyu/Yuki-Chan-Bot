# 聚焦模式通用架构重构设计（Focus Mode Architecture v2）

> 状态：P0–P5 已实施落地；P6（`art` 艺术创作域）待单独设计工具细节后接入。
> 前置阅读：`docs/focus-mode-paradigm.md`（理念：渐进披露 / 工作台收敛 / 退出即覆写 / 群聊流内并发）。
> 本文回答的问题：**怎样让"新增一个聚焦模式"从"改 5 个模块"变成"写 1 个声明文件"**，并且这件事要简单到 Yuki 能照着接口自己迭代。
> 第一个要落地的新模式是「艺术创作聚焦模式」（`art`：画画 + 资产登记），本文会把它当作示例贯穿全文。

---

## 一、现状审查

### 1.1 结构问题

| # | 问题 | 位置 | 后果 |
|---|---|---|---|
| S1 | 范式写成了通用的，但代码只实现了手机这一个域。`PHONE_*` 常量、`phone_focus_manager` 单例、`phone_trace_store` 遥测、`phone_focus_work` / `is_phone_summary` 字段名，硬编码散在 5 个模块里 | `engine_reply.py`、`toolchain.py`、`tools_phone*.py`、`context_snapshot.py`、`phone_focus.py` | 加一个 `art` 域要在 5 处加 `if`，还会多出第二套 `art_focus_work` 标记 |
| S2 | `chat_with_tools` 约 270 行，什么都管：LLM 循环、视图切换、轮次扩容、历史打标、内存覆写、手机遥测、调试快照 | `engine_reply.py:310-577` | 每加一个模式，循环里就多一层分支 |
| S3 | 有 3 个返回出口（内容被过滤 / skip / 正常回复），加上轮次用尽后的收尾，一共 4 处，每处都要手动调 `_after_turn` 和遥测 | 同上 | 已经对不齐：收尾分支只判断 `phone_tools_used`，漏了 `in_phone_focus`；内容被过滤的分支没记最终回复 |
| S4 | 接口靠 `try/except TypeError` 兼容新旧两种 `get_tools` 写法 | `_resolve_active_tools` | 签名演进不安全 |
| S5 | 有两套互不相知的闲置计数器：聚焦的 `idle_turns` 和 pruner 的 `_idle` | `phone_focus.py`、`tool_prune.py` | 规则冲突（见 B3） |
| S6 | 调试快照的 `tool_count` 总按常态视图计算 | `api_reply` | 聚焦时 WebUI 数字不准 |

### 1.2 行为缺陷

| # | 缺陷 | 本次处理 |
|---|---|---|
| B1 | **同批 `phone_action` + `phone_finish` 时，工作记录漏进历史**：`phone_finish` 执行时已经覆写了历史，但同批工具结果是在 `execute_tool_calls` 结束后才写入的，`phone_action` 的控件树会排在总结之后，永久留下 | ✅ 修（写入闸门，见 3.5） |
| B2 | 隐藏工具照样能执行：`ToolCallManager` 执行时不看当前视图；正文工具调用还原用的 `valid_tool_names` 也是全量工具名 | 暂不修，ToolView 预留开关 |
| B3 | 聚焦期间连续 2 轮只聊天，pruner 会把还在用的工作记录压成存根 | 暂不修，Hook 预留声明 |
| B4 | `phone_finish` 后，本轮剩余轮次上限不回落（仍为 100） | 暂不修 |
| B5 | 聚焦状态只在内存里，重启后带 `phone_focus_work` 的记录成了孤儿，永远不会被清理 | ✅ 修（启动时清扫孤儿记录，见 3.6） |

> 原则：P1–P3 是**纯等效重构**，B2–B4 的现状行为原样保留；只有 B1、B5 两处在 P4 修正。

---

## 二、设计目标

1. **一个声明 = 一个模式**：新模式只写 `core/focus/domains/<domain>.py`（一份声明 + 域内工具），不碰主循环、注册表、历史管理。
2. **主循环与模式无关**：`chat_with_tools` 不出现任何域名。所有和模式相关的行为都通过 Hook 进入。
3. **统一出口**：每轮只有一个收尾点，Hook 的 `on_turn_end` 保证恰好执行一次。
4. **非破坏**：`core.phone_focus` 的公开符号、`get_tools(phone_focus=)`、旧历史字段 `phone_focus_work` / `is_phone_summary` 全部可读可用，现有测试不改也能通过。
5. **可自迭代**：接口是纯数据 + 少量钩子，配套有一份可机器校验的 Checklist 和契约测试；Yuki 按模板新建模式后跑契约测试就能自证接入正确。

---

## 三、目标架构

```text
core/
├── focus/
│   ├── __init__.py          # 导出 focus_manager、FocusDomain、register_domain
│   ├── domain.py            # FocusDomain 声明（纯数据 + 可选钩子）
│   ├── manager.py           # FocusManager：多域状态机（每个 chat 最多 1 个活跃域）
│   ├── view.py              # ToolView：由状态推导出可见工具集合
│   ├── rewrite.py           # 纯函数：持久化历史覆写 / 内存 tool_messages 覆写
│   ├── tools.py             # 通用 start/finish 工具工厂
│   └── domains/
│       ├── phone.py         # 手机域声明（从 phone_focus.py 迁出）
│       └── art.py           # 艺术创作域（新）
├── engine/
│   ├── turn.py              # TurnState：单轮状态容器
│   ├── turn_hooks.py        # TurnHook 协议 + FocusHook / PruneHook / TraceHook / SnapshotHook
│   └── engine_reply.py      # 瘦身后的主循环
├── phone_focus.py           # 兼容层：重新导出旧符号
└── toolchain.py             # get_tools(view=...)，保留 phone_focus= 兼容
```

依赖方向：`engine → focus → toolchain`，域声明只依赖 `focus` 和各自的工具实现。`toolchain` 不再反向 import 任何域。

### 3.1 `FocusDomain`：模式声明

```python
@dataclass(frozen=True)
class FocusDomain:
    name: str                          # 域名，如 "phone" / "art"
    title: str                         # 人类可读名称，如 "手机" / "艺术创作"
    entry_tool: str                    # 常态唯一暴露的入口，如 "art_start"
    exit_tool: str                     # 退出工具，如 "art_finish"
    domain_tools: frozenset[str]       # 只在聚焦时展开的专精工具
    keep_tools: frozenset[str] = BASE_KEEP_TOOLS   # 聚焦时保留的基础工具：skip / send_master_private / send_qq_file
    summary_prefix: str = ""           # 默认 f"【{title}总结】"
    exit_hint: str = ""                # 内存覆写时附在总结后的当轮提示
    idle_turns_key: str = ""           # cfg.tools 上的配置键，空则用默认值 5
    max_rounds_key: str = ""           # cfg.tools 上的配置键，空则用默认值 100
    max_trace: int = 20

    # —— 可选钩子（都有空实现，按需覆盖）——
    on_enter: Callable[[str, str], None] | None = None          # (chat_id, goal) → 遥测开会话等
    on_exit: Callable[[str, str, str], None] | None = None      # (chat_id, summary, reason)
    on_model_call: Callable[[str, str, list], None] | None = None
    on_final_reply: Callable[[str, str, str], None] | None = None
    stub: Callable[[dict], str] | None = None                   # 给 pruner 的单行存根格式

    @property
    def work_tools(self) -> frozenset[str]:   # 覆写时要抹掉的工具 = 入口 + 专精 + 退出
        return frozenset({self.entry_tool, self.exit_tool, *self.domain_tools})

    @property
    def hidden_in_default(self) -> frozenset[str]:
        return frozenset({self.exit_tool, *self.domain_tools})

    @property
    def focus_allowed(self) -> frozenset[str]:
        return frozenset({self.exit_tool, *self.domain_tools, *self.keep_tools})
```

手机域迁移后的样子（与现有常量一一对应）：

```python
PHONE = FocusDomain(
    name="phone", title="手机",
    entry_tool="phone_start", exit_tool="phone_finish",
    domain_tools=frozenset({"phone_action", "phone_macro"}),
    summary_prefix="【手机操作总结】",
    exit_hint="（你已结束本轮手机操作并收起手机，请直接根据上述操作结果回复用户。）",
    idle_turns_key="phone_focus_idle_turns", max_rounds_key="phone_focus_max_rounds",
    on_enter=_trace_start, on_exit=_trace_finish,
    on_model_call=_trace_model_call, on_final_reply=_trace_final_reply,
    stub=_phone_stub,
)
register_domain(PHONE)
```

### 3.2 `FocusManager`：多域状态机

```python
@dataclass
class FocusState:
    chat_id: str
    domain: str
    goal: str = ""
    started_at: float
    idle_turns: int = 0
    trace: list[str]

class FocusManager:
    def register(self, domain: FocusDomain) -> None
    def domains(self) -> list[FocusDomain]
    def domain_of_tool(self, tool_name: str) -> FocusDomain | None   # 反查工具属于哪个域

    def active(self, chat_id) -> FocusState | None                   # 每个 chat 最多 1 个
    def is_focused(self, chat_id, domain: str | None = None) -> bool
    def enter(self, chat_id, domain: str, goal="") -> FocusState     # 已在其他域时：先自动退出旧域（生成兜底总结），再进入
    def record_step(self, chat_id, desc, note="") -> None            # 记到当前活跃域
    def exit(self, chat_id, *, history, summary="", reason="finish") -> FocusExit | None
    def after_turn(self, chat_id, used_domains: set[str], *, history) -> FocusExit | None
    def sweep_orphans(self, history) -> int                          # 启动时清扫孤儿记录（B5）
```

- **同一时刻只允许一个域**：工具视图是互斥的，不支持同时聚焦两个域，这样规则简单。真要用到"手机 + 画画"时，先退出手机再进入画画，退出时手机域会生成兜底总结。
- `exit()` 只负责**状态 + 持久化历史**，返回 `FocusExit(domain, summary, reason)`，不碰 `tool_messages`。内存覆写由 FocusHook 在批次结束后统一处理（见 3.5），这是修 B1 的关键。
- 兼容：`core.phone_focus.phone_focus_manager` 是一个薄适配器，把 `is_focused(cid)` 映射成 `is_focused(cid, "phone")`，`enter(cid, goal)` 映射成 `enter(cid, "phone", goal)`，以此类推；`PhoneFocusManager` 类名保留，供测试实例化。

### 3.3 `ToolView`：唯一的"当前可见工具"来源

```python
@dataclass(frozen=True)
class ToolView:
    visible: frozenset[str]

    @classmethod
    def resolve(cls, registry, manager, chat_id, exited_this_turn: set[str]) -> "ToolView":
        names = set(registry.list_functions())
        state = manager.active(chat_id)
        if state:                                         # 聚焦：白名单
            return cls(frozenset(names & manager.domain(state.domain).focus_allowed))
        for d in manager.domains():                       # 常态：隐藏各域重型工具
            names -= d.hidden_in_default
            if d.name in exited_this_turn:                # 本轮刚退出：连入口也收起，防止同轮重入
                names.discard(d.entry_tool)
        return cls(frozenset(names))
```

- `FunctionRegistry.get_tools(view: ToolView | None = None, *, phone_focus: bool | None = None)`：传 `view` 时按视图过滤；只传旧参数 `phone_focus=` 时走兼容路径，内部构造等价视图。`toolchain` 不再 import 任何域常量。
- B2 预留：`ToolCallManager.execute_tool_calls(..., view=None)`，传入后对不在视图里的调用返回 `ToolResult.failure("该工具当前未展开", "tool_not_in_view")`。**默认不传**，保持现状行为。

### 3.4 `TurnState` + `TurnHook`：主循环瘦身

```python
@dataclass
class TurnState:
    chat_id: str
    mode: str
    context: ToolContext
    tool_messages: list[dict]
    round_idx: int = 0
    max_rounds: int
    tools_executed: bool = False
    used_domains: set[str]            # 本轮碰过的域（替代 phone_tools_used）
    exited_this_turn: set[str]        # 本轮已退出的域（替代 phone_finished_this_turn）
    pending_exits: list[FocusExit]    # 本批由 exit_tool 产生、待内存覆写的退出
    tool_trace: list[dict]
    tools_used: list[str]
    outcome: str = ""                 # "reply" / "skip" / "filtered" / "exhausted"
    final: tuple[str, str] | None = None

class TurnHook(Protocol):
    def on_turn_start(self, st: TurnState) -> None: ...
    def before_llm(self, st: TurnState) -> None: ...                       # 可调整 max_rounds
    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None: ...
    def classify_persist(self, st: TurnState, msg: dict) -> PersistDecision: ...   # 写入 / 打标 / 丢弃
    def after_batch(self, st: TurnState, results: list[dict]) -> None: ...
    def on_turn_end(self, st: TurnState) -> None: ...                      # 恰好执行一次
```

挂载的 Hook（按顺序）：

| Hook | 职责（全部从现有代码迁移而来） |
|---|---|
| `FocusHook` | 进入/退出时调整 `max_rounds`；把 thought 和 tool 结果打上 `focus_work=<domain>` 标记；批次结束后执行 `pending_exits` 的内存覆写；`on_turn_end` 调 `manager.after_turn` |
| `PruneHook` | `on_turn_end` 调 `pruner.after_turn`（B3 预留：可跳过活跃域的记录，默认关闭） |
| `FocusTraceHook` | 把 `on_model_call` / `on_final_reply` / 插话 incoming 分发给活跃域或本轮用到的域的钩子（手机域接 `phone_trace_store`，art 域可以接资产日志） |
| `SnapshotHook` | 同步 `context_snapshot_store`，并修正 `tool_count`（S6） |

瘦身后的主循环骨架（约 80 行）：

```python
async def chat_with_tools(...):
    st = TurnState.begin(...)
    self.hooks.on_turn_start(st)
    try:
        while st.round_idx < st.max_rounds:
            st.round_idx += 1
            self.hooks.before_llm(st)
            view = ToolView.resolve(self.tool_registry, focus_manager, st.chat_id, st.exited_this_turn)
            msg = await self._call_llm(st, view)
            calls = self._extract_calls(msg)               # 包含正文工具调用的还原
            if not calls:
                st.final = self._finalize(st, msg)         # 设置 outcome = reply / filtered
                return st.final
            self.hooks.on_model_call(st, msg, calls)
            await self._emit_thought(st, msg, calls)       # 阶段性文本 → 暂存区，等待 classify
            results = await self.tool_manager.execute_tool_calls(calls, st.context, ...)
            if st.context.metadata.get("skip_reply"):
                st.outcome, st.final = "skip", (SKIP_REPLY_MARKER, SKIP_REPLY_MARKER)
                return st.final
            self._commit_batch(st, msg, results)           # 写入闸门（3.5）
            self.hooks.after_batch(st, results)            # 内存覆写、截图、插话合并
        st.final = await self._close_exhausted(st)
        return st.final
    finally:
        self.hooks.on_turn_end(st)                         # 单一出口
```

> 等效性说明：skip 分支现在不写本批工具结果、不附截图、不合并插话，迁移后保持这个顺序不变。`_emit_thought` 仍在执行工具**之前**实时发送；只有"写进历史"这一步延后到闸门里。

### 3.5 写入闸门（修 B1）

现状：工具执行过程中，`phone_finish` 立刻覆写了历史；执行结束后，本批其他工具的结果又被追加进历史，于是控件树漏到了总结后面。

改造：

1. `exit_tool` 的 handler 只调 `manager.exit(...)`，覆写**截至当前**的持久化历史，同时往 `context.metadata["focus_exits"]` 追加 `FocusExit`（替代 `phone_finish_summary`，旧键保留兼容写入）。
2. `_commit_batch` 按顺序处理本批的 thought 和 tool 结果，每条都过一遍 `classify_persist`。
3. `FocusHook.classify_persist` 判定规则：如果某条消息属于**本批已退出的域**（按工具名反查，或按调用前记下的活跃域），直接**丢弃**，不写入历史。
4. 总结消息由 `exit()` 写在原位置；同批后续的非域消息正常追加在它后面。

结果：不管 `phone_action` 和 `phone_finish` 是否同批、谁先谁后，历史里都只剩"群聊 + 总结"。

### 3.6 孤儿记录清扫（修 B5）

- 状态**不落盘**，重启等于强制退出聚焦。
- `YukiEngine.__init__` 装配完成后调 `focus_manager.sweep_orphans(history)`：
  - 遍历所有会话，找带 `focus_work` 标记（兼容旧的 `phone_focus_work`）、而当前**没有活跃状态**的连续工作片段；
  - 按片段原地替换：删除工作记录，在片段末尾插入 `{"role": "user", "content": "<prefix>（重启前未正常结束）<兜底总结>", "is_focus_summary": True, "focus_domain": <d>}`；
  - 兜底总结由片段内的 thought 文本和工具名拼成，不调用 LLM；
  - 片段中间的群友消息保持原序。
- 只在启动时执行一次，执行时会打日志并统计清扫条数。

### 3.7 历史字段规范

| 新字段 | 含义 | 兼容读取 |
|---|---|---|
| `focus_work: "<domain>"` | 聚焦工作记录（thought / tool） | `phone_focus_work: True` 视为 `"phone"` |
| `is_focus_summary: True` + `focus_domain` | 退出总结 | `is_phone_summary: True` |

写入一律用新字段；读取时两种都认。旧数据不迁移，自然老化即可。

---

## 四、示例：艺术创作聚焦模式（`art`）

> 下面只演示"接入成本"，工具的具体参数和资产库的存储形式待单独设计确认。

```python
# core/focus/domains/art.py
ART = FocusDomain(
    name="art", title="艺术创作",
    entry_tool="art_start", exit_tool="art_finish",
    domain_tools=frozenset({"art_draw", "art_asset"}),   # 画/改图、资产登记与检索
    keep_tools=BASE_KEEP_TOOLS,                          # 已含 send_qq_file，可直接发图
    summary_prefix="【艺术创作总结】",
    exit_hint="（你已结束本轮创作并收起画板，请直接根据创作结果回复用户。）",
    idle_turns_key="art_focus_idle_turns",
    max_rounds_key="art_focus_max_rounds",
    on_enter=_open_canvas_session, on_exit=_close_canvas_session,
)
register_domain(ART)

ART_TOOL_SPECS = [
    focus_start_spec(ART, description="开始画画或整理画作资产。", handler=_art_start_overview),
    ToolSpec(name="art_draw", ...),       # 复用 tools_media.generate_image_tool 的生成内核
    ToolSpec(name="art_asset", ...),      # 登记 / 打标签 / 检索 / 设为参考图
    focus_finish_spec(ART),               # 通用退出工具，必填 summary
]
```

- `art_start` 的首屏概览（对应范式要求的"进入即观察"）：最近的资产、人设参考图清单、当前画布状态。
- `art_draw` / `art_asset` 成功后调 `focus_manager.record_step(...)`，用于闲置自动退出时生成兜底总结。
- 常规的 `generate_image` 是否保留在常态视图里，取决于产品决策：可以继续保留，作为"随手画一张"的轻量入口；也可以收进 art 域的 `hidden_in_default`。
- 主循环、注册表、历史管理**一行不改**。工具注册只需在 `TOOL_SPECS` 里拼上 `ART_TOOL_SPECS`，或者由 `core/focus/domains/__init__.py` 自动汇总。

---

## 五、新增模式 Checklist（供人和 Yuki 自迭代共用）

1. 新建 `core/focus/domains/<d>.py`：写 `FocusDomain` 声明，并 `register_domain`。
2. 入口工具用 `focus_start_spec(domain, ...)` 生成：描述不超过 2 句；handler 要返回首屏观察结果；领域不可用时返回 `data={"focus": "aborted"}`，框架会自动回滚状态。
3. 专精工具：成功时调 `focus_manager.record_step`；大段中间输出用 `no_persist` 或 `remember=False`。
4. 退出工具用 `focus_finish_spec(domain)` 生成，不要手写覆写逻辑。
5. `config.py` 的 `tools` 段新增 `<d>_focus_idle_turns`、`<d>_focus_max_rounds`（可选）。
6. 在 `tests/test_focus_contract.py` 的参数列表里加上域名，跑通契约测试。

**契约测试**（对所有已注册的域参数化执行）：
- 常态视图里只能看到 `entry_tool`，看不到 `domain_tools` 和 `exit_tool`；
- 聚焦视图等于 `focus_allowed` 与已注册工具的交集；
- 同轮进入后，下一次 LLM 请求的视图已切换；
- 同批执行"专精工具 + 退出工具"后，历史里只剩群聊和总结（B1）；
- 插话保序；
- 闲置超过阈值后自动退出并写入兜底总结；
- 本轮退出后不能同轮重入；
- 重启后孤儿记录被清扫（B5）；
- 入口返回 `aborted` 时状态已回滚。

---

## 六、实施路线

| 阶段 | 内容 | 行为 | 验收 |
|---|---|---|---|
| P0 | 补"现状快照"测试：同轮切换、插话保序、闲置超过 5 轮退出、禁止同轮重入、3 条出口的收尾次数；B1、B5 各写一个复现测试，先标 xfail | 不变 | 现有测试和快照测试全部通过 |
| P1 | 建 `core/focus/`（domain / manager / rewrite / tools），手机作为第一个域注册；`phone_focus.py` 改为兼容层 | 不变 | 不改现有测试即可通过 |
| P2 | 加 `ToolView`；`toolchain` 和 `engine_reply` 去掉所有 `PHONE_*` 引用 | 不变 | `grep -n "phone" core/engine/engine_reply.py core/toolchain.py` 结果为空 |
| P3 | 引入 `TurnState` + Hooks，主循环改为单一出口，遥测和快照拆成 Hook | 不变（顺带补齐 3 条出口的遥测，S3） | 快照测试通过，`chat_with_tools` 不超过 100 行 |
| P4 | 写入闸门（B1）+ 启动时清扫孤儿记录（B5） | **改变** | 两个 xfail 转为通过 |
| P5 | 写契约测试，更新 `focus-mode-paradigm.md` 的第三、四节，指向新接口 | 不变 | 契约测试覆盖 phone 域 |
| P6 | 接入 `art` 域（另行设计工具细节） | 新功能 | art 加入契约测试参数并通过 |

每个阶段单独提交；测试统一在容器内跑：`docker exec yuki python -m pytest tests -q`。

---

## 七、暂缓项（已预留扩展点，默认关闭）

| 项 | 预留位置 | 打开方式 |
|---|---|---|
| B2 执行前视图校验 | `execute_tool_calls(view=...)`、正文工具调用还原的 `valid_tool_names` | 主循环传入 `view` |
| B3 聚焦期间 pruner 不折叠 | `PruneHook(skip_active_focus=False)` | 改为 True |
| B4 退出后轮次上限回落 | `FocusHook(restore_rounds_on_exit=False)` | 改为 True |
| 状态落盘 | `FocusManager` 的 `store` 注入点 | 实现 `FocusStateStore` |
