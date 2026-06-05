# YukiV6 贡献指南

欢迎参与 YukiV6 项目开发！本指南将帮助你快速上手并参与贡献。

---

## 一、开发环境搭建

### 1.1 系统要求

- **Python 版本**：≥ 3.10
- **操作系统**：Windows 10/11、Linux、macOS
- **Git**：用于版本控制

### 1.2 环境准备

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/YukiV6.git
cd YukiV6

# 2. 创建虚拟环境
python -m venv venv

# 3. 激活虚拟环境
# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 运行配置向导
python setup.py
```

### 1.3 开发工具推荐

- **IDE**：VS Code、PyCharm、Trae
- **代码格式化**：Black、isort
- **代码检查**：flake8、pylint
- **测试框架**：pytest

---

## 二、代码规范

### 2.1 命名规范

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

### 2.2 代码风格

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

### 2.3 异步编程规范

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

---

## 三、Git 工作流

### 3.1 分支管理

**主分支**：
- `main`: 生产环境代码
- `develop`: 开发分支

**功能分支**：
- `feature/<功能名>`: 新功能开发
- `fix/<问题名>`: Bug 修复
- `docs/<文档名>`: 文档更新

**分支命名**：
- 使用小写字母和连字符
- 例如：`feature/function-call`, `fix/memory-leak`

### 3.2 提交信息格式

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

### 3.3 提交前检查清单

提交前必须完成以下检查：

- [ ] **代码风格**：符合项目命名规范
- [ ] **Gitignore**：敏感文件未被提交
- [ ] **测试通过**：相关测试全部通过
- [ ] **文档更新**：修改了文档（如有必要）
- [ ] **Changelog 更新**：记录了重要变更
- [ ] **无敏感信息**：API Key、密码等未暴露

---

## 四、开发流程

### 4.1 新功能开发

1. **创建功能分支**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **开发功能**
   - 编写代码
   - 添加测试
   - 更新文档

3. **提交代码**
   ```bash
   git add .
   git commit -m "feat(module): 添加新功能"
   ```

4. **推送分支**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **创建 Pull Request**
   - 在 GitHub 上创建 PR
   - 填写 PR 描述
   - 等待代码审查

### 4.2 Bug 修复

1. **创建修复分支**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b fix/bug-description
   ```

2. **修复 Bug**
   - 定位问题
   - 修复代码
   - 添加测试

3. **提交代码**
   ```bash
   git add .
   git commit -m "fix(module): 修复 Bug 描述"
   ```

4. **推送并创建 PR**
   ```bash
   git push origin fix/bug-description
   ```

### 4.3 代码审查

**审查要点**：
- 代码风格是否符合规范
- 是否有潜在的 Bug
- 是否有安全隐患
- 是否有性能问题

**审查流程**：
1. 提交 PR
2. 等待审查者审查
3. 根据反馈修改代码
4. 审查通过后合并

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

### 5.3 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/test_config.py

# 运行并显示详细输出
python -m pytest -v

# 运行并生成覆盖率报告
python -m pytest --cov=.
```

---

## 六、文档规范

### 6.1 必须维护的文档

| 文档 | 路径 | 更新时机 |
|------|------|----------|
| 架构文档 | `docs/architecture.md` | 模块结构变更时 |
| 开发规划 | `docs/development-plan.md` | 计划变更时 |
| 更新日志 | `docs/changelog.md` | 每次提交时 |
| README | `README.md` | 项目说明变更时 |

### 6.2 文档更新规则

**Changelog 更新**：
- 每次提交必须更新 `docs/changelog.md`
- 记录在 `[未发布]` 部分
- 发布版本时，将 `[未发布]` 替换为版本号

**架构文档更新**：
- 新增/删除模块时更新
- 模块职责变更时更新
- 数据流变更时更新

---

## 七、安全规范

### 7.1 敏感信息保护

**禁止提交的信息**：
- API Key / Secret
- 数据库密码
- 私钥文件
- 配置文件中的敏感字段

**保护措施**：
- 使用 `.gitignore` 排除敏感文件
- 使用环境变量存储敏感配置
- 定期轮换 API Key

### 7.2 代码安全

**输入验证**：
- 验证所有外部输入
- 防止 SQL 注入、XSS 等攻击
- 限制输入长度和类型

**错误处理**：
- 不暴露内部错误详情
- 记录详细错误日志
- 提供友好的错误提示

---

## 八、问题反馈

### 8.1 Bug 报告

**Bug 报告模板**：

```
## Bug 描述
[简短描述 Bug]

## 复现步骤
1. [步骤 1]
2. [步骤 2]
3. [步骤 3]

## 预期行为
[描述预期行为]

## 实际行为
[描述实际行为]

## 环境信息
- 操作系统：[操作系统]
- Python 版本：[版本]
- 项目版本：[版本]

## 错误日志
[粘贴相关错误日志]

## 补充信息
[其他相关信息]
```

### 8.2 功能建议

**功能建议模板**：

```
## 功能描述
[简短描述功能]

## 需求背景
[描述为什么需要这个功能]

## 预期效果
[描述功能实现后的效果]

## 实现思路
[可选：提供实现思路]

## 补充信息
[其他相关信息]
```

---

## 九、联系与支持

### 9.1 获取帮助

- **文档**：查阅 `docs/` 目录下的文档
- **Issue**：在 GitHub 上创建 Issue
- **讨论**：在 GitHub Discussions 中讨论

### 9.2 参与贡献

- **代码贡献**：提交 PR
- **文档贡献**：完善文档
- **测试贡献**：编写测试
- **问题反馈**：报告 Bug 或提出建议

---

**文档版本**：v1.0  
**最后更新**：2026-06-04  
**维护人员**：项目开发团队
