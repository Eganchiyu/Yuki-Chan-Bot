import psutil


def get_memory_usage():
    """
    获取系统内存使用情况。
    返回:
        包含内存信息的字典
    """
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent": mem.percent
    }


if __name__ == '__main__':
    import json
    info = get_memory_usage()
    print(json.dumps(info, ensure_ascii=False, indent=2))