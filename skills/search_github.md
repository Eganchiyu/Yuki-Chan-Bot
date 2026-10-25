# search_github：通用 GitHub 搜索

## 功能
使用 GitHub API 搜索仓库或代码，返回结构化的搜索结果。

## 参数
- `query` (str, required): 搜索关键词
- `num_results` (int, optional): 返回结果数量，默认 5
- `search_type` (str, optional): 搜索类型，"repositories"（默认）或 "code"

## 注意事项
- **仓库搜索**：无需认证，可直接使用
- **代码搜索**：需要 GitHub Token，否则返回 401 错误

## 返回值
- 返回列表，根据 search_type 不同包含不同字段：
  - 仓库搜索：name, description, stars, url
  - 代码搜索：repository, path, url（需要 Token）

## 调用示例
```python
from search_github import search_github

# 搜索仓库（无需 Token）
results = search_github("machine learning")

# 搜索代码（需要配置 Token）
results = search_github("def main", search_type="code")

# 指定数量
results = search_github("python", num_results=10)

for r in results:
    print(r)
```

## 依赖
- requests
- json

## 其他信息
- 机主的 Github 名称为 `Eganchiyu`
- skills 目录下有 `github_token_operation_guide.md` 文件，详细介绍了 Token 操作。