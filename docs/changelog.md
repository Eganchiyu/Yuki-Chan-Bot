# YukiV6 更新日志

所有 notable changes 都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 新增
- 新增多模式基础框架 `core.modes`，将默认 QQ 群聊包装为 `QQChatMode`，并提供全局唯一聚焦模式状态管理
- 新增浏览器交互占位模块 `modules/browser_interaction`，支持进入浏览器模式、记录步骤、占位扫描和完成后返回来源会话
- 新增模式级工具注册 `ToolRegistryProvider`，支持普通 QQChatMode 与浏览器模式暴露不同工具组
- GitHub Push 卡片补充 Compare API 提交详情、提交评论数、文件数量、代码增删统计和比较链接
- GitHub 仓库监控新增 Pillow 事件小卡片渲染，并复用 WebSocket 图片发送逻辑推送到指定群聊
- 新增 `get_master_status` 工具，返回主人在线状态、活跃状态和当前聚焦窗口标题
- 增强 LiveYukiL2D minimal 桌宠的待机微笑张嘴、标准眼睛参数眨眼回退与轻微风场物理效果
- 新增 `docs/core-technical-debt.md`，梳理 `core/` 模块当前技术债、影响范围、整改优先级与短期落地清单
- 新增 `skills/video_understanding.py` 视频理解 skill：读取视频信息、均匀采样 4 帧、拼接四宫格压缩后调用配置中的视觉模型进行概括或问答，并加入文件类型、大小、时长、提示词长度和请求超时限制
- 新增主人私聊双模系统（`master_private` 模式）：群聊运行时自动接受主人私聊消息，维护独立的私聊上下文，使用专属个人助手 prompt，必回、无防抖、带完整工具链
- 新增 `get_yuki_setting_master_private()` 主人私聊专用 prompt，身份为专属小助手而非代管模式
- 新增 `config.py` 中 `StructuredMemoryConfig` 配置组，支持通过 `config.yaml` 控制结构化记忆开关和召回数量参数（`enabled`、`max_profiles`、`max_facts`、`max_summaries`），默认关闭
- 新增跨平台光标查询 `modules/LiveYukiL2D/liveyuki_l2d/cursor.py`：Windows 走 `GetCursorPos`，X11/XWayland 走 libX11 `XQueryPointer`，Wayland 走合成器（hyprctl / Hyprland IPC）
- 新增普通图片原生视觉输入：`model.llm_native_vision_enabled` 开启后，收到的普通图片不再外挂转写，而是作为 imageUrl 图块直接交给主模型理解，提升截图、文字图等内容的还原度；表情包仍走转写以节省视觉开销
- 新增 `model.backup_native_vision_enabled`：主线路失败切备用时，若备用模型不支持视觉，按需把图片附件转写为文本再发送，避免备用线路 400
- 新增原生视觉限额配置：`native_vision_max_images`（单次张数）、`native_vision_history_turns`（保留轮数）、`native_vision_max_size` / `native_vision_quality`（压缩参数）与图片下载大小/超时限制

### 变更
- 修复日志格式化器窄屏布局遗漏元数据，并增强对应的宽度与行前缀回归测试
- NapCat 接入层合并为单一文件 `network/napcat.py`（`NapCatGateway` 同时承担原 `BotConnector` 与 `MessageSender`），删除 `ws_connection.py` / `ws_sender.py`
- NapCat 读端改为常驻 reader + 帧路由：`echo` 命中挂起请求则唤醒调用方，带 `post_type` 的帧进事件队列，其余丢弃。**出站不再依赖有人消费事件流**，API 响应也不再混进事件流（此前 `send_request()` 的 Future 只有在 `listen()` 被迭代时才会被 resolve）
- `modules/message/` 三个文件（`CQProtocol` / `CQParser` / `GetMeta`）并入 `network/napcat.py`：CQ 码替换、群成员与消息查询、合并转发解析统一收口为网关方法
- 入站适配层 `listen_main.py` 去掉 9 个模块级全局与 `configure_runtime()` 注入式 setter，依赖收敛为 `napcat_listen(gateway, pipeline)`
- 删除 `SessionPipeline.wake_quickly()`：被叫到时改为在真实入队上一次到位（`debounce_flag=False` + `force_reply=True`），不再起"幽灵"入队任务再由真实入队 cancel 它
- 被叫到的判定新增"被 @"：以结构化 `at` 段为准（`messagePostFormat=array`），`raw_text` 兜底且容忍 `[CQ:at,qq=x,name=y]`，`@全体成员` 不算
- 戳一戳恢复"只处理戳到机器人自己"的过滤（原注释里的过滤误写为 `cfg.TARGET_QQ`），并统一按普通消息入队，不再插队
- `main.py` 新增单实例守卫（`data/yuki.lock` 上的 flock，进程退出自动释放；`YUKI_ALLOW_MULTI_INSTANCE=1` 可覆盖），避免两个实例同时消费 NapCat 事件
- QZone 监控与 GitHub 监控的启动改为配置开关（`qzone_monitor.enabled` 默认 false、`github_monitor.enabled` 默认 false），替代原先整段注释与 `getattr` 兜底
- 新增 `pytest` 异步模式配置（`pyproject.toml` 的 `asyncio_mode = "auto"`），修复 13 个未标注 `@pytest.mark.asyncio` 的用例被误判失败
- 修复 QZone 监控会破坏主连接的问题：它原来在缺少连接时临时自建 `connector.listen()` 再在 finally 里 `close()`，既抢事件又会关掉主监听的连接；网关的常驻 reader 已能独立完成请求-响应，这段临时 listener 逻辑整体删除
- NapCat 接入层的传输契约与入站策略加入回归测试：`tests/test_napcat_gateway.py`（本地假 OneBot 服务器验证帧路由、重连、CQ 解析）与 `tests/test_napcat_inbound.py`（被叫到/戳一戳过滤）
- 将 `modules/system_state` 合并进 `core/tools/tools_status.py`（主人状态监控 + `get_master_status` 工具统一收口），并删除该独立模块
- DeepSeek 等模型返回空字符时，发送阶段拦截并发送占位提示「Yuki回复了空字符」，避免静默无回复
- 小女仆终端/技能执行超时的进程树终止适配 Linux：POSIX 下以独立进程组（`start_new_session` + `os.killpg`）整组 `SIGKILL`，Windows 保留 `taskkill /T` 路径
- 主人状态监控适配 Linux：空闲检测改用 systemd-logind（兼容 X11/Wayland），前台窗口改为查询 X11 `_NET_ACTIVE_WINDOW`，保留 Windows（Win32）原始路径
- 移除 GPS-VPS 手机定位功能：删除 `modules/system_state/gps_receiver.py`，`get_master_status` 不再返回 GPS 定位结果
- 真实运行代码暂时关闭浏览器模式工具注入，保留浏览器模块及注册代码供后续启用
- LLM 回复生成保留 `finish_reason` 等安全过滤信号，被内容安全过滤时发送 `Filtered`，避免空回复静默吞掉
- 聊天历史中的图片改为“纯文本 + 轻量附件引用”存储：`image_attachments` 只记录索引与唯一 ID，Base64 不落盘；请求前才组装多模态消息，历史、日记与日志仍按文本处理
- `ImageStore` 登记改为磁盘文件名使用唯一 ID、短索引循环复用：`read_attachment` 校验索引与 ID 一致，避免 `[img:XXX]` 被复用后关联到错误图片；文件先写临时文件再 `os.replace` 原子落盘
- 工具调用间隙合并的新消息也复用同一套图片处理逻辑，避免绕过原生视觉与转写分流
- Live2D 桌宠改为**默认关闭**：开关优先级为环境变量 `YUKI_DESKTOP_PET`（1/0）> `modules/LiveYukiL2D/config.json` 的 `desktopPet.enabled`（默认 false），后者此前是没人读的死配置
- `main.py` 的桌宠启动改为在线程里执行（`asyncio.to_thread`）：原来它同步阻塞事件循环，起 aiohttp 服务最长要等 3 秒，把 NapCat 监听整体推迟
- `modules/LiveYukiL2D/desktop.py` 重写启动方式：直接用当前平台的 Electron 二进制，不再走 `npm run desktop`；启动前做平台自检（Linux 上发现 Windows 版 `electron.exe` 直接报错并给出重装命令）；子进程 stdout/stderr 接入项目日志，异常退出记录退出码，不再静默"已启动"
- `desktop.py` 不再在模块级导入 `server`（aiohttp 依赖），开关判断与环境自检可在无 aiohttp 环境下单独跑
- 桌宠 Electron 主进程补齐 Linux 适配：始终置顶层级按平台区分（`screen-saver` 仅 macOS 有效）；原生 Wayland 下追加 `GlobalShortcutsPortal` 特性并记录全局快捷键注册失败原因；主进程按帧轮询真实全局光标并推送给渲染进程
- 修复 Linux 上鼠标穿透彻底失效：Electron 的 `setIgnoreMouseEvents(..., { forward: true })` 只在 Windows/macOS 生效，窗口一旦忽略鼠标就收不到 `pointermove`，永久卡在穿透状态。改为由主进程推送全局光标、渲染进程做命中判定，并对状态做去重避免 IPC 刷屏
- 修复 Chromium 全局光标在 Hyprland/XWayland 下不更新的问题：`screen.getCursorScreenPoint()` 会停在窗口开始忽略鼠标时的坐标，改为优先读 Hyprland IPC（一次 unix socket 往返，不创建进程），`hyprctl` 与 Chromium 查询依次兜底
- 修复桌宠模型命中判定：原 `isHitOnModel` 用 model 矩阵去反算 view 变换后的坐标，两者不是同一坐标空间；且 Yuki 模型没有配置 `HitAreas`，`anyhitTest` 依赖的 `isHit` 在本仓库根本未定义。改为记录每帧真实绘制的 MVP，把可见 drawable 顶点投到画布像素做包围盒判定，结果与画面一致
- 修复桌宠表情/语音表情静默失效：`WebSDK/src/main.ts` 用 `require('./lappadapter')` 动态取 adapter，Rollup 无法静态分析导致整块被 tree-shake 掉，浏览器里 `require` 又是 undefined（控制台只剩一句 `require is not defined`）。改为静态 import，并移除 `lappadapter.ts` 中未使用的 Node `util` 导入
- `GET /api/cursor` 去掉 `ctypes.windll.user32`（Windows 专有），改用跨平台实现，取不到时返回 `available: false` 而不是抛异常
- 小女仆 terminal 默认允许常规写入、依赖安装和 git 操作，仅保留高风险命令拦截
- 小女仆专属虚拟环境启动前会验证 Python 是否可用，检测到旧解释器丢失或环境损坏时自动重建
- GitHub 仓库监控的单仓库推送目标改为 `chat_ids` 列表，支持一个仓库推送到多个群聊
- 统一项目网络连接 SSL 配置，新增 `utils.http_client` 作为 certifi CA 入口，并覆盖 aiohttp、urllib、httpx、requests 和 wss WebSocket 调用
- 表情包发送阶段的情绪判断改为本地规则，避免每次 `[MEME]` 检索额外调用 LLM 导致发送延迟
- 旧 RAG 日记召回取消按群聊硬隔离，改为全局召回后对当前群聊日记和当前发言者姓名进行加权重排
- Prompt 注入全局模式状态，使 QQChatMode 收到新消息时能感知当前浏览器等聚焦模式是否运行
- `search_group_snapshots` 未提供关键词时改为随机返回本群一定数量截屏，并补充文件名便于自由 roam 后发送
- 调整 minimal Live2D 呼吸幅度、鼠标跟随灵敏度与阻尼，使头部和身体待机动作更自然
- 将 `core/maid.py` 解耦为边界判定、通用常量、运行时工具、外部工具、提示词、主循环和 Worker 模块，保留 `core.maid` 兼容导出
- 将 `core/engine.py` 解耦为回复工具链、回复决策、日记摘要和后台监控 service，保留 `YukiEngine` 门面调用方式不变
- 将 `core/tools.py` 解耦为 `core/tools/` 包：按职责拆分为状态、定时、日记、小女仆、消息、富文本、截屏、媒体、检索、空间、浏览器、网易云等子服务，`TOOL_SPECS` 汇总于 `core/tools/tools.py`，并保留 `core.tools` 导入路径与公开 handler 名称不变
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
- 修复控制台日志在中文、Emoji 和长 JSON 场景下因显示宽度误判导致的二次折行与错位
- 屏蔽机器人自己发出的戳一戳事件，避免回灌消息管线导致重复触发对话
- 合并同一人连续戳同一目标的戳一戳消息为一条并累计「x次数」，压缩上下文占用
- 修复普通对话流程只将当前用户消息放入临时上下文、未写入 `chat_history.json`，导致后续 LLM 调用缺少用户历史记录的问题
- 修复小女仆快速查询日记时硬编码 `core/yuki_memory` 导致重复创建空 ChromaDB 的问题
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
