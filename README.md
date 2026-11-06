# YukiV6 (FrostFrame) — AI 虚拟助手 · 住在你电脑里的智能小管家

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V3-green.svg)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/license-MIT-important.svg)](LICENSE)

> **"虽然现在还很笨拙，但 Yuki 会慢慢成长的。所以...不许丢下我不管哦！"**

Yuki 是一个基于 Python 异步架构开发的个人智能助手系统，通过 QQ 平台（NapCat / OneBot 11 框架）与主人和群聊交互。系统底层具备动态长效记忆（RAG）、生物感精力值模拟、自主子代理（小女仆）系统、多模态表情包管理、Function Call 工具链调用与容器化受控自进化能力，默认搭载高度人格化的“电子妹妹”角色 **Yuki**。

---

## 目录

- [核心特性](#核心特性)
- [快速开始（大众部署指南）](#快速开始大众部署指南)
- [🤖 Agent 自动化部署指南（Agent向文档）](#-agent-自动化部署指南agent向文档)
- [功能玩法大赏](#功能玩法大赏)
- [系统流程](#系统流程)
- [项目结构](#项目结构)
- [文档索引与测试](#文档索引与测试)
- [技术栈](#技术栈)

---

## 核心特性

### 🧠 自主小女仆系统 (Maid Agent)

Yuki 通过 Function Call 工具 `delegate_to_maid`，可将复杂任务交由后台的“小女仆”异步处理：

- **执行后端**：由宿主侧 DeepSeek Harness（`deploy/maid_runner.py`）驱动，提供完整工具链、上下文压缩与工作区隔离
- **受控自改**：候选补丁写入 `staging/` → 宿主侧独立模型审查（`deploy/reviewer.py`）→ 宿主守护进程应用 + 5 道校验门（`deploy/verify.sh`）→ 失败自动回滚到基线
- **无人值守与非阻塞汇报**：后台任务完成后将结果写入 Yuki 记忆流，触发自然的异步回复；容器重启后支持自动补报已完成任务（`core/maid/maid_resume.py`）
- **技能热复用**：已固化的技能（`skills/`）可被后续任务直接调用，无需重复编写
- **能力边界判定**：委托前自动评估任务复杂度与安全风险，拦截高风险操作

### 🧠 记忆与日记系统 (Memory & RAG)

- **自动日记总结**：对话轮次达阈值或空闲超时，Yuki 以第一人称撰写日记，将上下文浓缩为记忆节点
- **向量 + 关键词双池检索**：基于 ChromaDB + `text2vec-base-chinese` 嵌入模型语义检索，结合 jieba 分词关键词补偿与时间衰减
- **跨轮记忆保留**：`RecallCacheStore` 自动保留最近两轮召回的 Top-1 记忆，维持连续话题的回忆连贯性
- **潜意识小本本**：`NotebookStore`（`update_notebook` 工具）允许 Bot 自主记录重要心愿、约定与长期目标并常驻注入上下文

### 🎭 生物感精力系统 (Energy Dynamics)

- **动态社交欲望**：Sigmoid 非线性映射计算破冰意愿，综合活跃度、精力值与时间权重
- **高斯拟合生物钟**：融合基础睡眠模型与晨间、午间、晚间三个高斯活跃峰，模拟真实作息节律
- **消息缓冲防抖**：群聊消息自动聚合防抖（默认 32 秒），避免频繁触发 API
- **群聊活跃度**：非线性提升 + 半衰降温（每 10 分钟 × 0.65），精确模拟群聊参与度
- **回复订阅（等回音）**：回复后自动评估“等待回应程度”，超时无人接话时注入追击提醒（最多两次）

### 🖼️ 多模态表情包与视觉管理 (Vision & Sticker System)

- **视觉理解**：接入 VLM（如 Qwen-VL）理解群聊表情包的含义与情感并缓存（`data/meme_cache.json`）
- **普通图片原生输入**：`model.llm_native_vision_enabled` 开启后，普通图片直接作为多模态图块交给主模型理解
- **入站图片预取**：收到带图消息即在防抖等待期间后台下载并做视觉处理，缩短回复延迟
- **向量检索 + 积热重排 + RLHF**：根据情绪在表情包向量库中检索，结合冷却机制与群友正反馈加权

### 🔗 Function Call 工具链系统

- **现役 12 个内置工具**：小女仆委托（`delegate_to_maid`）、日记搜索（`search_diary`）、小本本更新（`update_notebook`）、主动跳过回复（`skip`，不留痕）、主人私聊通知（`send_master_private`）、群聊戳一戳（`poke`）、QQ 文件发送（`send_qq_file`）、群聊截屏留念与检索（`capture_group_snapshot` / `search_group_snapshots`）、富文本（合并转发/小程序/卡片）分页解析（`parse_rich_message`）、文件下载（`download_file`）、文生图/参考图编辑（`generate_image`）
- **归档扩展工具（`_archive/`）**：网易云搜歌下载、QQ 空间说说发布、高德地图/网页搜索、主人桌面状态感知、定时任务等模块已归档在 `_archive/` 下并附带一键复原说明

### 💬 主人私聊双模系统 (Master Private Channel)

- **双模并行**：群聊运行时，主人私聊走独立管道（`master_private`）处理，互不干扰
- **永远响应保证**：主人私聊消息跳过精力值判定和防抖机制，即时响应
- **管理指令支持**：支持主人发送 `/开启`、`/关闭`、`/重启`、`/刷新`、`/切换`（主备模型线路对调）管理指令

---

## 快速开始（大众部署指南）

### 1. 前置准备

1. **Python 环境**：Python **3.11 及以上**（推荐安装 [uv](https://docs.astral.sh/uv/) 管理虚拟环境与依赖）。
2. **QQ 协议端（NapCatQQ）**：
   - 下载并登录 [NapCatQQ](https://github.com/NapCat-Team/NapCatQQ)（支持 Windows / Linux / Docker）。
   - 在 NapCat 网络配置中启用 **OneBot 11 正向 WebSocket Server**，默认监听端口 `3001`（地址为 `ws://localhost:3001`）。
3. **API Key**：
   - **必填**：首选对话模型 API Key（默认使用 [DeepSeek](https://platform.deepseek.com/)，也支持任意 OpenAI 兼容接口）。
   - **可选**：[阿里云百炼 DashScope](https://bailian.console.aliyun.com/) API Key（用于 `qwen3-vl-flash` 表情包视觉理解与通义万相文生图；若不配置，纯文本对话依然可用）。

---

### 2. 方式一：本地直接运行（推荐大众首选，Windows / Linux / macOS 通用）

#### Step 1：克隆仓库并准备虚拟环境

```bash
git clone https://github.com/Eganchiyu/Yuki-Chan-Bot.git
cd Yuki-Chan-Bot

# 方式 A：使用 uv（推荐）
uv venv --python 3.11
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1

# 方式 B：使用标准 venv
python3 -m venv .venv
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
```

#### Step 2：运行一键配置向导 `setup.py`

```bash
python setup.py
```

`setup.py` 会依次引导你完成以下 5 步，并在最后输出环境自检报告：
1. **建立运行目录**：创建 `models/`、`data/`、`yuki_memory/`、`logs/`、`configs/` 等必要文件夹。
2. **安装 Python 依赖**：自动调用 `uv sync` 或 `pip` 安装 `pyproject.toml` 中的依赖。
3. **生成配置文件**：自动生成带中文注释的 `configs/config.yaml` 和 `blacklist.txt`。
4. **交互式填写关键配置**：引导填写 LLM API Key、NapCat WebSocket 地址、机器人 QQ 号、主人 QQ 号与监听群号。
5. **下载 RAG 嵌入模型**：自动从国内魔搭社区（ModelScope）或 HuggingFace 镜像站下载 `text2vec-base-chinese`（约 391MB）到 `./models/text2vec-base-chinese`（只下载最小必需文件，不占用双倍缓存）。
   > 💡 **下载源切换提示**：默认按 `modelscope`（阿里云国内直连）→ `hf-mirror` → `huggingface` 自动故障切换，也可手动指定：`python setup.py --model-source modelscope`。

#### Step 3：自检与启动

```bash
# 随时运行环境与配置自检
python setup.py --check

# 试启动自检（加载全部组件与模型，但不消费 QQ 消息，验证无报错后以 0 退出）
YUKI_DRY_RUN=1 python main.py

# 正式启动！
python main.py
```

启动后，Yuki 会在 `http://127.0.0.1:8778/health` 提供健康探针，并在 `http://127.0.0.1:8777/` 提供本地只读 Context Debug WebUI。

---

### 3. 方式二：Docker 容器化 + 自进化守护部署（Linux 进阶生产环境）

如果你在 Linux 服务器/主机上长期运行，并希望开启**代码只读隔离**、**小女仆 Harness 执行器**与**受控自进化（改代码自动审查+校验+回滚）**，可使用 `deploy/` 下的容器化方案：

```bash
# 1. 先在宿主机完成基础配置与模型下载（无需在宿主机安装完整 Python 依赖）
python3 setup.py --non-interactive --skip-deps \
  --llm-api-key "sk-你的API_KEY" \
  --bot-qq 你的机器人QQ号 \
  --master-qq 你的主人QQ号 \
  --groups "群号1,群号2"

# 若本地还没有 models/text2vec-base-chinese，可在构建镜像后下载或先在 venv 中运行一次模型下载

# 2. 构建基础运行镜像（只打包依赖，代码在启动时只读挂载）
docker build -f deploy/Dockerfile -t yuki:base .

# 3. 若步骤 1 跳过了宿主机依赖，可直接借用容器下载嵌入模型到宿主机 ./models/
docker run --rm -v "$PWD:$PWD" -w "$PWD" -e HF_ENDPOINT=https://hf-mirror.com yuki:base \
  python setup.py --non-interactive --skip-deps

# 4. 启动生产容器（自动使用同绝对路径挂载，确保宿主机 NapCat 能通过 file:/// 读取本地图片）
bash deploy/run.sh

# 5. 检查容器健康状态
curl -s http://127.0.0.1:8778/health
```

**（可选）安装宿主常驻守护服务（自进化 `yuki-supervisor` + 小女仆 `yuki-maid-runner`）**：
```bash
sudo bash deploy/install-service.sh
```
详见 [deploy/README.md](deploy/README.md)。

---

### 4. 表情包库初始化（可选）

代码内置了完整的表情包检索与发送逻辑，但图片素材不随仓库分发。如需启用表情包发送：
1. 将表情包图片放入 `data/stickers/`。
2. 运行可视化打标工具：`python scripts/06_sticker_manager/label.py`
3. 导入向量库：`python scripts/04_meme_cache_tools/reset_and_import_meme.py`

---

## 🤖 Agent 自动化部署指南（Agent向文档）

> **本节专为 AI Coding Agent（如 DeepSeek Harness、Claude Code、Cursor、Codex、OpenHands 等）编写。**
> 当人类用户要求你“帮我部署/配置/启动这个项目”时，请严格遵循以下非交互式 SOP，**切勿直接运行不带参数的 `python setup.py`**（会阻塞在 `input()` 等待输入）。

### 0. Agent 执行铁律

1. **禁止交互式阻塞**：调用 `setup.py` 时必须带上 `--non-interactive`（或 `-y`）或 `--check`。
2. **缺失信息先提问**：若环境中没有 API Key 或目标 QQ 号，先一次性向机主询问以下 4 项必填参数，拿到后再执行配置命令：
   - `llm_api_key`（首选 LLM API Key，如 DeepSeek API Key）
   - `bot_qq`（机器人登录在 NapCat 上的 QQ 号）
   - `master_qq`（主人自己的 QQ 号）
   - `groups`（需要监听的 QQ 群号，可为空，仅用私聊时可只填 `master_qq`）
3. **权限边界**：遇到需要 `sudo`（如 `deploy/install-service.sh` 或安装系统包）或需要机主手机扫码登录 NapCat 时，立即停下并告知机主执行，不要尝试绕过。

### Step 1：探测当前环境状态（JSON 结构化输出）

首先使用系统已有的 `python3` 运行 `--check --json`（该命令为纯标准库实现，不依赖任何第三方包，随时可跑）：

```bash
python3 setup.py --check --json
```

解析返回的 JSON：
- `checks` 数组包含：`python_version`（需 `>=3.11`）、`python_dependencies`、`blacklist_txt`、`embedding_model`、`config_yaml`、`config.api.llm_api_key`、`config.target`、`napcat_ws_port`。
- `blocking_errors`：阻断启动的缺失项列表。
- `warnings`：非阻断注意事项（如 NapCat 尚未启动）。

### Step 2：准备 Python 虚拟环境与安装依赖

按以下优先级选择或创建 Python `>=3.11` 环境：
1. 若存在现成可用虚拟环境（如 `.venv/bin/python` 或 `conda` 环境），先用 `<python_bin> setup.py --check --json` 检查 `python_dependencies` 是否已满足。
2. 若需新建虚拟环境并安装依赖：
   ```bash
   # 优先使用 uv
   if command -v uv >/dev/null 2>&1; then
     uv venv --python 3.11
     uv sync
     PY_BIN=".venv/bin/python"
   else
     python3 -m venv .venv
     PY_BIN=".venv/bin/python"
     "$PY_BIN" setup.py --non-interactive --install-deps --skip-model
   fi
   ```

### Step 3：非交互式写入配置与准备嵌入模型

使用 `setup.py --non-interactive` 一次性完成目录创建、配置文件生成/更新与模型准备：

```bash
"$PY_BIN" setup.py --non-interactive --skip-deps \
  --robot-name "yuki" \
  --master-name "主人" \
  --llm-base-url "https://api.deepseek.com/v1" \
  --llm-api-key "${LLM_API_KEY}" \
  --llm-model "deepseek-chat" \
  --napcat-url "ws://127.0.0.1:3001" \
  --bot-qq "${BOT_QQ}" \
  --master-qq "${MASTER_QQ}" \
  --groups "${TARGET_GROUPS}"
```

- **可选参数注入**：
  - 视觉模型：`--vision-url "https://dashscope.aliyuncs.com/compatible-mode/v1" --vision-api-key "${VISION_KEY}" --vision-model "qwen3-vl-flash"`
  - 任意配置项点号路径覆盖（可多次传入 `--set`）：
    ```bash
    "$PY_BIN" setup.py --non-interactive --skip-deps --skip-model \
      --set model.llm_native_vision_enabled=true \
      --set rag.inject_top_k=5 \
      --set timing.debounce_time=25
    ```
- **模型下载源指定**：默认优先走国内 `modelscope` 直连源（无需代理且不占 `~/.cache/huggingface` 双倍磁盘），也可显式指定：
  ```bash
  "$PY_BIN" setup.py --non-interactive --skip-deps --model-source modelscope
  ```

### Step 4：启动前三级验证门（Agent 必跑）

在正式拉起服务前，依次运行以下 3 条命令并确认退出码均为 `0`：

```bash
# 1. 配置与环境自检（确认 ready == true）
"$PY_BIN" setup.py --check --json

# 2. 离线单元测试套件（61 项测试，无需联网，验证代码与依赖完整性）
"$PY_BIN" -m pytest -q

# 3. Dry-Run 试启动（验证 ChromaDB、嵌入模型、组件装配全部正常，不接管 NapCat）
YUKI_DRY_RUN=1 "$PY_BIN" main.py
```

### Step 5：启动运行与探针确认

根据机主选择的部署模式启动：

- **模式 A：本地进程启动**
  ```bash
  nohup "$PY_BIN" main.py > logs/stdout.log 2>&1 &
  ```
- **模式 B：Docker 容器启动**
  ```bash
  docker build -f deploy/Dockerfile -t yuki:base .
  bash deploy/run.sh
  ```

启动后等待 10~20 秒（加载嵌入模型与 ChromaDB），请求本地健康探针验证服务就绪：

```bash
curl -fsS http://127.0.0.1:8778/health
# 期望返回示例：{"ready": true, "mode": "serve", "napcat_online": true, "maid_queued": 0, "maid_running": 0}
```
- 若 `ready: true` 且 `napcat_online: true`：部署全部完成！
- 若 `ready: true` 但 `napcat_online: false`：Yuki 本身已正常启动，只需提示机主检查 NapCatQQ 是否已登录并开启 `3001` 端口正向 WebSocket。

---

## 功能玩法大赏

### 1. 群聊截屏留念 — 把名场面做成永久截图 (`modules/shot_memory/`)
- **精美渲染**：用 PIL 渲染带头像、气泡、群名头的聊天截图并按群保存在 `data/shot_memory/`。
- **工具联动**：Yuki 可主动或应群友要求调用 `capture_group_snapshot` 截屏留念，或用 `search_group_snapshots` 搜索历史名场面并直接发送。

### 2. 文生图与参考图编辑 — 让 Yuki 帮你画画 (`core/tools/tools_media.py`)
- **双引擎支持**：支持 DashScope（通义万相）和 OpenAI 兼容图像生成接口。
- **参考图编辑**：支持传入近期聊天图片索引 `[img:XXX]`（最多 4 张）结合内置人设图进行图像编辑，生成后通过 `send_qq_file` 自动发出。

### 3. 富文本解析 — 合并转发、小程序、卡片都能读 (`core/tools/tools_rich.py`)
- 消息中出现 `[合并转发:id=xxx]` 或 `[小程序]` 时，Yuki 可调用 `parse_rich_message` 分页展开阅读嵌套内容。

### 4. 潜意识小本本 — 记住和你的重要约定 (`core/notebook.py`)
- 遇到真正在意的心愿、长期目标或约定，Yuki 会调用 `update_notebook` 写进自己的小本本（`data/notebook.json`），跨会话持久伴随。

### 5. GitHub 仓库监控 (`modules/github_monitor/`)
- 在 `configs/config.yaml` 中开启 `github_monitor.enabled: true` 并配置仓库后，自动轮询 Issue / PR / Push 事件，将 Push 渲染为精美 PNG 卡片推送到指定群聊。

### 6. 戳一戳与私聊联动 (`core/tools/tools_message.py`)
- 支持群昵称自动解析为 QQ 号并调用 `poke` 戳一戳群友，或通过 `send_master_private` 随时向主人私聊汇报重要事项。

---

## 系统流程

```
NapCat (OneBot 11 正向 WebSocket)
    │
    ├─ 群聊消息 ──→ 入站指令拦截 (/开启 /关闭 /重启 /刷新 /切换 /help)
    │                  │
    │                  ▼
    │              入队缓冲 & 后台图片预取 (下载 + VLM 表情包转写)
    │                  │
    │                  ▼
    │              防抖聚合 & 精力值更新 & 社交欲望/RAG兴趣度打分
    │                  │
    │                  ▼
    │              是否回复？── 否 ──→ 潜水观察
    │                  │
    │                  是
    │                  ▼
    │              RAG 记忆检索 (含跨轮 Top-1 保留) + 上下文构建
    │                  │
    │                  ▼
    │              LLM 思考与生成 (多轮 Function Call 工具链)
    │                  │
    │                  ├─ 调用 skip ──→ 静默跳过且清除本轮痕迹
    │                  ├─ 其它工具 ───→ 执行工具 → 结果回传继续生成
    │                  └─ 最终回复 ───→ 标记归一化 + 分段发送 (文本 + 表情包) + 回复订阅登记
    │
    └─ 主人私聊消息 ──→ 跳过防抖/精力/决策 ──→ RAG 检索 + LLM 生成 ──→ send_private_msg
    │
    ▼
空闲/轮次达标 ──→ 触发第一人称日记总结 ──→ 存入 ChromaDB 向量库
```

---

## 项目结构

```
YukiV6/
├── main.py                          # 程序入口：单实例锁、组件装配、/health 与 /notify、启动监听
├── config.py                        # 配置中心：dataclass 定义源、YAML 自动同步与加载
├── init.py                          # 群聊开关状态持久化与启动检查
├── setup.py                         # 一键部署与配置工具（支持交互式向导、非交互式 CLI 与 --check 自检）
├── pyproject.toml                   # 项目依赖声明与 pytest 配置
├── blacklist.txt                    # 记忆检索屏蔽词黑名单
│
├── configs/                         # 配置文件目录
│   ├── config.yaml                  # 运行时配置（含 API Key，已在 .gitignore 忽略）
│   └── README.md                    # 配置系统说明文档
│
├── core/                            # 核心业务层
│   ├── session_pipeline.py          # 8 阶段串行会话管线（按 chat_id 加锁）
│   ├── brain.py                     # YukiState 状态管理（精力/活跃度/生物钟/消息缓冲）
│   ├── prompts.py                   # 系统提示词模板与上下文组装
│   ├── history_manager.py           # 对话历史持久化（原子化读写与标记自修复）
│   ├── reply_format.py              # 回复标记归一化与 <layout> 剥离
│   ├── tool_markup.py               # 文本工具调用还原与兜底清洗
│   ├── toolchain.py                 # Function Call 工具链框架
│   ├── notebook.py                  # 全局小本本存储
│   ├── recall_cache.py              # 跨轮 Top-1 召回缓存持久化
│   ├── reply_watch.py               # 回复订阅（等回音判定与追击提醒）
│   ├── engine/                      # 引擎门面与 4 个子服务（reply / decision / diary / monitor）
│   ├── tools/                       # 主模型挂载的 12 个 Function Call 工具
│   └── maid/                        # 小女仆自治系统（Harness 后端对接、能力边界、自进化准则）
│
├── modules/                         # 功能模块
│   ├── QQNapcatListen/              # QQ 入站事件监听与管理指令拦截
│   ├── memory/                      # RAG 记忆系统（ChromaDB + text2vec + jieba）
│   ├── stickers/                    # 表情包向量检索、冷却与 RLHF 加权
│   ├── vision/                      # 视觉处理、图片后台预取、短索引 ImageStore 与缓存
│   ├── shot_memory/                 # 群聊截屏留念渲染与检索
│   ├── github_monitor/              # GitHub 仓库事件监控与卡片渲染
│   ├── qzone/                       # QQ 空间说说发布与动态监控
│   └── debug/                       # Context Debug WebUI（端口 8777）与调试快照
│
├── network/                         # 网络通信层
│   └── napcat.py                    # NapCatGateway（WS 连接、帧路由、OneBot API 调用、CQ 解析）
│
├── utils/                           # 基础设施工具
│   ├── llm_client.py                # OpenAI 兼容客户端（主备故障转移 + 空回复/断连重试）
│   ├── http_client.py               # 统一 SSL/HTTP 客户端（certifi + 独立 DNS 解析池）
│   ├── health_server.py             # /health 探针与 /notify 端点（默认端口 8778）
│   ├── logger.py                    # 控制台(INFO) / 文件(DEBUG) 分级日志
│   ├── paths.py                     # 跨平台路径归一化
│   └── download_model.py            # RAG 嵌入模型下载工具
│
├── deploy/                          # 容器化部署、自进化守护（supervisor）与小女仆执行器（maid_runner）
├── skills/                          # 小女仆固化 Python 技能库
├── scripts/                         # 独立运维工具（表情包打标/导入、记忆库管理、精力曲线可视化等）
├── tests/                           # 11 个全离线 pytest 单元测试模块（61 项用例）
├── docs/                            # 架构、工具链、排障、自进化准则与 LLM 交接文档
└── _archive/                        # 已归档模块与一键复原指南
```

---

## 文档索引与测试

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统运行拓扑、目录树、核心数据流与代码定位速查表 |
| [docs/contributing.md](docs/contributing.md) | 开发与 LLM 交接指南（测试环境、常见开发流程、安全红线） |
| [docs/toolchain-usage.md](docs/toolchain-usage.md) | Function Call 工具链详解与扩展指南 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 常见问题排查手册 |
| [docs/evolution-charter.md](docs/evolution-charter.md) | 自进化安全准则（路径分级、限额、验证门） |
| [docs/database-profile.md](docs/database-profile.md) | 向量数据库与数据资产结构说明 |
| [docs/changelog.md](docs/changelog.md) | 版本更新日志 |
| [deploy/README.md](deploy/README.md) | 容器化、自进化守护进程与小女仆 Harness 执行器运维说明 |
| [configs/README.md](configs/README.md) | 配置系统说明 |

### 运行测试

测试套件全部采用离线 Mock，无需联网或真实 API Key：

```bash
# 运行全量测试
python -m pytest -q

# 运行单个测试模块
python -m pytest tests/test_toolchain.py -q
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| **语言与运行时** | Python 3.11+ / asyncio |
| **QQ 协议层** | NapCatQQ (OneBot 11 WebSocket, `websockets`) |
| **HTTP 客户端** | `aiohttp` + `certifi` |
| **主对话模型** | DeepSeek / OpenAI 兼容接口（可选原生多模态视觉输入） |
| **视觉与生图模型** | Qwen-VL / 通义万相（DashScope）或 OpenAI 兼容接口 |
| **向量数据库与嵌入** | ChromaDB + `sentence-transformers` (`shibing624/text2vec-base-chinese`) + `jieba` |
| **配置管理** | PyYAML + Python `dataclass` |
| **小女仆执行后端** | DeepSeek Harness (`deploy/maid_runner.py` 宿主子进程) |
| **生产容器与自进化** | Docker（代码只读挂载）+ systemd supervisor + 独立模型审查 + 5 道校验门 |

---

## 寄语

理解一个复杂系统就像推导一个高阶矩阵。从同步阻塞到异步并行的跨越，再到如今小女仆系统的自我进化，不仅是代码的优化，更是为了让 Yuki 在等待回音的间隙，依然能感受到这个世界的脉动。

---

_最后更新: 2026/11 · YukiV6 (FrostFrame)_
