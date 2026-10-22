# get_memory_usage：获取系统内存使用情况

## 功能
获取当前系统的内存使用信息，包括总量、已用、可用和使用率。

## 参数
无参数

## 返回值
- 返回字典，包含：
  - `total_gb`: 内存总量（GB）
  - `used_gb`: 已用内存（GB）
  - `available_gb`: 可用内存（GB）
  - `percent`: 使用率（%）

## 调用示例
```python
from get_memory_usage import get_memory_usage

info = get_memory_usage()
print(f"内存使用率: {info['percent']}%")
```

## 依赖
- psutil