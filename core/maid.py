import json
import subprocess
import os
from datetime import datetime
import asyncio
import re
import aiohttp
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from network.api_request import ApiCall
from utils.logger import get_logger

logger = get_logger("maid")

# 初始化全局稳健客户端
# 它内部已经处理了主线与备线的切换逻辑
api_client = ApiCall(LLM_API_KEY, LLM_BASE_URL)


def clean_json_output(text):
    """提取第一个 { 到最后一个 } 之间的内容，防止模型输出废话"""
    if not text: return ""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    return match.group(0) if match else text.strip()


async def call_cloud_maid_robust(messages):
    """
    使用 ApiCall 的稳健逻辑：
    1. 尝试 TeaTop (低价)
    2. 失败则熔断并尝试 DeepSeek 官方 (稳健)
    """
    # 强制要求 JSON 格式输出
    payload_kwargs = {
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }

    # 直接调用你 api_request.py 里的核心函数
    result = await api_client.robust_api_call(
        messages=messages,
        model=LLM_MODEL,
        **payload_kwargs
    )

    # 清洗可能存在的 Markdown 标签
    return clean_json_output(result)
# --- 目录初始化 ---
SKILLS_DIR = "skills"
TASKS_DIR = "tasks"
LOGS_DIR = "logs"

for d in [SKILLS_DIR, TASKS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

MAID_SYSTEM_PROMPT = f"""
你是一个具备高度自主进化能力的 AI 智能体，代号：**小女仆**。

### 核心使命
通过编写、优化和复用 Python 技能（Skills）来完成用户指令。你不仅在解决问题，还在构建自己的"数字大脑"。

### 运行上下文
- **当前路径**: {os.getcwd()}
- **操作系统**: {os.name} (请确保编写的代码跨平台兼容)
- **技能存储**: 所有技能存放在 `/skills` 目录下，以 `.py` 结尾。

### 进化法则（行为规范）
1. **检索优先**: 面对任务，首先调用 `list_skills` 检查是否有现成或类似的技能。
2. **模块化编写**: 编写技能时，务必包含必要的 try-except 块，并确保输出结果易于被你解析。
3. **即写即用**: 严禁只写不练。调用 `write_skill` 后，必须紧跟一个 `run_skill` 来验证正确性。
4. **迭代优化**: 如果 `run_skill` 返回报错，请根据错误信息调用 `write_skill` 重写代码。
5. **环境自愈**: 如果 `run_skill` 报错 "ModuleNotFoundError"，必须调用 `install_package` 安装缺失的包。

### 工具箱（JSON 接口）
1. `list_skills()`: 返回当前已固化的技能列表。
2. `write_skill(name, code)`: 
   - 'name': 必须是一个简短的英文标识符（如 'get_memory'），严禁不填或填 None。
   - 'code': 完整的 Python 代码（直接写代码，不要加 ```python 标记），需要包含print()语句来输出你需要的数据信息。请务必书写主程序，以免定义了函数但没有被调用而返回None。
3. `run_skill(name)`: 执行技能并获取标准输出（stdout）。
4. `install_package(pkg)`: 安装缺失的 pip 包。
5. `finish(reason)`: 
   - **禁止盲目结束**：严禁在没有看到成功结果或输出的具体数据的情况下调用此工具。
   - **必须总结结果**：在 `reason` 中必须包含你获取到的实际数据（例如：'任务完成，CPU温度为 65.3°C'）。

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


# --- 直接复用你 maid.py 的工具函数 ---
def write_skill(name, code):
    if not name or name == "None":
        return "错误：你没有为技能提供有效的 'name'。"
    path = f"skills/{name}.py"
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return f"技能 {name} 已保存。"


def run_skill(name):
    path = os.path.join(SKILLS_DIR, f"{name}.py")
    if not os.path.exists(path):
        available = os.listdir(SKILLS_DIR)
        return f"找不到技能 '{name}'，当前可用技能: {available}"

    try:
        import sys
        # 修改点 1：增加 errors='replace' 防止编码错误导致线程崩溃
        # 修改点 2：明确指定 encoding='utf-8'
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=20
        )

        # 修改点 3：增加对 None 的安全检查
        stdout_res = (result.stdout or "").strip()
        stderr_res = (result.stderr or "").strip()

        if result.returncode == 0:
            if not stdout_res:
                return "执行成功，但没有任何输出（请确保代码内有 print 语句输出结果），且包含运行代码的主程序，如果没有请重写代码"
            return f"执行成功！输出：\n{stdout_res}"
        else:
            error_msg = stderr_res if stderr_res else stdout_res
            return f"代码执行失败 (ReturnCode: {result.returncode})\n报错详情：\n{error_msg}"

    except subprocess.TimeoutExpired:
        return "错误：执行超时（20s）。"
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
    return os.listdir("skills") if os.path.exists("skills") else []


async def maid_evolution_loop(user_goal: str, chat_id: str = None):
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{LOGS_DIR}/trace_{task_id}.md"

    # [新改动] 追踪本次任务生成的临时技能文件
    created_skill_files = []

    current_skills = list_skills()
    messages = [
        {"role": "system", "content": MAID_SYSTEM_PROMPT},
        {"role": "user", "content": f"目标：{user_goal}\n当前技能：{current_skills}"}
    ]

    logger.info(f"[Maid] 🚀 任务启动: {user_goal}")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# 小女仆任务追踪: {task_id}\n\n**任务目标**: {user_goal}（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可）\n\n---\n")

    for i in range(1, 20):
        logger.info(f"[Maid] 🔍 第 {i} 轮决策中...")

        # 调用稳健 API
        content = await call_cloud_maid_robust(messages)

        if "Yuki 好像有点不舒服" in content:
            logger.error("[Maid] ❌ 线路全线崩溃，停止尝试。")
            break

        try:
            call = json.loads(content)
            thought = call.get("thought", "思考中...")
            tool = call.get("tool")
            args = call.get("args", {})

            logger.info(f"[Maid] 💭 思考: {thought}")
            logger.info(f"[Maid] 🛠️  动作: {tool}")

            if tool == "list_skills":
                res = list_skills()
            elif tool == "write_skill":
                skill_name = args.get('name')
                res = write_skill(skill_name, clean_code_block(args.get('code', '')))
                # [新改动] 记录创建的文件路径以便清理
                if skill_name:
                    file_path = os.path.join(SKILLS_DIR, f"{skill_name}.py")
                    if file_path not in created_skill_files:
                        created_skill_files.append(file_path)
            elif tool == "run_skill":
                res = run_skill(args.get('name'))
            elif tool == "install_package":
                pkg_name = args.get('pkg') or args.get('pkg_name')
                logger.info(f"[Maid] 📦 正在安装依赖: {pkg_name}")
                res = install_package(pkg_name.strip()) if pkg_name else "错误：未提供包名"
            elif tool == "finish":
                reason = args.get('reason', '任务完成')
                logger.info(f"[Maid] ✅ 任务达成: {reason}")

                # --- [新改动] 自动清理逻辑 ---
                for path in created_skill_files:
                    if os.path.exists(path):
                        os.remove(path)
                logger.info(f"[Maid] 🧹 已清理 {len(created_skill_files)} 个临时技能文件。")
                # -------------------------

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
            logger.warning("[Maid] ⚠️ JSON 解析失败，正在反馈给模型重试...")
            messages.append({"role": "user", "content": "错误：请务必输出纯净的 JSON 格式。"})
        except Exception as e:
            logger.error(f"[Maid] 🧨 运行异常: {str(e)}")
            messages.append({"role": "user", "content": f"运行中发生异常：{str(e)}（如果任务涉及发送图片任务，只需要保存文件，并在finish中返回该文件的绝对路径，说明这个图片可以被发送即可）"})

    # 超时清理
    for path in created_skill_files:
        if os.path.exists(path): os.remove(path)
    return {"status": "timeout", "result": "任务处理超时。", "goal": user_goal}


if __name__ == "__main__":
    # 1. 确保在程序结束时关闭 api_request 里的 Session
    async def main():
        try:
            # 2. 使用 await 调用异步的进化循环
            target_task = "输出系统时间"
            result = await maid_evolution_loop(target_task)

            # 3. 此时 result 才是真正的字典结果
            if result:
                logger.info(f"\n✅ 任务完成！结果: {result.get('result', '无返回信息')}")
        finally:
            # 4. 无论成功失败，关闭连接池释放资源
            await ApiCall.close()


    # 5. 启动 asyncio 事件循环
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[System] 用户手动停止了小女仆。")