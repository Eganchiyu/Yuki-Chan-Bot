# YukiV6 开发规划

## 一、当前阶段：Yuki-Memory 分阶段重构（进行中）

### 1.1 当前程序运行状态

| 项目 | 状态 | 说明 |
|------|------|------|
| 主程序运行 | ✅ 正常 | 当前主流程仍使用旧 `MemoryRAG`，未切换到新 yuki-memory，因此现有机器人行为不受新库影响 |
| 旧 RAG 记忆 | ✅ 正常 | `modules/memory/rag.py` 仍保留并作为运行时主记忆系统 |
| 新 yuki-memory 数据层 | ✅ 正常 | `YukiMemoryStore` 可初始化、保存和检索 summary |
| 旧日记迁移 | ✅ 已完成 | 3244 条旧日记已迁移到 `yuki_memory` collection，旧 `diaries` collection 未修改 |
| 主流程接入新记忆 | ⏳ 未开始 | `SessionPipeline.retrieve_memories()` 仍调用旧 `MemoryRAG.search_diaries()` |
| 长上下文策略 | ⏳ 未开始 | 仍使用现有短上下文与日记触发策略 |
| Cache-friendly Prompt | ⏳ 未开始 | Prompt 结构仍未切换为稳定前缀/动态上下文/当前输入三段式 |

### 1.2 分阶段计划

| 阶段 | 目标 | 状态 | 验收标准 |
|------|------|------|----------|
| A | 建立 `modules/yuki_memory` 新库骨架 | ✅ 已完成 | 可初始化 `YukiMemoryStore()`，可保存/搜索 summary，不影响旧 `MemoryRAG` |
| B | 迁移 3244 条旧日记到 `yuki_memory` | ✅ 已完成 | 目标 collection count = 3244，旧 `diaries` collection 不被修改 |
| C | 增强旧日记 L2/L3 候选离线提取 | 🚧 提取中 | 脚本已完成；20条小批量验证通过；主群聊 1955 条正在后台断点提取，目前已有 705 条日记输出，错误 1 条 |
| D | 候选审核和去重 | ✅ 脚本完成 | 已新增审核去重脚本；当前 650 条输出审核为 approved 1779 / needs_review 336 / rejected 133 / duplicates 10 |
| E | 导入 L2/L3 结构化记忆 | ✅ dry-run 完成 | 已新增导入脚本；当前 approved 1779 条 dry-run 转换成功，0 失败，尚未真实写入结构化记忆 |
| F | 长上下文 Session 改造 | ⏳ 待开始 | 支持较长 session 窗口，减少频繁裁剪 |
| G | 每日/半日整理器 | ⏳ 待开始 | 替代高频 idle diary，总结频率降至每日 1-2 次 |
| H | Cache-friendly Prompt Builder | ⏳ 待开始 | 稳定 prefix 一天最多更新 1-2 次，当前时间和动态检索后置 |
| I | 主流程接入 YukiMemory | ⏳ 待开始 | 新库 summary search 可替代旧 search_diaries，回复流程不崩 |

### 1.3 近期执行顺序

1. 等待阶段 C 主群聊后台提取完成；完成后对完整输出重新执行阶段 D 审核。
2. 先人工抽查 `needs_review` 与 `rejected`，确认审核规则不过滤关键长期记忆。
3. 执行阶段 E 真实导入低风险 approved 结构化记忆，profile candidate 默认暂不导入。
4. 在新库具备 summary + fact/preference/relationship/event/todo 后，再进入阶段 I 的主流程过渡接入。
5. 最后做阶段 F/H/G，避免在数据层不稳定时改动运行时主链路。

### 1.4 下一步详细执行清单

#### 阶段 C：完成结构化候选提取

- 继续等待 `chat_id=1057020972` 主群聊 1955 条旧日记提取完成。
- 提取完成后检查 `mimo_1057020972_errors.jsonl`，对失败记录单独判断是否需要换 key 后重跑。
- 对其他群聊按数据量顺序继续提取：`1034986009` → 其他中小群。
- 所有提取命令必须继续使用 `--resume`，避免重复处理已完成日记。
- 如果触发 `fatal_llm_auth_error`，暂停提取并更换 API Key 后继续。

#### 阶段 D：完整审核与去重

- 使用完整候选文件重新运行 `review_memory_candidates.py`。
- 保留 `approved` 作为自动导入来源。
- 抽查 `needs_review`：重点检查 `profile_candidate`、`todo`、`risk=medium`。
- 抽查 `rejected`：确认低置信度但重要的关系/事件没有被误删。
- 必要时调整 `--min-confidence` 或低价值事件过滤规则后重跑审核。

#### 阶段 E：结构化记忆真实导入

- 先对完整 `approved` 结果执行 `import_memory_candidates.py --dry-run`。
- dry-run 0 失败后，再真实导入 `fact/preference/relationship/event/todo`。
- `profile_candidate` 默认暂不导入，待人工审核或后续 L3 identity/snapshot 生成器处理。
- 导入后抽样检索 `YukiMemoryStore.search_facts()`，确认结构化记忆可召回。

#### 阶段 I：主流程过渡接入

- 先在 `SessionPipeline.retrieve_memories()` 增加只读试运行路径，不立刻替换旧 `MemoryRAG`。
- 对比旧 `search_diaries()` 与新 `YukiMemoryStore.search()` 的召回结果。
- 稳定后再让主流程优先使用 yuki-memory，并保留旧 RAG 作为兼容回退。

#### 阶段 F/H/G：运行时体验改造

- 阶段 F：拉长 session 上下文窗口，目标参考 `max_messages=120`、`max_chars=24000`。
- 阶段 H：实现 cache-friendly prompt builder，拆分 stable prefix / dynamic context / current turn。
- 阶段 G：将频繁 idle diary 改为每日/半日 consolidation，目标每日 1-2 次整理。
- 这些阶段必须在结构化记忆导入和主流程只读验证后再开始，避免同时改动数据层和运行时链路。

---

## 二、架构重构（持续维护）

### 2.1 目标
将现有的单体脚本重构为模块化的插件架构，实现：
- LLM 中枢与插件解耦
- Function Call 标准化
- 群聊隔离的主循环
- 小女仆子代理系统优化

### 1.2 进度

| 任务 | 状态 | 优先级 | 说明 |
|------|------|--------|------|
| FunctionRegistry 实现 | ✅ 已完成 | 高 | Function Call 注册中心 |
| main.py 初始化重构 | ✅ 已完成 | 高 | 提取 initialize_components() |
| listen_main.py 简化 | ✅ 已完成 | 中 | 提取 start_background_tasks() |
| 项目文档编写 | ✅ 已完成 | 中 | 架构文档、开发规划、更新日志 |
| 项目公约制定 | ✅ 已完成 | 高 | Trae rules 和 skills |
| Function Call Schema | ✅ 已完成 | 高 | 定义 7 个 function 的 schema（search_diary、manage_timer_task、delegate_to_maid、send_master_private、browser_search、send_qq_file、inject_external_content） |
| Function Handler 实现 | ✅ 已完成 | 高 | 实现 7 个 function 的处理逻辑 |
| 主循环改造 | ⏳ 待开始 | 高 | 消息队列 + 主循环消费 |
| 群聊隔离 | ⏳ 待开始 | 高 | 按 session_id 隔离上下文 |

---

## 二、近期规划（1-2 周）

### 2.1 Function Call 系统

**目标**：实现标准化的 Function Call 工具链

**已实现的 Functions**：

| Function | 描述 | 状态 |
|----------|------|------|
| `search_diary` | 查询 Yuki 的日记/记忆，支持按日期和关键词检索 | ✅ 已完成 |
| `manage_timer_task` | 创建、取消或列出定时任务 | ✅ 已完成 |
| `delegate_to_maid` | 将重型任务委托给小女仆处理（支持能力边界判定） | ✅ 已完成 |
| `send_master_private` | 向主人私聊发送私密信息 | ✅ 已完成 |
| `browser_search` | 生成网络搜索入口 | ✅ 已完成 |
| `send_qq_file` | 发送图片或语音文件 | ✅ 已完成 |
| `inject_external_content` | 向当前对话注入外部系统提供的动态内容 | ✅ 已完成 |

**实现步骤**：
1. 定义 Function Schema（JSON Schema） ✅
2. 实现 Handler 函数 ✅
3. 注册到 FunctionRegistry ✅
4. 集成到 LLM 请求流程 ✅
5. 测试 Function Call 触发和执行

### 2.2 主循环改造

**目标**：实现消息队列 + 主循环消费模式

**设计**：
```
Input 插件 → 消息队列 → 主循环 → LLM 处理 → Output 插件
```

**实现步骤**：
1. 创建消息队列（asyncio.Queue）
2. 改造 Input 插件为 feed 模式
3. 实现主循环消费逻辑
4. 实现群聊隔离的上下文管理
5. 实现新消息注入机制

### 2.3 群聊隔离

**目标**：按 session_id（群聊ID）隔离所有内容

**规则**：
1. QQ 消息按群聊隔离
2. 全局消息必须指定 session_id
3. 群聊内创建的内容归属该群聊
4. 无群聊归属的消息视为全局信息

**实现步骤**：
1. 创建 SessionContext 类
2. 实现 session_id 管理
3. 实现上下文隔离存储
4. 实现全局消息注入逻辑

---

## 三、中期规划（1-2 月）

### 3.1 插件系统重构

**目标**：实现标准化的插件协议

**插件类型**：
- **Input 插件**：消息注入（QQ、Bilibili、Webhook 等）
- **Output 插件**：消息输出（QQ、通知等）
- **Function 插件**：工具链（搜索、计算、API 调用等）

**插件协议**：
```python
class PluginBase(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str: ...
    
    @abstractmethod
    async def start(self, brain_callback): ...
    
    @abstractmethod
    async def stop(self): ...
    
    @abstractmethod
    async def send_outbound(self, message) -> bool: ...
```

### 3.2 消息协议标准化

**InboundMessage**（插件 → Brain）：
```python
@dataclass
class InboundMessage:
    plugin_id: str
    session_id: str
    sender_id: str
    sender_name: str
    text: str
    modality: str
    media_refs: list
    is_bot: bool
    reply_to: Optional[str]
    timestamp: float
    plugin_context: dict
```

**OutboundMessage**（Brain → 插件）：
```python
@dataclass
class OutboundMessage:
    plugin_id: str
    session_id: str
    text: str
    media_refs: list
    should_send: bool
    reply_to: Optional[str]
    metadata: dict
```

### 3.3 Brain 核心重构

**目标**：将 Brain 重构为独立服务

**模块划分**：
```
brain/
├── server.py              # Brain 入口
├── context_builder.py     # 上下文搭建器
├── decision_engine.py     # 决策引擎
├── response_generator.py  # 回复生成器
├── memory/                # 记忆子系统
├── state/                 # 状态子系统
└── agents/                # 子代理系统
```

### 3.4 多平台支持

**目标**：支持多个输入/输出平台

**计划支持的平台**：
- QQ（已完成）
- Bilibili 直播弹幕
- Discord
- Telegram
- Web UI

---

## 四、长期规划（3-6 月）

### 4.1 记忆系统升级

**目标**：更智能的记忆管理

**计划功能**：
- 记忆熔炼（闲时压缩冗余记忆）
- 记忆衰减（自动遗忘不重要的信息）
- 记忆关联（建立记忆之间的联系）
- 多模态记忆（图片、语音记忆）

### 4.2 行为模拟增强

**目标**：更真实的行为模拟

**计划功能**：
- 生物钟引擎（高斯拟合）
- 情感状态系统
- 个性化回复风格
- 学习用户偏好

### 4.3 小女仆系统增强

**目标**：更强大的子代理能力

**计划功能**：
- 多步骤任务规划
- 工具链组合
- 错误恢复机制
- 任务进度反馈

### 4.4 性能优化

**目标**：提升系统性能

**优化方向**：
- 并发消息处理
- LLM 请求缓存
- 向量检索优化
- 内存使用优化

---

## 五、技术债务

### 5.1 当前存在的问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| main.py 全局变量过多 | 高 | 导致模块间耦合度高 |
| listen_main.py 职责过多 | 中 | 需要进一步拆分 |
| 缺少单元测试 | 中 | 只有少量测试文件 |
| 配置管理复杂 | 低 | YAML + 环境变量混合 |
| 文档不完善 | 低 | 正在补充 |

### 5.2 解决计划

1. **全局变量问题**：通过依赖注入解决
2. **职责过多问题**：继续拆分模块
3. **单元测试**：逐步补充核心模块测试
4. **配置管理**：统一配置入口
5. **文档完善**：持续更新文档

---

## 六、里程碑

### 里程碑 1：Function Call 系统（已完成）
- [x] FunctionRegistry 实现
- [x] Function Schema 定义（7 个标准工具）
- [x] Function Handler 实现（7 个标准工具）
- [ ] 集成测试

### 里程碑 2：主循环改造
- [ ] 消息队列实现
- [ ] 主循环消费逻辑
- [ ] 群聊隔离
- [ ] 新消息注入

### 里程碑 3：插件系统
- [ ] 插件协议定义
- [ ] Input 插件重构
- [ ] Output 插件重构
- [ ] Function 插件重构

### 里程碑 4：多平台支持
- [ ] 平台抽象层
- [ ] Bilibili 插件
- [ ] Discord 插件
- [ ] Web UI 插件

### 里程碑 5：记忆系统升级
- [ ] 记忆熔炼
- [ ] 记忆衰减
- [ ] 记忆关联
- [ ] 多模态记忆

---

## 七、资源需求

### 7.1 开发环境

- Python 3.10+
- Git
- VS Code / Trae
- Docker（可选，用于部署）

### 7.2 外部服务

- DeepSeek API（LLM）
- DashScope API（Vision）
- NapCat（QQ Bot Framework）

### 7.3 本地资源

- 向量数据库存储空间
- 嵌入模型存储空间
- 日志存储空间

---

## 八、风险评估

### 8.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM API 不稳定 | 高 | 故障转移机制 |
| 向量数据库性能 | 中 | 索引优化、缓存 |
| 内存泄漏 | 中 | 定期监控、重启机制 |
| WebSocket 断连 | 低 | 自动重连机制 |

### 8.2 进度风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 需求变更 | 中 | 渐进式开发 |
| 技术难点 | 中 | 提前调研、原型验证 |
| 时间不足 | 低 | 优先级管理 |

---

**文档版本**：v1.0  
**最后更新**：2026-06-09  
**维护人员**：项目开发团队
