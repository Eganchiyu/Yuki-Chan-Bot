#!/usr/bin/env python3
"""
Yuki (FrostFrame) 一键部署与环境配置工具

支持两种运行方式：
1. 人类交互式向导（默认）：
   python setup.py

2. Agent / 自动化非交互式部署：
   python setup.py --non-interactive \
     --llm-api-key "sk-xxx" \
     --bot-qq 123456789 \
     --master-qq 987654321 \
     --groups "11111111,22222222"

3. 环境与配置健康自检（支持 --json 供 Agent 解析）：
   python setup.py --check
   python setup.py --check --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "config.yaml")
BLACKLIST_PATH = os.path.join(PROJECT_ROOT, "blacklist.txt")
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "text2vec-base-chinese")

REQUIRED_DIRS = [
    "models",
    "data",
    "yuki_memory",
    "logs",
    "configs",
    "output",
    "skills",
    "staging",
    "tasks",
    "workspace",
    "memo",
]

CORE_IMPORTS = [
    ("yaml", "pyyaml"),
    ("aiohttp", "aiohttp"),
    ("websockets", "websockets"),
    ("chromadb", "chromadb"),
    ("sentence_transformers", "sentence-transformers"),
    ("jieba", "jieba"),
    ("PIL", "pillow"),
]


# ==================== 基础工具函数 ====================

def _get_nested(data: dict, path: Tuple[str, ...], default: Any = None) -> Any:
    """按路径从嵌套字典取值。"""
    curr: Any = data
    for k in path:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            return default
    return curr


def _set_nested(data: dict, path: Tuple[str, ...], value: Any) -> None:
    """按路径向嵌套字典写值。"""
    curr = data
    for key in path[:-1]:
        if key not in curr or not isinstance(curr[key], dict):
            curr[key] = {}
        curr = curr[key]
    curr[path[-1]] = value


def _parse_scalar_or_list(raw: str) -> Any:
    """将 CLI --set 传入的字符串自动转换为 bool / int / float / list / str。"""
    val = raw.strip()
    low = val.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none"):
        return None
    if val.startswith("[") and val.endswith("]"):
        try:
            return json.loads(val)
        except Exception:
            inner = val[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar_or_list(x) for x in inner.split(",") if x.strip()]
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val.strip("'\"")


def _parse_int_list(raw: str) -> List[int]:
    """解析逗号分隔的 QQ 号/群号列表。"""
    result: List[int] = []
    for part in (raw or "").replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        result.append(int(part))
    return result


# ==================== YAML 读写（延迟导入，避免裸环境崩溃） ====================

def _load_yaml() -> dict:
    """读取 configs/config.yaml。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    import yaml
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(data: dict) -> None:
    """合并配置并生成带中文行内注释的 configs/config.yaml。"""
    import yaml
    from dataclasses import asdict
    from config import Config, _add_inline_comments, _deep_merge

    default_data = asdict(Config())
    current_cfg = _load_yaml()
    merged = _deep_merge(default_data, current_cfg)
    merged = _deep_merge(merged, data)

    raw_yaml = yaml.dump(
        merged,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    final_content = _add_inline_comments(raw_yaml)
    header = (
        "# YukiV6 配置文件\n"
        "# 所有配置均在此文件管理，请勿提交到 Git\n"
        "# 本文件已在 .gitignore 中\n\n"
    )
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(header + final_content)


# ==================== 步骤 1: 目录与基础文件 ====================

def ensure_dirs() -> None:
    """确保运行所需的目录全部存在。"""
    created = []
    for d in REQUIRED_DIRS:
        full = os.path.join(PROJECT_ROOT, d)
        if not os.path.exists(full):
            os.makedirs(full, exist_ok=True)
            created.append(d)
    if created:
        print(f"📁 已创建目录: {', '.join(created)}")
    else:
        print("📁 必要目录已就绪")


def ensure_files() -> None:
    """确保 blacklist.txt 与 configs/config.yaml 存在。"""
    if not os.path.exists(BLACKLIST_PATH):
        master_name = "主人"
        try:
            from config import cfg
            master_name = cfg.MASTER_NAME
        except Exception:
            pass
        with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
            f.write(f"yuki\n主人\n哥哥\n{master_name}\n人家\n")
        print("📝 已生成初始 blacklist.txt")
    else:
        print("📝 已存在 blacklist.txt，跳过")

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    try:
        from config import sync_config
        if not os.path.exists(CONFIG_PATH):
            sync_config(CONFIG_PATH, verbose=False)
            print("📄 已生成默认配置文件: configs/config.yaml")
        else:
            sync_config(CONFIG_PATH, verbose=False)
            print("📄 已同步配置文件结构: configs/config.yaml")
    except ImportError:
        print("⚠️ 尚未安装 PyYAML，将在依赖安装后生成 configs/config.yaml")


# ==================== 步骤 2: 依赖安装 ====================

def _read_pyproject_dependencies() -> List[str]:
    """使用标准库 tomllib 从 pyproject.toml 读取依赖列表。"""
    pyproject_path = os.path.join(PROJECT_ROOT, "pyproject.toml")
    if not os.path.exists(pyproject_path):
        return []
    import tomllib
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return list(data.get("project", {}).get("dependencies", []))


def check_missing_imports() -> List[str]:
    """返回当前 Python 环境中缺失的核心包名列表。"""
    import importlib.util
    missing = []
    for mod_name, pkg_name in CORE_IMPORTS:
        if importlib.util.find_spec(mod_name) is None:
            missing.append(pkg_name)
    return missing


def install_requirements(
    interactive: bool = True,
    force_install: bool = False,
    skip_install: bool = False,
) -> bool:
    """安装项目依赖（优先使用 uv，回退到 pip 解析 pyproject.toml）。"""
    if skip_install:
        print("⏭️  已跳过依赖安装 (--skip-deps)")
        return True

    missing = check_missing_imports()
    if not missing and not force_install:
        if interactive:
            ans = input("检测到核心依赖已安装，是否仍要更新/同步依赖? (y/N): ").strip().lower()
            if ans != "y":
                print("✅ 跳过依赖更新")
                return True
        else:
            print("✅ 核心 Python 依赖已就绪")
            return True
    elif interactive and not force_install:
        print(f"检测到缺失核心依赖: {', '.join(missing)}")
        ans = input("是否现在安装依赖? (Y/n): ").strip().lower()
        if ans == "n":
            return False

    has_uv = shutil.which("uv") is not None
    try:
        if has_uv and os.path.exists(os.path.join(PROJECT_ROOT, "pyproject.toml")):
            print("🚀 使用 uv sync 安装依赖...")
            subprocess.check_call(["uv", "sync"], cwd=PROJECT_ROOT)
            print("✅ 依赖安装完成 (uv)")
            return True

        print("📦 使用 pip 从 pyproject.toml 安装依赖...")
        deps = _read_pyproject_dependencies()
        if not deps:
            raise RuntimeError("未在 pyproject.toml 中找到依赖声明")

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--extra-index-url",
            "https://download.pytorch.org/whl/cpu",
            *deps,
        ]
        subprocess.check_call(cmd, cwd=PROJECT_ROOT)
        print("✅ 依赖安装完成 (pip)")
        return True
    except Exception as e:
        print(f"❌ 依赖安装失败: {e}")
        print("💡 建议手动执行:")
        print("   uv sync")
        print("   或: python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -e .")
        return False


# ==================== 步骤 3: 迁移旧版 .env ====================

def migrate_from_env() -> None:
    """如果存在旧版 .env，将非空值迁移到 configs/config.yaml。"""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return

    env_data: Dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env_data[k.strip()] = v.strip().strip('"').strip("'")

    cfg = _load_yaml()
    migrated = 0

    mapping: Dict[str, Tuple[str, ...]] = {
        "LLM_API_KEY": ("api", "llm_api_key"),
        "IMAGE_PROCESS_API_KEY": ("api", "image_process_api_key"),
        "NAPCAT_WS_URL": ("connection", "napcat_ws_url"),
        "NAPCAT_WS_TOKEN": ("connection", "napcat_ws_token"),
        "TARGET_QQ": ("target", "qq"),
        "TARGET_GROUPS": ("target", "groups"),
    }

    if env_data.get("ROBOT_NAME") and not cfg.get("robot_name"):
        cfg["robot_name"] = env_data["ROBOT_NAME"]
        migrated += 1
    if env_data.get("MASTER_NAME") and not cfg.get("master_name"):
        cfg["master_name"] = env_data["MASTER_NAME"]
        migrated += 1

    for env_key, yaml_path in mapping.items():
        val: Any = env_data.get(env_key)
        if not val:
            continue
        cur = _get_nested(cfg, yaml_path)
        if not cur:
            if env_key == "TARGET_QQ":
                val = int(val)
            elif env_key == "TARGET_GROUPS":
                val = _parse_int_list(val)
            _set_nested(cfg, yaml_path, val)
            migrated += 1

    if migrated > 0:
        _save_yaml(cfg)
        print(f"✅ 已从 .env 迁移 {migrated} 项配置")


# ==================== 步骤 4: 配置写入（CLI / 环境变量 / 交互式） ====================

def apply_cli_and_env_overrides(args: Optional[argparse.Namespace] = None) -> bool:
    """将 CLI 参数与环境变量写入 configs/config.yaml。返回是否有变更。"""
    cfg = _load_yaml()
    changed = False

    def _apply(path: Tuple[str, ...], val: Any) -> None:
        nonlocal changed
        if val is None or val == "":
            return
        if _get_nested(cfg, path) != val:
            _set_nested(cfg, path, val)
            changed = True
            display = "***" if "key" in path[-1] or "token" in path[-1] else val
            print(f"  ✓ {'.'.join(path)} = {display}")

    # 1. 环境变量兜底（仅当配置里尚未填写或显式传入时生效）
    env_llm_key = os.environ.get("YUKI_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if env_llm_key and not _get_nested(cfg, ("api", "llm_api_key")):
        _apply(("api", "llm_api_key"), env_llm_key)

    env_vision_key = os.environ.get("YUKI_VISION_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if env_vision_key and not _get_nested(cfg, ("api", "image_process_api_key")):
        _apply(("api", "image_process_api_key"), env_vision_key)

    env_pairs = [
        ("YUKI_ROBOT_NAME", ("robot_name",), str),
        ("YUKI_MASTER_NAME", ("master_name",), str),
        ("YUKI_LLM_BASE_URL", ("api", "llm_base_url"), str),
        ("YUKI_LLM_MODEL", ("model", "llm"), str),
        ("YUKI_VISION_URL", ("api", "image_process_url"), str),
        ("YUKI_VISION_MODEL", ("model", "vision"), str),
        ("YUKI_NAPCAT_WS_URL", ("connection", "napcat_ws_url"), str),
        ("YUKI_NAPCAT_WS_TOKEN", ("connection", "napcat_ws_token"), str),
        ("YUKI_BOT_QQ", ("connection", "qq"), int),
        ("YUKI_MASTER_QQ", ("target", "qq"), int),
        ("YUKI_TARGET_GROUPS", ("target", "groups"), _parse_int_list),
    ]
    for env_name, path, caster in env_pairs:
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                _apply(path, caster(raw))
            except Exception as e:
                print(f"  ⚠️ 环境变量 {env_name} 格式无效: {e}")

    # 2. 显式 CLI 参数（优先级最高，直接覆盖）
    if args is not None:
        _apply(("robot_name",), getattr(args, "robot_name", None))
        _apply(("master_name",), getattr(args, "master_name", None))
        _apply(("api", "llm_base_url"), getattr(args, "llm_base_url", None))
        _apply(("api", "llm_api_key"), getattr(args, "llm_api_key", None))
        _apply(("model", "llm"), getattr(args, "llm_model", None))
        _apply(("api", "backup_base_url"), getattr(args, "backup_base_url", None))
        _apply(("api", "backup_api_key"), getattr(args, "backup_api_key", None))
        _apply(("model", "backup"), getattr(args, "backup_model", None))
        _apply(("api", "image_process_url"), getattr(args, "vision_url", None))
        _apply(("api", "image_process_api_key"), getattr(args, "vision_api_key", None))
        _apply(("model", "vision"), getattr(args, "vision_model", None))
        _apply(("connection", "napcat_ws_url"), getattr(args, "napcat_url", None))
        _apply(("connection", "napcat_ws_token"), getattr(args, "napcat_token", None))
        if getattr(args, "bot_qq", None) is not None:
            _apply(("connection", "qq"), int(args.bot_qq))
        if getattr(args, "master_qq", None) is not None:
            _apply(("target", "qq"), int(args.master_qq))
        if getattr(args, "groups", None):
            _apply(("target", "groups"), _parse_int_list(args.groups))

        for item in getattr(args, "set_values", None) or []:
            if "=" not in item:
                print(f"  ⚠️ 忽略无效 --set 参数（应为 key.path=val）: {item}")
                continue
            k, v = item.split("=", 1)
            path_tuple = tuple(p.strip() for p in k.split(".") if p.strip())
            if path_tuple:
                _apply(path_tuple, _parse_scalar_or_list(v))

    if changed:
        _save_yaml(cfg)
        print("📄 配置已写入 configs/config.yaml")
    return changed


def config_yaml(mode: int = 0) -> None:
    """交互式配置向导（对齐最新 config.py 结构）。"""
    del mode
    cfg = _load_yaml()
    changed = False

    def _ask(prompt_text: str, path: Tuple[str, ...], default: Any = "", is_secret: bool = False) -> str:
        nonlocal changed
        cur = _get_nested(cfg, path, default)
        if is_secret:
            hint = "已设置(回车保持)" if cur else "未设置"
        else:
            hint = f"默认 {cur}" if cur not in ("", None, [], 0) else "未设置"
        val = input(f"{prompt_text} [{hint}]: ").strip()
        if val:
            _set_nested(cfg, path, val)
            changed = True
            print(f"  ✓ {'.'.join(path)} 已更新")
        return val

    print("\n--- 1. 机器人与主人身份 ---")
    _ask("机器人名称", ("robot_name",), "yuki")
    _ask("机器人对你的称呼", ("master_name",), "主人")

    print("\n--- 2. 主对话模型 (LLM) 配置 [必填] ---")
    _ask("首选 LLM Base URL (OpenAI 兼容)", ("api", "llm_base_url"), "https://api.deepseek.com/v1")
    _ask("首选 LLM API Key", ("api", "llm_api_key"), "", is_secret=True)
    _ask("首选 LLM 模型名称", ("model", "llm"), "deepseek-chat")

    print("\n--- 3. 备选 LLM 与视觉模型 (可选，回车跳过) ---")
    _ask("备选 LLM Base URL", ("api", "backup_base_url"), "https://api.deepseek.com/v1")
    _ask("备选 LLM API Key (留空则复用首选 Key)", ("api", "backup_api_key"), "", is_secret=True)
    _ask("备选 LLM 模型名称", ("model", "backup"), "deepseek-chat")
    _ask("视觉模型 API URL (用于表情包理解)", ("api", "image_process_url"), "https://dashscope.aliyuncs.com/compatible-mode/v1")
    _ask("视觉模型 API Key (如 DashScope Key)", ("api", "image_process_api_key"), "", is_secret=True)
    _ask("视觉模型名称", ("model", "vision"), "qwen3-vl-flash")

    print("\n--- 4. NapCat (OneBot 11) 连接配置 [必填] ---")
    _ask("NapCat 正向 WebSocket 地址", ("connection", "napcat_ws_url"), "ws://localhost:3001")
    _ask("NapCat WebSocket Token (无则留空)", ("connection", "napcat_ws_token"), "", is_secret=True)

    cur_bot_qq = _get_nested(cfg, ("connection", "qq"), 0)
    bot_qq_raw = input(f"机器人自身 QQ 号 [当前 {cur_bot_qq or '未设置'}]: ").strip()
    if bot_qq_raw:
        try:
            _set_nested(cfg, ("connection", "qq"), int(bot_qq_raw))
            changed = True
            print("  ✓ connection.qq 已更新")
        except ValueError:
            print("  ❌ QQ 号必须为纯数字，已跳过")

    print("\n--- 5. 监听目标 (主人 QQ 与群聊) [必填] ---")
    cur_master_qq = _get_nested(cfg, ("target", "qq"), 0)
    master_qq_raw = input(f"主人 QQ 号 (用于接收私聊与管理指令) [当前 {cur_master_qq or '未设置'}]: ").strip()
    if master_qq_raw:
        try:
            _set_nested(cfg, ("target", "qq"), int(master_qq_raw))
            changed = True
            print("  ✓ target.qq 已更新")
        except ValueError:
            print("  ❌ QQ 号必须为纯数字，已跳过")

    cur_groups = _get_nested(cfg, ("target", "groups"), [])
    groups_hint = ",".join(str(g) for g in cur_groups) if cur_groups else "未设置"
    group_raw = input(f"监听的目标群号 (多个用逗号隔开) [当前 {groups_hint}]: ").strip()
    if group_raw:
        try:
            _set_nested(cfg, ("target", "groups"), _parse_int_list(group_raw))
            changed = True
            print("  ✓ target.groups 已更新")
        except ValueError:
            print("  ❌ 群号格式错误，必须为逗号分隔的数字，已跳过")

    if changed:
        _save_yaml(cfg)
        print("\n📄 配置已保存到 configs/config.yaml")
    else:
        print("\n保持现有 configs/config.yaml 不变")


# ==================== 步骤 5: RAG 嵌入模型下载 ====================

def is_model_ready() -> bool:
    """检查本地 text2vec-base-chinese 模型关键文件是否已存在。"""
    cfg_json = os.path.join(MODEL_DIR, "config.json")
    has_weights = (
        os.path.exists(os.path.join(MODEL_DIR, "model.safetensors"))
        or os.path.exists(os.path.join(MODEL_DIR, "pytorch_model.bin"))
    )
    return os.path.exists(cfg_json) and has_weights


def ensure_model(interactive: bool = True, force: bool = False, skip: bool = False) -> bool:
    """确保本地嵌入模型就绪。"""
    if skip:
        print("⏭️  已跳过模型下载 (--skip-model)")
        return is_model_ready()

    if is_model_ready() and not force:
        print(f"✅ 本地已存在 RAG 嵌入模型: {MODEL_DIR}")
        if interactive:
            ans = input("是否重新下载并覆盖模型? (y/N): ").strip().lower()
            if ans != "y":
                return True
            force = True
        else:
            return True

    try:
        from utils.download_model import download_model
        download_model(force=True if not interactive else force)
        return is_model_ready()
    except ImportError as e:
        print(f"⚠️ 依赖尚未安装，无法下载模型: {e}")
        return False
    except Exception as e:
        print(f"❌ 模型下载失败: {e}")
        print("💡 若国内网络访问 HuggingFace 超时，可设置镜像环境变量后重试：")
        print("   HF_ENDPOINT=https://hf-mirror.com python setup.py --non-interactive --skip-deps")
        return False


# ==================== 步骤 6: 环境与配置健康自检 (--check) ====================

def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_check(as_json: bool = False) -> int:
    """运行部署前自检。返回退出码：0=可启动，1=存在阻断项。"""
    checks: List[Dict[str, Any]] = []
    blocking_errors: List[str] = []
    warnings: List[str] = []

    # 1. Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    checks.append({"item": "python_version", "ok": py_ok, "detail": py_ver})
    if not py_ok:
        blocking_errors.append(f"Python 版本需要 >= 3.11，当前为 {py_ver}")

    # 2. 核心依赖
    missing_pkgs = check_missing_imports()
    deps_ok = len(missing_pkgs) == 0
    checks.append({
        "item": "python_dependencies",
        "ok": deps_ok,
        "detail": "all installed" if deps_ok else f"missing: {', '.join(missing_pkgs)}",
    })
    if not deps_ok:
        blocking_errors.append(f"缺失 Python 依赖: {', '.join(missing_pkgs)}")

    # 3. 必要文件与模型
    has_blacklist = os.path.exists(BLACKLIST_PATH)
    checks.append({"item": "blacklist_txt", "ok": has_blacklist, "detail": BLACKLIST_PATH})
    if not has_blacklist:
        blocking_errors.append("缺少 blacklist.txt（可运行 python setup.py --non-interactive 自动生成）")

    model_ok = is_model_ready()
    checks.append({"item": "embedding_model", "ok": model_ok, "detail": MODEL_DIR})
    if not model_ok:
        blocking_errors.append("缺少 RAG 嵌入模型 models/text2vec-base-chinese")

    # 4. 配置文件与必填项
    has_cfg = os.path.exists(CONFIG_PATH)
    checks.append({"item": "config_yaml", "ok": has_cfg, "detail": CONFIG_PATH})
    if not has_cfg:
        blocking_errors.append("缺少 configs/config.yaml")
    elif deps_ok:
        cfg_data = _load_yaml()
        llm_key = str(_get_nested(cfg_data, ("api", "llm_api_key"), "") or "").strip()
        ws_url = str(_get_nested(cfg_data, ("connection", "napcat_ws_url"), "ws://localhost:3001") or "").strip()
        bot_qq = int(_get_nested(cfg_data, ("connection", "qq"), 0) or 0)
        master_qq = int(_get_nested(cfg_data, ("target", "qq"), 0) or 0)
        groups = _get_nested(cfg_data, ("target", "groups"), []) or []

        key_ok = bool(llm_key)
        checks.append({"item": "config.api.llm_api_key", "ok": key_ok, "detail": "configured" if key_ok else "empty"})
        if not key_ok:
            blocking_errors.append("configs/config.yaml 中未填写 api.llm_api_key")

        target_ok = master_qq > 0 or len(groups) > 0
        checks.append({
            "item": "config.target",
            "ok": target_ok,
            "detail": f"master_qq={master_qq}, groups={groups}",
        })
        if not target_ok:
            warnings.append("target.qq（主人QQ）与 target.groups（目标群）均未配置，启动后不会响应任何会话")

        if bot_qq <= 0:
            warnings.append("connection.qq（机器人自身QQ号）未配置，建议填写以准确识别自身消息")

        # 5. NapCat 端口连通性探测（非阻断警告）
        parsed = urlparse(ws_url if "://" in ws_url else f"ws://{ws_url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 3001)
        napcat_reachable = _probe_tcp(host, port)
        checks.append({
            "item": "napcat_ws_port",
            "ok": napcat_reachable,
            "detail": f"{host}:{port} ({ws_url})",
        })
        if not napcat_reachable:
            warnings.append(f"当前无法连接 NapCat 端口 {host}:{port}（请确认 NapCat 已启动并开启正向 WebSocket）")

    ready = len(blocking_errors) == 0
    if as_json:
        print(json.dumps({
            "ready": ready,
            "python": sys.executable,
            "project_root": PROJECT_ROOT,
            "checks": checks,
            "blocking_errors": blocking_errors,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    else:
        print("\n=== Yuki 部署环境自检报告 ===")
        for c in checks:
            icon = "✅" if c["ok"] else "❌"
            print(f"  {icon} {c['item']}: {c['detail']}")
        if warnings:
            print("\n⚠️  注意事项:")
            for w in warnings:
                print(f"  - {w}")
        if blocking_errors:
            print("\n❌ 阻断问题 (需修复后才能启动 main.py):")
            for err in blocking_errors:
                print(f"  - {err}")
        else:
            print("\n🎉 所有核心检查通过！可通过 [ python main.py ] 启动，或使用 [ YUKI_DRY_RUN=1 python main.py ] 试启动验证。")

    return 0 if ready else 1


# ==================== 主流程入口 ====================

def quick_setup(mode: int = 0, args: Optional[argparse.Namespace] = None) -> int:
    """完整初始化流程（保留 quick_setup(mode) 签名以兼容 init.py 调用）。"""
    interactive = not bool(getattr(args, "non_interactive", False))
    skip_deps = bool(getattr(args, "skip_deps", False))
    install_deps = bool(getattr(args, "install_deps", False))
    skip_model = bool(getattr(args, "skip_model", False))
    force_model = bool(getattr(args, "force_model", False))

    print("\n>>> 步骤 1/5: 建立目录结构")
    ensure_dirs()

    print("\n>>> 步骤 2/5: 检查与安装 Python 依赖")
    install_requirements(
        interactive=interactive,
        force_install=install_deps,
        skip_install=skip_deps,
    )

    print("\n>>> 步骤 3/5: 初始化配置文件与迁移旧版 .env")
    ensure_files()
    migrate_from_env()

    print("\n>>> 步骤 4/5: 写入配置项")
    apply_cli_and_env_overrides(args)
    if interactive:
        config_yaml(mode)

    print("\n>>> 步骤 5/5: 准备 RAG 嵌入模型 (text2vec-base-chinese)")
    ensure_model(interactive=interactive, force=force_model, skip=skip_model)

    return run_check(as_json=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yuki (FrostFrame) 一键部署与配置工具（支持交互式向导与 Agent 非交互式 CLI）"
    )
    parser.add_argument(
        "-y", "--non-interactive",
        action="store_true",
        help="非交互模式（不调用 input，适合 Agent / CI / 自动化脚本执行）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅执行环境、依赖、模型与配置完整性自检，不修改任何文件",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="配合 --check 使用，输出 JSON 格式自检报告供 Agent 解析",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="强制安装/同步 Python 依赖",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="跳过 Python 依赖安装步骤",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="跳过 RAG 嵌入模型下载步骤",
    )
    parser.add_argument(
        "--force-model",
        action="store_true",
        help="强制重新下载 RAG 嵌入模型",
    )

    # 常用配置项快捷参数
    cfg_group = parser.add_argument_group("常用配置参数 (写入 configs/config.yaml)")
    cfg_group.add_argument("--robot-name", help="机器人名称 (默认 yuki)")
    cfg_group.add_argument("--master-name", help="主人称呼 (默认 主人)")
    cfg_group.add_argument("--llm-base-url", help="首选 LLM API Base URL")
    cfg_group.add_argument("--llm-api-key", help="首选 LLM API Key (也可通过环境变量 YUKI_LLM_API_KEY 传入)")
    cfg_group.add_argument("--llm-model", help="首选 LLM 模型名称 (默认 deepseek-chat)")
    cfg_group.add_argument("--backup-base-url", help="备选 LLM API Base URL")
    cfg_group.add_argument("--backup-api-key", help="备选 LLM API Key")
    cfg_group.add_argument("--backup-model", help="备选 LLM 模型名称")
    cfg_group.add_argument("--vision-url", help="视觉模型 API URL")
    cfg_group.add_argument("--vision-api-key", help="视觉模型 API Key (也可通过环境变量 YUKI_VISION_API_KEY 传入)")
    cfg_group.add_argument("--vision-model", help="视觉模型名称 (默认 qwen3-vl-flash)")
    cfg_group.add_argument("--napcat-url", help="NapCat WebSocket 地址 (默认 ws://localhost:3001)")
    cfg_group.add_argument("--napcat-token", help="NapCat WebSocket Token")
    cfg_group.add_argument("--bot-qq", type=int, help="机器人自身 QQ 号 (connection.qq)")
    cfg_group.add_argument("--master-qq", type=int, help="主人 QQ 号 (target.qq)")
    cfg_group.add_argument("--groups", help="目标群号列表，逗号分隔，如 '123456,789012'")
    cfg_group.add_argument(
        "--set",
        dest="set_values",
        action="append",
        metavar="KEY=VAL",
        help="按点号路径设置任意配置项（可多次传入，如 --set rag.inject_top_k=5 --set debug=false）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return run_check(as_json=args.json)

    if not args.non_interactive and shutil.which("uv") and sys.prefix == sys.base_prefix:
        venv_python = (
            os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
            if sys.platform == "win32"
            else os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
        )
        if os.path.exists(venv_python):
            print("💡 检测到 .venv 虚拟环境存在但未激活，建议使用：uv run python setup.py\n")

    rc = quick_setup(0, args)
    print("\n✨ 配置流程结束！如需细调更多参数，请编辑 configs/config.yaml。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
