# core 模块技术债分析

## 1. 范围

本文只梳理 `core/` 目录内的技术债，覆盖：
- [brain.py](file:///d:/Projects/YukiV6/core/brain.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)
- [private_context.py](file:///d:/Projects/YukiV6/core/private_context.py)
- [prompts.py](file:///d:/Projects/YukiV6/core/prompts.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)

## 2. 总体结论

`core/` 已经完成了从单体脚本到分层管线的第一轮重构，但仍存在明显的技术债积累：
- 职责边界已经拆开，但跨模块状态仍然分散
- 工具链、会话管线、小女仆、历史存储之间仍有重复状态和隐式耦合
- 部分实现保留了兼容旧逻辑的分支，导致维护成本上升
- 运行时稳定性依赖较多“约定式约束”，缺少统一的状态模型和测试覆盖

这些债务目前不一定直接导致故障，但会持续放大后续改动成本。

## 2.1 本轮已处理内容

本轮已先处理“会话历史写入分散”和“旧写入路径重复”两类高优先级问题，未一次性拆散所有模块，避免引入过多新文件和迁移风险。

**已落地方案**
- 在 [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py) 中新增 `get_session()` 与 `append_session_message()`，作为会话级读写入口。
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py) 的会话初始化改为通过 `HistoryManager.get_session()` 补齐 system prompt，减少重复初始化逻辑。
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py) 删除私有重复方法 `_append_session_message()`，工具链阶段性文本、工具结果、小女仆回调统一委托 `HistoryManager.append_session_message()` 写入。
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py) 中 `send_master_private` 不再整份 `load()` / `save()` 主人私聊历史，改为追加单条会话消息。
- `append_session_message()` 自动补齐 `time` 字段并立即落盘，保证工具链、小女仆和私聊同步写入格式一致。

**验证结果**
- `python -m pytest tests/test_toolchain.py -q`：9 个测试通过。
- `python tests/test_ice_break_pipeline.py`：15 个脚本入口测试通过。
- 直接用 `pytest tests/test_ice_break_pipeline.py` 仍依赖异步测试插件，当前环境会报插件缺失，这不是本轮代码断言失败。

## 3. 主要技术债

### 3.1 状态分散，跨模块同步成本高

**涉及文件**
- [brain.py](file:///d:/Projects/YukiV6/core/brain.py)
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- `YukiState` 同时保存精力、活跃度、消息缓冲、任务队列、用户映射、破冰计数等多类状态
- `HistoryManager` 使用 `_cache` 缓存历史，`SessionPipeline` 又直接操作 `history_dict`
- 工具层又把部分会话状态放进 `maid_current_tasks`、`maid_task_queue`、`_timer_tasks`、`_timer_handles`
- `engine.py`、`tools.py`、`session_pipeline.py` 都会读写会话相关数据

**问题**
- 状态来源不唯一，容易出现“内存态”和“历史态”不同步
- 功能修改时必须同时理解多个存储点，认知负担高
- 后续若引入并发或多进程，当前模式很难直接扩展

**建议**
- 统一会话上下文模型，明确哪些状态属于 `session`，哪些属于 `runtime`，哪些属于 `persistent`
- 尽量让 `SessionPipeline` 成为唯一的会话编排入口，其他模块只消费上下文，不直接改会话主结构
- 小女仆、定时任务、私聊快照等独立能力改成各自的状态仓库

**本轮进展**：已部分解决
- 已将会话历史读取、初始化和追加收敛到 `HistoryManager.get_session()` / `append_session_message()`。
- `engine.py`、`tools.py` 中高频历史追加路径已不再直接拼接和保存整份 `history_dict`。
- 仍未完全解决 `YukiState` 内 runtime 状态过多的问题，小女仆任务、定时任务、活跃度等状态后续仍需要独立仓库或更清晰的数据结构。

**优先级**：高

### 3.2 兼容旧逻辑过多，行为路径不够单一

**涉及文件**
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [prompts.py](file:///d:/Projects/YukiV6/core/prompts.py)

**现状**
- `engine.py` 中保留了大量注释掉的旧实现和备用方案
- `maid.py` 仍兼容旧工具名、旧提示词输出和临时/固化技能两套路径
- `tools.py` 中部分工具同时保留“返回字符串”和“返回结构化结果”的历史痕迹
- `prompts.py` 里存在多个相近场景的 prompt 变体，风格与约束重复

**问题**
- 旧路径越积越多，容易让新改动误命中过时分支
- 行为不够确定，排查问题时必须先判断当前走的是哪条兼容链路
- 代码可读性下降，单个文件承担了过多“历史包袱”

**建议**
- 逐步删除不再使用的旧分支、注释块和兼容别名
- 明确每个工具和每个场景只有一条推荐路径
- 先清理高频路径，再清理长尾兼容逻辑

**本轮进展**：已部分解决
- 已移除 `YukiEngine._append_session_message()` 这条旧的私有写入路径，统一改用 `HistoryManager.append_session_message()`。
- 已清理 `send_master_private` 中“整份读取主人私聊历史再手动 append/save”的旧路径。
- 仍未处理 `maid.py`、`prompts.py` 中更大范围的旧工具名、旧 prompt 变体和注释块，后续应继续按高频路径分批删除。

**优先级**：高

### 3.3 `engine.py` 职责过重，聚合了过多业务

**涉及文件**
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)

**现状**
- `YukiEngine` 负责对话生成、工具调用、多轮工具链、消息合并、破冰、日记总结、后台小女仆回调
- `engine.py` 末尾还额外放了 `maid_worker()`，进一步扩大了职责范围
- 工具链执行、消息生成、状态处理、后台任务调度都被塞进同一模块

**问题**
- 单文件过大，局部修改容易引发非预期联动
- 单元测试难度高，因为需要同时模拟 LLM、工具链、历史和任务回调
- 后续若要拆分运行时调度和回复生成，会比较痛

**建议**
- 将“对话生成”“工具执行”“后台任务桥接”拆成更清晰的服务层
- `maid_worker()` 独立出去，避免 engine 继续膨胀
- 先抽离低耦合逻辑，再处理高耦合链路

**本轮进展**：已部分缓解
- 已删除 `engine.py` 内部重复的历史追加 helper，降低 `YukiEngine` 对历史数据结构细节的直接负责程度。
- `maid_worker()` 仍保留在 `engine.py`，因为当前 `modules/QQNapcatListen/listen_main.py` 仍直接导入该符号；本轮为了避免扩大改动面，暂未迁移文件位置。
- 下一步更适合先调整导入边界，再将 `maid_worker()` 迁移到 `maid.py` 或独立 worker 模块。

**优先级**：高

### 3.4 历史记录与缓存的一致性风险较高

**涉及文件**
- [history_manager.py](file:///d:/Projects/YukiV6/core/history_manager.py)
- [session_pipeline.py](file:///d:/Projects/YukiV6/core/session_pipeline.py)
- [engine.py](file:///d:/Projects/YukiV6/core/engine.py)

**现状**
- `HistoryManager` 直接把整个 history 缓存在内存 `_cache`
- `SessionPipeline` 中存在多处 `load()` / `save()` 混用
- `engine.py` 也会在工具期间直接追加 session 消息

**问题**
- 并发修改时容易出现后写覆盖前写
- 缓存和磁盘状态没有统一的版本控制或变更通知
- 工具调用期间插入消息时，如果回写顺序错乱，历史可能被污染

**建议**
- 让历史写入集中在管线收口点
- 增加最小粒度的 session 级变更封装，避免模块之间直接操作同一字典
- 后续考虑引入更明确的持久化接口，替代“谁拿到字典谁都能改”的模式

**本轮进展**：已部分解决
- 已新增最小粒度的 session 级封装：`HistoryManager.get_session()` 负责会话初始化，`HistoryManager.append_session_message()` 负责追加消息、补时间戳并落盘。
- 工具链期间插入的阶段性文本、工具结果、工具期间新增消息和小女仆回调，已改为通过统一接口写入。
- `SessionPipeline.finalize_conversation()`、摘要回写等主流程收口点仍保留整份 `history_dict` 保存，这是当前管线批量变更的必要路径；后续可继续拆成 session 级事务接口。

**优先级**：高

### 3.5 工具链能力扩张快，但边界和测试不足

**涉及文件**
- [toolchain.py](file:///d:/Projects/YukiV6/core/toolchain.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)
- [maid.py](file:///d:/Projects/YukiV6/core/maid.py)

**现状**
- 工具数量已经覆盖日记、定时任务、小女仆、私聊快照、截屏、QQ 文件、地图、网页搜索、图片生成等多个领域
- `ToolContext` 已经开始收敛运行时依赖，但工具实现仍会直接访问较多外部对象
- 部分工具在异常、超时、缺参时返回结构不完全一致

**问题**
- 工具越多，参数协议越难维护
- 不同工具的返回格式不一致，LLM 侧更容易误判
- 缺少专门的工具层回归测试，改一个工具容易影响别的工具

**建议**
- 统一工具返回格式和错误码风格
- 为每个高风险工具补最小 smoke test
- 清晰区分“查询类工具”“写入类工具”“外部副作用工具”

**优先级**：中高

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

### 3.8 私聊上下文快照能力已可用，但数据模型还偏轻

**涉及文件**
- [private_context.py](file:///d:/Projects/YukiV6/core/private_context.py)
- [tools.py](file:///d:/Projects/YukiV6/core/tools.py)

**现状**
- 群聊重要事件会保存到 `data/private_context.json`
- 快照只保留最近 10 条上下文和 50 条快照
- 结构主要是消息和原因描述，元数据仍然比较少

**问题**
- 缺少来源类型、优先级、消息主题等更细粒度标签
- 快照查询和召回只能做简单过滤，后续扩展空间有限
- 文件型存储适合轻量场景，但长期可能遇到一致性和检索效率问题

**建议**
- 后续为快照增加结构化字段
- 给快照建立更明确的生命周期和归档策略
- 若使用频率继续上升，再考虑迁移到统一记忆存储

**优先级**：中

## 4. 推荐整改顺序

1. 先收敛会话状态和历史写入路径，降低并发和同步风险。
2. 再拆 `engine.py` 和 `maid.py` 的职责边界，减少单文件过重。
3. 接着清理兼容旧逻辑和重复 prompt，缩短维护链路。
4. 最后补工具层测试与返回格式统一，让扩张速度可控。

## 5. 短期落地清单

- [x] 部分统一 `SessionPipeline` 与 `HistoryManager` 的写入边界：已新增会话级 `get_session()` / `append_session_message()`，并迁移工具链、小女仆回调和主人私聊同步写入路径
- [ ] 把 `maid_worker()` 从 `engine.py` 中拆出：本轮暂缓，需先调整 `listen_main.py` 的导入边界
- [x] 部分清理 `engine.py` 中不再使用的旧实现：已删除 `_append_session_message()` 重复写入逻辑
- [x] 已验证 `send_master_private`、`manage_timer_task`、`send_qq_file` 所在工具链 smoke test：`tests/test_toolchain.py` 通过；`delegate_to_maid` 仍建议补专门测试
- [ ] 整理 `prompts.py` 中重复的回复规范
- [ ] 统一工具返回结构与错误码风格

## 6. 结语

`core/` 的问题不是“功能不够”，而是“功能已经多到开始互相牵扯”。
下一阶段的重点不是再堆能力，而是把状态、职责和边界收紧，否则后续每加一个新能力，维护成本都会成倍上升。
