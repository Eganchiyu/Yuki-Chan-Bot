# Yuki 更新日志

本项目重要架构与功能演进记录（日常开发明细见 `memo/Log.md`）。

---

## [未发布]

---

## [1.0.0] - 2026-11-04

### 新增
- **大众与 Agent 友好的一键部署体系 (`setup.py` + `README.md`)**：
  - 重写 `setup.py`：消除顶部第三方库硬导入（裸环境即可执行 `--help` 与 `--check --json`），支持交互式向导与 Agent 非交互式 CLI（`-y`、`--llm-api-key`、`--bot-qq`、`--master-qq`、`--groups`、`--set key.path=val`）及环境变量注入
  - 内置 `--check [--json]` 部署前健康自检：检查 Python 版本、核心依赖、配置文件必填项、RAG 向量模型完整性及 NapCat WebSocket 端口连通性
  - `README.md` 新增完整的 **Agent 自动化部署指南（5 步非交互式 SOP）** 与大众本地/Docker 双模式部署文档
- **向量模型国内源极速直下与单实例内存优化 (`utils/download_model.py`)**：
  - 默认优先走阿里魔搭社区（`modelscope`）国内 CDN 直连流式下载（自动回退 `hf-mirror` → `huggingface`），附带实时进度条，直接写入 `./models/text2vec-base-chinese/`，彻底消除 `~/.cache/huggingface` 双倍磁盘占用（节省 ~391MB 磁盘）
  - 新增 `get_embed_model()` 与 `get_chroma_client()` 进程内单例缓存，`MemoryRAG` 与 `StickerManager` 共享同一 `SentenceTransformer`、同一 `ChromaDB` 客户端与 `MemeProcessor`，消除重复加载（节省 ~400MB 内存，启动与测试耗时减半）
- **容器化自进化运行底座 (`deploy/`)**：
  - `deploy/Dockerfile` + `run.sh`：镜像仅装依赖，代码树与宿主机**同绝对路径 `:ro` 只读挂载**，数据卷独立 `:rw` 挂载；`deploy/` 脚本默认动态解析仓库根目录（支持 `YUKI_ROOT` 覆盖）
  - `deploy/supervisor.py` + `reviewer.py` + `verify.sh`：路径分级校验、独立模型两级审查（`blocking`/`advisory`）、`yuki_memory` 硬链接快照、5 道校验门（编译/导入/pytest/试启动/探针）、失败自动 `git reset` 回滚
  - `utils/health_server.py`：提供 `/health` 存活探针与 `POST /notify` 重启前群聊/私聊通知端点
  - `deploy/retention.py`：trace 按周归档、大日志截断、`staging/` 清理、记忆快照保留最近 7 份
- **小女仆 DeepSeek Harness 后端 (`core/maid/` + `deploy/maid_runner.py`)**：
  - 小女仆执行体全面切换为宿主侧 `dsh --profile yuki-maid --json`，通过 `tasks/dsh/<id>/` 文件协议通信
  - `core/maid/maid_resume.py`：容器重启后自动扫描已完成但未带 `reported.ok` 的任务并补报
- **网络看门狗与运维指令**：
  - `deploy/netwatch.py`（`yuki-netwatch.service`）+ NM `90-mihomo-reload`：30s 探活 `direct`/`proxy` 路径，阶梯式重载/重启 mihomo 解决 WiFi 漫游后 IPv4 出站挂死问题
  - 主人专属 `/刷新` 指令（群聊/私聊通用）：经 `data/netforce_pending/` + `yuki-netforce.path` 触发宿主真实探活并回报原会话
  - 主人专属 `/重启` 指令：先回复「正在重启」并落盘 `data/restart_notice.json`，经 `staging/` 交由宿主重建容器，新进程连上 NapCat 后自动补发「重启完成」
  - `utils/http_client.py` 新增 `DedicatedDnsResolver`（独立 4 线程 DNS 解析池），`utils/llm_client.py` 在连接层异常时自动重建全局 aiohttp Session 重试
- **对话与工具能力**：
  - 新增 `skip` 工具（`core/tools/tools_skip.py`）：群聊不适合插话时主动跳过本轮回复，管线通过 `_prune_skipped_round` 抹去本轮工具痕迹
  - 新增 `update_notebook` 工具与 `core/notebook.py`：维护全局小本本（`data/notebook.json`，上限 512 字），在上下文中作为潜意识底色注入且工具结果不落盘历史（`persist_result=False`）
  - 新增跨轮召回缓存 `core/recall_cache.py`（`data/recall_best.json`）：按 `chat_id` 保留最近两轮召回的 top-1 并排在注入最前，群聊兴趣度计算仅看本轮新召回；新增 `rag.inject_top_k`（默认 5）配置
  - 新增回复自动订阅 `core/reply_watch.py`：回复后按问句/触发词/精力/生物钟/活跃度自动评分订阅“等回音”，超时无人接话时注入提醒（最多 2 次）
  - 新增入站图片预取 `modules/vision/prefetch.py`：消息入队即后台下载并做视觉处理，与普通图片原生多模态输入（`llm_native_vision_enabled`）协同
  - 新增回复标记容错 `core/reply_format.py` 与文本工具调用还原 `core/tool_markup.py`：自动剥离 `<layout>`、归一化 `[MEME:情绪]`、还原正文中的 DSML/`<tool_call>` 调用
  - 支持多主人 QQ 号配置 `target.masters`（`cfg.MASTER_QQS` / `cfg.is_master_qq()`）及 `master_private` 双模私聊通道
  - `generate_image` 工具内置 Yuki 与主人固定人设参考图说明

### 变更
- **依赖声明跨平台泛化 (`pyproject.toml`)**：`requires-python` 放宽为 `>=3.11`，移除锁死全量传递依赖的 `==` 约束与残缺 `uv.lock`，改为顶层核心依赖 `>=` 约束
- **网络接入层收口**：原 `BotConnector`、`MessageSender` 与 `modules/message/` 合并为单一 `network/napcat.py::NapCatGateway`，常驻 `_reader()` 协程严格分离 API `echo` 响应与入站事件流
- **RAG 打分重构**：同群/发言者/关键词加成改为相对语义分的比例提升，加入 180 天半衰期时间衰减与停用词过滤
- **思考等级配置**：移除无效的 `model.disable_thinking`，新增 `model.thinking_effort`；DeepSeek 视觉端点固定下发 `reasoning_effort="none"`
- **BOT 防套娃**：白名单 BOT 消息不再触发点名强制回复与防抖跳过，纯 BOT 发言回复欲乘 `0.75` 惩罚
- **测试套件整合 (`tests/`)**：整合重写为 11 个全离线 pytest 测试模块，清除需联网或残留临时文件的旧测试，本机与只读容器内 `pytest -q` 全绿

### 归档与移除
- **记忆库清理**：彻底删除弃用的 `yuki_memory` collection（7830 条结构化记忆实验数据）并 `VACUUM`，ChromaDB 仅保留现役 `diaries` 与 `stickers`（详见 `docs/database-profile.md`）
- **未挂载代码统一归档至 `_archive/`**：
  - 剥离并归档 Live2D 桌宠（`_archive/LiveYukiL2D/`）与浏览器交互聚焦模式（`_archive/modules/browser_interaction/`、`_archive/focus_modes/`）
  - 归档旧版容器内小女仆内置循环（`_archive/maid_legacy/`）
  - 从主模型卸载并归档低频/未就绪工具：网易云点歌（`_archive/ncm_tools/`）、QQ 空间说说工具（`_archive/qzone_tool/`）、网页/高德搜索（`_archive/search_tools/`）、主人桌面状态（`_archive/master_status/`）、定时任务（`_archive/timer_tool/`）、昵称解析（`_archive/user_resolve_tool/`）
  - 精简 `/docs` 目录，移除过期或重复的 `module-relationship.md`、`module-interface.md`、`development-plan.md`、`docs/Log.md`

---

## [0.10.0] - 2026-06-05

- 新增 `core/toolchain.py` 与 `core/tools.py`，接入 OpenAI 兼容 Function Call 工具链
- 清理仓库硬编码敏感信息，统一收敛至 `configs/config.yaml` 与 `config.py`
