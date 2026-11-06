# Yuki 项目架构与代码定位指南

## 一、运行拓扑概览

Yuki 是基于 NapCat（OneBot 11 正向 WebSocket）的 QQ AI 助手。线上采用**容器只读代码 + 宿主守护进程**架构：

```
宿主机 (Debian)
├── NapCatQQ (ws://127.0.0.1:3001)
├── yuki 容器 (yuki:base, --network host, 同绝对路径挂载)
│   ├── 代码树 :ro 只读挂载 (core/ modules/ network/ utils/ main.py config.py)
│   ├── 数据目录 :rw 挂载 (data/ yuki_memory/ logs/ output/ workspace/ staging/ tasks/ skills/)
│   ├── main.py → NapCatGateway + SessionPipeline + YukiEngine
│   └── HTTP 探针 (127.0.0.1:8778 /health, /notify) & Debug WebUI (127.0.0.1:8777)
└── 宿主 Systemd 服务 (deploy/)
    ├── yuki-supervisor.service  (轮询 staging/，执行 模型审查→快照→5道校验门→重启容器→失败回滚)
    ├── yuki-maid-runner.service (轮询 tasks/dsh/，拉起 DeepSeek Harness 执行小女仆任务)
    └── yuki-netwatch.service    (30s 探活 direct/proxy，自动重载 mihomo；配合 yuki-netforce.path 响应 /刷新)
```

---

## 二、目录结构

```
/home/asumi/Yuki/
├── main.py                      # 入口：单实例锁(data/yuki.lock)、组件装配、/health 与 /notify、启动监听
├── config.py                    # 配置中心：_ATTR_MAP 定义源、configs/config.yaml 自动补全与热重载(cfg 单例)
├── init.py                      # 群聊开关状态持久化 (data/group_state.json) 与启动前检查
├── setup.py                     # 首次安装与配置向导
├── pyproject.toml               # 依赖与 pytest 配置 (asyncio_mode = "auto")
│
├── core/                        # 核心业务层
│   ├── session_pipeline.py      # 8 阶段串行会话管线 (按 chat_id 加锁防并发分叉)
│   ├── brain.py                 # YukiState：精力值、高斯生物钟、群活跃度、message_buffer、maid_task_queue
│   ├── prompts.py               # 系统提示词与上下文组装 (build_chat_context)【人格硬禁区】
│   ├── history_manager.py       # 会话级历史持久化 (data/chat_history.json)，原子写与标记自修复
│   ├── reply_format.py          # <layout> 剥离、[MEME:情绪] 归一化、历史标记修复
│   ├── tool_markup.py           # DSML / <tool_call> / <function=> 文本工具调用还原与兜底清洗
│   ├── toolchain.py             # ToolSpec / FunctionRegistry / ToolCallManager / ToolContext / SKIP_REPLY_MARKER
│   ├── notebook.py              # NotebookStore：全局小本本 (data/notebook.json，≤512 字，潜意识注入)
│   ├── recall_cache.py          # RecallCacheStore：跨轮保留最近两轮召回的 top-1 (data/recall_best.json)
│   ├── reply_watch.py           # 回复后自动评分订阅“等回音”，超时无人接话触发提醒 (最多 2 次)
│   ├── engine/                  # 引擎门面与 4 个子服务
│   │   ├── engine.py            #   YukiEngine 门面
│   │   ├── engine_reply.py      #   LLM 回复生成、多轮工具链调用、阶段文本实时发送
│   │   ├── engine_decision.py   #   群聊回复意愿打分 (精力 + 活跃度 + RAG 兴趣度 + 关键词/防套娃)
│   │   ├── engine_diary.py      #   会话浓缩总结、写日记入 ChromaDB
│   │   └── engine_monitor.py    #   后台空闲日记巡检、破冰巡检
│   ├── tools/                   # 主模型挂载的 12 个 Function Call 工具
│   │   ├── tools.py             #   TOOL_SPECS 汇总声明
│   │   ├── tools_maid.py        #   delegate_to_maid (后台委托小女仆)
│   │   ├── tools_diary.py       #   search_diary (按日期/关键词或随机翻看日记)
│   │   ├── tools_notebook.py    #   update_notebook (覆盖更新小本本，persist_result=False)
│   │   ├── tools_skip.py        #   skip (群聊主动跳过本轮回复且不留痕，persist_result=False)
│   │   ├── tools_message.py     #   send_master_private / poke / send_qq_file
│   │   ├── tools_snapshot.py    #   capture_group_snapshot / search_group_snapshots
│   │   ├── tools_rich.py        #   parse_rich_message (合并转发/小程序/JSON/XML 分页展开)
│   │   ├── tools_media.py       #   download_file / generate_image (含固定人设参考图)
│   │   └── tools_common.py      #   路径解析、昵称解析等工具共用函数
│   └── maid/                    # 小女仆子代理系统 (Harness 后端)
│       ├── maid.py              #   门面导出
│       ├── maid_worker.py       #   消费 maid_task_queue，完成后写回历史并触发汇报回复
│       ├── maid_harness.py      #   写 tasks/dsh/<id>/request.json，监听 events.jsonl 与 result.json
│       ├── maid_resume.py       #   容器重启后巡检未汇报的已完成任务并补报 (reported.ok)
│       ├── maid_boundary.py     #   委托前能力边界判定与报告格式化
│       ├── maid_charter.py      #   自进化准则代码侧单一来源【硬禁区】
│       ├── maid_memory.py       #   任务状态 (tasks/state/) 与索引 (logs/task_index.jsonl)
│       ├── maid_tools.py        #   search_diary_fast 等辅助函数
│       ├── maid_backend.py      #   固定导出 harness_evolution_loop
│       └── maid_common.py       #   路径与常量
│
├── modules/                     # 功能模块
│   ├── QQNapcatListen/          # 入站事件监听与指令拦截 (listen_main.py)
│   ├── memory/rag.py            # MemoryRAG 单例：ChromaDB (diaries) 向量+jieba关键词检索、比例加成与时间衰减
│   ├── stickers/manager.py      # StickerManager：ChromaDB (stickers) 检索、积热冷却与 RLHF 偏好加成
│   ├── vision/                  # 视觉处理
│   │   ├── processor.py         #   MemeProcessor：表情包 VLM 转写 / 普通图片登记原生视觉附件
│   │   ├── prefetch.py          #   入队即后台预取下载与识别，normalize 阶段直接复用
│   │   ├── image_store.py       #   近期图片短索引 [img:XXX] 与唯一附件 ID 映射
│   │   └── cache.py             #   表情包识别缓存 (data/meme_cache.json)
│   ├── shot_memory/             # 群聊截屏留念：live_buffer.py / renderer.py / store.py
│   ├── github_monitor/          # GitHub 仓库事件轮询与 Push 卡片渲染 (默认关闭)
│   ├── qzone/                   # QQ 空间说说发布与动态监控 (监控默认关闭)
│   └── debug/                   # ContextSnapshotStore 与只读 WebUI (端口 8777)
│
├── network/
│   └── napcat.py                # NapCatGateway：WS 连接、常驻 reader 帧路由、OneBot API 调用、CQ 码解析
│
├── utils/
│   ├── llm_client.py            # OpenAI 兼容客户端：主备熔断切换、空回复/断连重试、非视觉备用降级
│   ├── http_client.py           # certifi SSL 上下文 + DedicatedDnsResolver (独立 4 线程 DNS 解析池)
│   ├── logger.py                # 控制台(INFO 短摘要+降噪) / 文件(DEBUG 明细) 分级日志
│   ├── health_server.py         # 127.0.0.1:8778 /health 与 POST /notify
│   └── paths.py                 # 路径归一化
│
├── deploy/                      # 容器、守护进程与宿主服务 (详见 deploy/README.md)
├── skills/                      # 小女仆可复用的 Python 技能 (<name>.py + <name>.md)
├── tests/                       # 11 个全离线 pytest 测试文件 (详见 tests/README.md)
├── _archive/                    # 已下线/归档模块与复原手册 (Live2D、旧内置女仆循环、NCM、聚焦模式等)
└── memo/Log.md                  # 持续追加的开发日志
```

---

## 三、核心数据流

### 3.1 入站与会话管线 (`listen_main.py` → `SessionPipeline`)

1. **帧路由 (`network/napcat.py::NapCatGateway._reader`)**：
   - `echo` 命中挂起请求 → 唤醒 `gateway.call()`；
   - 含 `post_type` → 放入事件队列供 `gateway.listen()` 消费；API 响应与事件流严格隔离。
2. **入站适配 (`modules/QQNapcatListen/listen_main.py::napcat_listen`)**：
   - 拦截群指令：主人专用 `/开启`、`/关闭`、`/重启`（写 `data/restart_notice.json` + `staging/restart_*/request.json`）、`/刷新`（写 `data/netforce_pending/` 触发宿主探活，私聊同样可用）、`/切换`（内存里对调主备模型的模型名/地址/Key，私聊同样可用，重启后恢复）；群友 `/help`；
   - 路由模式：白名单群聊为 `group`；主人私聊为 `master_private`（跳过防抖与精力判定，必回）；
   - 唤醒判定：非 BOT 消息命中名字或 `@` 机器人时，`debounce_flag=False` 且 `force_reply=True`。
3. **入队与预取 (`SessionPipeline.enqueue_message`)**：
   - 写入 `yuki.message_buffer[chat_id]`；若为真人消息则调用 `reply_watch.resolve()` 取消待回执订阅；
   - 后台触发 `vision.prefetch.prefetch_images()` 提前下载图片/转写表情包。
4. **8 阶段串行处理 (`SessionPipeline.process_loop`，按 `_chat_locks[chat_id]` 串行)**：
   - `prepare_message_batch`：防抖等待（默认 20s，点名/私聊/破冰跳过），合并缓冲区消息；
   - `normalize_incoming_content`：复用预取结果，普通图片登记为 `image_attachments`（原生视觉开启时）或转写为文本，表情包转写为 `[表情:描述]`，兜底清除残留 `[图片占位符]`；
   - `prepare_chat_context`：加载会话历史并更新群活跃度；
   - `retrieve_memories`：`MemoryRAG.search_diaries()` 召回 `cfg.INJECT_TOP_K`（默认 5）条日记，并经 `RecallCacheStore` 合并最近两轮的 top-1；
   - `decide_reply_action`：`EngineDecisionService` 综合精力、活跃度、本轮新召回兴趣度（`recall_new_results`）、关键词与纯 BOT 降欲（`×0.75`）判定是否回复；
   - `generate_reply`：`EngineReplyService.api_reply()` 组装提示词（含回忆、`NotebookStore` 小本本、近期图片附件）并执行最多 4 轮工具调用。若调用了 `skip` 工具，返回 `SKIP_REPLY_MARKER`，管线调用 `_prune_skipped_round` 抹去本轮痕迹并直接结束；
   - `send_reply`：经 `clean_visible_reply()` 剥离 `<layout>`、归一化 `[MEME:情绪]` 后分段发送文本与表情包；
   - `finalize_conversation`：原子落盘历史、触发 `reply_watch.auto_subscribe()` 评估是否订阅等回音、达到轮数阈值时异步触发 `do_summarize()` 写日记。

### 3.2 小女仆委托与自进化流 (`core/maid/` + `deploy/`)

- **日常任务**：`delegate_to_maid` → 入队 `yuki.maid_task_queue` → `maid_worker` 调用 `maid_harness.harness_evolution_loop()` → 写 `tasks/dsh/<id>/request.json` → 宿主 `deploy/maid_runner.py` 在 `workspace/dsh_<id>/` 下拉起 `dsh --profile yuki-maid --json` → 结果写回 `result.json` → `maid_worker` 注入会话历史并唤醒管线汇报。
- **跨重启补报**：若任务期间容器因自改或 `/重启` 重建，`core/maid/maid_resume.py` 启动后巡检 `tasks/dsh/*/result.json`（未带 `reported.ok` 的任务）自动补报。

---

## 四、代码定位速查表（LLM 交接索引）

| 我想找 / 修改…… | 直接看这里 |
|---|---|
| 启动流程、单实例锁、`/health` 与 `/notify` | `main.py` |
| 新增/修改配置项、默认值、YAML 热重载 | `config.py`（改 `_ATTR_MAP` 或 `@property`） |
| 主人多 QQ 号判定 (`cfg.MASTER_QQS` / `cfg.is_master_qq`) | `config.py` (`TargetConfig`) |
| 群指令 (`/开启` `/关闭` `/重启` `/刷新` `/切换`)、戳一戳、`@` 唤醒 | `modules/QQNapcatListen/listen_main.py` |
| OneBot WebSocket 收发、CQ 码解析、合并转发拉取 | `network/napcat.py` (`NapCatGateway`) |
| 防抖合并、图片占位替换、分段发表情包、`skip` 抹痕 | `core/session_pipeline.py` (`SessionPipeline`) |
| 群聊回不回、精力消耗、回复欲打分、纯 BOT 降欲 | `core/engine/engine_decision.py` (`EngineDecisionService`) |
| 多轮工具调用、工具期间新消息合并、清洗致空兜底 | `core/engine/engine_reply.py` (`EngineReplyService`) |
| 日记生成总结、空闲日记巡检、冷场破冰巡检 | `core/engine/engine_diary.py`、`core/engine/engine_monitor.py` |
| 精力恢复、高斯生物钟、群活跃度衰减 | `core/brain.py` (`YukiState`) |
| 系统提示词、回忆与【小本本】注入顺序 | `core/prompts.py` (`build_chat_context`)【注：人格文本属硬禁区】 |
| `<layout>` 思考外泄修复、`[MEME:]` 括号容错 | `core/reply_format.py` |
| 模型把工具调用写成正文 (`DSML` / `<tool_call>`) | `core/tool_markup.py` |
| 主模型可用工具列表、参数 Schema 与 Handler | `core/tools/tools.py` 及 `core/tools/tools_*.py` |
| 小本本 (`data/notebook.json`) 读写与截断 | `core/notebook.py`、`core/tools/tools_notebook.py` |
| 日记向量检索、同群/发言者/关键词比例加分、时间衰减 | `modules/memory/rag.py` (`MemoryRAG`) |
| 跨轮保留最近两轮召回的 top-1 (`data/recall_best.json`) | `core/recall_cache.py` (`RecallCacheStore`) |
| 回复后“等回音”自动订阅与超时追击 | `core/reply_watch.py` |
| 普通图片原生多模态输入、表情包 VLM 转写、入站预取 | `modules/vision/processor.py`、`prefetch.py`、`image_store.py` |
| LLM 请求、主备熔断、空回复重试、`thinking_effort`、DNS 池 | `utils/llm_client.py`、`utils/http_client.py` |
| 小女仆任务派发、DSH 事件解析、重启后补报 | `core/maid/maid_harness.py`、`maid_worker.py`、`maid_resume.py` |
| 小女仆人设、行为准则与自改文件协议 | `deploy/dsh-home/AGENTS.md`、`core/maid/maid_charter.py` |
| 宿主自改守护、独立模型审查、5 道校验门、网络看门狗 | `deploy/supervisor.py`、`reviewer.py`、`verify.sh`、`netwatch.py` |
| 已下线功能（Live2D、NCM、聚焦模式、旧内置女仆循环等） | `_archive/README.md` 及对应子目录 |
