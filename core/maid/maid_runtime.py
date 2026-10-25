import ast
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import venv

from core.maid.maid_approval import classify_command
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


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SKILL_DEFAULT_TIMEOUT = 120
SKILL_MAX_TIMEOUT = 600


def _normalize_skill_timeout(timeout) -> int:
    try:
        timeout = int(timeout or SKILL_DEFAULT_TIMEOUT)
    except Exception:
        timeout = SKILL_DEFAULT_TIMEOUT
    return max(5, min(timeout, SKILL_MAX_TIMEOUT))


def _normalize_interpreter(interpreter) -> str:
    """yuki：用主进程解释器（项目依赖齐全）；maid：用隔离的 maid_venv。"""
    return "yuki" if str(interpreter or "").strip().lower() in {"yuki", "main", "system"} else "maid"


def _get_maid_python_exec() -> str:
    """获取小女仆专属虚拟环境的 Python 执行路径。"""
    if os.name == 'nt':
        return os.path.join(MAID_VENV_DIR, "Scripts", "python.exe")
    return os.path.join(MAID_VENV_DIR, "bin", "python")


def _get_maid_pip_cmd(python_exec: str) -> list:
    """统一用 `python -m pip` 调用 pip。

    虚拟环境被搬迁/重建后 bin/pip 脚本里的 shebang 常指向已不存在的解释器，
    直接执行会报 `[Errno 2] No such file or directory`，走模块方式可绕开。
    """
    return [python_exec, "-m", "pip"]


def _check_venv_home(venv_dir: str) -> str:
    """检查 pyvenv.cfg 里记录的 base 解释器目录是否还存在（环境被搬迁时会失效）。"""
    cfg_path = os.path.join(venv_dir, "pyvenv.cfg")
    if not os.path.exists(cfg_path):
        return "缺少 pyvenv.cfg"
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep and key.strip().lower() == "home":
                    home = value.strip()
                    if home and not os.path.isdir(home):
                        return f"pyvenv.cfg 中的 home 目录不存在：{home}"
                    return ""
    except Exception as e:
        return f"读取 pyvenv.cfg 失败：{e}"
    return ""


def _new_session_kwargs() -> dict:
    """POSIX 下让子进程独立成进程组，便于超时时整组终止；Windows 不接受该参数。"""
    return {"start_new_session": True} if os.name != "nt" else {}


def _handle_rmtree_error(func, path, exc_info) -> None:
    """处理 Windows 虚拟环境只读文件或权限残留导致的删除失败。"""
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception as e:
        logger.warning(f"[Maid] 删除虚拟环境残留失败: {path}, {e}")


async def _is_maid_env_usable(python_exec: str) -> tuple[bool, str]:
    """确认虚拟环境解释器真实可用。

    不能用 `python --version` 判断：标准库缺失（如 encodings 找不到）时它照样返回 0，
    必须实际导入模块触发解释器完整初始化。
    """
    if not os.path.exists(python_exec):
        return False, "未找到 Python 执行文件"

    home_problem = _check_venv_home(MAID_VENV_DIR)
    if home_problem:
        return False, home_problem

    try:
        process = await asyncio.create_subprocess_exec(
            python_exec, "-c", "import encodings, sys; sys.stdout.write(sys.prefix)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **(_new_session_kwargs()),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except Exception as e:
        return False, str(e)

    if process.returncode != 0:
        output = _decode_process_output(stderr or stdout).strip()
        detail = output.splitlines()[0] if output else f"返回码 {process.returncode}"
        return False, f"解释器无法启动：{detail}"

    stdout, _ = await _run_pip(python_exec, ["--version"])
    if "pip" not in stdout.lower():
        return False, "环境中缺少可用 pip"
    return True, stdout.strip().splitlines()[0] if stdout.strip() else "ok"


async def _run_pip(python_exec: str, args: list) -> tuple[str, str]:
    """用 `python -m pip` 执行 pip 命令，避免依赖可能已失效的 bin/pip 脚本。"""
    if isinstance(args, str):
        args = [args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *_get_maid_pip_cmd(python_exec), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return _decode_process_output(stdout), _decode_process_output(stderr)
    except Exception as e:
        return "", str(e)


async def _create_maid_env() -> None:
    logger.info("[Maid] 正在创建专属虚拟环境 (初次创建可能需要几秒钟)...")
    await asyncio.to_thread(venv.create, MAID_VENV_DIR, with_pip=True)
    logger.info("[Maid] 专属虚拟环境创建完毕。")


async def _repair_maid_pip(python_exec: str) -> bool:
    """install_package 前的兜底：环境能跑但缺 pip 时用 ensurepip 补一下。"""
    stdout, _ = await _run_pip(python_exec, ["--version"])
    if "pip" in stdout.lower():
        return True
    logger.warning("[Maid] 环境中缺少 pip，尝试 ensurepip 修复...")
    try:
        proc = await asyncio.create_subprocess_exec(
            python_exec, "-m", "ensurepip", "--upgrade",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"[Maid] ensurepip 失败: {e}")
    stdout, _ = await _run_pip(python_exec, ["--version"])
    return "pip" in stdout.lower()


async def _rebuild_maid_env(reason: str) -> None:
    logger.warning(f"[Maid] 检测到虚拟环境不可用，将重建：{reason}")
    if os.path.exists(MAID_VENV_DIR):
        await asyncio.to_thread(shutil.rmtree, MAID_VENV_DIR, onerror=_handle_rmtree_error)
    await _create_maid_env()


def _read_venv_version(venv_dir: str) -> str:
    """读取 pyvenv.cfg 记录的 Python 版本，用于判断能否原地升级修复。"""
    cfg_path = os.path.join(venv_dir, "pyvenv.cfg")
    if not os.path.exists(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep and key.strip().lower() == "version":
                    return value.strip()
    except Exception:
        return ""
    return ""


async def _upgrade_maid_env(reason: str) -> bool:
    """原地修复：重新生成 bin/ 与 pyvenv.cfg，保留已安装的 site-packages。

    典型场景是环境从别的机器/路径拷来，pyvenv.cfg 里的 home 失效、bin/pip 的 shebang
    指向不存在的解释器。只有 Python 版本一致时才能复用旧包，否则直接重建。
    """
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    venv_version = _read_venv_version(MAID_VENV_DIR)
    if not venv_version.startswith(current):
        return False

    logger.warning(f"[Maid] 尝试原地修复虚拟环境（保留已装依赖）：{reason}")
    try:
        await asyncio.to_thread(
            venv.EnvBuilder(with_pip=True, upgrade=True, clear=False).create,
            MAID_VENV_DIR,
        )
    except Exception as e:
        logger.warning(f"[Maid] 原地修复失败: {e}")
        return False

    usable, why = await _is_maid_env_usable(_get_maid_python_exec())
    if not usable:
        logger.warning(f"[Maid] 原地修复后环境仍不可用: {why}")
        return False
    logger.info("[Maid] 虚拟环境原地修复完成，已安装依赖保持不变。")
    return True


_maid_env_ready = False


async def _ensure_maid_env() -> str:
    """获取小女仆专属虚拟环境的 Python 执行路径。如果不存在或损坏则自动创建。"""
    global _maid_env_ready
    python_exec = _get_maid_python_exec()

    # 本次进程内已确认可用就不再重复起子进程自检（每次约 1s）
    if _maid_env_ready and os.path.exists(python_exec):
        return python_exec

    if not os.path.exists(python_exec):
        logger.info("[Maid] 检测到无虚拟环境。")
        await _create_maid_env()
    else:
        usable, reason = await _is_maid_env_usable(python_exec)
        if not usable:
            if not await _upgrade_maid_env(reason):
                await _rebuild_maid_env(reason)
        elif not await _repair_maid_pip(python_exec):
            await _rebuild_maid_env("环境中没有可用的 pip")

    _maid_env_ready = True
    return python_exec


_pip_list_cache = {}


async def _get_installed_packages(python_exec: str) -> set:
    """缓存已安装包列表，避免每次跑脚本都花 0.7s 调 pip list。"""
    cached = _pip_list_cache.get(python_exec)
    if cached is not None:
        return cached

    pip_list_out, pip_list_err = await _run_pip(python_exec, ["list", "--format=json"])
    try:
        installed = {item["name"].lower() for item in json.loads(pip_list_out or "[]")}
    except Exception:
        installed = set()
        if pip_list_err.strip():
            logger.warning(f"[Maid] 无法读取环境已安装包列表: {pip_list_err.strip().splitlines()[-1]}")
    _pip_list_cache[python_exec] = installed
    return installed


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

    installed_pkgs = set(await _get_installed_packages(python_exec))

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
            _, install_err = await asyncio.wait_for(
                _run_pip(python_exec, ["install", *to_install]), timeout=180
            )
            if "error" in install_err.lower():
                logger.warning(f"[Maid] 依赖安装可能失败: {install_err.strip().splitlines()[-1]}")
            else:
                installed_pkgs.update(name.lower() for name in to_install)
                _pip_list_cache[python_exec] = installed_pkgs
        except asyncio.TimeoutError:
            logger.warning("[Maid] 自动安装依赖超时（180s），跳过")
        except Exception as e:
            logger.error(f"[Maid] 自动安装依赖异常: {e}")


async def _kill_process_tree(process) -> None:
    """终止整个进程树。Windows 用 taskkill /T；POSIX 用进程组整组 SIGKILL。"""
    if process.returncode is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass
    else:
        # 子进程以 start_new_session 启动，属于独立进程组，可安全整组终止
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    try:
        await process.wait()
    except Exception:
        pass


def _is_terminal_command_allowed(command: str, allow_write: bool = True) -> tuple[bool, str]:
    """兼容旧接口的判定：只返回硬拦截结果；可疑命令交由 approver 静默判定。"""
    verdict, reason = classify_command(command)
    if verdict == "block":
        return False, f"命令被硬拦截：{reason}"
    return True, ""


async def terminal_command_maid(
    command: str,
    cwd: str = None,
    timeout: int = TERMINAL_DEFAULT_TIMEOUT,
    allow_write: bool = True,
    approver=None,
    thought: str = "",
) -> str:
    """
    终端工具：用于查看环境、运行短命令、执行项目脚本。

    硬拦截只针对不可逆命令；命中启发式可疑规则时先交给 approver（Yuki）静默判定，
    没有 approver 的调用路径直接放行，避免 CLI 调试被卡住。
    """
    verdict, reason = classify_command(command)
    if verdict == "block":
        return json.dumps({"ok": False, "error": f"终端命令被安全网拦截：{reason}", "command": command}, ensure_ascii=False)

    try:
        timeout = int(timeout or TERMINAL_DEFAULT_TIMEOUT)
    except Exception:
        timeout = TERMINAL_DEFAULT_TIMEOUT
    timeout = max(1, min(timeout, TERMINAL_MAX_TIMEOUT))

    workdir = os.path.abspath(cwd or os.getcwd())
    if not os.path.exists(workdir) or not os.path.isdir(workdir):
        return json.dumps({"ok": False, "error": f"cwd 不存在或不是目录：{workdir}"}, ensure_ascii=False)

    if verdict == "ask":
        if approver is None:
            logger.info(f"[Maid] 可疑命令无 approver，直接放行：{command}")
        else:
            try:
                approved, why = await approver(command, workdir, thought)
            except Exception as e:
                approved, why = False, f"授权判定异常：{e}"
            if not approved:
                logger.warning(f"[Maid] 命令未获授权：{command}（{why}）")
                return json.dumps({
                    "ok": False,
                    "error": f"命令未获授权，未执行：{why}",
                    "command": command,
                    "approval": "denied",
                }, ensure_ascii=False)
            logger.info(f"[Maid] 命令获授权：{command}（{why}）")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **(_new_session_kwargs()),
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


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
IMAGE_MAX_BYTES = 15 * 1024 * 1024
IMAGE_MAX_SIDE = 768
IMAGE_JPEG_QUALITY = 70


def _read_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _compress_image_b64(data: bytes) -> str:
    """复用视觉管线的压缩逻辑；依赖缺失或解析失败时返回空串。"""
    try:
        from modules.vision.processor import MemeProcessor
    except Exception as e:
        logger.warning(f"[Maid] 无法加载图片压缩器: {e}")
        return ""
    try:
        return MemeProcessor.compress_image(data, max_size=IMAGE_MAX_SIDE, quality=IMAGE_JPEG_QUALITY) or ""
    except Exception as e:
        logger.warning(f"[Maid] 图片压缩失败: {e}")
        return ""


async def prepare_image_message(path, question=None):
    """读取本地图片并压成原生图块，返回 (工具结果文本, 带图消息)。"""
    if not path:
        return "错误：未提供图片路径", None

    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return f"错误：图片不存在 '{abs_path}'", None
    if os.path.isdir(abs_path):
        return f"错误：'{abs_path}' 是目录", None

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return f"错误：'{ext or '(无扩展名)'}' 不是支持的图片格式（支持 {', '.join(sorted(IMAGE_EXTENSIONS))}）", None

    file_size = os.path.getsize(abs_path)
    if file_size > IMAGE_MAX_BYTES:
        return f"错误：图片过大（{file_size / 1024 / 1024:.1f} MB），上限 {IMAGE_MAX_BYTES // 1024 // 1024} MB", None
    if file_size == 0:
        return f"错误：图片 '{abs_path}' 是空文件", None

    try:
        data = await asyncio.to_thread(_read_image_bytes, abs_path)
        b64_data = await asyncio.to_thread(_compress_image_b64, data)
    except Exception as e:
        return f"错误：读取图片失败 - {e}", None

    if not b64_data:
        return f"错误：无法解析图片 '{abs_path}'（压缩失败，可能不是有效图片）", None

    prompt = (question or "").strip() or "请查看这张图片，说明画面内容；如有文字请转写。"
    image_message = {
        "role": "user",
        "content": [
            {"type": "text", "text": f"[图片 {os.path.basename(abs_path)}] {prompt}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
        ],
    }
    return (
        f"已读取图片 {os.path.basename(abs_path)}（{file_size / 1024:.1f} KB），"
        f"图片已附在这条消息里，请直接查看后再回答。",
        image_message,
    )


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


async def write_and_run_temp_skill(name, code, timeout=SKILL_DEFAULT_TIMEOUT, interpreter="maid"):
    """写入临时技能并立即执行，减少 write_temp_skill -> run_skill 两轮决策浪费。"""
    write_res = write_temp_skill(name, code)
    if write_res.startswith("错误"):
        return write_res
    run_res = await run_skill(name, timeout=timeout, interpreter=interpreter)
    return f"{write_res}\n\n=== 立即执行结果 ===\n{run_res}"


async def run_skill(name, timeout=SKILL_DEFAULT_TIMEOUT, interpreter="maid"):
    # (修改一处逻辑) 优先去工作区找草稿，找不到再去技能区找固化技能
    temp_path = os.path.join(WORKSPACE_DIR, f"{name}.py")
    perm_path = os.path.join(SKILLS_DIR, f"{name}.py")

    path = temp_path if os.path.exists(temp_path) else perm_path
    if not os.path.exists(path):
        return f"找不到技能 '{name}'。"

    timeout = _normalize_skill_timeout(timeout)
    interpreter = _normalize_interpreter(interpreter)

    try:
        if interpreter == "yuki":
            python_exec = sys.executable or "python"
        else:
            python_exec = await _ensure_maid_env()
            await _ensure_skill_deps(path, python_exec)

        # 2. 使用异步子进程创建，避免阻塞整个事件循环
        # 草稿脚本位于 workspace/，sys.path[0] 是它自己所在目录；把项目根塞进
        # PYTHONPATH，模型才能直接 import config / utils / core 这些项目模块。
        child_env = os.environ.copy()
        existing = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = PROJECT_ROOT + (os.pathsep + existing if existing else "")

        process = await asyncio.create_subprocess_exec(
            python_exec, path,
            cwd=PROJECT_ROOT,
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **(_new_session_kwargs()),
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.exceptions.TimeoutError):
            # 超时则物理抹除整个进程树
            await _kill_process_tree(process)
            return (
                f"错误：执行超时（{timeout}s）。物理进程已被强制终止。"
                f"若任务本身更慢，请在 args 里提高 'timeout'（上限 {SKILL_MAX_TIMEOUT}s）。"
            )

        stdout_res = _decode_process_output(stdout).strip()
        stderr_res = _decode_process_output(stderr).strip()

        if process.returncode == 0:
            if not stdout_res and not stderr_res:
                return "执行成功，但没有任何输出（请确保代码内有 print 语句输出结果），且包含运行代码的主程序，如果没有请重写代码"
            parts = [f"执行成功！输出：\n{stdout_res or '(无 stdout)'}"]
            if stderr_res:
                parts.append(f"[stderr]\n{stderr_res}")
            return "\n\n".join(parts)
        else:
            error_msg = stderr_res if stderr_res else stdout_res
            tail_lines = error_msg.splitlines()[-40:]
            return (
                f"代码执行失败 (ReturnCode: {process.returncode})\n"
                f"报错详情（末 {len(tail_lines)} 行）：\n" + "\n".join(tail_lines)
            )

    except Exception as e:
        # 这里会捕获到类似 'NoneType' 的报错并返回给 AI
        return f"系统异常：{str(e)}"


async def install_package(pkg):
    try:
        python_exec = await _ensure_maid_env()
        if not await _repair_maid_pip(python_exec):
            return "安装异常: 专属虚拟环境中没有可用的 pip（自动修复失败）"

        check_stdout, _ = await _run_pip(python_exec, ["show", pkg])
        if check_stdout.strip():
            return f"成功：依赖包 {pkg} 已经安装过，无需重复安装。"

        stdout, stderr = await _run_pip(python_exec, ["install", pkg])
        if "error" not in stderr.lower() and stdout.strip():
            return f"成功安装依赖包: {pkg}"
        return f"安装失败: {stderr or stdout}"
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
