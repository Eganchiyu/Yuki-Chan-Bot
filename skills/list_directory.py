import os

def list_directory(path):
    """
    列出指定目录下的所有文件和子目录，包括文件名、类型和大小。
    
    参数:
        path (str): 要列出的目录路径。
    
    返回:
        list[dict]: 每个元素包含 name (文件名), type ('file' 或 'directory'), size (文件大小，目录为0)。
    """
    items = []
    for entry in os.scandir(path):
        info = {
            'name': entry.name,
            'type': 'directory' if entry.is_dir() else 'file',
            'size': entry.stat().st_size if entry.is_file() else 0
        }
        items.append(info)
    return items

if __name__ == '__main__':
    import json
    result = list_directory('D:/Asumi')
    print(json.dumps(result, ensure_ascii=False, indent=2))