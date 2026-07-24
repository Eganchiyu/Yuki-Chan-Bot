# YukiV6 更新日志

所有 notable changes 都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 新增
- 主人状态监控接入 GPS-VPS 接收端，`get_master_status` 返回最新手机定位状态
- GitHub Push 卡片补充 Compare API 提交详情、提交评论数、文件数量、代码增删统计和比较链接
- GitHub 仓库监控新增 Pillow 事件小卡片渲染，并复用 WebSocket 图片发送逻辑推送到指定群聊
- 新增 `get_master_status` 工具，返回主人在线状态、活跃状态和当前聚焦窗口标题
- 增强 LiveYukiL2D minimal 桌宠的待机微笑张嘴、标准眼睛参数眨眼回退与轻微风场物理效果
- 新增 `docs/core-technical-debt.md`，梳理 `core/` 模块当前技术债、影响范围、整改优先级与短期落地清单
- 新增 `skills/video_understanding.py` 视频理解 skill：读取视频信息、均匀采样 4 帧、拼接四宫格压缩后调用配置中的视觉模型进行概括或问答，并加入文件类型、大小、时长、提示词长度和请求超时限制
- 新增主人私聊双模系统（`master_private` 模式）：群聊运行时自动接受主人私聊消息，维护独立的私聊上下文，使用专属个人助手 prompt，必回、无防抖、带完整工具链
- 新增 `get_yuki_setting_master_private()` 主人私聊专用 prompt，身份为专属小助手而非代管模式
- 新增 `config.py` 中 `StructuredMemoryConfig` 配置组，支持通过 `config.yaml` 控制结构化记忆开关和召回数量参数（`enabled`、`max_profiles`、`max_facts`、`max_summaries`），默认关闭

### 变更
- 调整 minimal Live2D 呼吸幅度、鼠标跟随灵敏度与阻尼，使头部和身体待机动作更自然
- 将 `core/maid.py` 解耦为边界判定、通用常量、运行时工具、外部工具、提示词、主循环和 Worker 模块，保留 `core.maid` 兼容导出
- 将 `core/engine.py` 解耦为回复工具链、回复决策、日记摘要和后台监控 service，保留 `YukiEngine` 门面调用方式不变
- 二次重新评估 `docs/core-technical-debt.md`：将当前重点调整为历史并发一致性、消息失败恢复、后台任务生命周期、Maid 执行边界和核心行为测试缺口，并更新 P0/P1/P2 整改顺序与状态清单
- 统一 `ToolResult` 工具结果协议，使用稳定错误码，增加参数校验、超时保护和异常脱敏
- 删除 `HistoryManager` 的 `get_chat` / `append_chat` 历史兼容别名，统一使用 session 级接口
- 删除 `prompts.py` 中废弃的重复上下文构建实现，保留唯一生效路径
- 将空闲日记摘要回写收敛为 `HistoryManager.replace_session()`，避免后台巡检通过全量 `load()`/`save()` 覆盖其他会话的并发更新
- 重构 `core` 会话数据流：历史管理器返回独立 session 快照并提供原子替换接口，工具上下文不再持有完整历史字典，小女仆 Worker 迁移到 `core/maid.py`
- 收敛 `core` 会话历史写入入口：新增 `HistoryManager.get_session()` 与 `append_session_message()`，让工具链、小女仆回调和主人私聊同步统一通过会话级接口落盘，减少跨模块直接改 `history_dict`
- 移除 `YukiEngine._append_session_message()` 私有重复写入逻辑，工具链阶段性文本、工具结果和工具期间新增消息统一委托 `HistoryManager` 写入
- 移除 `modules/LiveYukiL2D/main.py` 未使用薄入口，保留 `desktop.py` 与 `server.py` 的启动/服务职责边界
- 合并 LiveYukiL2D 桌宠启动入口，将 Electron 启动逻辑统一迁入 `modules/LiveYukiL2D/desktop.py`
- 简化 `modules/LiveYukiL2D/desktop.py` 桌宠窗口启动与桌面 API 逻辑，移除多余包装并复用鼠标穿透配置值
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
- 将 LiveYukiL2D 鼠标视觉跟踪逻辑独立到 `frontend/minimal/src/mouse_tracker.ts`，降低入口耦合并便于后续调整坐标和跟随策略
- 优化 LiveYukiL2D 鼠标视觉跟踪：缓存桌面坐标、按渲染帧消费最新位置，以 Live2D 头部视觉中心进行相对定位并使用时间无关的指数平滑，降低 IPC/布局查询开销并改善跟手性
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
- 修复启动后台任务时小女仆 Worker 导入到同名模块导致 `'module' object is not callable` 的问题
- 修复退出清理阶段调用不存在的 `cfg._save_raw()` 导致配置保存报错的问题
- 修复 GitHub PushEvent 的 Events API 不返回 commits 详情导致通知显示 0 条提交的问题，改用 Compare API 获取并展示提交信息
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
