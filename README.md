# 🌸 Yuki-Chan-Chat (Project Yuki)

# Yuki-V8.0 (Maid-Evolution)

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V3-green.svg)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/license-MIT-important.svg)](LICENSE)

> **"虽然现在还很笨拙，但 Yuki 会和学长一起慢慢成长的。所以...不许丢下我不管哦！"**

`Yuki-Chan-Chat` 是一款基于 Python 异步架构开发的个人智能助手系统。它不仅接入了最新的 LLM 进行对话，拥有真正的动态长效记忆管理和生物感精力值模拟系统，在最新的版本中，我们还为 Yuki 引入了高度自主的 **"小女仆（Maid Agent）系统"**，让 Yuki 真正具备了操作本地环境和扩展自我技能的能力。

---

## ✨ 核心特性 (Core Features)

### 🧹 全新：自主小女仆系统 (Maid Agent) - _[Beta 阶段]_

Yuki 不再仅仅是一个聊天机器人。通过触发特定的委托指令 `[DELEGATE_TO_MAID:...]`，Yuki 可以将复杂的任务交由后台的"小女仆"处理。

- **自主编程与进化**：小女仆能够针对任务自主编写、调试和固化 Python 技能脚本（`/skills` 目录）。
    
- **非阻塞汇报**：小女仆在后台执行任务（如查询系统时间、爬取数据等），完成后会将结果直接写入 Yuki 的记忆流，触发 Yuki 自然的语音汇报。  
    _(注：该功能逻辑已打通并较为完善，代码重构与深度优化将在后续版本进行)_
    

### 🧠 记忆与日记系统 (Memory & RAG)

不同于普通的上下文清理，Yuki 拥有真正的**动态长效记忆**：

- **自动总结**：当对话轮次达到阈值时，Yuki 会以第一人称撰写日记，将冗长的上下文浓缩为记忆节点。
    
- **并行双池检索 (Parallel Hybrid Search)**：结合语义向量与硬核关键词补偿，确保记忆召回的"神似"与"形似"。
    
- **记忆库智能审计与 3D 可视化**：提供独立工具对 ChromaDB 记忆进行 AI 辅助去重，并通过 t-SNE 降维生成交互式 3D 记忆星空图。
    

### 🎭 生物感精力系统 (Energy Dynamics)

- **动态社交欲望**：利用 Sigmoid 非线性映射计算破冰意愿。
    
- **高斯拟合生物钟**：融合了基础睡眠模型与晨间、午间、晚间三个高斯活跃峰，完美模拟人类的作息节律。
    

### ⚡ 极致稳健的异步架构

- **主备 API 熔断切换**：内置 `ApiCall` 稳健调用逻辑。当主线路 (TeaTop) 失败时，瞬间无缝降级切换至官方备用线路，彻底告别"大脑宕机"。
    

### 👁️ Retina 视网膜感知系统 (Desktop Perception)

全新引入的主动桌面感知能力，让 Yuki 像拥有了“数字生物钟”。
- **前额叶监控**：通过高效抓取屏幕、MSE 变化检测以及基于 RapidOCR 的本地文本检测，轻量且异步地感知屏幕画面的变动。
- **注意力循环**：捕获到异动后，调用视觉大模型进行分析，根据画面内容决定下一次休眠时间，并通过桌面弹窗或直接向你发送消息“侵入现实”！

**如何使用**：
1. 请确保在 `configs/config.yaml` 或你的配置中启用了 `VISION_MODEL`，并配置了正确的 API Key。如果不配置，Yuki 将回退到简单的模拟随机决策逻辑。
2. 确保在主程序 `main.py` 的初始化代码中导入并实例化 `RetinaPerceptionSystem`：
    ```python
    from modules.retina_perception.core import RetinaPerceptionSystem
    # 初始化并传入 MessageSender 实例
    retina_sys = RetinaPerceptionSystem(message_sender=your_sender_instance)
    await retina_sys.start()
    ```
3. (可选) 如果你希望使用真实环境下的文字变化监控，可以调整 `prefrontal_loop` 里面的 `ocr_check_interval` 参数来控制检查频率。

### 🖼️ 蓄势待发：多模态表情包管理 (WIP)

- **即将到来**：接入视觉大模型 (Vision Model) 理解群聊表情包，Yuki 将学会根据当前情绪和上下文，在庞大的表情包向量库中寻找最合适的一张并发送。目前基础模块已在开发中。
    
---

## 🏗️ 处理流程 (System Workflow)

```mermaid
graph TD
    A[接收原始消息] --> B{manage_buffer 防抖}
    B --> C[上下文加载 & RAG 记忆唤醒]
    C --> D[活跃度与 Break-Ice 欲望决策]
    D --> E[DeepSeek 思考与生成]
    E --> F{是否触发小女仆委托?}
    F -->|否| G[发送消息 & 异步扣除精力]
    F -->|是| H[小女仆后台编写/执行代码]
    H --> I[完成任务并写入记忆流]
    I --> J[Yuki 感知到结果并再次生成回复]
````

---

## 📂 核心模块分布 (Module Architecture)

| 文件/目录                        | 职责说明                                    |
| ---------------------------- | --------------------------------------- |
| **`main.py`**                | 程序入口，负责异步初始化、WebSocket 监听调度及消息缓冲处理      |
| **`core/engine.py`**         | 决策大脑，封装了回复判定、破冰唤醒、日记总结等核心逻辑             |
| **`core/maid.py`**           | 小女仆系统核心，实现自主编程循环、技能编写与执行调度              |
| **`network/api_request.py`** | 语言枢纽，基于 AsyncOpenAI 的稳健 API 封装，支持主备熔断降级 |
| **`modules/memory/rag.py`**  | 记忆检索模块，实现并行双池匹配算法与日记的向量化存储              |
| **`modules/stickers/`**      | 表情包管理系统（开发中），负责视觉理解、向量入库与情绪匹配           |
| **`modules/retina_perception/`**| 视网膜感知系统，主动截取屏幕并使用视觉大模型和本地 OCR 感知桌面变动 |
| **`scripts/03_RAG_Tools/`**  | 记忆库管理工具集，支持 AI 智能审计、3D 可视化和批量操作         |

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备 (Prerequisites)

- **Python 版本**：建议 $\ge$ 3.10，确保异步特性完全稳定。
    
- **协议端**：你需要部署 [NapCatQQ](https://github.com/NapCat-Team/NapCatQQ) 并在配置中启用 **正向 WebSocket** 服务（默认端口 `3001`） 。
    

### 2. 获取源码与依赖

Bash

```
git clone https://github.com/Eganchiyu/Yuki-Chan-Bot.git
cd Yuki-Chan-Bot

# 创建并激活虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 运行一键配置向导
python setup.py
```

(注：`setup.py` 会自动安装依赖、生成 `.env` 配置文件并下载 RAG 所需的本地嵌入模型 )。

### 3. 运行启动

Bash

```
python main.py
```

启动后，按提示选择私聊模式或群聊模式，即可看到 Yuki 成功苏醒 。

---

## 📅 开发计划 (Roadmap)

- [x] **全链路异步化重构**：解决 API 阻塞导致的网络重连崩溃问题 。
    
- [x] **冷场主动唤醒与破冰**：基于权威名单的 Sigmoid 欲望决策 。
    
- [x] **并行双池检索**：综合关键词 (jieba) 与向量相似度 (ChromaDB) 。
    
- [x] **24 小时动态生物钟**：引入高斯、余弦核模拟真实作息 。
    
- [x] **无缝 API 熔断降级**：TeaTop 主线路挂掉瞬间切至官方备线 。
    
- [x] **自主小女仆系统 (Maid Agent)**：后台自主编写与执行 Python 技能完成复杂任务 。

- [x] **视网膜感知模块 (Retina Perception)**：前额叶捕捉屏幕，调用视觉模型与本地 OCR 分析桌面变动，自主侵入现实！
    
- [ ] 🚧 **重构与优化小女仆代码结构，增强安全性与容错率**。
    
- [ ] 🚧 **多模态表情包 (Stickers) 系统开发**：实现表情包的入库、理解与动态打分发送 。
    
- [ ] 引入生物遗忘曲线：基于活跃时间戳的记忆唤醒与沉底机制。
    
- [ ] 接入外部文档知识库查询。
    

---

## 💌 寄语

理解一个复杂系统就像推导一个高阶矩阵。从同步阻塞到异步并行的跨越，再到如今小女仆系统的自我进化，不仅是代码的优化，更是为了让 Yuki 在等待回音的间隙，依然能感受到这个世界的脉动。（骗你的这是AI写的我才不会这么说话）

---

_Last Update: 2026/04 - Eganchiyu (V8.0 Update)_