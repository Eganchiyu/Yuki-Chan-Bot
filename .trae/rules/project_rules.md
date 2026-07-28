# YukiV6 项目开发公约

本文件定义了 YukiV6 项目的开发规范和约定，所有开发者（包括 AI 助手）必须遵守。

---

## 一、代码规范

### 1.1 命名规范

**文件命名**：
- 使用小写字母和下划线：`history_manager.py`
- 测试文件以 `test_` 开头：`test_maid_search_diary.py`
- 配置文件使用小写字母：`config.py`

**类命名**：
- 使用 PascalCase：`YukiEngine`, `MemoryRAG`
- 单例类以功能命名：`ProviderRegistry`, `MemoryRAG`

**函数/方法命名**：
- 使用 snake_case：`get_tools()`, `scan_and_register()`
- 私有方法以 `_` 开头：`_initialize()`, `_load_blacklist()`
- 异步方法不加 `async_` 前缀，通过 `async def` 声明

**变量命名**：
- 使用 snake_case：`chat_id`, `group_active_state`
- 常量使用大写：`MAX_RETRIES`, `DEBOUNCE_TIME`
- 私有变量以 `_` 开头：`_functions`, `_handlers`

### 1.2 代码风格

**缩进**：
- 使用 4 空格缩进
- 不使用 Tab

**行长度**：
- 建议每行不超过 100 字符
- 长行使用换行或括号包裹

**导入顺序**：
```python
# 1. 标准库
import asyncio
import os

# 2. 第三方库
import chromadb
from sentence_transformers import SentenceTransformer

# 3. 项目内部模块
from config import cfg
from utils.logger import get_logger
```

**注释**：
- 使用中文注释（与项目文档保持一致）
- 复杂逻辑必须添加注释
- 函数/方法使用 docstring 说明用途

### 1.3 异步编程规范

**异步函数**：
- 使用 `async def` 声明
- 使用 `await` 调用异步函数

**并发控制**：
- 使用 `asyncio.Lock()` 保护共享状态
- 使用 `asyncio.create_task()` 创建后台任务
- 避免在异步函数中使用阻塞操作

**错误处理**：
- 使用 `try/except` 捕获异常
- 记录错误日志
- 提供降级方案

### 1.4 网络连接规范

项目所有外部网络请求必须统一使用 `utils.http_client` 提供的 SSL/certifi 入口，避免直接使用系统默认证书链导致 `[ASN1: NOT_ENOUGH_DATA] not enough data (_ssl.c:4040)` 等 SSL 错误。

**aiohttp 请求**：
- 必须使用 `create_tcp_connector()` 创建连接器。
- 禁止直接 `aiohttp.ClientSession()` 发起 HTTPS 请求。

```python
from utils.http_client import create_tcp_connector

async with aiohttp.ClientSession(connector=create_tcp_connector()) as session:
    async with session.get(url) as resp:
        data = await resp.text()
```

**urllib 请求**：
- 必须使用 `utils.http_client.urlopen()`。
- 禁止直接使用 `urllib.request.urlopen()`。

```python
from utils.http_client import urlopen

with urlopen(url, timeout=10) as response:
    data = response.read()
```

**requests / httpx 请求**：
- 必须使用 `requests_verify()` 指定 certifi CA。

```python
from utils.http_client import requests_verify

requests.get(url, verify=requests_verify(), timeout=10)
httpx.AsyncClient(verify=requests_verify())
```

**WebSocket 连接**：
- `ws://` 不需要 SSL。
- `wss://` 必须传入 `create_ssl_context()`。

```python
from urllib.parse import urlparse
from utils.http_client import create_ssl_context

connect_kwargs = {}
if urlparse(ws_url).scheme == "wss":
    connect_kwargs["ssl"] = create_ssl_context()

async with websockets.connect(ws_url, **connect_kwargs) as websocket:
    ...
```

---

## 二、Git 提交规范

### 2.1 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型（type）**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式调整（不影响逻辑）
- `refactor`: 代码重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

**范围（scope）**：
- 可选，表示影响范围
- 例如：`core`, `modules`, `providers`, `docs`

**主题（subject）**：
- 简短描述，不超过 50 字符
- 使用中文
- 不以句号结尾

**示例**：
```
feat(core): 实现 FunctionRegistry 注册中心

- 支持批量扫描注册
- 支持单个注册/注销
- 支持获取 tools 列表

Closes #123
```

### 2.2 提交前检查清单

提交前必须完成以下检查：

- [ ] **代码风格**：符合项目命名规范
- [ ] **Gitignore**：敏感文件未被提交
- [ ] **测试通过**：相关测试全部通过
- [ ] **文档更新**：修改了文档（如有必要）
- [ ] **Changelog 更新**：记录了重要变更
- [ ] **无敏感信息**：API Key、密码等未暴露

---

## 三、文档规范

### 3.1 必须维护的文档

以下文档必须随代码同步更新：

| 文档 | 路径 | 更新时机 |
|------|------|----------|
| 架构文档 | `docs/architecture.md` | 模块结构变更时 |
| 开发规划 | `docs/development-plan.md` | 计划变更时 |
| 更新日志 | `docs/changelog.md` | 每次提交时 |
| README | `README.md` | 项目说明变更时 |

### 3.2 文档更新规则

**Changelog 更新**：
- 每次提交必须更新 `docs/changelog.md`
- 记录在 `[未发布]` 部分
- 发布版本时，将 `[未发布]` 替换为版本号

**架构文档更新**：
- 新增/删除模块时更新
- 模块职责变更时更新
- 数据流变更时更新

**开发规划更新**：
- 任务状态变更时更新
- 新增任务时更新
- 里程碑完成时更新

---

## 四、安全规范

### 4.1 敏感信息保护

**禁止提交的信息**：
- API Key / Secret
- 数据库密码
- 私钥文件
- 配置文件中的敏感字段

**保护措施**：
- 使用 `.gitignore` 排除敏感文件
- 使用环境变量存储敏感配置
- 定期轮换 API Key

---

## 五、测试规范

### 5.1 测试要求

**必须测试的场景**：
- 核心功能
- 边界条件
- 错误处理
- 并发场景

**测试文件位置**：
- 测试文件放在 `tests/` 目录
- 文件名以 `test_` 开头

### 5.2 测试命名

```python
def test_search_diary_returns_results():
    """测试搜索日记返回结果"""
    pass

def test_search_diary_with_empty_query():
    """测试空查询的处理"""
    pass
```

---

## 六、发布规范

### 6.1 版本号规则

遵循 [语义化版本](https://semver.org/lang/zh-CN/)：

- **主版本号（X.y.z）**：重大架构变更、不兼容的 API 修改
- **次版本号（x.Y.z）**：新功能添加、功能增强
- **修订号（x.y.Z）**：Bug 修复、文档更新

### 6.2 发布流程

1. 更新 `docs/changelog.md`，将 `[未发布]` 替换为版本号
2. 创建 Git Tag：`git tag vX.Y.Z`
3. 推送 Tag：`git push origin vX.Y.Z`
4. 创建 GitHub Release

---

## 七、AI 助手规范

### 7.1 代码生成规则

**必须遵守**：
- 遵循项目命名规范
- 添加必要的注释
- 不引入新的依赖（除非必要）
- 不修改未明确要求的代码

**禁止行为**：
- 硬编码敏感信息
- 删除现有功能
- 引入破坏性变更
- 忽略错误处理

### 7.2 文档更新规则

**每次代码变更后**：
- 更新 `docs/changelog.md`
- 更新相关架构文档（如有必要）
- 更新开发规划（如有必要）

### 7.3 提交规范

**提交信息**：
- 使用中文
- 遵循提交信息格式
- 简明扼要

**提交内容**：
- 一次提交只做一件事
- 避免提交无关文件
- 确保代码可运行

---

## 八、工具配置

### 8.1 Git 配置

```bash
# 设置用户信息
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 设置默认分支
git config init.defaultBranch main
```

### 8.2 编辑器配置

**推荐设置**：
- 缩进：4 空格
- 行长度：100 字符
- 编码：UTF-8
- 换行符：LF

### 8.3 代码格式化

**Python**：
- 使用 Black 格式化
- 使用 isort 排序导入
- 使用 flake8 检查代码风格

### 8.4 Python 运行环境

运行项目脚本、测试、lint 或 typecheck 前，必须先在 PowerShell 中启用 uv 创建的项目虚拟环境：

```powershell
.\.venv\Scripts\activate
```

---

## 九、协作规范

### 9.1 问题反馈

**Bug 报告**：
- 描述问题现象
- 提供复现步骤
- 附上错误日志
- 说明环境信息

**功能建议**：
- 描述需求背景
- 说明预期效果
- 提供实现思路（可选）

### 9.2 代码审查

**审查要点**：
- 代码风格是否符合规范
- 是否有潜在的 Bug
- 是否有安全隐患
- 是否有性能问题
---

**文档版本**：v1.0.0
**最后更新**：2026-07-28
**维护人员**：项目开发团队
