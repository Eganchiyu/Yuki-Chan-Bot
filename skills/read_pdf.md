# read_pdf：读取PDF文件并提取文本内容

## 功能
读取PDF文件，提取所有页面的纯文本内容。

## 参数
- `file_path` (str): PDF文件的路径（绝对或相对）。

## 返回
- str: PDF文件的文本内容。

## 异常
- 如果文件不存在或无法打开，抛出异常。

## 使用示例
```python
from read_pdf import read_pdf_text
text = read_pdf_text('example.pdf')
print(text)
```

## 依赖
- PyMuPDF (fitz)

## 注意事项
- 仅提取纯文本，不包含图片、表格等非文本元素。
- 对于扫描版PDF（图片形式），无法提取文字。