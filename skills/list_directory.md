# list_directory：列出指定目录下的所有文件和子目录

## 功能
遍历指定目录，返回每个条目的名称、类型（文件/目录）和大小（字节）。

## 参数
- `path` (str): 要列出的目录路径。

## 返回
- `list[dict]`: 每个字典包含 `name` (文件名), `type` ('file' 或 'directory'), `size` (文件大小，目录为0)。

## 示例
```python
from list_directory import list_directory
items = list_directory('D:/Asumi')
for item in items:
    print(f"{item['name']} ({item['type']}, {item['size']} bytes)")
```