import fitz

def read_pdf_text(file_path: str) -> str:
    """
    读取PDF文件并返回纯文本内容。
    参数:
        file_path: PDF文件的绝对路径或相对路径。
    返回:
        PDF文件的文本内容字符串。
    异常:
        如果文件不存在或无法打开，抛出异常。
    """
    doc = fitz.open(file_path)
    text = ''
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(read_pdf_text(sys.argv[1]))
    else:
        print('请提供PDF文件路径作为参数。')