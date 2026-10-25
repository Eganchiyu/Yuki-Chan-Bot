# search_image：搜索并下载一张随机二次元图片（关键词仅用于命名）

## 功能
从随机二次元图片API获取一张图片并保存到本地。

## 参数
- `keyword` (str): 关键词，用于生成文件名，不参与搜索。
- `save_dir` (str): 保存目录，默认为`D:/Projects/YukiV6/temp_images`。

## 返回值
- 成功：图片文件的绝对路径（字符串）。
- 失败：`None`。

## 调用示例
```python
from search_image import search_image
path = search_image('帅气男头')
print(path)
```

## 依赖
- requests
- os
- random