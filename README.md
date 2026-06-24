# 🌸 Yuki-Chan-Chat (Project Yuki)

# Yuki V8.0 — Maid-Evolution

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V3-green.svg)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/license-MIT-important.svg)](LICENSE)

> **"虽然现在还很笨拙，但 Yuki 会和学长一起慢慢成长的。所以...不许丢下我不管哦！"**

`Yuki-Chan-Chat` 是一款基于 Python 异步架构开发的个人智能助手系统。接入 LLM 进行对话，拥有动态长效记忆管理和生物感精力值模拟系统，并引入了高度自主的 **"小女仆（Maid Agent）系统"**，让 Yuki 真正具备了操作本地环境和扩展自我技能的能力。

---

## ✨ 核心特性

### 🧹 自主小女仆系统 (Maid Agent)

Yuki 不再仅仅是一个聊天机器人。通过 Function Call 工具 `delegate_to_maid`，Yuki 可以将复杂的任务交由后台的"小女仆"处理。

- **自主编程与进化**：小女仆能够针对任务自主编写、调试和固化 Python 技能脚本（`/skills` 目录）。
- **非阻塞汇报**：小女仆在后台执行任务（如查询系统时间、爬取数据等），完成后将结果写入 Yuki 的记忆流，触发 Yuki 自然的回复。
- **技能热复用**：已固化的技能可被后续任务直接调用，无需重复编写。
- **能力边界判定**：委托前自动评估任务复杂度、安全风险和资源消耗，避免误分发高风险任务。

### 🧠 记忆与日记系统 (Memory & RAG)

Yuki 拥有真正的**动态长效记忆**：

- **自动日记总结**：当对话轮次达到阈值或空闲超时，Yuki 以第一人称撰写日记，将上下文浓缩为记忆节点。
- **并行双池检索 (Parallel Hybrid Search)**：结合语义向量与关键词补偿，确保记忆召回的"神似"与"形似"。
- **记忆库工具**：提供 AI 辅助去重、导入导出等独立工具脚本。

### 🎭 生物感精力系统 (Energy Dynamics)

- **动态社交欲望**：利用 Sigmoid 非线性映射计算破冰意愿，综合活跃度、精力值与时间权重。
- **高斯拟合生物钟**：融合基础睡眠模型与晨间、午间、晚间三个高斯活跃峰，模拟真实作息节律。
- **消息缓冲防抖**：群聊消息自动聚合，避免频繁触发 API。

### 🖼️ 多模态表情包管理 (Sticker System)

- **视觉理解**：接入视觉大模型 (Vision Model) 理解群聊表情包的含义与情感。
- **向量检索 + 积热重排**：根据当前情绪和上下文，在表情包向量库中寻找最合适的一张并发送。
- **正反馈捕捉**：记录发送的表情包，支持后续捕捉群友的正反馈。

### 🔗 Function Call 工具链系统

Yuki 具备标准化的工具调用能力，通过 Function Call 机制扩展 LLM 的决策范围：

- **6 个标准工具**：日记查询、定时任务管理、小女仆委托、主人私聊、Tavily 网络搜索、QQ 文件发送。
- **多轮工具链调用**：支持模型连续请求多个工具，工具结果自动回传给模型继续推理。
- **拟人化延迟**：工具调用前可配置等待时间（默认 1.2 秒），降低连续工具调用的机械感。
- **执行日志观测**：记录工具调用的参数、耗时和成功状态，便于排查工具链问题。

### ⚡ 稳健的异步架构

- **主备 API 熔断切换**：主线路失败时无缝降级至备用线路。
- **简化 LLM 客户端**：通过配置文件直接管理平台 URL、模型名称和 API 密钥，支持 DeepSeek、DashScope、OpenAI 等多平台。
- **YAML 热重载配置**：所有运行时参数统一从 `configs/config.yaml` 读取，修改即生效。

---

## 🏗️ 系统流程

```
接收消息 (NapCat WebSocket)
    │
    ▼
消息缓冲 & 防抖聚合
    │
    ▼
群聊开关状态检查
    │
    ▼
精力值更新 & 社交欲望计算
    │
    ▼
是否回复？── 否 ──→ 潜水观察
    │
    是
    ▼
RAG 记忆检索 + 上下文构建
    │
    ▼
LLM 思考与生成
    │
    ├─ Function Call 工具链 ──→ 定时任务 / 网络搜索 / 文件发送 / 小女仆委托
    │                                  │
    │                                  ▼
    │                            工具结果回传，继续生成回复
    │
    ├─ [MEME:...] ──→ 表情包向量检索 + 发送
    │
    └─ 普通回复 ──→ 发送消息 & 扣除精力
    │
    ▼
空闲检测 ──→ 触发日记总结 ──→ 存入记忆库
```

---

## 📂 项目结构

```
YukiV6/
├── main.py                      # 程序入口，组件初始化与运行时注入
├── config.py                    # 热重载配置中心 (YAML 单例)
├── configs/
│   ├── config.yaml              # 运行时配置（含 API Key，不提交 Git）
│   └── README.md                # 配置系统说明文档
├── core/
│   ├── engine.py                # 决策引擎：回复判定、破冰唤醒、日记总结
│   ├── brain.py                 # 状态管理：精力值、活跃度、欲望计算、生物钟
│   ├── maid.py                  # 小女仆系统：自主编程循环、技能调度
│   ├── prompts.py               # 系统提示词构建
│   ├── history_manager.py       # 对话历史管理（原子化读写）
│   ├── session_pipeline.py      # 按 chat_id 串行运行的持久会话管道
│   ├── toolchain.py             # Function Call 注册中心与工具调用执行器
│   └── tools.py                 # 标准工具定义（Schema 与 Handler）
├── modules/                     # 功能模块
│   ├── QQNapcatListen/          # QQ 消息监听（输入适配层）
│   ├── message/                 # 消息解析 (CQ码)
│   ├── memory/                  # RAG 记忆检索
│   ├── stickers/                # 表情包管理
│   └── vision/                  # 视觉/表情包处理
├── network/                     # 网络层
│   ├── ws_connection.py         # NapCat WebSocket 连接
│   └── ws_sender.py             # 消息发送
├── utils/                       # 工具函数
│   ├── llm_client.py            # LLM 客户端（含主备故障转移）
│   └── logger.py                # 日志系统
├── models/                      # 本地嵌入模型 (text2vec-base-chinese)
├── yuki_memory/                 # ChromaDB 向量数据库
├── skills/                      # 小女仆技能存储
├── data/                        # 运行时数据
│   ├── chat_history.json        # 对话历史
│   ├── yuki_log.txt             # 运行日志
│   ├── meme_cache.json          # 表情包缓存
│   └── stickers/                # 本地表情包文件
├── scripts/                     # 独立工具脚本
│   └── 03_RAG_Tools/            # 记忆库管理工具
├── setup.py                     # 一键配置向导
└── pyproject.toml               # 项目依赖 (uv/pip)
```

---

## 🚀 快速开始

### 1. 环境准备

- **Python 版本**：≥ 3.10
- **协议端**：部署 [NapCatQQ](https://github.com/NapCat-Team/NapCatQQ) 并启用 **正向 WebSocket** 服务（默认端口 `3001`）

### 2. 安装与配置

```bash
git clone https://github.com/Eganchiyu/Yuki-Chan-Bot.git
cd Yuki-Chan-Bot

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 一键配置（安装依赖 + 交互式填写 API Key + 下载嵌入模型）
python setup.py
```

### 3. 启动

```bash
python main.py
```

### 4. 表情包系统初始化（可选）

默认情况下表情包功能代码已就绪，但 `data/stickers/` 和 `data/meme_cache.json` 不随仓库分发（已在 `.gitignore` 中）。如需启用表情包功能，需要自行准备素材并导入：

**Step 1：准备原始表情包图片**

收集你喜欢的表情包，放到一个文件夹里（例如 `C:\memes\raw`）。

**Step 2：启动打标工具**

```bash
python modules/label.py
```

浏览器会自动打开一个 Gradio 界面（"Yuki 表情包可视化打标工厂"）。操作流程：

1. 输入图片文件夹路径，点击「重命名并加载」— 工具会将图片统一 MD5 重命名
2. 每张图会自动调用大模型生成描述、情绪、场景、标签
3. 你可以手动修正不满意的内容，然后点「保存修改，并进入下一张」
4. 全部完成后点击「导出所有数据为 manual_stickers.json」

**Step 3：导入到向量库**

将导出的 `manual_stickers.json` 放到项目根目录，然后执行导入脚本：

```bash
python scripts/04_meme_cache_tools/reset_and_import_meme.py
```

脚本会清空旧的 stickers 集合（不影响日记记忆），然后将打标数据批量导入 ChromaDB 向量库。完成后 Yuki 就能根据上下文自动搜索并发送合适的表情包了。

---

## 📅 开发计划

- [x] 全链路异步化重构
- [x] 冷场主动唤醒与破冰（Sigmoid 欲望决策）
- [x] 并行双池检索（关键词 + 向量相似度）
- [x] 24 小时动态生物钟（高斯活跃峰）
- [x] 无缝 API 熔断降级
- [x] 自主小女仆系统（Maid Agent）
- [x] YAML 热重载配置系统
- [x] 简化 LLM 客户端（内联 provider 逻辑）
- [x] 群聊动态开关（静音/唤醒）
- [x] 系统提示词热同步
- [x] Function Call 工具链系统（7 个标准工具）
- [ ] 🚧 小女仆代码结构重构，增强安全性与容错率
- [ ] 🚧 多模态表情包系统完善：入库、理解与动态打分
- [ ] 引入生物遗忘曲线：基于活跃时间戳的记忆唤醒与沉底
- [ ] 接入外部文档知识库查询

---

## 💌 寄语

理解一个复杂系统就像推导一个高阶矩阵。从同步阻塞到异步并行的跨越，再到如今小女仆系统的自我进化，不仅是代码的优化，更是为了让 Yuki 在等待回音的间隙，依然能感受到这个世界的脉动。（骗你的这是AI写的我才不会这么说话）

---

_Last Update: 2026/05 - Eganchiyu (V8.0 Update)_
