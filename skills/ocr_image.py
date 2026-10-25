# maid_deps: easyocr
import os
import sys
import easyocr


def ocr_image(image_path: str, lang: list = None, gpu: bool = False) -> str:
    """使用easyocr提取图片中的文字。

    Args:
        image_path: 图片文件的绝对路径或相对路径。
        lang: 识别语言列表，默认 ['ch_sim', 'en'] 支持中文简体+英文。
        gpu: 是否使用GPU加速，默认False（CPU模式）。

    Returns:
        识别出的文本字符串，每行对应一个文本块。如果出错返回错误信息。
    """
    if lang is None:
        lang = ['ch_sim', 'en']

    if not os.path.exists(image_path):
        return f"图片不存在: {image_path}"
    try:
        reader = easyocr.Reader(lang, gpu=gpu)
        result = reader.readtext(image_path, detail=0)
        return '\n'.join(result)
    except Exception as e:
        return f"OCR失败: {str(e)}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ocr_image.py <图片路径> [lang] [gpu]")
        print("示例: python ocr_image.py D:/Projects/YukiV6/data/image_store/027.jpg")
        sys.exit(1)

    image_path = sys.argv[1]
    lang = sys.argv[2].split(",") if len(sys.argv) > 2 else ['ch_sim', 'en']
    gpu = sys.argv[3].lower() == "true" if len(sys.argv) > 3 else False

    result = ocr_image(image_path, lang=lang, gpu=gpu)
    print(result)
