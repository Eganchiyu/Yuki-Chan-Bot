import json
import os
import re
from datetime import datetime
from urllib.parse import quote_plus

import aiohttp


def search_diary_fast(date_str=None, keyword=None):
    if not date_str and not keyword:
        return "错误：请至少提供 date_str 或 keyword"

    try:
        import chromadb
        from config import cfg

        # 绕过 RAG，直接连接配置中的向量数据库目录
        client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)

        # 2. 获取 Collection（不加载任何 Embedding 模型）
        collection = client.get_collection(name="diaries") # 替换为你的真实 collection name

        # 3. 瞬间拉取所有文档文本
        results = collection.get(include=["documents"])
        docs = results.get('documents', [])

        if not docs:
            return "记忆库目前为空。"

        matched_docs = []
        for doc in docs:
            match = True
            if date_str:
                safe_date = re.escape(date_str)
                if not re.search(rf"【日记\({safe_date}.*?\)】", doc):
                    match = False

            if keyword and match:
                if keyword not in doc:
                    match = False

            if match:
                matched_docs.append(doc)

        # ... 后续的格式化输出逻辑与之前一致 ...
        max_results = 8
        res_str = f"成功找到 {len(matched_docs)} 条记录（最多展示前{max_results}条）：\n"
        for i, d in enumerate(matched_docs[:max_results]):
            preview = d.replace("\n", " ")
            res_str += f"[{i+1}] {preview}...\n"

        return res_str

    except Exception as e:
        return f"搜索异常: {str(e)}"


def read_file_content(file_path: str, max_lines: int = 500) -> str:
    """
    通用文件读取工具 - 供小女仆使用。
    支持 txt, md, json, csv, py, yaml 等文本文件。

    Args:
        file_path: 文件绝对路径或相对路径
        max_lines: 最大读取行数（防止大文件撑爆上下文）

    Returns:
        文件内容字符串，或错误信息
    """
    # 处理路径
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        return f"错误：文件不存在 '{abs_path}'"

    # 检查文件大小（限制 10MB）
    file_size = os.path.getsize(abs_path)
    if file_size > 10 * 1024 * 1024:
        return f"错误：文件过大 ({file_size / 1024 / 1024:.1f} MB)，超过 10MB 限制"

    # 检查是否是二进制文件
    binary_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
                        '.mp3', '.mp4', '.avi', '.wav', '.flac', '.ogg',
                        '.zip', '.rar', '.7z', '.tar', '.gz',
                        '.exe', '.dll', '.so', '.dylib',
                        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}

    ext = os.path.splitext(abs_path)[1].lower()
    if ext in binary_extensions:
        return f"错误：'{abs_path}' 是二进制文件 ({ext})，无法直接读取。建议使用 OCR 或专门的解析工具。"

    # 读取文件
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines > max_lines:
            content = "".join(lines[:max_lines])
            content += f"\n\n... [截断] 共 {total_lines} 行，只显示前 {max_lines} 行"
        else:
            content = "".join(lines)

        return f"=== 文件: {os.path.basename(abs_path)} ({total_lines} 行) ===\n{content}"

    except UnicodeDecodeError:
        return f"错误：'{abs_path}' 编码不是 UTF-8，无法读取"
    except Exception as e:
        return f"错误：读取文件失败 - {str(e)}"


def list_directory_content(dir_path: str = ".", show_hidden: bool = False) -> str:
    """
    列出目录内容 - 供小女仆使用。
    显示文件/子目录名称、大小、修改时间等信息。

    Args:
        dir_path: 目录路径，绝对路径或相对路径，默认当前目录
        show_hidden: 是否显示隐藏文件（以.开头），默认 False

    Returns:
        目录内容字符串，或错误信息
    """
    abs_path = os.path.abspath(dir_path)

    if not os.path.exists(abs_path):
        return f"错误：路径不存在 '{abs_path}'"

    if not os.path.isdir(abs_path):
        return f"错误：'{abs_path}' 不是目录，而是文件。请使用 read_file 读取文件内容。"

    try:
        entries = os.listdir(abs_path)
    except PermissionError:
        return f"错误：没有权限访问 '{abs_path}'"
    except Exception as e:
        return f"错误：无法列出目录 - {str(e)}"

    # 过滤隐藏文件
    if not show_hidden:
        entries = [e for e in entries if not e.startswith(".")]

    if not entries:
        return f"目录 '{abs_path}' 为空。"

    # 分类：目录优先，然后文件
    dirs = []
    files = []
    for name in entries:
        full_path = os.path.join(abs_path, name)
        try:
            is_dir = os.path.isdir(full_path)
            size = os.path.getsize(full_path)
            mtime = os.path.getmtime(full_path)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except (OSError, PermissionError):
            is_dir = False
            size = 0
            mtime_str = "未知"

        entry = {
            "name": name,
            "is_dir": is_dir,
            "size": size,
            "mtime": mtime_str,
        }
        if is_dir:
            dirs.append(entry)
        else:
            files.append(entry)

    # 格式化输出
    lines = [f"=== 目录: {abs_path} ==="]
    lines.append(f"共 {len(dirs)} 个子目录, {len(files)} 个文件\n")

    # 表头
    lines.append(f"{'类型':<6} {'大小':>10} {'修改时间':<16} {'名称'}")
    lines.append("-" * 60)

    # 目录
    for d in sorted(dirs, key=lambda x: x["name"]):
        lines.append(f"{'[目录]':<6} {'-':>10} {d['mtime']:<16} {d['name']}/")

    # 文件
    for f in sorted(files, key=lambda x: x["name"]):
        size_str = _format_file_size(f["size"])
        lines.append(f"{'文件':<6} {size_str:>10} {f['mtime']:<16} {f['name']}")

    return "\n".join(lines)


def _format_file_size(size: int) -> str:
    """格式化文件大小为人类可读格式"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f}GB"


# === 新增工具：从 Yuki 移交过来的能力 ===

async def manage_timer_task_maid(title=None, due_time=None, delay_seconds=None, action="create", task_id=None, message=None):
    """
    定时任务管理工具 - 供小女仆使用。
    注意：此工具返回操作指令，实际执行由小女仆主循环处理。
    """
    # 小女仆不直接管理定时任务，返回指令让 Yuki 执行
    return {
        "action": action,
        "title": title,
        "due_time": due_time,
        "delay_seconds": delay_seconds,
        "task_id": task_id,
        "message": message,
        "note": "定时任务需要由 Yuki 执行，请在 finish 中返回此指令"
    }


async def browser_search_maid(query, max_results=5, search_depth="basic"):
    """
    网页搜索工具 - 供小女仆使用。
    调用 Tavily 搜索服务，返回网页结果。
    """
    if not query:
        return "错误：缺少搜索关键词"

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        return f"未配置 TAVILY_API_KEY，无法搜索。请访问：{url}"

    _TAVILY_SEARCH_URL = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": True,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_TAVILY_SEARCH_URL, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return f"错误：Tavily 搜索请求失败 (HTTP {response.status})"

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        })

    answer = data.get("answer")
    if answer:
        return f"搜索结果摘要：{answer}\n\n详细结果：{json.dumps(results, ensure_ascii=False, indent=2)}"
    else:
        return f"已搜索到 {len(results)} 条结果：\n{json.dumps(results, ensure_ascii=False, indent=2)}"


async def amap_search_maid(keywords, search_type="text", location=None, address=None, city=None, radius=3000, page_size=10):
    """
    高德地图搜索工具 - 供小女仆使用。
    search_type: text=关键词搜索, around=周边搜索(需坐标), geocode=地名转坐标
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return "错误：未配置 AMAP_API_KEY，无法调用高德地图服务"

    _AMAP_AROUND_URL = "https://restapi.amap.com/v5/place/around"
    _AMAP_TEXT_URL = "https://restapi.amap.com/v5/place/text"
    _AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

    timeout = aiohttp.ClientTimeout(total=15)

    if search_type == "geocode":
        if not address:
            return "错误：geocode 模式需要 address 参数"
        params = {"key": api_key, "address": address}
        if city:
            params["city"] = city
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_AMAP_GEOCODE_URL, params=params) as response:
                data = await response.json(content_type=None)
        if data.get("status") != "1":
            return f"错误：高德地图返回 - {data.get('info', '未知错误')}"
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return "未找到该地址的坐标信息"
        results = [{"name": g.get("formatted_address"), "location": g.get("location"), "city": g.get("city"), "district": g.get("district")} for g in geocodes[:5]]
        return f"已定位到 {len(results)} 个地址：\n{json.dumps(results, ensure_ascii=False, indent=2)}"

    if not keywords:
        return "错误：缺少搜索关键词"

    if search_type == "around":
        if not location:
            return "错误：周边搜索需要中心点坐标（经度,纬度）"
        params = {
            "key": api_key, "keywords": keywords, "location": location,
            "radius": max(100, min(int(radius), 50000)),
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        url = _AMAP_AROUND_URL
    else:
        params = {
            "key": api_key, "keywords": keywords,
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        if city:
            params["region"] = city
        url = _AMAP_TEXT_URL

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return f"错误：高德地图请求失败 (HTTP {response.status})"

    if data.get("status") != "1":
        return f"错误：高德地图返回 - {data.get('info', '未知错误')}"

    pois = []
    for poi in (data.get("pois") or []):
        biz = poi.get("business") or {}
        pois.append({
            "name": poi.get("name"), "address": poi.get("address"),
            "location": poi.get("location"), "type": poi.get("type"),
            "distance": poi.get("distance"), "city": poi.get("cityname"),
            "tel": biz.get("tel"), "rating": biz.get("rating"), "cost": biz.get("cost"),
        })
    count = data.get("count", len(pois))
    summary = f"共找到 {count} 个地点" if count else "未找到相关地点"
    return f"{summary}：\n{json.dumps(pois, ensure_ascii=False, indent=2)}"
