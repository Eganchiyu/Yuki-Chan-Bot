# Post Commit Check Skill

## 描述

在每次代码提交后自动执行一系列检查，确保代码质量、文档同步和项目规范。

## 触发条件

当用户完成代码提交（git commit）后触发。

## 执行步骤

### 1. Gitignore 检查

检查是否有敏感文件被意外提交：

```bash
# 检查是否有敏感文件
git ls-files | grep -E "\.(env|key|pem|secret)$"

# 检查是否有大型数据文件
git ls-files | grep -E "\.(db|sqlite|bin)$" | head -20
```

**检查项**：
- `.env` 文件
- API Key 文件
- 私钥文件
- 大型数据文件
- 缓存文件

**处理方式**：
- 如果发现敏感文件，提示用户添加到 `.gitignore`
- 如果发现大型文件，提示用户使用 Git LFS 或排除

### 2. 代码风格审查

检查代码是否符合项目规范：

```bash
# Python 代码风格检查（如果有配置）
python -m flake8 --max-line-length=100 --ignore=E501,W503 .

# 或使用 ruff（更快）
ruff check .
```

**检查项**：
- 命名规范
- 缩进规范
- 导入顺序
- 注释规范

**处理方式**：
- 列出不符合规范的文件
- 提供修复建议
- 自动修复简单问题（如果可能）

### 3. 命名方式检查

检查文件、类、函数命名是否符合规范：

```bash
# 检查文件命名（应使用小写和下划线）
find . -name "*.py" | grep -E "[A-Z]" | grep -v "__"

# 检查类命名（应使用 PascalCase）
grep -r "class [a-z]" --include="*.py" .

# 检查函数命名（应使用 snake_case）
grep -r "def [A-Z]" --include="*.py" .
```

**检查项**：
- 文件名：小写 + 下划线
- 类名：PascalCase
- 函数名：snake_case
- 常量：大写 + 下划线

### 4. README 同步检查

检查 README.md 是否需要更新：

```bash
# 检查 README 是否存在
if [ ! -f README.md ]; then
    echo "警告: README.md 不存在"
fi

# 检查 README 中的链接是否有效
grep -oE "https?://[^)]+" README.md | while read url; do
    curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200" || echo "链接失效: $url"
done
```

**检查项**：
- README 是否存在
- 项目描述是否准确
- 安装说明是否完整
- 使用示例是否有效

### 5. Changelog 同步检查

检查 `docs/changelog.md` 是否已更新：

```bash
# 检查 changelog 是否有未发布的内容
if grep -q "## \[未发布\]" docs/changelog.md; then
    echo "Changelog 有未发布的内容"
else
    echo "警告: Changelog 可能未更新"
fi
```

**检查项**：
- Changelog 是否存在
- 是否有未发布的内容
- 是否记录了本次变更

**处理方式**：
- 如果 Changelog 未更新，提示用户添加变更记录
- 提供变更记录模板

### 6. Docs 同步检查

检查文档是否与代码同步：

```bash
# 检查文档文件是否存在
for doc in docs/architecture.md docs/development-plan.md docs/changelog.md; do
    if [ ! -f "$doc" ]; then
        echo "警告: $doc 不存在"
    fi
done

# 检查文档最后更新时间
for doc in docs/*.md; do
    echo "$doc: $(git log -1 --format="%ai" -- "$doc")"
done
```

**检查项**：
- 文档文件是否存在
- 文档是否最近更新
- 文档内容是否与代码一致

**处理方式**：
- 如果文档缺失，提示用户创建
- 如果文档过期，提示用户更新

## 输出格式

### 成功输出

```
✅ Post Commit Check 完成

检查结果：
- [✓] Gitignore: 无敏感文件
- [✓] 代码风格: 符合规范
- [✓] 命名方式: 符合规范
- [✓] README: 已同步
- [✓] Changelog: 已更新
- [✓] Docs: 已同步
```

### 警告输出

```
⚠️ Post Commit Check 完成（有警告）

检查结果：
- [✓] Gitignore: 无敏感文件
- [!] 代码风格: 3 个文件不符合规范
  - main.py: 行 45 超过 100 字符
  - core/engine.py: 行 12 缺少空行
  - modules/rag.py: 导入顺序不正确
- [✓] 命名方式: 符合规范
- [!] README: 可能需要更新
- [✓] Changelog: 已更新
- [✓] Docs: 已同步

建议操作：
1. 修复代码风格问题
2. 检查并更新 README
```

### 错误输出

```
❌ Post Commit Check 失败

检查结果：
- [✗] Gitignore: 发现敏感文件
  - .env
  - config/secrets.yaml
- [✓] 代码风格: 符合规范
- [✓] 命名方式: 符合规范
- [✗] README: 不存在
- [✗] Changelog: 未更新
- [✓] Docs: 已同步

必须修复：
1. 将敏感文件添加到 .gitignore
2. 创建 README.md
3. 更新 docs/changelog.md
```

## 配置选项

### 启用/禁用检查

在 `.trae/config.yaml` 中配置：

```yaml
post_commit_check:
  enabled: true
  checks:
    gitignore: true
    code_style: true
    naming: true
    readme: true
    changelog: true
    docs: true
```

### 自动修复

```yaml
post_commit_check:
  auto_fix:
    code_style: false  # 不自动修复代码风格
    readme: false      # 不自动更新 README
    changelog: true    # 自动提示更新 Changelog
```

## 集成方式

### 作为 Git Hook

创建 `.git/hooks/post-commit`：

```bash
#!/bin/bash
# Post Commit Check

echo "执行 Post Commit Check..."

# 调用 Trae skill
trae run post_commit_check
```

### 作为 CI/CD 步骤

在 GitHub Actions 中集成：

```yaml
name: Post Commit Check

on:
  push:
    branches: [ main, develop ]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Post Commit Check
        run: |
          # 执行检查脚本
          python scripts/post_commit_check.py
```

## 相关文件

- `.trae/rules/project_rules.md`: 项目开发公约
- `docs/changelog.md`: 更新日志
- `docs/architecture.md`: 架构文档
- `.gitignore`: Git 忽略文件

## 版本历史

- v1.0 (2026-06-01): 初始版本

---

**维护人员**：项目开发团队  
**最后更新**：2026-06-01
