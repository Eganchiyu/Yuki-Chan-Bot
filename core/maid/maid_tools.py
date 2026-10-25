import json
import os
import random
import re
from datetime import datetime
from urllib.parse import quote_plus

import aiohttp

from config import cfg
from utils.http_client import create_tcp_connector

# 读文件三重防爆：单次字节上限、单行字符上限（base64/压缩包伪装成 .txt 时的主要闸门）
READ_FILE_MAX_BYTES = 64 * 1024
READ_FILE_MAX_LINE_CHARS = 2000


DIARY_PREVIEW_MAX = 8


def search_diary_fast(date_str=None, keyword=None):
    """按日期/关键词检索日记；无参数时随机翻看。命中结果同样随机抽取，不按时间顺序。"""
    try:
        import chromadb
        from config import cfg

        # 绕过 RAG，直接连接配置中的向量数据库目录
        client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)

        # 2. 获取 Collection（不加载任何 Embedding 模型）
        collection = client.get_collection(name="diaries") # 替换为你的真实 collection name

        # 3. 过滤交给向量库底层（where_document），不再把全表拉进内存
        conditions = []
        if date_str:
            # 日记正文固定以 【日记(YYYY-MM-DD HH:MM)】 开头，日期前缀可直接用 $contains 粗筛
            conditions.append({"$contains": f"【日记({date_str}"})
        if keyword:
            # Chroma 的 $contains 区分大小写：常见大小写形态各查一次取并集，
            # 最终精确判定仍由下面的 lower() 比对负责。
            keyword_variants = {
                keyword,
                keyword.lower(),
                keyword.upper(),
                keyword.title(),
                keyword.capitalize(),
            }
            keyword_conditions = [{"$contains": kw} for kw in sorted(keyword_variants)]
            conditions.append(
                keyword_conditions[0] if len(keyword_conditions) == 1 else {"$or": keyword_conditions}
            )

        if conditions:
            where_document = conditions[0] if len(conditions) == 1 else {"$and": conditions}
            results = collection.get(where_document=where_document, include=["documents"])
        else:
            # 无日期无关键词：随机翻看日记本
            results = collection.get(include=["documents"])
        candidates = results.get("documents") or []

        if not candidates:
            return "没有找到匹配的日记。" if conditions else "记忆库目前是空的。"

        # 4. 候选集已经很小，再用正则做精确校验（保持原日期语义）
        date_pattern = re.compile(rf"【日记\({re.escape(date_str)}.*?\)】") if date_str else None
        keyword_lower = keyword.lower() if keyword else None
        matched_docs = []
        for doc in candidates:
            if date_pattern and not date_pattern.search(doc):
                continue
            if keyword_lower is not None and keyword_lower not in doc.lower():
                continue
            matched_docs.append(doc)

        if not matched_docs:
            return "没有找到匹配的日记。"

        # 5. 随机抽取，避免总是返回最早写入的那几条
        picked = random.sample(matched_docs, min(DIARY_PREVIEW_MAX, len(matched_docs)))
        if conditions:
            header = f"成功找到 {len(matched_docs)} 条记录（随机抽取 {len(picked)} 条展示）：\n"
        else:
            header = f"随机翻看日记本（共 {len(matched_docs)} 条，随机抽取 {len(picked)} 条）：\n"
        res_str = header
        for i, d in enumerate(picked):
            preview = d.replace("\n", " ")
            res_str += f"[{i+1}] {preview}...\n"

        return res_str

    except Exception as e:
        return f"搜索异常: {str(e)}"


def read_file_content(
    file_path: str,
    max_lines: int = 500,
    offset: int = 0,
    max_bytes: int = READ_FILE_MAX_BYTES,
) -> str:
    """
    通用文件读取工具 - 供小女仆使用。
    支持 txt, md, json, csv, py, yaml 等文本文件。

    三重防爆：行数上限、字节上限、单行字符上限。任何一项命中都只截断不报错，
    并给出续读需要的 offset，避免把 base64/压缩包伪装成 .txt 的文件整份喂进上下文。

    Args:
        file_path: 文件绝对路径或相对路径
        max_lines: 最大读取行数
        offset: 从第几行开始读（0 基），用于分段续读
        max_bytes: 本次最多返回的字节数

    Returns:
        文件内容字符串，或错误信息
    """
    # 处理路径
    if not file_path:
        return "错误：未提供文件路径"
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        return f"错误：文件不存在 '{abs_path}'"
    if os.path.isdir(abs_path):
        return f"错误：'{abs_path}' 是目录，请用 list_directory 查看"

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

    try:
        max_lines = max(1, int(max_lines or 500))
    except Exception:
        max_lines = 500
    try:
        offset = max(0, int(offset or 0))
    except Exception:
        offset = 0
    try:
        max_bytes = max(1024, int(max_bytes or READ_FILE_MAX_BYTES))
    except Exception:
        max_bytes = READ_FILE_MAX_BYTES

    try:
        with open(abs_path, "rb") as f:
            head = f.read(8192)
            if b"\x00" in head:
                return f"错误：'{abs_path}' 看起来是二进制文件，无法直接读取。建议使用 OCR 或专门的解析工具。"
            f.seek(0)

            total_lines = 0
            collected = []
            used_bytes = 0
            long_lines_cut = 0
            stopped_by = ""

            for index, raw_line in enumerate(f):
                total_lines = index + 1
                if index < offset:
                    continue
                if stopped_by:
                    continue  # 已经截断，只继续数总行数
                if len(collected) >= max_lines:
                    stopped_by = "lines"
                    continue

                try:
                    text = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    return f"错误：'{abs_path}' 编码不是 UTF-8，无法读取"

                if len(text) > READ_FILE_MAX_LINE_CHARS:
                    kept = text[:READ_FILE_MAX_LINE_CHARS]
                    dropped = len(text) - READ_FILE_MAX_LINE_CHARS
                    text = f"{kept}…[本行过长，已截断 {dropped} 字符]\n"
                    long_lines_cut += 1

                size = len(text.encode("utf-8"))
                if used_bytes + size > max_bytes:
                    stopped_by = "bytes"
                    continue
                collected.append(text)
                used_bytes += size

        if offset >= total_lines:
            return f"错误：offset={offset} 超出文件行数（共 {total_lines} 行）"

        start = offset + 1
        end = offset + len(collected)
        content = "".join(collected)

        footer = []
        if stopped_by == "lines" and end < total_lines:
            footer.append(f"已达单次 {max_lines} 行上限")
        if stopped_by == "bytes" and end < total_lines:
            footer.append(f"已达单次 {max_bytes // 1024}KB 上限")
        if long_lines_cut:
            footer.append(f"{long_lines_cut} 行因超长被截到 {READ_FILE_MAX_LINE_CHARS} 字符")

        notice = ""
        if footer:
            notice = (
                f"\n\n... [截断] 已显示第 {start}-{end} 行（共 {total_lines} 行，"
                f"文件 {file_size / 1024:.1f} KB）：{'；'.join(footer)}。"
            )
            if end < total_lines:
                notice += f"继续读取请用 offset={end}"
            elif long_lines_cut:
                notice += "超长行只返回开头部分，若需要其余内容请用 terminal（如 head/cut/grep）。"
        elif end < total_lines:
            notice = f"\n\n... [还有 {total_lines - end} 行] 继续读取请用 offset={end}"

        return f"=== 文件: {os.path.basename(abs_path)} ({total_lines} 行, {file_size / 1024:.1f} KB) ===\n{content}{notice}"

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

    api_key = cfg.TAVILY_API_KEY
    if not api_key:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        return f"未配置 search.tavily_api_key（Tavily Key），无法搜索。请访问：{url}"

    _TAVILY_SEARCH_URL = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": True,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
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
    api_key = cfg.AMAP_API_KEY
    if not api_key:
        return "错误：未配置 search.amap_api_key（高德地图 Key），无法调用高德地图服务"

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
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
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

    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
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
