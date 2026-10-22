# github_operations：GitHub 仓库操作指南

## 功能

使用 GitHub REST API 对指定仓库执行查询、读取和写入操作。

## Token 配置

认证信息从项目配置中读取，不要硬编码到文档或代码中：

- 配置文件：`configs/config.yaml` 中的 `github_token`

> **安全提示**：Token 属于敏感信息，禁止提交到代码库或写入文档。

## 常用 API 端点

### 仓库信息

```
GET /repos/{owner}/{repo}
```

返回仓库基本信息，包括名称、描述、星标数、fork 数等。

### Issues 列表

```
GET /repos/{owner}/{repo}/issues
```

查询参数：
- `state`：`open`（默认）、`closed`、`all`
- `per_page`：每页数量，默认 30
- `page`：页码

### Pull Requests 列表

```
GET /repos/{owner}/{repo}/pulls
```

查询参数：
- `state`：`open`（默认）、`closed`、`all`
- `per_page`：每页数量
- `page`：页码

## 调用示例

### 仓库信息

```bash
curl -s \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/{owner}/{repo}
```

### Issues 列表

```bash
curl -s \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=100"
```

### Pull Requests 列表

```bash
curl -s \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=100"
```

### 创建 Issue

```bash
curl -s -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Content-Type: application/json" \
  -d '{"title":"Issue 标题","body":"Issue 内容","labels":["bug"]}' \
  https://api.github.com/repos/{owner}/{repo}/issues
```

### 创建 Pull Request

```bash
curl -s -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Content-Type: application/json" \
  -d '{"title":"PR 标题","body":"PR 描述","head":"feature-branch","base":"main"}' \
  https://api.github.com/repos/{owner}/{repo}/pulls
```

## 错误处理

常见 HTTP 状态码：

| 状态码 | 含义 | 处理方式 |
|--------|------|----------|
| 200 | 成功 | 正常处理响应 |
| 401 | 未认证 | 检查 Token 是否正确 |
| 403 | 禁止访问 | 可能是速率限制或权限不足 |
| 404 | 未找到 | 仓库或资源不存在 |
| 429 | 速率限制 | 等待后重试，检查 `X-RateLimit-Reset` |

## 其他信息
- 机主的 Github 名称为 `Eganchiyu`
- curl（命令行 HTTP 客户端）
- 项目已有 `modules/github_monitor`，必要时可参考