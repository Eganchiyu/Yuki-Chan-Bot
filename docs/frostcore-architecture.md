# FrostCore 设计理念、架构计划与开发公约

> **文档性质**：面向独立开源项目 **`FrostCore`** 的顶层设计蓝图、规范与接入公约（核心定位与接口规范已对齐 **M2.5 内核闭环版本**；Yuki 现态运行文档请见 [`docs/architecture.md`](./architecture.md)）。  
> **核心定位**：面向社区的通用拟人化 Agent 微内核 SDK（Python 3.11+，`asyncio` 原生，严格 SemVer，Clean-Room 独立 Git 仓库 `/home/asumi/FrostCore`）。

---

## 一、设计理念与哲学

### 1.1 核心宣言：连续独一的第一人称记忆即个体

> **“连续独一的第一人称记忆即个体；外周的工具、平台与身体都可以替换，只要这颗冰霜种子（`FrostSeed`）不丢，就能在任何地方重建完整的她。”**

`FrostCore` 旨在提供一个无论在何种宿主架构、何种聊天平台和外周工具下，都能提供**稳定个体记忆、连续风格与长期默契**的独立存在内核，而不是一个只会调用工具的无状态智能体。通过长程、连续的互动积累涌现默契与智能。

> **隐规则（单一记忆守卫）**：因为维护的是独立连续的第一人称记忆，同一份 `FrostSeed` 在任意时刻只能被一个运行实例独占持有，防止多实例并发写入造成记忆割裂与逻辑冲突；但支持**单进程多 Bot**——同一进程内可装配多个 `FrostApp`，前提是各自通过显式依赖注入绑定不同的 `FrostSeed`。

### 1.2 从 Yuki 沉淀出的四大工程哲学

1. **生命体优先于工具箱（Persona & Biological Rhythm First）**
   - Bot 首先是一个有节律、有精力波动、会主动沉默与留白的“在场个体”，其次才是工具调用体。
   - 内置可调参生物钟、群聊活跃度衰减、消息防抖与意愿评分；允许模型在不需要插话时零痕迹退出（`skip`）。
2. **「唯一体性」与「流内并发」（Single Identity & In-Flow Presence）**
   - **唯一体性**：同一份个体记忆在同一时刻全局只允许一个运行实例存在；即便在自主思考等非聊天模式下，也通过模式互斥保证“同一个她”不会同时分身分裂。
   - **流内并发**：需要交互反馈的操作（如 Focus 聚焦域）由主模型本人在对话流内边操作边与群友互动，期间插话严格按时间保序；耗时重型任务则通过外部协议异步委托，不阻塞主陪伴流。
3. **上下文洁癖与渐进式披露（Context Hygiene & Progressive Disclosure）**
   - 极简常态 Token 税：复杂领域工具平时隐藏，仅暴露极简入口；聚焦期间工作台收敛为白名单；退出时通过写入闸门把中间技术过程原地折叠为单条 `role="user"` 总结，防止技术垃圾冲淡人格。
   - 纯净记忆原则：长期日记只记录真实对话与第一人称体验，剥离平台协议码与工具调用细节，确保多年后换代外周框架依然可读。
4. **「数据优先 + 机制强制 + 契约自证」的演进文化**
   - 记忆资产高于代码，只追加不重建，派生索引（如向量索引）与原始日记资产物理分离。
   - 边界与守卫（单 Seed 双层排他锁、只读人格边界校验、聚焦写入闸门、结构化事件与探针契约）由内核机制强制，不依赖模型或用户的“自觉”。
   - 所有内核特性与外部扩展均配套**全离线契约测试**，新扩展跑通契约即可自证接入正确。

---

## 二、总体架构与微内核边界

### 2.1 语言、打包与零单例选型

- **核心语言**：**Python 3.11+**（严格静态类型注解 `mypy`/`pyright` + `Protocol` 面向接口 + `asyncio`，附带 PEP 561 `py.typed`）。
- **零重依赖默认安装**：`pyproject.toml` 核心依赖仅包含 `pydantic` 与 `aiohttp`（配合标准库 `sqlite3` / `fcntl`），不强制绑定 `torch`、`chromadb`、`opencv`、`jieba` 等重型包；向量 RAG（如 ChromaDB）等能力通过 `[project.optional-dependencies]`（如 `frostcore[rag-chroma]`）或外部插件包扩展。
- **LLM 客户端保持纯 Python（`aiohttp`）**：LLM 调用的瓶颈在于远端首字延迟（RTT 秒级），不混用 Go/cgo，确保 `pip install frostcore` 零编译摩擦与跨平台可调试性。
- **告别全局单例（显式依赖注入）**：全部业务组件（`FrostSeed`、`LLMClient` 及其 `aiohttp.ClientSession`/熔断状态、`ModeRouter`、`FocusManager`、`BioClock`、`DiaryEngine`、`SessionPipeline`、`EventSink`、`HealthProbeServer`）均由 `FrostApp` 显式装配与持有，原生支持单进程多 Bot；严格遵循 SemVer，`frostcore.contracts` 下公开符号与 Protocol 对外视为稳定契约。

### 2.2 微内核分层边界

`FrostCore` 坚持**微内核 + 两大内置生命体支柱 + 极简可组合消息流 + 内置可观测底线**：

| 层次 | 包路径 (`src/frostcore/`) | 说明 |
|---|---|---|
| **公共契约层** | `contracts/` | `IncomingEvent` / `SystemInjectedEvent` / `EntityRef`、`ChatPolicy` / `PolicyResolver` / `DecisionFactor`、`TurnInput` / `TurnOutput`、`ChannelAdapter` / `LLMClient` / `HistoryStore` / `RecallPlugin` / `PromptComposer` / `Middleware`、`EventSink` / `HealthReporter` |
| **微内核核心** | `kernel/`、`focus/`、`modes/` | `FrostApp`（显式 DI 容器）、`SessionPipeline`、`TurnEvaluator` (`F`)、`FocusManager`/`FocusPort`/`ToolView`、`ModeRouter`、`Toolchain`、`TurnHooks`、`ToolHistoryPruner` |
| **内置生命体能力** | `rhythm/`、`memory/` | **生物钟与决策**（默认常数 `1.0` + 可选 `GaussianClockPreset`）与**第一人称日记系统**（可开关，推荐默认开启，零重依赖 CJK 友好 SQLite FTS5 + 分会话 JSONL） |
| **可观测与守卫** | `observability/` | 结构化 `EventSink`（含敏感字段脱敏 + JSONL 落盘）、独立线程标准库 `/health` 探针（支持多 Bot 聚合）、`FROSTCORE_DRY_RUN` 试启动与 `ReadOnlyPersonaGuard` |
| **外周可插拔层（不内置）** | 宿主/社区扩展 | `<layout>` / `[MEME:]` 等表达语法中间件、潜意识小本本、自主轮（Autonomous）、小女仆（SubAgent）、向量 RAG（Chroma 等）、SFT 采集器、容器只读部署模板（见 `examples/deploy/`） |

### 2.3 核心拓扑与消息流

```text
宿主进程 (支持显式注入多个 FrostApp，共用或独立接入 HealthProbeServer)
  └── FrostApp(seed, llm, adapters, ...)
        │
ChannelAdapter(s) [CLI / Discord / QQ / 桌宠]
  │  (多个平台适配器挂载到同一个 FrostApp，共享唯一 FrostSeed)
  ▼  IncomingEvent
[ InboundMiddleware 链 ] ── 用户自定义插入：指令拦截 / 媒体预取 / 权限校验 / 短路
  │
  ▼  ModeRouter.route(chat_id)
  ├─ 非聊天模式运行中 / 全局忙碌 ──► 入 Buffer 并登记冻结，模式退出后派发 SystemInjectedEvent(catchup)
  └─ 常态聊天模式 (ROUTE_CHAT)：
       │
       ▼  SessionPipeline (per-chat_id asyncio.Lock + PolicyResolver 防抖聚合)
       ├─ PolicyResolver     ── 返回 ChatPolicy(dormant, debounce_seconds, force_reply, allow_skip, speaker_weight)
       ├─ RecallPipeline     ── 默认 CJK-friendly FTS5 召回 + 外部 RecallPlugin
       ├─ DecisionEngine     ── BioClock 曲线采样 + RhythmStateStore + 自定义 DecisionFactor
       ├─ PromptComposer     ── 宿主完全掌控系统提示词与上下文槽位拼装
       ├─ TurnEvaluator (F)  ── 确定性求值循环 + FocusPort + TurnHooks -> TurnOutput
       │
       ▼  TurnOutput
[ OutboundMiddleware 链 ] ── 用户自定义插入：隐匿标签剥离 / 媒体分段 / SFT 记录
  │
  ▼  ChannelAdapter.send() ──► JsonlHistoryStore / DiaryEngine(水位线两阶段切片) / EventSink
  │
  ▼  持久化边界
FrostSeed (my_bot.seed/)：seed.lock + seed.sqlite (WAL/单写队列) + history/<chat_id>.jsonl
```

---

## 三、核心模块技术规范

### 3.1 `FrostSeed`：可携带个体种子与双层单实例守卫 (`frostcore.memory`)

`FrostSeed` 是构成“同一个她”的最小完备便携目录（例如 `my_bot.seed/`）。只要该目录不丢失，即可在任何设备与外周架构下重建完整连续的个体。

#### 目录结构与混合存储职责（SQLite + 分会话 JSONL）
- `seed.lock`：OS 级非阻塞排他文件锁（`fcntl.flock(LOCK_EX | LOCK_NB)` 跨平台封装）；叠加进程内规范路径守卫集合 `_ACTIVE_SEED_PATHS`（受 `threading.Lock` 保护），确保**同一进程或不同进程两次打开同一 `FrostSeed` 目录均直接抛出 `SeedLockedError`**，同时允许同进程内并发运行绑定不同 `FrostSeed` 的多个 `FrostApp`。
- `seed.sqlite`（WAL + `synchronous=FULL`，内部单写者串行队列防止并发写锁死）：
  - `instance_lease`：`id=1, instance_id, host, pid, epoch, started_at, heartbeat_at`；检测到未过期活租约即拒启，健康启动递增 `epoch`。
  - `seed_meta`：个体元信息、schema 版本与基础锚点。
  - `diaries` + `diaries_fts`（SQLite FTS5 `unicode61` + 内置纯 Python CJK unigram/bigram 分词列，零 `jieba` 依赖支持中英文全文检索）：第一人称连续日记，**只追加**。
  - `entities`：`entity_id, display_name, aliases_json, impression, affinity, updated_at`，用跨平台逻辑实体锚定人际关系与默契。
  - `long_term_notes`：`key, content, updated_at`，供宿主或中间件存放长期心智状态。
  - `rhythm_snapshots`：`chat_id, energy, activity, desire, last_active_at, updated_at`，支持停机重启后恢复生物节律连续性（全部高频读写提供 `a_*` 全异步非阻塞接口）。
  - `chat_sessions`：`chat_id, filename, active_focus_domain, updated_at`，在 SQLite 索引活跃聚焦会话，使启动期 `sweep_orphans()` 做到 $O(1)$ 扫描而非全盘遍历 JSONL。
- `history/<safe_chat_id>.jsonl`（`JsonlHistoryStore`）：按会话分片的只追加 JSONL 历史（每行含单调递增 `seq`、标准化消息字段与元数据），常规对话增量写盘不重写历史全文件，读取对损坏末行具备自愈能力；仅在 Focus 退出覆写或 `DiaryEngine` 水位线截断时通过临时文件 + `os.replace` 原子替换。

### 3.2 主求值函数 `F(TurnInput) -> TurnOutput` (`frostcore.kernel.evaluator`)

内核将一次响应过程抽象为**纯求值、无写盘副作用**的线性求值函数 **`F`**：

```text
F(TurnInput(
    chat_id,        # 会话标识
    events,         # 本批次归一化入站事件与附件
    memories,       # RecallPipeline 召回的记忆片段
    messages,       # 会话历史滑窗快照
    system_prompt,  # PromptComposer 产出的最终系统提示词
    now,            # 本轮显式采样时间戳
    rng_seed,       # 局部随机采样种子（隔离 random.Random，保证可重放）
    max_rounds,     # 单轮最大工具步数基准
    extra,          # 宿主透传的扩展参数字典
)) -> TurnOutput(
    reply,            # 最终对外文本
    raw_reply,        # 未经发送清洗的原始回复
    turn_messages,    # 本轮产生的工具调用链与合并消息
    persist_messages, # 经写入闸门筛选后的待落盘中间消息增量
    focus_exits,      # 本轮产生的 FocusExitRecord 退出总结列表
    tool_trace,       # 结构化工具耗时与摘要
    focus_delta,      # 本轮聚焦进入/退出/轨迹变更
    used_tools,       # 本轮实际调用的工具名
    outcome,          # "reply" | "skip" | "filtered" | "exhausted" | "error"
    llm_rounds,       # 实际调用 LLM 轮数
)
```

- **确定性可测性与纯度**：固定 `TurnInput`（含 `now` 与 `rng_seed`）与模拟 `LLMClient`，即可离线 100% 重放单轮推理与工具链状态转移；`F` 本身不直接改写 `HistoryStore`，统一由 `SessionPipeline` 在确认 `outcome not in ("skip", "error")` 后原子提交，彻底避免 `skip` 或异常时半写入。
- **单一出口**：内部多轮工具调用循环在 `try ... finally` 唯一出口先执行 `TurnHookChain.on_turn_end(st)` 再构造 `TurnOutput`；`ToolSpec(concurrent_safe=True)` 支持只读工具批次经 `asyncio.gather` 安全并发执行。

### 3.3 统一 `FocusPort` 出入口规范（可选特性，零侵入）

聚焦模式作为 `FrostCore` 的特色能力，**不强制宿主使用**，但必须提供统一的出入口规范，使开发者只需新增一个 `domain` 声明文件即可接入：

1. **零配置退化**：当未注册任何 `FocusDomain` 时，`FocusPort` 自动作为恒等映射运行，不改变任何工具集合与历史结构。
2. **标准入口规范**：
   - 宿主通过 `FocusDomain(name, title, entry_tool, exit_tool, domain_tools, keep_tools, summary_prefix, idle_turns, max_rounds, ...)` 声明域，并使用通用工厂 `focus_start_spec` / `focus_finish_spec` 生成首尾工具（零全局配置键绑定，参数显式携带）。
   - 在 `F(...)` 每一次向 LLM 发起请求前，统一由 `FocusPort.resolve_tools(chat_id, registry, exited_this_turn)` 计算 `ToolView`（常态仅暴露 `entry_tool`；聚焦内收敛为白名单；同轮已退出则隐藏 `entry_tool` 防重入）。
3. **标准出口规范（写入闸门 + 原地覆写）**：
   - 每条消息落盘前经 `FocusHook.classify_persist()` 判定：属于本批已退出域的工具消息与过程思考直接丢弃；
   - 退出时由纯函数按时间顺序保留聚焦期间插入的真人对话，将所有聚焦工作痕迹原地替换为一条 `role="user"` 总结（兼容 OpenAI `tool_calls`/`tool` 成对校验，彻底去除 Yuki 历史兼容字段）；
   - 启动期自动执行 `sweep_orphans()` 清理进程异常中断遗留的孤儿工作片段。

### 3.4 可调参生物钟与策略决策 (`frostcore.rhythm`)

- **默认常数 `1.0`**：`BioClock` 的默认时间曲线 `TimeCurve = Callable[[float], float]` 为 `ConstantClock(1.0)`。开箱即保持平稳可用，不因深夜衰减造成新手困扰。
- **自定义曲线采样**：用户可传入任意对时间采样的曲线函数（如正弦波、分段函数或 SDK 附带的可选 `GaussianClockPreset`）驱动精力上限与活跃基准，配合 `RhythmStateStore` 持久化进 `FrostSeed.rhythm_snapshots`。
- **策略解耦**：由宿主注入 `PolicyResolver` 返回 `ChatPolicy(dormant, debounce_seconds, force_reply, allow_skip, speaker_weight)`，配合可注册 `DecisionFactor` 列表完成“群聊/私聊/特权通道/休眠/防套娃”全部语义，内核不写死任何平台或称呼。

### 3.5 `DiaryEngine`：推荐内置与防并发冲突协议 (`frostcore.memory.diary`)

日记功能配置上**允许关闭**，但**强烈推荐默认开启**，它是长期人格构建的基石。为避免 `DiaryEngine` 总结写盘与核心求值函数 `F(...)` 并发篡改会话滑窗，强制采用**「水位线 + 两阶段无长锁切片」**协议：

1. **Phase 1（短持 `chat_lock` 取快照）**：检查 `not consolidating[chat_id]` 且当前未处于聚焦模式，通过 `DialogueFilter` 提取纯对话，记下最高序列号 `watermark_seq`，置 `consolidating[chat_id] = True` 后**立刻释放 `chat_lock`**（后台总结绝不卡住群聊响应）。
2. **Phase 2（无锁异步生成 + 只追加落盘）**：调用可定制的 `DiarySummarizer` 生成第一人称日记，经 `FrostSeed` 单写队列执行 `append_diary()`。
3. **Phase 3（再短持 `chat_lock` 按水位线切片）**：重新加锁，将 `seq <= watermark_seq` 的旧对话截断保留最近 `keep_last_turns` 条，**原封不动保留 `seq > watermark_seq` 期间由 `F(...)` 新产生的所有对话**；若期间会话已进入聚焦模式，仅安全清理聚焦前旧片段，不触碰活跃工作区。

### 3.6 可观测、只读守卫与探针契约 (`frostcore.observability`)

- **结构化事件契约 (`EventSink`)**：内核关键节点（模式切换、能力门禁拒绝 `mode.capability_denied`、求值结束/错误、工具耗时、聚焦进出、日记落盘、健康告警）统一发出 `StructuredEvent`；内置 `JsonlEventSink`（强制脱敏 `api_key`/`token`/`secret`/`authorization` 与 `data:image/` 大载荷）、`MemoryEventSink` 与 `NullEventSink`，文本截断采用字素簇感知 `safe_truncate()` 防止切断 ZWJ Emoji 序列。
- **独立线程 `/health` 探针 (`HealthProbeServer`)**：采用标准库 `ThreadingHTTPServer` 独立线程运行（不占用 `asyncio` 主循环），支持注册多个 `FrostApp` 探针回调汇总多 Bot 就绪状态（全就绪返 HTTP `200`，未就绪返 `503`）。
- **`DRY_RUN` 与只读守卫 (`FROSTCORE_DRY_RUN` / `ReadOnlyPersonaSnapshot`)**：试启动模式仅完成配置/种子锁/只读快照校验与探针置位而不接管外部渠道；`ReadOnlyPersonaSnapshot.verify_composed()` 支持校验 `ComposedPrompt.persona_block` 精确 SHA-256 或在动态拼接时间/记忆槽位时校验核心人格锚点完整保留。外层容器只读挂载与自进化模板置于 `examples/deploy/`，不侵入核心包。

---

## 四、开发与扩展公约（FrostCore Conventions）

所有基于 `FrostCore` 构建的宿主应用、插件与二开模块，应共同遵守以下 6 条公约：

### 公约 1：唯一存在与单进程多 Bot 公约（Single-Seed Invariant & Explicit DI）
- 同一份 `FrostSeed` 在任意时刻**严禁**被两个进程或同进程内的两个 `FrostApp` 实例同时打开（违者触发 `SeedLockedError`）。
- 内核禁止模块级可变全局单例；同一个宿主进程可通过显式依赖注入运行多个 `FrostApp`（多 Bot），前提是每个 `FrostApp` 绑定各自独立的 `FrostSeed`；同一 Bot 多平台陪伴的标准拓扑仍是**单 `FrostApp` 挂载多个 `ChannelAdapter`**。

### 公约 2：灵魂与肉身分离公约（De-Peripheralized Memory）
- 写入 `FrostSeed.diaries` 与 `entities` 的文本应坚持**去外周化**：剥离平台专有控制码（如 CQ 码、Markdown 卡片 JSON）及底层工具调试回显，只沉淀第一人称经历、情绪与关系印象。
- 跨平台身份通过 `EntityRef.entity_id` 与别名表关联，避免因更换通讯软件而丢失长期默契。

### 公约 3：可组合消息流公约（Middleware Pipeline）
- `<layout>` 隐匿独白、`[MEME:情绪]` 表情插槽、潜意识小本本、图片预取与 SFT 轨迹采集均作为 `InboundMiddleware`、`PromptComposer` 或 `OutboundMiddleware` 插入，**不得侵入微内核主求值循环 `F`**。
- 中间件必须支持清晰短路（如指令拦截、休眠静默）与幂等兜底，异常不得导致 `chat_lock` 死锁或 `FrostSeed` 半写入。

### 公约 4：外挂模式与唯一体性公约（面向“自主轮”等扩展）
- 如需接入类似 Yuki「自主轮」的非聊天模式，必须通过 `Mode` + `ModeCapabilities` 向 `ModeRouter` 注册，并严格遵守全局单非聊天模式互斥锁与**机制强制的能力门禁**：
  - `can_send=False`、`writes_chat_history=False`、`allow_sub_focus=False`、`triggers_diary=False` 由 `FrostApp`、`SessionPipeline`、`FocusManager` 与 `DiaryEngine` 在执行出口强制拦截并上报 `mode.capability_denied`（`CHAT_CAPABILITIES` 默认 `allow_sub_focus=True`）；
  - 模式退出后由 `ModeRouter` 统一将冻结期缓冲的真人消息转换为 `SystemInjectedEvent(system_kind="catchup")` 交付 `SessionPipeline` 补台；
  - 若中途失败或主动放弃（`do_nothing` / `abandon`），必须保持 `HistoryStore` 与 `FrostSeed` 零痕迹。

### 公约 5：异步后台委托公约（面向“小女仆 / SubAgent”等扩展）
- 后台重型子代理完全由宿主管理生命周期，通过 `SystemInjectedEvent(system_kind="subagent_report")` 将结果投递回内核：
  - 系统注入事件**不得**计入日记对话轮次阈值，也**不得**提前解除人工等待订阅；
  - 若此时该会话正处于可接收内部事件的非聊天模式（`capabilities.accepts_inner_event=True`），应优先由 `ModeRouter.deliver_inner_event()` 消费而非直接发往外周平台；
  - 被用户强制取消的后台任务严禁回写 `HistoryStore`。

### 公约 6：契约测试与可观测自证公约（Contract-First Verification）
- 内核随包提供 `frostcore.testing`（含 `FakeLLMClient`、`MemoryChannelAdapter`、`FakeClock` 与各组件契约验证函数）。
- 任何新增的 `FocusDomain`、`Mode`、`RecallPlugin`、`ChannelAdapter`，均须纳入离线 `pytest` 契约测试并通过（无网络、无真实 API Key、全 `tmp_path` 隔离），禁止破坏既有状态机不变式与公共契约（SemVer）。

---

## 五、独立仓库建设路线（`/home/asumi/FrostCore`）

| 阶段 | 目标 | 核心交付物 | 状态与验收标准 |
|---|---|---|---|
| **M1 · 种子与微内核骨架** | 跑通 `FrostSeed` + `F(TurnInput)` + `FocusPort` + `ModeRouter` + 探针/事件契约 | `pyproject.toml`、`contracts/`、`observability/`、`memory/`、`focus/`、`modes/`、`kernel/`、`testing/` | **已完成**：离线 `pytest` 覆盖双开锁拒启动、Focus 写闸门、模式互斥与 `F` 确定性回放 |
| **M2 · 生命体支柱、消息流与 Quickstart** | 跑通生物钟、日记并发协议、CJK FTS5 召回、消息中间件、多 Bot 装配与 CLI Quickstart | `rhythm/`、`memory/`（FTS5 + `DiaryEngine`）、`llm/`、`SessionPipeline`、`FrostApp`、`adapters/cli.py`、`examples/01~03` + `examples/deploy/` | **已完成**：验证默认 `1.0` 与高斯曲线、水位线并发防覆盖、单进程多 Bot 独立 Seed 运行、`/health` 聚合与 `DRY_RUN` |
| **M2.5 · 内核闭环加固与文档体系** | 修复人格护卫动态槽位误报、补全 `ModeCapabilities` 机制门禁、纯化 `F` 原子落盘、全异步节奏 I/O 与 $O(1)$ 启动索引 | `verify_composed`、`ModeCapabilities` 4 项门禁、纯 `TurnEvaluator` + `SessionPipeline` 原子提交、`a_*` 异步 API、`chat_sessions` 索引、`concurrent_safe`、`docs/architecture.md` & `extension-guide.md` | **已完成**：39 项离线测试、`mypy --strict` 与 `ruff` 全绿 |
| **M3 · 调度原语、主动性与外挂生态验证** | 补充生命周期托管、破冰心跳、流式/多模态链路、Builder 与外挂示例 | `ModeRunner`、`IceBreakMonitor`、`MediaAttachment` 渲染与流式接口、`FrostAppBuilder`、外部 `AutonomousMode`/`ReplyWatch` 插件示例 | 外部开发者/Agent 仅凭文档与示例即可接入新平台、新 FocusDomain 与自主模式 |
| **M4 · Yuki 迁移与扩展插件化** | 将向量 RAG、`<layout>`/`[MEME:]`、Autonomous、Maid 抽为独立包并由 Yuki 接入验证 | `frostcore-rag-chroma` 等可选扩展包 + Yuki 适配层 | Yuki 原有核心场景与测试基线全通过 |
