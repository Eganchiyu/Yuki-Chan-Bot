# ocr_image：使用easyocr提取图片文字

## 功能
利用easyocr库对图片进行光学字符识别（OCR），支持中文和英文。

## 参数
- `image_path` (str): 图片文件路径（必填）
- `lang` (list): 识别语言列表，默认 ['ch_sim', 'en']
- `gpu` (bool): 是否启用GPU，默认False

## 返回
识别出的文本字符串，每行一个文本块。

## 调用示例
```bash
python D:/Projects/YukiV6/skills/ocr_image.py D:/Projects/YukiV6/data/image_store/027.jpg
python D:/Projects/YukiV6/skills/ocr_image.py D:/Projects/YukiV6/data/image_store/027.jpg ch_sim,en false
```
