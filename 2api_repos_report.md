# GitHub「2api」逆向/反代开源仓库清单报告

> 采集时间：2026-09-18  |  数据来源：GitHub Search API  
> 关键词策略：平台名 + 2api / reverse proxy / api 逆向 / free-api / 逆向  
> 语言、star、更新时间均为搜索时快照。

---

## 1) Workbuddy 国内版（含 WorkBuddy/CodeBuddy 同族）

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| **Sliverkiss/workbuddy2api** | 997 | Go | 2026-09-18 | ✅ | WorkBuddy 官方 OpenAI 兼容反向代理，OAuth 登录、多账号轮转、工具调用、流式响应。同类最热门。 |
| linguo2625469/workbuddy2api-panel | 438 | Go | 2026-09-18 | ✅ | 基于上者的增强分支，多账号网关 + Web 管理面板（账号池可视化/积分任务/配置热更新），自动完成任务中心。 |
| ardeyouxipianyi/workbuddy2api-hub | 89 | Python | 2026-09-18 | ✅ | 国内外双域独立路由切换、设备指纹防风控、成长任务自动化、后台调度 + Web 看板。 |
| Tom6814/WorkBuddy2API | 39 | Python | 2026-09-18 | ✅ | WorkBuddy/CodeBuddy 逆向 API，支持 Docker 部署。 |
| momo0410/workbuddy-switch-gateway | 34 | Rust | 2026-09-18 | ✅ | 账号管理 + OpenAI 兼容网关（整合 workbuddy-switch 与 workbuddy2api）。 |
| xiaofan6ya/workbuddy2api | 24 | Python | 2026-09-18 | ✅ | 桌面端登录态转 OpenAI/Anthropic 兼容 API + 多账号代理共享平台（按 Key 配额、用量记账）。 |
| linbeize/workbuddy2api-gui | 18 | Go | 2026-09-18 | ✅ | workbuddy2api 的可视化 Web 控制台。 |
| jilin0105/WorkBuddy2API-Android | 15 | Kotlin | 2026-09-18 | ✅ | Android 原生实现，无需 Python/Docker，装到手机即用。 |
| ShouZhuo0413/codebuddy2api | 229 | Python | 2026-09-18 | ✅ | 同族：CodeBuddy/WorkBuddy 订阅转 OpenAI + Anthropic 兼容 API。 |
| maiphucgiang/codebuddy2api | 137 | Python | 2026-09-18 | ✅ | 同上，CodeBuddy 订阅转本地 OpenAI API。 |

**结论**：国内版生态最成熟，仓库多、活跃度高、多支持 Docker/Web 面板，可直接部署。

---

## 2) Traework (Trae) 国内版

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| **Sliverkiss/traework2api** | 95 | Go | 2026-09-17 | ✅ | TraeWork 国内版 OpenAI 兼容反代（同作者另有 workbuddy2api）。 |
| linqiu919/trae2api | 39 | Go | 2026-06-11 | ⚠️ 已归档 | 早期 trae2api，仓库已 archived。 |
| connectedGraph/trae2api-web | 20 | Go | 2026-09-16 | ✅ | TRAE SOLO 的 OpenAI 兼容反代，多账号池、自动保活、内置 Web 面板。 |
| autumnsentiment/Trae2api-cn | 19 | Python | 2026-09-16 | ✅ | Trae 国内版 2api（Python 实现）。 |
| a137460387/trae2api | 0 | JavaScript | 2026-09-17 | ✅ | Trae 国内/国际双区域多账号池，自动选区，OpenAI & Anthropic 兼容。 |
| JeffHu0912/trae2api | 9 | Go | 2026-09-17 | ✅ | TRAE SOLO 反代服务 + 多账号管理面板。 |
| bluechonk/trae-credential-reverse-engineering | 9 | TypeScript | 2026-09-14 | ❌ 仅逆向 | TRAE SOLO CN 凭据存储逆向分析，非 2api 服务。 |

**结论**：有专门仓库，首选 Sliverkiss/traework2api 或 trae2api-web。

---

## 3) Qoder / QoderCN

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| **avaritiachaos/qoder-proxy** | 176 | JavaScript | 2026-09-16 | ✅ | Qoder CN CLI 本地 OpenAI 兼容代理（注明仅供学习）。 |
| d4ncboz/qoder-workflow | 143 | Python | 2026-09-15 | ✅ | Qoder 生态端到端框架 + 高性能 OpenAI 兼容网关。 |
| **cubk1/qoder2api** | 85 | Java | 2026-09-18 | ✅ | Qoder 逆向 & Qoder2api demo。 |
| EchoPing07/Qoder-2API-Go | 24 | Go | 2026-09-18 | ✅ | 将 Qoder AI 服务转为 OpenAI 格式 API。 |
| fengyinxia/qoder2api | 22 | Python | 2026-09-17 | ✅ | QoderWork → OpenAI 兼容桥（动态模型加载，纯 Python）。 |
| D3-vin/Qoder2Api | 22 | Go | 2026-09-17 | ✅ | Qoder 2API Go 实现。 |
| jyao0708/qoder2api | 20 | Go | 2026-08-31 | ✅ | Qoder 暴露为 OpenAI & Anthropic 本地 API，兼容 Codex/Claude Code CLI。 |
| Ttungx/qoder2222api | 7 | Python | 2026-09-03 | ✅ | qoder 逆向，白嫖模型。 |

**结论**：Qoder 项目丰富，多语言实现，可直接部署。

---

## 4) Dumate 百度搭子

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| Wang-JQ77/dumate-api | 1 | Python | 2026-08-28 | ✅ | DuMate AI 能力本地 API 封装：积分查询、任务执行、**OpenAI 兼容接口**。 |
| Wang-JQ77/dsh-llm-dumate | 1 | JavaScript | 2026-08-28 | ✅ | DSH 插件，为 DeepSeek Harness 接入 DuMate 模型（依赖桌面版，无需 API Key）。 |
| baidubce/dumate-bench | 8 | Python | 2026-09-17 | ❌ 非2api | 百度官方 DuMate 基准测试，非反代。 |

**结论**：⚠️ **无专门的 dumate2api 项目**。仅有零星个人封装（star 极低），生态空白。

---

## 5) MiniMaxCode 国内版

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| juangchuank-ops/minimax2api | 5 | Python | 2026-09-18 | ⚠️ | 通用 MiniMax 2api（非 Code 专用）。 |
| xinxinshuhao-create/kuku2api | 30 | Python | 2026-09-17 | ✅ | 见下方「库库Ai」，其底层即调用 MiniMax 模型。 |

**结论**：⚠️ **未找到专门的 MiniMaxCode 国内版 2api 仓库**，仅有通用 minimax2api。

---

## 6) MiniMaxCode 国际版

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| everyoneexe/minimax2api | 1 | Python | 2026-09-18 | ✅ | MiniMax AI 的 OpenAI 兼容代理，自动账号管理（国际向）。 |
| snake-aabb-wtf/minimaxM3-web2api | 12 | Python | 2026-09-18 | ✅ | 将 MiniMax Agent 网页聊天转为 OpenAI 兼容 API，逆向还原前端 JS 签名算法（x-signature + yy）。 |

**结论**：⚠️ **未找到专门的 MiniMaxCode 国际版 2api**，但有 MiniMax Agent 网页逆向代理可参考。

---

## 7) 百度库库 Ai

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| **xinxinshuhao-create/kuku2api** | 30 | Python | 2026-09-17 | ✅ | 为「GenFlow Pro」网页工作台提供 OpenAI 兼容 API，含每日签到调度器。 |
| rjcodesandtech/kuku-chatbot-api | 0 | Python | 2021-05-25 | ⚠️ | 早期 Kuku AI Chatbot 非官方 API（与百度库库无关，同名）。 |

**结论**：找到 1 个可能的 kuku2api（30 star），但描述指向 GenFlow Pro，与「百度库库Ai」的对应关系需人工确认。

---

## 8) WPS灵犀

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| lewis-hui1202/WPS-AI | 54 | JavaScript | 2026-09-17 | ⚠️ 非反代 | WPS 全家桶 AI 助手，可挂 OpenAI/Anthropic/Codex 模型，**不是灵犀2api**。 |
| Githun1314/lingxi-skin-manager | 3 | JavaScript | 2026-08-25 | ❌ | WPS 灵犀第三方皮肤管理器。 |
| 其余 lingxi-* | 0 | - | - | ❌ | 均为 Skill/插件/仿制对话助手，非 2api。 |

**结论**：⚠️ **未找到 WPS 灵犀 2api 逆向/反代仓库**，生态空白。

---

## 9) 讯飞 AStudio

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| vibe-coding-labs/iflycode-2api | 1 | Python | 2026-09-09 | ❌ 已停服 | 讯飞星火飞码转 OpenAI API（多账号池）。**上游已停服，无法使用**。 |
| lza6/xinghuo-2api | 3 | Python | 2026-05-02 | ✅ | 讯飞星火（非 AStudio）2api：Nginx+FastAPI、Cookie/GtToken 认证、Docker 部署。 |
| vibe-coding-labs/iflycode-reverse-engineer | 0 | Java | 2026-07-05 | ❌ 仅逆向 | iFlyCode JetBrains 插件通信协议逆向文档。 |

**结论**：⚠️ **未找到讯飞 AStudio 专门的 2api 仓库**；讯飞系仅有星火/飞码的相关项目。

---

## 10) workbuddy2api 本身

| 仓库 (owner/repo) | Star | 语言 | 最近更新 | 可直接部署 | 简述 |
|---|---|---|---|---|---|
| **Sliverkiss/workbuddy2api** | 997 | Go | 2026-09-18 | ✅ | 元祖项目。WorkBuddy 的 OpenAI 兼容反向代理，支持 OAuth 登录、多账号轮转、工具调用与流式响应。创建于 2026-07-28，社区衍生分支众多。 |

---

## 总览表

| # | 平台 | 是否有专门 2api 仓库 | 最佳候选 |
|---|---|---|---|
| 1 | Workbuddy 国内版 | ✅ 丰富 | Sliverkiss/workbuddy2api (997★) |
| 2 | Traework/Trae 国内版 | ✅ 有 | Sliverkiss/traework2api (95★) |
| 3 | Qoder/QoderCN | ✅ 丰富 | avaritiachaos/qoder-proxy (176★) |
| 4 | Dumate 百度搭子 | ⚠️ 空白 | Wang-JQ77/dumate-api (1★) |
| 5 | MiniMaxCode 国内版 | ⚠️ 空白 | juangchuank-ops/minimax2api (5★，非专用) |
| 6 | MiniMaxCode 国际版 | ⚠️ 空白 | snake-aabb-wtf/minimaxM3-web2api (12★) |
| 7 | 百度库库Ai | ⚠️ 待确认 | xinxinshuhao-create/kuku2api (30★) |
| 8 | WPS灵犀 | ❌ 未找到 | 无 |
| 9 | 讯飞AStudio | ❌ 未找到 | 讯飞系仅有星火/飞码项目 |
| 10 | workbuddy2api 本身 | ✅ | Sliverkiss/workbuddy2api (997★) |

## 补充说明
- **可部署性判断**：含 Docker / 一键部署 / Web 面板说明的记为「✅」；仅有逆向分析或已停服/归档的标「❌/⚠️」；纯说明性内容标注「非2api」。
- **空白平台**（Dumate、MiniMaxCode 双版本、WPS灵犀、讯飞AStudio）说明当前 GitHub 上尚无成熟的「官方网页端 → OpenAI 兼容 API」开源项目，如需此类能力可能需要自行开发。
- 数据为 2026-09-18 的 GitHub 搜索快照，star 与更新时间会动态变化。
