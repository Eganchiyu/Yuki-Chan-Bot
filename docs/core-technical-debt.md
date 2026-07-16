# core 模块技术债分析

## 1. 范围

本文只梳理 `core/` 目录内的技术债，覆盖：
- [brain.py](file:///d:/Projects/YukiV6/core/brain.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)
- [prompts.py](file:///d:/Projects/YukiV6/core/prompts.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)

## 2. 总体结论

`core/` 已完成第一轮结构性重构，当前不能再按“单体脚本、完全没有边界”评价。会话级历史 API、统一工具结果协议、按会话串行化、破冰主管道和小女仆 Worker 边界已经形成，上一轮最突出的“写入入口分散”和“功能旁路”风险明显下降。

当前风险重心已经转移到运行时可靠性：
- 后台摘要可能用旧快照覆盖新消息，历史持久化失败也没有明确的脏状态和恢复语义
- 消息从缓冲区取出后，管线失败缺少统一重试、恢复或死信策略
- `YukiState` 仍混合业务状态、会话状态和后台任务状态，且 `chat_id` 键类型不完全统一
- 无限循环和 `asyncio.create_task()` 缺少统一的启动、取消、等待和异常回收机制
- Maid 仍暴露终端、文件和依赖安装等高风险执行面，关键词拦截不能替代权限隔离
- 核心行为测试覆盖不足，部分测试仍是失败占位或使用过期的管线假设

因此，当前阶段的首要目标不是继续增加功能，而是建立可证明的历史一致性、消息可靠性、任务生命周期和执行边界。

## 2.1 相较上一轮的变化

**已明显缓解**
- `HistoryManager.get_session()`、`append_session_message()`、`replace_session()` 已成为主要会话读写入口，工具链、小女仆回调和主人私聊同步不再高频读写整份 `history_dict`。
- `ToolResult`、参数校验、超时保护和异常脱敏已在 `ToolCallManager` 中统一，基础协议测试已覆盖。
- 破冰流程已纳入 `SessionPipeline`，不再维护独立的旁路回复链。
- `maid_worker()` 已迁移到 [maid.py](file:///d:/Projects/YukiV6/core/maid.py)，`engine.py` 不再承担后台任务消费入口。

**仍未解决且风险上升为主要问题**
- 会话 API 解决了可变对象越权修改，但没有解决摘要、批量替换和写盘失败之间的版本一致性问题。
- 按会话锁只覆盖部分管线处理，跨后台任务、工具回调和文件存储的并发语义仍不完整。
- `engine.py`、`maid.py` 的单文件职责仍然过重；Worker 迁移只是边界修正，不是文件级拆分的完成。
- 工具协议测试集中在执行器，尚未覆盖工具副作用、发送失败、私聊快照并发和 Maid 安全策略。

本次评估为静态审查结论，未将未执行的测试结果视为验证证据。

## 3. 主要技术债

### 3.1 运行时状态分散，键规范不统一

**涉及文件**
- [brain.py](file:///d:/Projects/YukiV6/core/brain.py)
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- `YukiState` 同时保存精力、活跃度、消息缓冲、定时器、小女仆任务、用户映射和破冰计数等多类状态。
- 部分状态由 `YukiState` 持有，部分由 `SessionPipeline`、`tools.py` 和 `HistoryManager` 分别持有，尚无明确的 runtime/session/persistent 所有权模型。
- 不同入口对 `chat_id` 的处理不完全一致，存在原始类型和 `str(chat_id)` 混用的风险。

**问题**
- 状态来源不唯一，容易出现内存态、会话快照和持久化历史不同步。
- 同一个会话可能因为键类型不同落入多个运行时条目，导致防抖、能量和任务状态表现不一致。
- 后续引入并发或多进程时，当前模型缺少统一的状态边界和冲突处理方式。

**建议**
- 统一会话上下文模型，明确哪些状态属于 `session`，哪些属于 `runtime`，哪些属于 `persistent`
- 尽量让 `SessionPipeline` 成为唯一的会话编排入口，其他模块只消费上下文，不直接改会话主结构
- 小女仆、定时任务、私聊快照等独立能力改成各自的状态仓库

**已有缓解**
- 会话历史的主要读写已收敛到 `HistoryManager` 的 session API，降低了可变缓存被直接修改的风险。
- `YukiState` 已显式声明 `topic_hormone`，减少了动态扩展字段的隐式约定。

**下一步**：增加统一 `normalize_chat_id()`，按领域拆分 runtime state，并明确每个状态的唯一 owner。

**优先级**：P1

### 3.2 历史一致性与持久化失败语义不足

**涉及文件**
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- `finalize_conversation()` 和后台摘要会基于会话快照执行批量替换，但当前没有会话版本号或 compare-and-swap 保护。
- 摘要任务开始后若同一会话产生新消息，后台结果可能以旧快照为基础回写并覆盖新内容。
- `_save_locked()` 更新内存缓存后写盘失败，缺少 dirty 标记、重试和明确的持久化失败状态；重启后可能回退到旧文件。
- `HistoryManager` 仍以全量 JSON 文件和内存 `_cache` 为基础，没有变更通知或跨进程协调。

**问题**
- 后写的后台结果可能覆盖较新的用户消息或工具结果。
- 写盘失败时调用方难以区分“内存已更新”和“数据已持久化”。
- 工具、摘要和管线收口并发执行时，缺少冲突检测和合并规则。

**建议**
- 为 session 增加版本或变更序号，批量替换使用 compare-and-swap。
- 写盘失败时保留 dirty 状态，提供重试、告警和明确的调用方失败语义。
- 对摘要结果定义冲突合并策略，禁止旧快照无条件覆盖新消息。

**已有缓解**
- session 快照、`append_session_message()` 和 `replace_session()` 已减少直接修改共享字典的路径。
- 空闲摘要已使用 `replace_session()`，但这只能降低全量读写范围，不能替代版本校验。

**下一步**：为 session 增加版本或变更序号；摘要回写前做 compare-and-swap，写盘失败保留脏状态并支持重试或阻断后续覆盖。

**优先级**：P0

### 3.3 消息处理失败后缺少可靠恢复语义

**涉及文件**
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)

**现状**
- `prepare_message_batch()` 会从缓冲区取出消息，随后 `run_once()` 的准备、决策、生成、发送或收口阶段均可能失败。
- 外层主要记录异常，当前没有统一的失败消息重新入队、有限重试、死信或失败状态记录。

**问题**
- 用户消息可能已经从缓冲区消费，但没有生成或发送成功的回复，且不会再次处理。
- 发送失败、历史保存失败和 LLM 失败的恢复策略不同，却没有被建模为明确的状态。

**建议**
- 为消息批次定义处理状态和幂等标识。
- 对 LLM、工具、发送和持久化失败分别定义有限重试与不可恢复路径。
- 保留失败批次的诊断信息，避免仅依赖日志定位丢消息。

**下一步**：定义消息处理状态，明确“已消费、生成失败、发送失败、保存失败”的语义；为可恢复错误增加有限重试，为不可恢复错误进入死信或诊断队列。

**优先级**：P1

### 3.4 后台任务缺少统一生命周期管理

**涉及文件**
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- `idle_diary_checker()`、`ice_break_monitor()` 和 `decay_heartbeat()` 是长期运行的无限循环。
- 摘要、破冰回调、定时任务和工具回调通过 `asyncio.create_task()` 创建，但没有统一保存、取消、等待和异常汇总机制。
- 服务停止、模块重载或测试结束时，后台任务可能残留；任务异常也可能只表现为未处理的后台错误。

**问题**
- 进程关闭时无法保证任务完成、取消或释放资源。
- 后台任务异常缺少统一观测入口，难以判断功能是否已经停止工作。
- 测试无法可靠清理任务，容易产生跨测试污染和事件循环残留。

**建议**
- 统一登记所有后台 `Task`，提供启动、取消、等待和异常汇总入口。
- 为无限循环增加停止事件，并在服务关闭时等待任务退出。
- 回收摘要、定时任务和工具回调任务，避免事件循环残留。

**已有缓解**
- Worker 已迁移到 `maid.py`，减少了引擎中的一类后台消费职责。

**下一步**：建立任务 supervisor，统一登记 `Task`，提供 stop event、取消、等待和异常报告；所有无限循环都必须有可测试的停止条件。

**优先级**：P1

### 3.5 工具链能力扩张快，但边界和测试不足

**涉及文件**
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)

**现状**
- 工具数量已经覆盖日记、定时任务、小女仆、私聊快照、截屏、QQ 文件、地图、网页搜索、图片生成等多个领域
- `ToolContext` 已经开始收敛运行时依赖，但工具实现仍会直接访问较多外部对象
- 工具结果统一由 `ToolResult` 表达，执行器统一处理参数错误、超时和异常脱敏

**问题**
- 工具越多，参数协议越难维护
- 不同工具的返回格式不一致，LLM 侧更容易误判
- 缺少专门的工具层回归测试，改一个工具容易影响别的工具

**建议**
- 统一工具返回格式和错误码风格
- 为每个高风险工具补最小 smoke test
- 清晰区分“查询类工具”“写入类工具”“外部副作用工具”

**优先级**：中高

**本轮重新评估**：工具执行器协议已达到可用基线，但工具副作用边界仍未形成分类和权限模型。当前重点从“统一返回结构”转为覆盖真实工具行为，尤其是发送、定时任务、文件、网络和小女仆委托。

### 3.6 `maid.py` 同时承担协议、执行、适配和安全控制

**涉及文件**
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)

**现状**
- `maid.py` 包含任务边界判断、临时工作区管理、依赖安装、终端执行、文件读取、目录读取、网页搜索、地图搜索、技能运行、任务循环等内容
- 该文件同时是小女仆的执行器、工具库和安全网

**问题**
- 文件过长，理解成本高
- 工具增加时容易让职责继续膨胀
- 安全控制与业务执行混在一起，不利于独立审查

**建议**
- 将“任务编排”“系统工具”“安全限制”拆成独立层
- 把通用文件/目录/终端能力尽量统一到 `tools.py` 的标准工具体系里
- 让 `maid.py` 只保留子代理运行时核心逻辑

**优先级**：中高

**本轮重新评估**：这是当前的高风险执行面，优先级上调为 P0/P1。关键词黑名单、超时和默认禁止写入只能作为应用层防线，不能视为沙箱。短期应限制工作目录、读取范围、依赖来源并补安全测试；中期应使用低权限进程或容器隔离。

### 3.7 prompt 体系仍偏分散，约束容易重复或冲突

**涉及文件**
- [prompts.py](file:///d:/Projects/YukiV6/core/prompts.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- 私聊、主人私聊、群聊、破冰模式分别维护独立 prompt
- 一些回复规范在不同 prompt 中重复出现
- 工具调用约束、身份设定、输出格式要求夹杂在一起

**问题**
- 修改一个输出约束时需要检查多个 prompt
- 容易出现同一行为在不同场景下描述不一致
- prompt 体积继续增长后，维护成本会更高

**建议**
- 把稳定的人设前缀、场景差异、工具约束拆成更明确的组合层
- 统一输出格式约束，减少重复文案
- 保留必要差异，避免多个 prompt 互相打架

**优先级**：中

**本轮重新评估**：prompt 重复仍是维护债务，但相较历史一致性、消息恢复和执行安全属于 P2。应在核心运行时稳定后，按稳定人设、场景差异和工具约束分层组合。

**建议**
- 后续为快照增加结构化字段
- 给快照建立更明确的生命周期和归档策略
- 若使用频率继续上升，再考虑迁移到统一记忆存储

**优先级**：中

**本轮重新评估**：私聊快照仍适合低频轻量场景，但当前全量 JSON 写入无锁、无临时文件替换，并发时可能丢快照或损坏文件。优先补原子写入和进程内锁，再决定是否迁移统一记忆存储。

## 4. 推荐整改顺序

1. **P0：先修历史一致性和执行边界。** 为 session 增加版本校验，处理写盘失败；同时限制 Maid 的工作目录、文件读取、依赖安装和终端执行范围。
2. **P1：补消息可靠性和后台任务生命周期。** 定义批次失败状态、重试与死信；建立统一 task supervisor，支持停止、取消、等待和异常报告。
3. **P1：统一 runtime 状态模型。** 规范 `chat_id`，拆分消息管线、行为模拟、定时任务和小女仆状态的 owner。
4. **P1：补关键行为测试。** 覆盖摘要并发、写盘失败、消息恢复、状态键规范、Maid 安全策略、私聊快照和发送失败；处理 [tests/test_maid.py](file:///d:/Projects/YukiV6/tests/test_maid.py) 的失败占位。
5. **P2：再清理职责和兼容逻辑。** 拆分 `engine.py`、`maid.py`，删除未启用旧决策实现、空兼容接口和旧工具名分支，随后组合 prompt。
6. **P2：同步架构文档。** 更新 [docs/architecture.md](file:///d:/Projects/YukiV6/docs/architecture.md)，使主流程、工具链和后台任务描述与当前 `SessionPipeline` 实现一致。

## 5. 当前状态清单

- [x] 会话历史主要读写路径收敛到 `HistoryManager` 的 session API
- [x] 工具结果协议、参数校验、超时和异常脱敏已形成基础实现
- [x] 破冰流程纳入 `SessionPipeline`，小女仆 Worker 移出 `engine.py`
- [ ] 为 session 增加版本控制和摘要 compare-and-swap，定义写盘失败语义
- [ ] 为消息批次增加失败恢复、有限重试和死信/诊断路径
- [ ] 建立后台任务 supervisor，统一停止、取消、等待和异常报告
- [ ] 统一 `chat_id` 规范并拆分 `YukiState` 中的 runtime 状态
- [ ] 收紧 Maid 文件、终端和依赖安装边界，补充安全测试
- [ ] 补齐 HistoryManager、Engine、Maid、私聊快照和发送失败测试
- [ ] 清理旧兼容路径并同步 `docs/architecture.md`

## 6. 结语

`core/` 已经具备继续演进的结构基础，但还没有达到并发可靠、状态单一归属、后台任务可控、执行权限可审计和测试可防回归的成熟度。下一阶段应优先处理 P0/P1 风险，再进行大范围文件拆分和兼容逻辑清理。
