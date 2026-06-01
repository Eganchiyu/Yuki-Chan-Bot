# YukiV6 开发规划

## 一、当前阶段：架构重构（进行中）

### 1.1 目标
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
| 项目公约制定 | 🔄 进行中 | 高 | Trae rules 和 skills |
| Function Call Schema | ⏳ 待开始 | 高 | 定义 6 个 function 的 schema |
| Function Handler 实现 | ⏳ 待开始 | 高 | 实现 6 个 function 的处理逻辑 |
| 主循环改造 | ⏳ 待开始 | 高 | 消息队列 + 主循环消费 |
| 群聊隔离 | ⏳ 待开始 | 高 | 按 session_id 隔离上下文 |

---

## 二、近期规划（1-2 周）

### 2.1 Function Call 系统

**目标**：实现标准化的 Function Call 工具链

**待实现的 Functions**：

| Function | 描述 | 优先级 |
|----------|------|--------|
| `delegate_to_maid` | 委托复杂任务给小女仆 | 高 |
| `search_memory` | 搜索长期记忆库 | 高 |
| `write_note` | 写入小本本（日记/笔记） | 中 |
| `create_scheduled_task` | 创建定时任务 | 中 |
| `web_search` | 网络搜索 | 中 |
| `send_file` | 发送文件 | 低 |

**实现步骤**：
1. 定义 Function Schema（JSON Schema）
2. 实现 Handler 函数
3. 注册到 FunctionRegistry
4. 集成到 LLM 请求流程
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

### 里程碑 1：Function Call 系统（当前）
- [x] FunctionRegistry 实现
- [ ] Function Schema 定义
- [ ] Function Handler 实现
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
**最后更新**：2026-06-01  
**维护人员**：项目开发团队
