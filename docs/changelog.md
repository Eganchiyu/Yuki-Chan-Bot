# YukiV6 更新日志

所有 notable changes 都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 新增
- 新增主人私聊双模系统（`master_private` 模式）：群聊运行时自动接受主人私聊消息，维护独立的私聊上下文，使用专属个人助手 prompt，必回、无防抖、带完整工具链
- 新增 `core/private_context.py` 私聊上下文管理器：支持保存群聊上下文快照到 `data/private_context.json`，最多保留 50 条，支持按群聊过滤召回
- 新增 `recall_private_context` 工具：主人私聊时可召回最近的群聊上下文快照，了解群里发生了什么
- 增强 `send_master_private` 工具：新增 `reason` 参数，发送私信时自动保存群聊上下文快照，消息同步写入主人私聊的 `chat_history.json`
- 新增 `get_yuki_setting_master_private()` 主人私聊专用 prompt，身份为专属小助手而非代管模式
- 新增 `config.py` 中 `StructuredMemoryConfig` 配置组，支持通过 `config.yaml` 控制结构化记忆开关和召回数量参数（`enabled`、`max_profiles`、`max_facts`、`max_summaries`），默认关闭

### 变更
- `napcat_listen()` 支持群聊模式下同时接收主人私聊消息，路由为 `master_private` 模式
- `SessionPipeline.decide_reply_action()` 对 `master_private` 模式跳过精力决策，强制回复
- `SessionPipeline.prepare_message_batch()` 对 `master_private` 模式跳过防抖，立即处理
- `SessionPipeline.send_reply()` 和 `YukiEngine._send_tool_thought()` 对 `master_private` 模式使用私聊 API（`send_private_msg`）发送
- `sync_system_prompts()` 对主人 QQ 号的 chat_id 注入 `master_private` prompt 而非代管 prompt
- `_chat_with_tools()` 将 `history_manager` 传入 ToolContext metadata，供工具写入跨会话历史
- `YukiMemoryRetriever` 改为从 `cfg.structured_memory` 读取开关和召回数量，移除 `enabled` 参数硬编码
- `SessionPipeline.retrieve_memories()` 移除重复的 `top_k` 硬编码，统一由 retriever 从配置读取
- 新增 `modules/debug/context_snapshot.py`、`modules/debug/webui_server.py` 和 `scripts/debug_tools/start_context_debug_webui.py`，提供本地只读 Context Debug WebUI、快照 API、自动刷新页面、上下文复制/导出与敏感字段脱敏
- Debug WebUI 支持通过 `YUKI_CONTEXT_DEBUG_WEBUI=1` 在主程序进程内后台启动，共享实时 snapshot store，避免独立进程无法读取主程序内存快照
- `SessionPipeline` 与 `YukiEngine.api_reply()` 接入轻量 debug snapshot，记录输入合并、回复决策、旧 RAG/Yuki-Memory 召回、完整 LLM messages 与 pipeline 阶段耗时，不改变主回复流程
- 新增 `docs/context-debug-webui-plan.md`，规划用于实时观察 Yuki 状态、完整 LLM 构建上下文、旧 RAG 与 Yuki-Memory 召回结果的本地 Debug WebUI
- 新增 `docs/yuki-memory-runtime-guide.md`，记录 Yuki-Memory 当前开发状态、操作手册、函数说明、离线处理流程和下一步计划
- 新增 `docs/yuki-memory-plugin-guide.md`，记录 Yuki-Memory 插件接入方式、接口示例、扩展点和接入禁忌
- 新增 `modules/yuki_memory/retriever.py`，为主流程提供 Yuki-Memory 结构化上下文检索适配层，支持 profile/fact/summary 分层召回并失败回退旧 RAG
- 新增 `build_structured_memory_prompt()`，在回复上下文中注入结构化长期记忆，同时保留旧 `MemoryRAG.search_diaries()` 回忆作为补充
- 新增 `modules/yuki_memory/consolidator.py` 多层压缩整理器，支持原始对话→粗样本→重叠 buffer 摘要→结构化候选→短日记→可选写入 `yuki_memory` 的旁路管线
- 新增 `scripts/03_RAG_Tools/consolidate_runtime_memory.py`，支持从聊天历史中对指定群聊 dry-run 多层整理，并可通过 `--base-url`/`--api-key`/`--model` 指定测试 LLM
- 更新 `docs/development-plan.md`，新增 Yuki-Memory 分阶段开发计划并标注当前程序运行状态
- 增强 `scripts/03_RAG_Tools/backfill_memory_candidates.py`，支持 chat_id 过滤、随机抽样、时间排序、batch 进度、失败重试、错误 JSONL、统计报告、`--base-url`/`--api-key`/`--model` 自定义 API 配置，以及鉴权/key 过期错误立即暂停与连续失败熔断
- 使用小米 MiMo `mimo-v2.5-pro` 完成 20 条小批量候选提取验证：20 条日记→87 条候选，类型分布 fact 36/event 27/relationship 11/profile 10/preference 2/todo 1，全部 low risk，0 失败
- 新增 `scripts/03_RAG_Tools/review_memory_candidates.py`，支持候选自动审核、低价值过滤、同主体同类型相似去重，并输出 approved / needs_review / rejected / review_report
- 新增 `scripts/03_RAG_Tools/import_memory_candidates.py`，支持将审核通过候选转换为 `MemoryRecord` 并 dry-run/真实导入 `yuki_memory` collection
- 阶段 D/E 管线已用当前主群聊 650 条提取结果验证：2248 条候选审核为 approved 1779 / needs_review 336 / rejected 133，导入 dry-run 1779 条 0 失败
- 阶段 C 主群聊结构化候选提取持续后台运行，当前 `chat_id=1057020972` 已输出 705 / 1955 条日记结果，错误 1 条；使用 `--resume` 和 `--max-consecutive-failures 5` 保证可暂停、可续跑、鉴权失败可停机提示
- 新增 `modules/yuki_memory/` 第一阶段骨架，提供 `MemoryRecord`、`YukiMemoryStore` 和 `LegacyDiaryMigrator`，支持独立保存/检索标准记忆

### 移除
- 清理 `modules/LiveYukiL2D/liveyuki_l2d` 中未接入的独立 LLM 管线、运行时状态和未使用协议 helper
- 移除语音转写功能（`parse_Audio_CQ_codes`、`fetch_ptt_text` 调用），修复运行异常问题
- 移除 `CQParser.sender` 延迟初始化依赖
- 移除 `CQProtocol.extract_audio_file_ids` 方法
- 移除 `session_pipeline.py` 中 `voice_message_id` 提取逻辑
- 移除 `main.py` 中 `parser.sender = sender` 赋值
- 新增 `scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py`，支持将旧日记备份 dry-run、limit、resume 迁移到 `yuki_memory` collection
- 新增 `tests/test_yuki_memory_store.py`，覆盖 yuki-memory metadata、存储检索、旧日记转换和迁移脚本
- 新增 `scripts/03_RAG_Tools/backfill_memory_candidates.py`，支持从日记备份中离线 dry-run/断点续跑提取结构化长期记忆候选
- 增强 `scripts/03_RAG_Tools/export_memory.py`，导出全量记忆时同步生成日记数量、重复项、长度、时间范围和 metadata 标准字段统计
- 新增 `MemoryRAG.save_memory()` 标准化记忆写入接口，支持 `type/status/confidence/importance/supersedes/source_ids` 等 Hy-Memory Lite 元数据
- 新增 `tests/test_toolchain.py`，覆盖 `ToolSpec`、`FunctionRegistry` 和 `ToolCallManager` 的最小 smoke test
- 新增 `docs/toolchain-usage.md`，整理 `core/toolchain.py` 与 `core/tools.py` 的调用流程、标准工具清单、扩展步骤和排查建议
- 破冰流程主管道集成测试：新增 `tests/test_ice_break_pipeline.py`，覆盖纯函数、提示词注入、管道阶段、监控集成和端到端传播共 12 个 smoke test
- 工具链新增 Tavily 网络搜索适配，支持通过 `TAVILY_API_KEY` 环境变量调用实时网页搜索
- 工具链定时任务升级为精确定时唤醒，到点后通过主管道触发 Yuki 回复

### 变更
- 收紧 `review_memory_candidates.py` 审核规则：event importance<3 直接拒绝、importance<=3 需匹配低价值关键词；fact/preference/relationship importance<=1 归入 needs_review；全量审核 approved 从 9950 降至 4297，event 从 3614 降至 397
- 增强 `YukiMemoryRetriever._dedupe()`，按 (type, subject) 分组去重，每组只保留 importance/confidence/score 最优条目，避免同主体重复记忆污染上下文
- 增强 `build_structured_memory_prompt()`，增加跨类型内容相似度去重（阈值 0.82），将重复表述压缩为单条最优记忆
- 收紧 `ToolContext` 运行时依赖，工具通过 `context.sender` 与 `context.yuki` 访问必要对象，不再直接依赖完整 `YukiEngine`
- 简化 `ToolCallManager` 状态管理，移除未使用的 session 追踪状态，并改为读取 `cfg.timing.tool_call_delay_seconds`
- 调整工具链多轮调用输出行为：工具调用轮次中的模型阶段性文本会实时发送，并从最终聚合回复中移除，避免最后统一释放导致重复或延迟输出
- 优化 QQ 文件发送工具，支持图片、语音和普通文件自动识别，并从群聊 prompt 中移除手写本地 CQ 文件码说明
- 小女仆委托统一保留 function-call 工具路径，移除 prompt 中的标签式委托说明
- **破冰流程主管道化重构**：
  - `ice_break_monitor` 不再直接调用独立的 `break_ice()`，改为通过 `process_callback` 触发主管道 `process_loop(ice_break=True)`
  - `SessionPipeline` 全链路支持 `ice_break` 上下文标记：`prepare_message_batch` 跳过防抖并构建合成输入、`normalize_incoming_content` 跳过消息规范化、`decide_reply_action` 跳过决策强制回复、`finalize_conversation` 递增破冰失败计数
  - `build_chat_context` 新增 `ice_break` 参数，破冰模式下注入专用指令到系统消息中
  - 新增 `get_ice_break_instructions()` 纯函数，替代原 `build_ice_break_prompt()` 的指令构建逻辑
  - `main_process` 和 `process_loop` 新增 `ice_break` 参数透传
  - 破冰回复现在享受完整的工具链能力（表情包搜索、小女仆委托、RAG 记忆检索等）

### 修复
- 修复 `prompts.py` 中 f-string 内中文引号导致的语法错误
- 修复后台定时、破冰和小女仆回调可能绕过普通消息缓冲入口的问题，统一经 `SessionPipeline.enqueue_message()` 串行调度
- 修复点名缩短防抖使用全局状态的问题，改为按 `chat_id` 隔离防抖时间
- 修正生物钟与活跃度衰减注释，使说明与代码实际时间一致，并复用生物钟权重计算逻辑

### 移除
- 移除 `YukiEngine.break_ice()` 独立破冰方法（约 55 行）
- 移除 `build_ice_break_prompt()` 函数（已被 `get_ice_break_instructions` + `build_chat_context` 替代）

---

## [0.10.0] - 2026-06-05

### 新增
- **硬编码敏感信息清理**：
  - 在 `config.py` 中新增 `TargetConfig.whitelist` 字段和 `Config.TARGET_WHITELIST` 属性，支持白名单 QQ 号配置
  - 将 `modules/QQNapcatListen/listen_main.py` 中硬编码的 QQ 号白名单改为从配置读取
  - 将 `core/history_manager.py` 中硬编码的真实姓名改为从 `cfg.MASTER_NAME` 和 `cfg.ROBOT_NAME` 动态读取
  - 将 `modules/memory/rag.py` 和 `setup.py` 中的黑名单默认值改为从配置读取主人名称
  - 将 `scripts/03_RAG_Tools/yuki_memoryDB_tool.py` 中硬编码的 API Key 和 URL 改为从配置读取
  - 将 `scripts/01_api_test_tools/` 目录下多个测试脚本中的硬编码 API URL 改为从配置读取
  - 将 `modules/label.py` 中硬编码的绝对路径改为动态获取项目根目录
  - 将 `network/ws_sender.py` 中硬编码的测试群号改为从配置读取
  - 清理 `core/engine.py` 中包含本机路径和 IP 地址的注释代码块
  - 更新 `blacklist.txt`、`modules/memory/blacklist.txt`、`scripts/03_RAG_Tools/blacklist.txt`，将真实姓名替换为通用占位符
  - 更新 `scripts/01_api_test_tools/teatop.py` 中的测试 Prompt，移除真实姓名
  - 更新 `.gitignore`，添加 `manual_stickers.json`、`temp_expression.png`、`window_list.txt` 防止敏感数据文件被提交

### 变更
- **工具链与小女仆协同第一阶段重构**：
  - 新增 `core/toolchain.py`，提供 `FunctionRegistry`、`ToolCallManager`、`ToolContext` 与 `ToolResult`
  - 新增 `core/tools.py`，将日记查询、定时任务、小女仆委托、主人私密发送、浏览器搜索、QQ 文件发送、外部内容注入包装为统一工具接口
  - `YukiEngine.api_reply()` 接入 OpenAI 兼容 tools 多轮调用流程，保留原有标签式委托与表情包搜索兼容逻辑
  - `utils/llm_client.py` 新增原始 message 返回接口，支持 tool_calls 场景
  - 小女仆新增能力边界判定、标准任务构造与结果报告封装，降低高风险或高成本任务误分发风险
  - `config.py` 补齐旧版大写配置属性与 `_raw` 兼容字段，保持现有测试和旧调用路径可用
  - 同群消息处理改为按 `chat_id` 串行管道，运行中新消息只入队等待，不再取消当前处理任务
  - 工具链调用期间的可见回复、工具结果和新增用户消息会写入当前 session 上下文，避免消息流分叉
  - 工具链新增模型请求、执行参数、执行耗时和 `search_diary` 参数日志，并在工具调用前加入可配置等待时间（默认 1.2 秒）
  - 新增 `config.py` 中 `TimingConfig.tool_call_delay_seconds` 配置项，用于控制工具调用前等待时间
  - `core/engine.py` 新增工具调用日志，记录模型请求的工具名称列表
  - 新增 `core/session_pipeline.py`，将持久会话管道从 `main.py` 抽离，明确按 `chat_id` 串行运行的会话泵职责
  - `main.py` 精简为组件初始化、运行时注入和程序入口编排
  - `modules/QQNapcatListen/listen_main.py` 调整为输入适配层，通过 `configure_runtime()` 注入组件，消除对 `main.py` 的反向导入
  - `core/engine.py` 归并工具链上下文辅助逻辑，减少 `_chat_with_tools()` 内部嵌套职责
  - 更新 `docs/architecture.md`、`docs/development-plan.md`、`README.md` 同步目标架构状态
  - 新增 `docs/api-reference.md`，提供核心模块、标准工具、LLM 客户端和配置管理的 API 接口文档
  - 新增 `docs/deployment-guide.md`，提供环境要求、部署步骤、配置说明和监控维护指南
  - 新增 `docs/troubleshooting.md`，提供启动问题、连接问题、API 调用问题和内存性能问题的排查指南
  - 新增 `docs/module-interface.md`，提供各模块公共方法签名和使用示例
  - 新增 `docs/contributing.md`，提供开发环境、代码规范、Git 工作流和测试规范指南

### 变更
- **修复 RAG 初始化依赖兼容性**：
  - 补充 `onnxruntime` 作为 ChromaDB 必需运行依赖
  - 收紧 `sentence-transformers`、`numpy`、`pandas`、`pyarrow`、`scikit-learn`、`opencv-python` 版本范围
  - 同步更新 `pyproject.toml` 和 `requirements.txt` 依赖清单，保持一致
  - 避免 Windows 环境下 `pyarrow` 原生扩展访问冲突导致启动静默退出

- **main.py 消息处理管道化重构**：
  - 备份原始主程序到 `backup/main_backup_pipeline_20260604.py`
  - 新增 `MessagePipeline`，按阶段拆分消息入口、内容标准化、上下文准备、回复决策、记忆检索、回复生成、消息发送和收尾保存
  - 将 `main_process()` 简化为管道入口，保持原有消息处理行为

- **移除 Provider 模块，内联 LLM 客户端逻辑**：
  - 删除 `providers/` 目录及全部 9 个文件（base、registry、fallback、openai_compatible、deepseek、dashscope、ytea）
  - 新增 `utils/llm_client.py`，内联所有 provider 功能
  - 保留主备故障转移逻辑（熔断 → 切换备用 → 120 秒自动恢复）
  - 保留全局 aiohttp Session TCP 连接复用
  - 系统退化至使用配置文件直接管理 API 参数
  - 更新 `README.md`、`docs/architecture.md` 同步文档

- **移除 WebUI 管理面板**：
  - 删除 `webui.py` 文件（Gradio WebUI 配置面板）
  - 从 `main.py` 中移除 `start_webui()` 函数及其调用
  - 从 `main.py` 中移除 `from webui import build_ui` 导入
  - 简化主程序启动流程（步骤编号从 5 步减少到 4 步）

---

## [未发布] - 2026-06-01

### 新增
- **FunctionRegistry**: Function Call 注册中心
  - 支持批量扫描注册（`scan_and_register`）
  - 支持单个注册/注销
  - 支持获取 tools 列表
  - 支持获取 handler 函数

- **项目文档**：
  - `docs/architecture.md`: 项目架构文档
  - `docs/development-plan.md`: 开发规划
  - `docs/changelog.md`: 更新日志

- **项目公约**：
  - `.trae/rules/project_rules.md`: 项目开发规范

### 变更
- **main.py 初始化重构**：
  - 提取 `initialize_components()` 函数
  - 提取 `start_webui()` 函数
  - 提取 `warmup_groups()` 函数
  - 简化 `__main__` 块（从 100+ 行减少到 30 行）

- **listen_main.py 简化**：
  - 提取 `start_background_tasks()` 函数
  - 提取 `handle_group_switch()` 函数
  - 简化 `napcat_listen()` 函数

### 修复
- 无

### 移除
- 无

---

## [0.9.0] - 2026-05-30

### 新增
- **重构规划文档**：
  - `docs/完全重构规划：架构评估与新蓝图.md`
  - 定义了 LLM 中枢 + 插件协议的目标架构
  - 定义了 InboundMessage / OutboundMessage 消息协议
  - 定义了 PluginBase 插件基类

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.8.0] - 2026-05-15

### 新增
- **Function Call 讨论**：
  - 学习 OpenAI Function Call 标准格式
  - 规划 6 个 Function 的 Schema 设计
  - 讨论主循环 + 消息队列架构

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.7.0] - 2026-05-01

### 新增
- **小女仆系统**：
  - 实现 `core/maid.py` 子代理系统
  - 支持异步任务队列
  - 支持多步骤任务分解

- **表情包系统**：
  - 实现 `modules/stickers/manager.py`
  - 支持表情包学习与 RLHF
  - 支持正反馈捕捉

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.6.0] - 2026-04-15

### 新增
- **RAG 记忆系统**：
  - 实现 `modules/memory/rag.py`
  - 集成 ChromaDB 向量数据库
  - 集成 text2vec-base-chinese 嵌入模型
  - 支持日记存储与检索
  - 支持关键词提取（jieba）

- **视觉处理模块**：
  - 实现 `modules/vision/processor.py`
  - 支持图片理解（VLM）
  - 支持表情包识别

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.5.0] - 2026-04-01

### 新增
- **Provider 系统**：
  - 实现 `providers/registry.py` Provider 注册中心
  - 实现 `providers/base.py` Provider 基类
  - 实现 `providers/fallback.py` 故障转移 Provider
  - 实现 `providers/deepseek.py` DeepSeek Provider
  - 实现 `providers/dashscope.py` 阿里灵积 Provider

- **配置管理**：
  - 实现 `config.py` 配置管理
  - 支持 YAML 配置文件
  - 支持配置热重载

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.4.0] - 2026-03-15

### 新增
- **精力值系统**：
  - 实现精力值计算与恢复
  - 实现活跃度感知与衰减
  - 实现欲望演算系统

- **破冰系统**：
  - 实现破冰监控
  - 实现无人理睬计数器

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.3.0] - 2026-03-01

### 新增
- **WebUI 管理面板**：
  - 实现 `webui.py`
  - 支持配置管理
  - 支持状态监控

- **日志系统**：
  - 实现 `utils/logger.py`
  - 支持文件日志
  - 支持控制台日志
  - 支持调试模式

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.2.0] - 2026-02-15

### 新增
- **消息处理**：
  - 实现 `modules/message/CQParser.py` CQ 码解析器
  - 实现 `modules/message/CQProtocol.py` CQ 协议工具
  - 支持 @、回复、图片等消息类型

- **历史记录**：
  - 实现 `core/history_manager.py`
  - 支持按群聊隔离
  - 支持 JSON 持久化

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## [0.1.0] - 2026-02-01

### 新增
- **项目初始化**：
  - 创建项目结构
  - 实现基础 WebSocket 连接
  - 实现基础消息监听
  - 实现基础消息发送

- **核心模块**：
  - 实现 `core/brain.py` 状态管理
  - 实现 `core/engine.py` 主引擎
  - 实现 `core/prompts.py` 提示词管理

### 变更
- 无

### 修复
- 无

### 移除
- 无

---

## 版本说明

### 版本号规则

- **主版本号（Major）**：重大架构变更、不兼容的 API 修改
- **次版本号（Minor）**：新功能添加、功能增强
- **修订号（Patch）**：Bug 修复、文档更新

### 状态标签

- **[未发布]**：正在开发中，尚未发布
- **[x.y.z]**：已发布的版本

### 变更类型

- **新增**：新功能
- **变更**：现有功能的变更
- **修复**：Bug 修复
- **移除**：移除的功能

---

**最后更新**：2026-06-01  
**维护人员**：项目开发团队
