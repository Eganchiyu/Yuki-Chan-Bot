# YukiV6 更新日志

所有 notable changes 都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布] - 2026-06-04

### 变更
- **移除 Provider 模块，内联 LLM 客户端逻辑**：
  - 删除 `providers/` 目录及全部 9 个文件（base、registry、fallback、openai_compatible、deepseek、dashscope、ytea）
  - 新增 `utils/llm_client.py`，内联所有 provider 功能
  - 保留主备故障转移逻辑（熔断 → 切换备用 → 120 秒自动恢复）
  - 保留全局 aiohttp Session TCP 连接复用
  - 系统退化至使用配置文件直接管理 API 参数
  - 更新 `README.md`、`docs/architecture.md` 同步文档

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
