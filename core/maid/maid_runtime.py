import ast
import asyncio
import json
import os
import shutil
import subprocess
import sys
import venv

from core.maid.maid_common import (
    MAID_VENV_DIR,
    SKILLS_DIR,
    TERMINAL_DEFAULT_TIMEOUT,
    TERMINAL_MAX_TIMEOUT,
    WORKSPACE_DIR,
    _decode_process_output,
    _truncate_text,
    logger,
)


def _get_maid_python_exec() -> str:
    """获取小女仆专属虚拟环境的 Python 执行路径。"""
    if os.name == 'nt':
        return os.path.join(MAID_VENV_DIR, "Scripts", "python.exe")
    return os.path.join(MAID_VENV_DIR, "bin", "python")


def _handle_rmtree_error(func, path, exc_info) -> None:
    """处理 Windows 虚拟环境只读文件或权限残留导致的删除失败。"""
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception as e:
        logger.warning(f"[Maid] 删除虚拟环境残留失败: {path}, {e}")


async def _is_maid_env_usable(python_exec: str) -> tuple[bool, str]:
    """确认虚拟环境解释器真实可启动，避免保留已失效的旧环境。"""
    if not os.path.exists(python_exec):
        return False, "未找到 Python 执行文件"

    try:
        process = await asyncio.create_subprocess_exec(
            python_exec, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    except Exception as e:
        return False, str(e)

    output = _decode_process_output(stdout or stderr).strip()
    if process.returncode != 0:
        return False, output or f"python --version 返回 {process.returncode}"
    return True, output


async def _create_maid_env() -> None:
    logger.info("[Maid] 正在创建专属虚拟环境 (初次创建可能需要几秒钟)...")
    await asyncio.to_thread(venv.create, MAID_VENV_DIR, with_pip=True)
    logger.info("[Maid] 专属虚拟环境创建完毕。")


async def _rebuild_maid_env(reason: str) -> None:
    logger.warning(f"[Maid] 检测到虚拟环境不可用，将重建：{reason}")
    if os.path.exists(MAID_VENV_DIR):
        await asyncio.to_thread(shutil.rmtree, MAID_VENV_DIR, onerror=_handle_rmtree_error)
    await _create_maid_env()


async def _ensure_maid_env() -> str:
    """获取小女仆专属虚拟环境的 Python 执行路径。如果不存在或损坏则自动创建。"""
    python_exec = _get_maid_python_exec()

    if not os.path.exists(python_exec):
        logger.info("[Maid] 检测到无虚拟环境。")
        await _create_maid_env()
    else:
        usable, reason = await _is_maid_env_usable(python_exec)
        if not usable:
            await _rebuild_maid_env(reason)

    return python_exec


async def _ensure_skill_deps(script_path: str, python_exec: str):
    """解析脚本依赖，自动安装缺失的包。安装过的直接跳过。"""
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code)
    except Exception as e:
        logger.debug(f"[Maid] 解析脚本依赖跳过: {e}")
        return

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])

    if hasattr(sys, "stdlib_module_names"):
        stdlib = set(sys.stdlib_module_names)
    else:
        stdlib = {"os", "sys", "time", "re", "json", "asyncio", "datetime", "subprocess", "shutil", "pathlib", "math", "random"}

    third_party = imports - stdlib
    if not third_party:
        return

    pip_exec = os.path.join(os.path.dirname(python_exec), "pip.exe" if os.name == 'nt' else "pip")

    try:
        proc = await asyncio.create_subprocess_exec(
            pip_exec, "list", "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            installed_pkgs = {item["name"].lower() for item in json.loads(stdout.decode('utf-8'))}
        else:
            installed_pkgs = set()
    except Exception:
        installed_pkgs = set()

    aliases = {"cv2": "opencv-python", "bs4": "beautifulsoup4", "pil": "pillow", "yaml": "pyyaml"}

    to_install = []
    for pkg in third_party:
        pkg_lower = pkg.lower()
        install_name = aliases.get(pkg_lower, pkg_lower)
        if install_name not in installed_pkgs:
            to_install.append(install_name)

    if to_install:
        logger.info(f"[Maid] 自动为脚本补充安装环境依赖: {to_install}")
        try:
            install_proc = await asyncio.create_subprocess_exec(
                pip_exec, "install", *to_install,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await install_proc.communicate()
        except Exception as e:
            logger.error(f"[Maid] 自动安装依赖异常: {e}")


async def _kill_process_tree(process) -> None:
    """Windows 下优先 taskkill /T，失败再 kill 当前进程。"""
    if process.returncode is not None:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    except Exception:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await process.wait()
    except Exception:
        pass


def _is_terminal_command_allowed(command: str, allow_write: bool = False) -> tuple[bool, str]:
    """小女仆终端的轻量安全网。外层还有 LLM 把关，这里只拦明显危险命令。"""
    cmd = (command or "").strip()
    if not cmd:
        return False, "命令为空"
    lowered = cmd.lower()

    blocked_keywords = [
        "format ", "format.com", "shutdown", "restart-computer", "stop-computer",
        "bcdedit", "diskpart", "reg delete", "reg add", "takeown", "icacls",
        "cipher /w", "taskkill /f", "del /f /s /q c:", "rmdir /s /q c:",
        "rm -rf /", "rm -rf /*", ":(){:|:&};:",
    ]
    for keyword in blocked_keywords:
        if keyword in lowered:
            return False, f"命令包含高风险片段：{keyword}"

    if not allow_write:
        write_patterns = [
            ">", ">>", " del ", " erase ", " rmdir ", " rd ", "rm ", "mv ", "move ",
            "copy ", "xcopy ", "robocopy ", "mkdir ", "md ", "ren ", "rename ",
            "pip install", "npm install", "pnpm install", "yarn add", "cargo install",
            "git commit", "git push", "git reset", "git clean",
        ]
        padded = f" {lowered} "
        for pattern in write_patterns:
            if pattern in padded or pattern in lowered:
                return False, f"该命令疑似会修改系统/文件/依赖：{pattern.strip()}。如任务确实需要，请用 allow_write=true。"

    return True, ""


async def terminal_command_maid(command: str, cwd: str = None, timeout: int = TERMINAL_DEFAULT_TIMEOUT, allow_write: bool = True) -> str:
    """
    受限终端工具：用于查看环境、运行短命令、执行项目脚本。
    默认允许常规文件写入、依赖安装和 git 操作；仍会拦截明显危险命令。
    """
    allowed, reason = _is_terminal_command_allowed(command, allow_write=allow_write)
    if not allowed:
        return json.dumps({"ok": False, "error": f"终端命令被安全网拦截：{reason}", "command": command}, ensure_ascii=False)

    try:
        timeout = int(timeout or TERMINAL_DEFAULT_TIMEOUT)
    except Exception:
        timeout = TERMINAL_DEFAULT_TIMEOUT
    timeout = max(1, min(timeout, TERMINAL_MAX_TIMEOUT))

    workdir = os.path.abspath(cwd or os.getcwd())
    if not os.path.exists(workdir) or not os.path.isdir(workdir):
        return json.dumps({"ok": False, "error": f"cwd 不存在或不是目录：{workdir}"}, ensure_ascii=False)

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _kill_process_tree(process)
            return json.dumps({"ok": False, "error": f"终端命令超时 ({timeout}s)，进程已终止", "command": command, "cwd": workdir}, ensure_ascii=False)

        stdout_text = _truncate_text(_decode_process_output(stdout).strip())
        stderr_text = _truncate_text(_decode_process_output(stderr).strip())
        return json.dumps({
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "cwd": workdir,
            "command": command,
            "stdout": stdout_text,
            "stderr": stderr_text,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"终端执行异常：{str(e)}", "command": command}, ensure_ascii=False)


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


def write_temp_skill(name, code):
    """(修改原有write_skill) 在临时工作区写入草稿代码"""
    if not name or name == "None":
        return "错误：你没有为技能提供有效的 'name'。"
    path = os.path.join(WORKSPACE_DIR, f"{name}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return f"草稿 {name} 已保存至临时工作区。若要立即验证，优先使用 write_and_run_temp_skill 一步完成。"


async def write_and_run_temp_skill(name, code):
    """写入临时技能并立即执行，减少 write_temp_skill -> run_skill 两轮决策浪费。"""
    write_res = write_temp_skill(name, code)
    if write_res.startswith("错误"):
        return write_res
    run_res = await run_skill(name)
    return f"{write_res}\n\n=== 立即执行结果 ===\n{run_res}"


async def run_skill(name):
    # (修改一处逻辑) 优先去工作区找草稿，找不到再去技能区找固化技能
    temp_path = os.path.join(WORKSPACE_DIR, f"{name}.py")
    perm_path = os.path.join(SKILLS_DIR, f"{name}.py")

    path = temp_path if os.path.exists(temp_path) else perm_path
    if not os.path.exists(path):
        return f"找不到技能 '{name}'。"

    try:
        import sys
        python_exec = await _ensure_maid_env()
        await _ensure_skill_deps(path, python_exec)

        # 2. 使用异步子进程创建，避免阻塞整个事件循环
        process = await asyncio.create_subprocess_exec(
            python_exec, path,
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

        stdout_res = _decode_process_output(stdout).strip()
        stderr_res = _decode_process_output(stderr).strip()

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


async def install_package(pkg):
    try:
        python_exec = await _ensure_maid_env()
        pip_exec = os.path.join(os.path.dirname(python_exec), "pip.exe" if os.name == 'nt' else "pip")

        check_proc = await asyncio.create_subprocess_exec(
            pip_exec, "show", pkg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await check_proc.communicate()
        if check_proc.returncode == 0:
            return f"成功：依赖包 {pkg} 已经安装过，无需重复安装。"

        install_proc = await asyncio.create_subprocess_exec(
            pip_exec, "install", pkg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await install_proc.communicate()

        if install_proc.returncode == 0:
            return f"成功安装依赖包: {pkg}"
        else:
            return f"安装失败: {_decode_process_output(stderr)}"
    except Exception as e:
        return f"安装异常: {str(e)}"


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


def read_skill(name):
    """读取技能文档和源码。允许只有 .md 的说明型技能存在。"""
    py_path = os.path.join(SKILLS_DIR, f"{name}.py")
    md_path = os.path.join(SKILLS_DIR, f"{name}.md")

    if not os.path.exists(py_path) and not os.path.exists(md_path):
        return f"错误：找不到技能 '{name}'"

    result = f"=== 技能 {name} ===\n"
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            result += f"[文档说明]\n{f.read()}\n"
    if os.path.exists(py_path):
        with open(py_path, "r", encoding="utf-8") as f:
            result += f"\n[源代码]\n{f.read()}"

    return result
