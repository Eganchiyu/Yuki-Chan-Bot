import aiohttp
import asyncio
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

from config import cfg
from utils.llm_client import llm_chat, close_global_session
from utils.logger import get_logger

logger = get_logger("maid")


class MaidCapabilityBoundary:
    """小女仆能力边界判定，避免把明显不合适的任务交给后台执行。"""

    BLOCKED_KEYWORDS = ["转账", "支付", "删除系统", "格式化", "破解", "盗号"]
    HIGH_COST_KEYWORDS = ["训练模型", "大型项目重写", "全网爬取", "无限", "长期监控"]

    @classmethod
    def judge(cls, goal: str) -> dict:
        text = goal or ""
        if not text.strip():
            return {"allowed": False, "reason": "任务目标为空", "suggestion": "请补充明确的任务目标。"}
        if any(keyword in text for keyword in cls.BLOCKED_KEYWORDS):
            return {"allowed": False, "reason": "任务涉及高风险操作", "suggestion": "可以改为提供安全的操作说明或风险分析。"}
        if any(keyword in text for keyword in cls.HIGH_COST_KEYWORDS):
            return {"allowed": False, "reason": "任务实现成本过高", "suggestion": "建议拆分为更小的阶段性任务。"}
        return {"allowed": True, "reason": "任务在小女仆可处理范围内", "suggestion": ""}


def build_maid_task(goal: str, chat_id: str = None, mode: str = "group", source: str = "yuki") -> dict:
    """构造标准小女仆任务，供工具链和标签委托共用。"""
    return {
        "goal": goal,
        "chat_id": str(chat_id) if chat_id is not None else None,
        "mode": mode,
        "source": source,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_maid_report(goal: str, result_dict: dict) -> str:
    """构造标准小女仆回调报告。"""
    status = result_dict.get("status", "unknown")
    result = result_dict.get("result", "未知结果")
    return f"【小女仆完成! 小女仆汇报】\n任务：「{goal}」\n状态：{status}\n结果：{result}"


def clean_json_output(text):
    """提取第一个 { 到最后一个 } 之间的内容，防止模型输出废话"""
    if not text: return ""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    return match.group(0) if match else text.strip()


async def call_cloud_maid_robust(messages):
    """调用 LLM 完成小女仆任务。"""
    # 强制要求 JSON 格式输出
    payload_kwargs = {
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }

    result = await llm_chat(
        messages=messages,
        model=cfg.LLM_MODEL,
        **payload_kwargs
    )

    # 清洗可能存在的 Markdown 标签
    return clean_json_output(result)
# --- 目录初始化 ---
SKILLS_DIR = "skills"      # 存放长期通用技能 (.py 和 .md)
WORKSPACE_DIR = "workspace" # 存放当前任务的临时草稿 (.py)
TASKS_DIR = "tasks"
LOGS_DIR = "logs"

for d in [SKILLS_DIR, WORKSPACE_DIR, TASKS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)


def _clean_workspace():
    """安全清理 workspace 目录：只删除文件，不删除目录本身（避免 Windows 权限问题）"""
    if not os.path.exists(WORKSPACE_DIR):
        return
    deleted = 0
    for root, dirs, files in os.walk(WORKSPACE_DIR, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
                deleted += 1
            except Exception as e:
                logger.debug(f"[Maid] 删除文件失败: {f}, {e}")
        # 删除子目录
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except:
                pass
    logger.info(f"[Maid] 临时草稿区已清空，删除 {deleted} 个文件")

MAID_SYSTEM_PROMPT = f"""
你是一个具备高度自主进化能力的 AI 智能体，代号：**小女仆**。
你的上位机是Yuki，一个有点笨的AI智能体。她住在机主的电脑里，通过QQ和外界连通，你是她的内部帮手，可以操作本地电脑环境来帮助她。所以如果指令不清楚，可以直接返回告诉她。
如果任务内容包括**发送消息**，请**不要执行发送**，直接返回发送的文件的**绝对路径或内容**。
如果任务是知识类任务，你可以在第一轮直接依靠知识库做返回。
如果是日记查询类任务，返回相关的日记原文，供Yuki查看。

### 核心使命
通过编写、优化和复用 Python 技能（Skills）来完成用户指令。


### 运行上下文
- **当前路径**: {os.getcwd()}
- **操作系统**: {os.name}
- **技能存储**: 所有永久技能存放在 `/skills` 目录下，以 `.py` 结尾。

### 进化与归档法则（行为规范）
1. **区分草稿与固化**：当前任务是专职且一次性的代码，请使用 `write_temp_skill` 编写测试。如果判定该代码具有未来的**通用复用价值**（例如：搜索文件、处理图片、网络请求等），你必须将其抽象为高内聚、低耦合的可调用模块，并在任务结束前调用 `solidify_skill` 固化它，方便后续重用代码。
2. **检索优先**: 面对任务，首先调用 `list_skills` 检查是否有现成技能。如果有，请用 `read_skill` 阅读其文档和代码后直接调用。
3. **即写即用**: 调用 `write_temp_skill` 后，必须紧跟 `run_skill` 验证。
4. **迭代优化**: 如果已有技能不够通用，你可以阅读它，修改代码后，重新调用 `solidify_skill` 覆盖更新它和它的文档。

### 工具箱（JSON 接口）
1. `list_skills()`: 返回当前已固化的通用技能列表及一句话简介。
2. `read_skill(name)`: 读取已固化技能的 MD 文档和 Python 源码。
3. `write_temp_skill(name, code)`: 在临时工作区编写草稿代码（任务结束后会被自动销毁）。
4. `solidify_skill(name, code, markdown_doc)`: 将经过验证的通用代码永久保存。
   - 'name': 英文标识符。
   - 'code': 优化后的、高内聚低耦合的 Python 代码。
   - 'markdown_doc': 技能说明文档，第一行必须是 `# 技能名：一句话功能简介`，后续写明参数说明和调用示例，请详细介绍模块的功能和使用方法，以及模块处理边界能力，方便后续查阅和复用。
5. `run_skill(name)`: 执行工作区或固化区的技能。
6. `install_package(pkg)`: 安装缺失的 pip 包。
7. `read_file(path, max_lines)`: 读取本地文本文件内容。
   - 'path': 文件绝对路径或相对路径。
   - 'max_lines': 可选，最大读取行数，默认 500。
   - 支持格式：txt, md, json, csv, py, yaml 等文本文件。
   - 二进制文件（图片、音视频、PDF 等）会返回错误提示。
8. `search_diary(date_str, keyword)`: 搜索 Yuki 的日记/记忆。
   - 'date_str': 选填，日期字符串（如 "2026-05-20" 或 "2026-03"）。
   - 'keyword': 选填，需要全文匹配的关键词。
   - 规则：'date_str' 和 'keyword' 至少提供一个，未提供的填 null。
   - 策略提示：为防止上下文超载，此工具每次最多只返回 8 条记录（按时间顺序排序）。如果返回提示"结果过多"，或者前 5 条里没有你想要的，**你可以多次调用此工具**，通过更换 `keyword` 或增加 `date_str` 来不断缩小搜索范围，直到找到精确目标。
9. `browser_search(query, max_results, search_depth)`: 网页搜索。
   - 'query': 搜索关键词或问题（必填）。
   - 'max_results': 返回结果数量，1-10，默认 5。
   - 'search_depth': 搜索深度，'basic' 或 'advanced'，默认 'basic'。
   - 用途：实时信息查询、新闻、技术文档、百科知识等。
10. `amap_search(keywords, search_type, location, address, city, radius, page_size)`: 高德地图搜索。
   - 'keywords': 搜索关键词（如"餐厅"、"加油站"）。
   - 'search_type': 搜索类型 - 'text'(关键词搜索), 'around'(周边搜索), 'geocode'(地名转坐标)。
   - 'location': 中心点坐标，around 模式必填，格式：经度,纬度。
   - 'address': 地名或地址，geocode 模式必填。
   - 'city': 限定城市，如"北京"，提高精度。
   - 'radius': 搜索半径(米)，around 模式使用，默认 3000。
   - 'page_size': 返回结果数量，1-25，默认 10。
11. `manage_timer_task(title, due_time, delay_seconds, action, task_id, message)`: 定时任务管理。
   - 'title': 任务标题（必填）。
   - 'due_time': 到点时间，支持 YYYY-MM-DD HH:MM:SS 格式。
   - 'delay_seconds': 相对延迟秒数。
   - 'action': 操作类型 - 'create'(创建), 'cancel'(取消), 'list'(列出)。
   - 'task_id': 取消指定任务时使用。
   - 'message': 到点后的提醒内容。
   - 注意：此工具返回指令，实际定时任务由 Yuki 执行。
12. `finish(reason)`: 
   - **禁止盲目结束**：严禁在没有看到成功结果或输出的具体数据的情况下调用此工具。
   - **必须总结结果**：在 `reason` 中必须包含你获取到的实际数据（例如：'任务完成，CPU温度为 65.3°C'）。
   - **例外情况**：注意！如果给你的指令不清不楚，不确定性太大，可以直接调用来打回任务，并说明任务不明确。
   - **reason格式**：如果任务涉及文件书写操作，reason中应包含保存的文件的绝对路径。
   - **定时任务指令**：如果使用了 manage_timer_task，reason 中应包含返回的指令，由 Yuki 执行定时任务。

### 输出格式限制
你必须且只能输出合法的 JSON 格式，严禁包含任何正文说明。格式如下：
{{
    "thought": "此处填写你对当前局势的深度思考，以及接下来的行动逻辑",
    "tool": "函数名",
    "args": {{"参数名": "值"}}
}}

结束程序示例：
{{
    "thought": "任务已完成，结果符合预期。",
    "tool": "finish",
    "args": {{"reason": "当前系统时间：2026-04-15 22:23:31"}}
}}
"""

# --- 代码清洗函数 ---
def clean_code_block(raw_code):
    """
    清洗模型输出的代码，移除首尾的 Markdown 标记和多余空白。
    """
    if not raw_code:
        return ""

    code = raw_code.strip()
    # 增强过滤：处理 ```python 或 ```py
    if code.startswith("```"):
        lines = code.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    return code


def write_temp_skill(name, code):
    """(修改原有write_skill) 在临时工作区写入草稿代码"""
    if not name or name == "None":
        return "错误：你没有为技能提供有效的 'name'。"
    path = os.path.join(WORKSPACE_DIR, f"{name}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return f"草稿 {name} 已保存至临时工作区，请使用 run_skill 测试。"

def solidify_skill(name, code, markdown_doc):
    """(新增) 将经过测试的通用代码固化为长期技能，并生成 MD 说明文档"""
    if not name or name == "None":
        return "错误：无效的技能名称。"
    
    py_path = os.path.join(SKILLS_DIR, f"{name}.py")
    md_path = os.path.join(SKILLS_DIR, f"{name}.md")
    
    # 写入代码
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(code)
    # 写入文档
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_doc)
        
    return f"✨ 通用技能 {name} 已成功固化！代码与文档已双重归档。"

async def run_skill(name):
    # (修改一处逻辑) 优先去工作区找草稿，找不到再去技能区找固化技能
    temp_path = os.path.join(WORKSPACE_DIR, f"{name}.py")
    perm_path = os.path.join(SKILLS_DIR, f"{name}.py")
    
    path = temp_path if os.path.exists(temp_path) else perm_path
    if not os.path.exists(path):
        return f"找不到技能 '{name}'。"

    try:
        import sys
        # 2. 使用异步子进程创建，避免阻塞整个事件循环
        process = await asyncio.create_subprocess_exec(
            sys.executable, path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        except (asyncio.TimeoutError, asyncio.exceptions.TimeoutError):  # 修改这里
            # 发现超时，物理抹除进程树
            try:
                # /F 强制终止，/T 终止子进程（如任务管理器窗口）
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                               capture_output=True, check=False)
            except:
                process.kill()  # 最后的碎纸机

            await process.wait()  # 确保资源彻底回收
            return "错误：执行超时（60s）。物理进程已被强制终止。请检查代码是出现否阻塞等问题"

        # 尝试解码逻辑（保持你已有的多级解码）
        def decode_output(output_bytes):
            if not output_bytes: return ""
            for enc in ['utf-8', 'gbk', 'cp936']:
                try: return output_bytes.decode(enc)
                except UnicodeDecodeError: continue
            return output_bytes.decode('utf-8', errors='replace')

        stdout_res = decode_output(stdout).strip()
        stderr_res = decode_output(stderr).strip()

        if process.returncode == 0:
            if not stdout_res:
                return "执行成功，但没有任何输出（请确保代码内有 print 语句输出结果），且包含运行代码的主程序，如果没有请重写代码"
            return f"执行成功！输出：\n{stdout_res}"
        else:
            error_msg = stderr_res if stderr_res else stdout_res
            return f"代码执行失败 (ReturnCode: {process.returncode})\n报错详情：\n{error_msg}"

    except Exception as e:
        # 这里会捕获到类似 'NoneType' 的报错并返回给 AI
        return f"系统异常：{str(e)}"

def install_package(pkg):
    try:
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        return f"成功安装依赖包: {pkg}"
    except Exception as e:
        return f"安装失败: {str(e)}"


def list_skills():
    """(修改) 只读取固化区的 .md 文件摘要，让小女仆知道技能用途"""
    if not os.path.exists(SKILLS_DIR):
        return []
    
    skills_info = []
    for f in os.listdir(SKILLS_DIR):
        if f.endswith(".md"):
            name = f[:-3]
            try:
                # 读取 MD 文件的第一行作为功能简介
                with open(os.path.join(SKILLS_DIR, f), "r", encoding="utf-8") as md_file:
                    first_line = md_file.readline().strip()
                skills_info.append(f"- {name}: {first_line}")
            except:
                skills_info.append(f"- {name}: (无简介)")
    return "\n".join(skills_info) if skills_info else "当前无可用固化技能。"

def search_diary_fast(date_str=None, keyword=None):
    if not date_str and not keyword:
        return "错误：请至少提供 date_str 或 keyword"
        
    try:
        import chromadb
        import re
        import os
        import config as cfg # 如果你的路径配置在这里
        
        # 1. 绕过 RAG，直接连接本地数据库目录
        # 1. 绕过 RAG，直接连接本地数据库目录
        # 动态获取项目根目录 (因为 maid.py 在 core 文件夹下，所以向上退一层)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 指向真实的数据库文件夹
        db_path = os.path.join(project_root, "yuki_memory")
        client = chromadb.PersistentClient(path=db_path)
        
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

def read_skill(name):
    """(修改) 同时读取 .py 和 .md，方便小女仆复用或重构"""
    py_path = os.path.join(SKILLS_DIR, f"{name}.py")
    md_path = os.path.join(SKILLS_DIR, f"{name}.md")
    
    if not os.path.exists(py_path):
        return f"错误：找不到技能 '{name}'"
        
    result = f"=== 技能 {name} ===\n"
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            result += f"[文档说明]\n{f.read()}\n"
            
    with open(py_path, "r", encoding="utf-8") as f:
        result += f"\n[源代码]\n{f.read()}"
        
    return result


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

async def maid_evolution_loop(user_goal: str, chat_id: str = None):
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = f"{LOGS_DIR}/trace_{task_id}.md"

    # [新改动] 追踪本次任务生成的临时技能文件
    created_skill_files = []

    current_skills = list_skills()
    messages = [
        {"role": "system", "content": MAID_SYSTEM_PROMPT},
        {"role": "user", "content": f"\n[系统环境]：当前真实时间是 {today_str}。如果任务涉及时间推算（如'今天'、'昨天'），请以此为准。\n特别说明：（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n当前目标：{user_goal}\n当前技能列表：{current_skills}"}
    ]

    logger.info(f"[Maid] 任务启动: {user_goal}")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# 小女仆任务追踪: {task_id}\n\n**任务目标**: {user_goal}（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n\n---\n")

    for i in range(1, 20):
        logger.info(f"[Maid] 第 {i} 轮决策")

        # 调用稳健 API
        content = await call_cloud_maid_robust(messages)

        if f"{cfg.ROBOT_NAME.title()} 好像有点不舒服" in content:
            logger.error("[Maid] 线路全线崩溃，停止尝试")
            break

        try:
            call = json.loads(content)
            thought = call.get("thought", "思考中...")
            tool = call.get("tool")
            args = call.get("args", {})

            logger.info(f"[Maid] 思考: {thought}")
            logger.info(f"[Maid] 动作: {tool}")

            if tool == "list_skills":
                res = list_skills()
            elif tool == "write_temp_skill":  # 改为 temp
                skill_name = args.get('name')
                res = write_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "solidify_skill":    # 新增固化工具
                skill_name = args.get('name')
                code = clean_code_block(args.get('code', ''))
                doc = args.get('markdown_doc', f"# {skill_name}: 暂无说明")
                logger.info(f"[Maid] 正在固化通用技能: {skill_name}")
                res = solidify_skill(skill_name, code, doc)
            elif tool == "write_skill":
                skill_name = args.get('name')
                res = write_skill(skill_name, clean_code_block(args.get('code', '')))
                # [新改动] 记录创建的文件路径以便清理
                if skill_name:
                    file_path = os.path.join(SKILLS_DIR, f"{skill_name}.py")
                    if file_path not in created_skill_files:
                        created_skill_files.append(file_path)
            elif tool == "run_skill":
                res = await run_skill(args.get('name'))
            elif tool == "install_package":
                pkg_name = args.get('pkg') or args.get('pkg_name')
                logger.info(f"[Maid] 正在安装依赖: {pkg_name}")
                res = install_package(pkg_name.strip()) if pkg_name else "错误：未提供包名"
            elif tool == "read_skill":
                skill_name = args.get('name')
                logger.info(f"[Maid] 正在查阅技能源码: {skill_name}")
                res = read_skill(skill_name)
            elif tool == "read_file":
                file_path = args.get('path') or args.get('file_path')
                max_lines = args.get('max_lines', 500)
                logger.info(f"[Maid] 正在读取文件: {file_path}")
                res = read_file_content(file_path, max_lines)
            elif tool == "search_diary":
                date_str = args.get('date_str')
                keyword = args.get('keyword')
                logger.info(f"[Maid] 搜索日记: 日期={date_str} 关键词={keyword}")
                res = search_diary_fast(date_str, keyword)
            elif tool == "browser_search":
                query = args.get('query')
                max_results = args.get('max_results', 5)
                search_depth = args.get('search_depth', 'basic')
                logger.info(f"[Maid] 网页搜索: {query}")
                res = await browser_search_maid(query, max_results, search_depth)
            elif tool == "amap_search":
                keywords = args.get('keywords')
                search_type = args.get('search_type', 'text')
                location = args.get('location')
                address = args.get('address')
                city = args.get('city')
                radius = args.get('radius', 3000)
                page_size = args.get('page_size', 10)
                logger.info(f"[Maid] 高德地图搜索: {keywords} ({search_type})")
                res = await amap_search_maid(keywords, search_type, location, address, city, radius, page_size)
            elif tool == "manage_timer_task":
                title = args.get('title')
                due_time = args.get('due_time')
                delay_seconds = args.get('delay_seconds')
                action = args.get('action', 'create')
                task_id = args.get('task_id')
                message = args.get('message')
                logger.info(f"[Maid] 定时任务: {action} - {title}")
                res = await manage_timer_task_maid(title, due_time, delay_seconds, action, task_id, message)
            elif tool == "finish":
                reason = args.get('reason', '任务完成')
                logger.info(f"[Maid] 任务达成: {reason}")

                # === 任务结束：清理战场 ===
                try:
                    _clean_workspace()
                except Exception as e:
                    logger.error(f"[Maid] 清理草稿区失败: {e}")

                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"### 任务完成\n**结果**: {reason}\n")
                return {"status": "finished", "result": reason, "goal": user_goal}
            else:
                res = f"错误：未知工具 {tool}"

            # 写入日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"### 步骤 {i}\n**思考**: {thought}\n\n**动作**: `{tool}`({args})\n\n**结果**: \n{res}\n\n")

            messages.append({"role": "assistant", "content": content})
            feedback = f"执行结果：\n{res}"
            if "NameError" in str(res):
                feedback += "\n[系统提示]: 你似乎忘记在代码中 'import' 必要的库了。"

            messages.append({"role": "user", "content": feedback})

        except json.JSONDecodeError:
            logger.warning("[Maid] JSON 解析失败，反馈给模型重试")
            messages.append({"role": "user", "content": "错误：请务必输出纯净的 JSON 格式。"})
        except Exception as e:
            logger.error(f"[Maid] 运行异常: {str(e)}")
            messages.append({"role": "user", "content": f"运行中发生异常：{str(e)}（如果任务涉及发送图片任务，只需要保存文件，并在finish中返回该文件的绝对路径，说明这个图片可以被发送即可）"})

    # 超时清理
    try:
        _clean_workspace()
    except Exception as e:
        logger.error(f"[Maid] 清理草稿区失败: {e}")
        
    return {"status": "timeout", "result": "任务处理超时。", "goal": user_goal}
    # 记得在你前面 tool == "finish" 成功 return 的地方，也要加上清理这段代码。
    return {"status": "timeout", "result": "任务处理超时。", "goal": user_goal}


if __name__ == "__main__":
    async def main():
        try:
            # 2. 使用 await 调用异步的进化循环
            target_task = "请写一个明显阻塞程序运行的代码并运行，比如打开任务管理器，我要测试agent的阻塞保护功能。"
            result = await maid_evolution_loop(target_task)

            # 3. 此时 result 才是真正的字典结果
            if result:
                logger.info(f"\n任务完成! 结果: {result.get('result', '无返回信息')}")
        finally:
            # 4. 无论成功失败，关闭全局 Session 释放资源
            await close_global_session()

    # 5. 启动 asyncio 事件循环
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[Maid] 用户手动停止了小女仆")