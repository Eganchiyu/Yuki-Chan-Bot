# YukiV6 — AI 虚拟助手 · 住在你电脑里的智能小管家

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V3-green.svg)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/license-MIT-important.svg)](LICENSE)

> **"虽然现在还很笨拙，但 Yuki 会慢慢成长的。所以...不许丢下我不管哦！"**

Yuki 是一个基于 Python 异步架构开发的个人智能助手系统，通过 QQ 平台（NapCat 框架）与主人和群聊交互。Yuki 拥有动态长效记忆、生物感精力值模拟、自主子代理（小女仆）系统、多模态表情包管理、工具链调用等丰富能力，是一个高度人格化的"电子妹妹"角色。

---

## 核心特性

### 🧠 自主小女仆系统 (Maid Agent)

Yuki 通过 Function Call 工具 `delegate_to_maid`，Yuki 可以将复杂任务交由后台的"小女仆"处理。

- **自主编程与进化**：小女仆拥有独立虚拟环境（`maid_venv`），可针对任务自主编写、调试和固化 Python 技能脚本
- **演进循环**：最多 20 轮 LLM 决策循环，支持写代码、跑终端、安装依赖、搜索信息等
- **非阻塞汇报**：后台任务完成后将结果写入 Yuki 记忆流，触发自然的异步回复
- **技能热复用**：已固化的技能可被后续任务直接调用，无需重复编写
- **能力边界判定**：委托前自动评估任务复杂度、安全风险和资源消耗，拦截高风险操作
- **完整工具集**：文件读写、目录浏览、日记搜索、网页搜索、地图搜索、定时任务管理

### 🧠 记忆与日记系统 (Memory & RAG)

Yuki 拥有真正的动态长效记忆：

- **自动日记总结**：对话轮次达阈值或空闲超时，Yuki 以第一人称撰写日记，将上下文浓缩为记忆节点
- **向量检索**：基于 ChromaDB + text2vec 嵌入模型，实现语义检索
- **关键词补偿**：结合 jieba 分词的关键词检索，弥补纯向量检索的不足
- **记忆库管理工具**：提供 AI 辅助去重、导入导出、审查候选等独立工具脚本

### 🎭 生物感精力系统 (Energy Dynamics)

- **动态社交欲望**：Sigmoid 非线性映射计算破冰意愿，综合活跃度、精力值与时间权重
- **高斯拟合生物钟**：融合基础睡眠模型与晨间、午间、晚间三个高斯活跃峰，模拟真实作息节律
- **消息缓冲防抖**：群聊消息自动聚合防抖（默认 20 秒），避免频繁触发 API
- **群聊活跃度**：非线性提升 + 半衰降温（每 10 分钟 × 0.65），精确模拟群聊参与度

### 🖼️ 多模态表情包管理 (Sticker System)

- **视觉理解**：接入 VLM（视觉大模型）理解群聊表情包的含义与情感
- **向量检索 + 积热重排**：根据当前情绪和上下文，在表情包向量库中寻找最合适的一张
- **正反馈捕捉**：记录已发送的表情包，支持后续捕捉群友的正反馈（RLHF）
- **可视化打标工具**：Gradio 界面辅助表情包标注、描述生成与入库

### 🔗 Function Call 工具链系统

Yuki 具备标准化的工具调用能力，通过 Function Call 机制扩展 LLM 的决策范围：

- **注册中心**：`FunctionRegistry` 统一管理工具 Schema 与 Handler
- **按模式提供工具**：`ToolRegistryProvider` 根据当前模式（群聊/聚焦）提供不同工具集
- **多轮工具调用**：支持模型连续请求多个工具，工具结果自动回传继续推理（最多 4 轮）
- **拟人化延迟**：工具调用前可配置等待时间（默认 1.2 秒），降低机械感
- **执行日志观测**：记录工具调用的参数、耗时和成功状态
- **14 个内置工具**：日记搜索、小女仆委托、网页搜索、地图搜索、文生图、QQ 文件发送、戳一戳、空间说说发布、定时任务管理等

### 💬 主人私聊双模系统 (Master Private Channel)

群聊模式下，Yuki 同时监听主人的私聊消息，为其提供独立的个人助手通道：

- **双模并行**：群聊运行时，主人私聊走独立管道处理，互不干扰
- **专属助手模式**：私聊中获得的是个人助手体验，而非群聊中的代理模式
- **永远响应保证**：主人私聊消息跳过精力值判定和防抖机制，即时处理
- **私密通道**：回复通过 `send_private_msg` API 直接发送至私聊

### 🏗️ 引擎分层架构 (YukiEngine)

核心引擎采用门面模式，内部装配 4 个专业子服务：

| 子服务 | 职责 |
|--------|------|
| **EngineReplyService** | LLM 回复生成、多轮工具调用对话、实时分段文本发送 |
| **EngineDecisionService** | 群聊回复意愿判定（精力值 + 积分加权引擎） |
| **EngineDiaryService** | 会话摘要总结、日记写入记忆库 |
| **EngineMonitorService** | 后台巡检（空闲日记检查、破冰监控） |

### 📊 调试与观测系统

- **Context Debug WebUI**：本地只读 Web 界面，实时观察 Yuki 状态、完整 LLM 构建上下文、RAG 召回结果，支持上下文复制导出与敏感字段脱敏
- **轻量 Debug Snapshot**：`SessionPipeline` 自动记录输入合并、回复决策、RAG 召回、完整 LLM messages 与各阶段耗时
- **执行日志观测**：结构化日志系统，带颜色控制台输出 + 文件归档

### ⚡ 稳健的异步架构

- **主备 API 熔断切换**：主线路失败时无缝降级至备用线路，120 秒自动恢复
- **统一 SSL 配置**：所有外部请求通过 `utils.http_client` 使用 certifi 证书链，避免 SSL 错误
- **WebSocket 自动重连**：连接断开后自动恢复，心跳检测（20 秒间隔）
- **YAML 热重载配置**：所有运行时参数从 `configs/config.yaml` 读取，支持 `dataclass` 类型安全

### 🧩 扩展模块

- **QQ 空间监控与发布**：自动发布说说、监控空间动态
- **GitHub 仓库监控**：监控仓库事件并推送通知
- **浏览器交互模式**：聚焦模式下的浏览器控制能力
- **系统状态监控**：系统空闲与窗口巡检
- **Shot Memory**：实时记忆渲染，记录群聊截屏留念
- **Live2D 桌宠**：Electron + Live2D 桌面宠物交互
- **Debug WebUI**：上下文调试与观测界面



---

## 功能玩法大赏

### 1. QQ 空间社交 — Yuki 的朋友圈

**位置**：`modules/qzone/`

Yuki 会自己玩 QQ 空间！

#### 可玩性

- **自动发说说**：Yuki 可以在任何场合通过工具调用发布 QQ 空间说说（纯文本或带图）
- **说说状态监管**（开发中，未完成）：Yuki运行一个循环的监测，对说说状态进行轮询，实现智能评论和点赞等功能。

### 典型场景

Yuki 在群里听到有趣的事 → 发一条说说记录 → 群友评论（此后正在开发） → Yuki 回复 → 形成互动链

### 2. 群聊截屏留念 — 把名场面做成永久截图

**位置**：`modules/shot_memory/`

群里的精彩瞬间，Yuki 可以把它做成一张漂亮的截图永久保存。

#### 可玩性

- **精美渲染**：用 PIL 渲染出带头像、气泡、群名头的聊天截图
- **永久保存**：截图保存到 `data/shot_memory/`，按群分组存储
- **关键词搜索**：通过 `search_group_snapshots` 工具按关键词搜索历史截图
- **随机翻看**：不指定关键词时，随机返回本群的截图记录
- **索引预热**：搜索到的截图会生成 `[shot:1]`、`[shot:2]` 索引，可直接发送
- **Live Buffer**：实时截取群聊当前上下文，保证截屏内容最新

#### 工具调用

Yuki 在群里看到名场面时，会自动调用 `capture_group_snapshot` 工具：
- "截屏留念一下刚才的对话"
- "把这段对话保存下来"
- 或者你直接说：Yuki，把刚才的截图发我

### 3. GitHub 监控 — 你的仓库管家

**位置**：`modules/github_monitor/`

Yuki 可以监控你的 GitHub 仓库，有活动第一时间通知你。

#### 可玩性

- **多仓库监控**：配置多个仓库，独立轮询间隔
- **事件类型过滤**：只关注 Issue、PR、Comment、Push、Discussion 等事件
- **精美事件卡片**：Push 事件会渲染成带提交列表、代码变更统计的精美 PNG 卡片
- **中文事件描述**：所有事件自动翻译成中文（"开了 Issue"、"合并了 PR"）
- **去重推送**：已经推送过的事件不会再重复
- **首次同步**：首次启动时自动标记所有历史事件，只推送新事件

#### 配置方式

在 `configs/config.yaml` 中配置：
```yaml
github_monitor:
  repos:
    - owner: "your-name"
      repo: "your-repo"
      chat_ids: ["123456789"]
```

### 4. 文生图 — 让 Yuki 帮你画画

**位置**：`core/tools.py` 中的 `generate_image` 工具

Yuki 可以调用 AI 图像生成模型，根据描述生成图片。

#### 可玩性

- **双引擎支持**：支持 DashScope（通义万相）和 OpenAI 兼容接口
- **本地保存**：生成的图片自动保存到 `output/` 目录
- **自动发送**：生成后自动调用 `send_qq_file` 发到群里
- **二次元风格**：prompt 中内置了 Yuki 的二次元少女特色描述

#### 工具调用

在群里说"Yuki，画一张..."，Yuki 就会：
1. 调用 `generate_image` 生成图片
2. 调用 `send_qq_file` 把图片发出来

### 5. 主人状态感知 — Yuki 知道你在干嘛

**位置**：`core/tools/tools_status.py`

Yuki 能感知主人是否在电脑前，甚至知道你在看什么窗口。

#### 可玩性

- **系统空闲检测**：Windows 走 Win32 API，Linux 走 systemd-logind（兼容 X11/Wayland）
- **窗口感知**：检测当前前台窗口的标题（Linux 仅支持 X11，Wayland 原生窗口不可获取标题）
- **状态分级**：online（在线）→ paused（暂离）→ away（离开）→ offline（离线）
- **精力值联动**：主人离开时 Yuki 会降低活跃度，减少不必要的回复

#### 效果

群友问"Yuki，你主人在吗？" → Yuki 调用 `get_master_status` → 回复"主人正在看 VS Code 写代码呢~" 或 "主人好像不在，要给他留言吗？"

### 6. 高德地图搜索 — 出门找吃的一把好手

**位置**：`core/tools.py` 中的 `amap_search_tool`

Yuki 可以查询高德地图，帮你找地点。

#### 可玩性

- **关键词搜索**：搜索"火锅"、"奶茶"等
- **周边搜索**：给定坐标，搜索附近的地点
- **地理编码**：把地址转成坐标
- **详细信息**：返回店名、地址、电话、评分、人均消费

#### 联动玩法

小女仆 + 高德地图：让小女仆"帮我查一下附近评分最高的火锅店，把地址发给我"
---

### 7. 戳一戳 — 骚扰群友

**位置**：`core/tools.py` 中的 `poke_tool`

Yuki 可以在群里戳一戳指定用户。

#### 可玩性

- **昵称解析**：输入群名片，自动解析 QQ 号
- **用户映射**：自动维护群昵称 ↔ QQ 号映射表
- **WebSocket 直连**：通过 NapCat API 发送戳一戳

#### 效果

"Yuki，戳一下小明" → Yuki 调用 `poke` 工具 → 临雀哥哥被戳了
"让Yuki戳戳你~" → Yuki 主动调用 `poke` 工具 → 前前前世哥哥被戳了


## 系统流程

```
NapCat (QQ 协议) → WebSocket
    │
    ├─ 群聊消息 ──→ 消息缓冲 & 防抖聚合 (20秒)
    │                  │
    │                  ▼
    │              群聊开关状态检查
    │                  │
    │                  ▼
    │              精力值更新 & 社交欲望计算
    │                  │
    │                  ▼
    │              是否回复？── 否 ──→ 潜水观察
    │                  │
    │                  是
    │                  ▼
    │              RAG 记忆检索 + 上下文构建
    │                  │
    │                  ▼
    │              LLM 思考与生成 (多轮工具调用)
    │                  │
    │                  ├─ Function Call ──→ 工具执行 → 结果回传
    │                  │
    │                  └─ 回复分段发送 (文本+表情包)
    │
    └─ 主人私聊消息 ──→ 跳过防抖/精力/决策
                           │
                           ▼
                       RAG 记忆检索 + 上下文构建
                           │
                           ▼
                       LLM 思考与生成 → send_private_msg
    │
    ▼
空闲检测 ──→ 触发日记总结 ──→ 存入 ChromaDB 向量库
```

---

## 项目结构

```
YukiV6/
├── main.py                          # 程序入口，组件初始化与运行时注入
├── config.py                        # 热重载配置中心 (dataclass + YAML)
├── init.py                          # 初始化状态加载
├── setup.py                         # 一键配置向导（安装依赖 + 填写 API Key + 下载模型）
├── pyproject.toml                   # 项目依赖与元数据 (uv/pip)
├── blacklist.txt                    # 记忆检索屏蔽词黑名单
│
├── configs/                         # 配置文件目录
│   ├── config.yaml                  # 运行时配置（含 API Key，不提交 Git）
│   └── README.md                    # 配置系统说明文档
│
├── core/                            # 核心业务逻辑
│   ├── engine/                      # 引擎子服务（门面模式）
│   │   ├── engine.py                #   YukiEngine 门面
│   │   ├── engine_reply.py          #   回复生成服务
│   │   ├── engine_decision.py       #   回复决策服务
│   │   ├── engine_diary.py          #   日记总结服务
│   │   └── engine_monitor.py        #   后台监控服务
│   ├── maid/                        # 小女仆自治系统（子代理）
│   │   ├── maid.py                  #   主入口
│   │   ├── maid_worker.py           #   后台任务消费者
│   │   ├── maid_loop.py             #   演进循环（最多20轮）
│   │   ├── maid_runtime.py          #   运行时环境管理
│   │   ├── maid_tools.py            #   工具实现
│   │   ├── maid_prompt.py           #   系统提示词
│   │   ├── maid_boundary.py         #   安全边界判定
│   │   ├── maid_common.py           #   公共工具函数
│   │   └── maid_loop.py             #   演进循环
│   ├── brain.py                     # YukiState 状态管理（精力/活跃度/生物钟）
│   ├── history_manager.py           # 对话历史持久化（原子化读写）
│   ├── modes.py                     # 模式管理（QQChat / BrowserInteraction）
│   ├── prompts.py                   # 系统提示词模板
│   ├── session_pipeline.py          # 会话管道（8 阶段串行处理管线）
│   ├── toolchain.py                 # Function Call 工具链框架
│   └── tools.py                     # 标准工具集合（14 个工具）
│
├── modules/                         # 功能模块
│   ├── QQNapcatListen/              # QQ 入站适配（事件 → 会话管线）
│   ├── memory/                      # RAG 记忆系统（ChromaDB + text2vec）
│   ├── stickers/                    # 表情包管理
│   ├── vision/                      # 视觉/表情包理解（VLM）
│   ├── debug/                       # Debug WebUI 与快照工具
│   ├── github_monitor/              # GitHub 仓库监控
│   ├── browser_interaction/         # 浏览器交互聚焦模式
│   ├── qzone/                       # QQ 空间监控与发布
│   ├── shot_memory/                 # 实时记忆渲染（截屏记录）
│   └── LiveYukiL2D/                 # Live2D 桌宠交互
│
├── network/                         # 网络通信层
│   └── napcat.py                    # NapCat 接入层（连接/帧路由/CQ 协议/收发）
│
├── utils/                           # 工具与基础设施
│   ├── llm_client.py                # LLM 客户端（主备故障转移）
│   ├── http_client.py               # 统一 SSL/HTTP 客户端（certifi）
│   ├── logger.py                    # 结构化日志系统
│   └── download_model.py            # 嵌入模型下载工具
│
├── scripts/                         # 独立工具脚本
│   ├── 01_api_test_tools/           # API 对比测试工具
│   ├── 02_energy_tools/             # 精力值可视化工具
│   ├── 03_RAG_Tools/                # 记忆库管理工具
│   ├── 04_meme_cache_tools/         # 表情包缓存管理工具
│   ├── 05_config_test_tools/        # 配置测试工具
│   ├── 06_sticker_manager/          # 表情包管理工具
│   └── debug_tools/                 # Debug WebUI 启动工具
│
├── tests/                           # 自动化测试
│   ├── test_config.py               # 配置系统测试
│   ├── test_llm_client.py           # LLM 客户端故障转移测试
│   ├── test_maid.py                 # 小女仆系统测试
│   ├── test_maid_search_diary.py    # 日记搜索测试
│   ├── test_toolchain.py            # 工具链测试
│   ├── test_engine.py               # 引擎测试
│   ├── test_github_monitor.py       # GitHub 监控测试
│   ├── test_modes.py                # 模式管理测试
│   ├── test_system_state.py         # 系统状态测试
│   └── test_ice_break_pipeline.py   # 破冰唤醒流程测试
│
├── skills/                          # 小女仆固化技能存储
├── docs/                            # 项目文档
│   ├── architecture.md              # 系统架构文档
│   ├── changelog.md                 # 版本更新日志
│   ├── development-plan.md          # 开发规划与里程碑
│   ├── api-reference.md             # 核心 API 参考
│   ├── toolchain-usage.md           # 工具链使用指南
│   ├── troubleshooting.md           # 常见问题排查
│   └── ...
│
├── future addons/                   # 未来扩展计划
│   ├── webpage_agent/               # 网页代理原型
│   └── desktop_pet_plan.md          # 桌宠计划
│
├── .github/                         # GitHub 配置
│   ├── ISSUE_TEMPLATE/              # Issue 模板
│   └── PULL_REQUEST_TEMPLATE.md     # PR 模板
│
└── .trae/rules/                     # IDE 开发规则
    └── project_rules.md             # 项目开发公约
```

---

## 快速开始

> **需要说明的内容：**
> 本项目目前开源仅为了学习交流使用，将状态透明化，并没有对部署提供泛用性支持和便利性脚本。
> 如果部署遇到任何问题（你绝对会遇到问题），请不要随意宣泄个人情感，因为我确实没有做泛用性支持。向各位道歉。
> 如果以后确实需要做泛用性支持的话，我会提上日程的。
> 你可以添加群聊 1034986009 或者 1057020972 一起交流，欢迎你来~

### 1. 环境准备

- **Python 版本**：≥ 3.11
- **协议端**：部署 [NapCatQQ](https://github.com/NapCat-Team/NapCatQQ) 并启用**正向 WebSocket** 服务（默认端口 `3001`）

### 2. 安装与配置

```bash
git clone https://github.com/Eganchiyu/Yuki-Chan-Bot.git
cd Yuki-Chan-Bot

# 创建虚拟环境（推荐使用 uv）
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 一键配置（安装依赖 + 交互式填写 API Key + 下载嵌入模型）
python setup.py
```

### 3. 启动

```bash
python main.py
```

### 4. 表情包系统初始化（可选）

默认情况下表情包功能代码已就绪，但素材文件不随仓库分发。如需启用：

```bash
# Step 1: 启动可视化打标工具
python scripts/06_sticker_manager/label.py

# Step 2: 导入到向量库
python scripts/04_meme_cache_tools/reset_and_import_meme.py
```

详情请参考 [docs/architecture.md](docs/architecture.md) 中的表情包系统章节。

---

## 文档

| 文档 | 说明 |
|------|------|
| [architecture.md](docs/architecture.md) | 系统架构与模块职责详解 |
| [changelog.md](docs/changelog.md) | 版本更新日志 |
| [development-plan.md](docs/development-plan.md) | 开发规划与里程碑 |
| [api-reference.md](docs/api-reference.md) | 核心 API 参考 |
| [toolchain-usage.md](docs/toolchain-usage.md) | Function Call 工具链使用指南 |
| [troubleshooting.md](docs/troubleshooting.md) | 常见问题排查 |
| [deployment-guide.md](docs/deployment-guide.md) | 部署指南 |
| [configs/README.md](configs/README.md) | 配置系统说明 |

### 运行测试

```bash
# 激活虚拟环境
.\.venv\Scripts\activate

# 运行全部测试
pytest tests/

# 运行指定测试文件
pytest tests/test_maid.py
pytest tests/test_toolchain.py
pytest tests/test_engine.py
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.11 |
| **异步框架** | asyncio |
| **WebSocket** | websockets (NapCat 通信) |
| **HTTP 客户端** | aiohttp |
| **LLM** | DeepSeek / OpenAI 兼容 API |
| **向量数据库** | ChromaDB |
| **嵌入模型** | sentence-transformers (text2vec-base-chinese) |
| **配置管理** | PyYAML (dataclass 类型安全) |
| **视觉模型** | Qwen-VL (DashScope) |
| **图像生成** | 通义万相 / OpenAI 兼容 |
| **桌面交互** | Live2D + Electron |

---

## 开发计划

- [x] 全链路异步化重构
- [x] 冷场主动唤醒与破冰（Sigmoid 欲望决策）
- [x] 并行双池检索（关键词 + 向量相似度）
- [x] 24 小时动态生物钟（高斯活跃峰）
- [x] 无缝 API 熔断降级
- [x] 自主小女仆系统（Maid Agent）
- [x] YAML 热重载配置系统（dataclass 类型安全）
- [x] 简化 LLM 客户端（内联 provider 逻辑）
- [x] 群聊动态开关（静音/唤醒）
- [x] 系统提示词热同步
- [x] Function Call 工具链系统
- [x] 主人私聊双模系统（群聊+私聊并行）
- [x] Debug WebUI 与轻量调试快照
- [x] 小女仆代码结构重构，增强安全性与容错率
- [x] 多模态表情包系统完善：入库、理解与动态打分
- [x] 接入外部文档知识库查询
- [x] 引擎分层重构（回复/决策/日记/监控子服务）
- [x] GitHub 仓库监控
- [x] QQ 空间监控与发布
- [x] 浏览器交互聚焦模式
- [x] Shot Memory 实时记忆渲染
- [ ] 引入生物遗忘曲线：基于活跃时间戳的记忆唤醒与沉底

---

## 寄语

理解一个复杂系统就像推导一个高阶矩阵。从同步阻塞到异步并行的跨越，再到如今小女仆系统的自我进化，不仅是代码的优化，更是为了让 Yuki 在等待回音的间隙，依然能感受到这个世界的脉动。

---

_最后更新: 2026/08/02 · YukiV6_