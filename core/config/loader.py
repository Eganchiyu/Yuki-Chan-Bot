# core/config/loader.py
"""YukiV6 配置加载、保存、YAML 行尾注释注入与 CLI 同步工具。"""

import os
import shutil
import sys
from dataclasses import asdict, fields
from typing import Optional

import yaml

from core.config.schema import (
    Config,
    GitHubMonitorRepoConfig,
    LLMProviderConfig,
    _ATTR_MAP,
    _SECTION_HEADERS,
)
from utils import BASE_DIR

_LIST_ITEM_DATACLASS = {
    "providers": LLMProviderConfig,
    "repos": GitHubMonitorRepoConfig,
}

_YAML_HEADER = (
    "# YukiV6 配置文件\n"
    "# 所有配置均在此文件管理，请勿提交到 Git\n"
    "# 本文件已在 .gitignore 中\n\n"
)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_dataclass(cls, data: dict):
    """将字典递归转换为 dataclass 实例（支持嵌套 dataclass 与 dataclass 列表）。"""
    if not isinstance(data, dict):
        return data

    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}

    for key, value in data.items():
        if key not in field_types:
            continue
        field_type = field_types[key]
        if hasattr(field_type, "__dataclass_fields__") and isinstance(value, dict):
            kwargs[key] = _dict_to_dataclass(field_type, value)
        elif key in _LIST_ITEM_DATACLASS and isinstance(value, list):
            item_cls = _LIST_ITEM_DATACLASS[key]
            kwargs[key] = [
                _dict_to_dataclass(item_cls, item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            kwargs[key] = value

    return cls(**kwargs)


def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置文件（默认 configs/config.yaml）。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    default_config = Config()

    if not os.path.exists(config_path):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        save_config(default_config, config_path)
        default_config._raw = {}
        default_config._content_hash = ""
        return default_config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        bak_path = config_path + ".bak"
        shutil.copy2(config_path, bak_path)
        print(f"[Config] 配置文件解析失败，已备份到 {bak_path}: {e}")
        return default_config

    config = _dict_to_dataclass(Config, yaml_data)
    if config.providers:
        config._sync_api_model_from_providers()
    config._raw = yaml_data
    config._content_hash = ""
    return config


def _strip_legacy_api_when_providers_active(data: dict) -> dict:
    """当已启用 providers 队列时，落盘 YAML 不再输出冗余的顶层 api 段与 model 旧主备字段。"""
    if not data.get("providers"):
        return data
    cleaned = dict(data)
    cleaned.pop("api", None)
    if isinstance(cleaned.get("model"), dict):
        model_dict = dict(cleaned["model"])
        for legacy_key in ("llm", "backup", "llm_native_vision_enabled", "backup_native_vision_enabled"):
            model_dict.pop(legacy_key, None)
        cleaned["model"] = model_dict
    return cleaned


def save_config(config: Config, config_path: Optional[str] = None):
    """保存配置到 YAML 文件（自动附带分组标题与字段行尾注释）。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    if hasattr(config, "_sync_media_api_between_api_and_model"):
        config._sync_media_api_between_api_and_model()
    data = _strip_legacy_api_when_providers_active(asdict(config))
    yaml_content = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    yaml_content = _add_inline_comments(yaml_content)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(_YAML_HEADER + yaml_content)


def _get_section_for_field(field_path: tuple) -> str:
    """根据字段路径获取所属 section。"""
    def _find_section(cls, prefix=(), target_path=()):
        for f in fields(cls):
            current_path = prefix + (f.name,)
            metadata = f.metadata or {}
            section = metadata.get("section", "")
            if current_path == target_path:
                return section
            field_type = f.type
            if hasattr(field_type, "__dataclass_fields__"):
                result = _find_section(field_type, current_path, target_path)
                if result:
                    return result
        return ""

    return _find_section(Config, (), field_path)


def generate_default_config() -> str:
    """生成默认配置 YAML 文本（用于 setup.py）。"""
    default_config = Config()
    data = asdict(default_config)
    yaml_content = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return _YAML_HEADER + yaml_content


def _add_inline_comments(yaml_text: str) -> str:
    """给 YAML 文本添加分组标题与行尾注释。"""
    comment_map = {path: comment for _name, (path, _default, comment) in _ATTR_MAP.items() if comment}

    lines = yaml_text.split("\n")
    path_stack = []
    result = []

    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            result.append(line)
            continue

        indent = len(line) - len(stripped)
        level = indent // 2
        path_stack = path_stack[:level]

        if level == 0 and ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":")[0].strip()
            if key in _SECTION_HEADERS:
                result.append("")
                result.append(_SECTION_HEADERS[key])

        if ":" in stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            path_stack.append(key)
            path_tuple = tuple(path_stack)
            if path_tuple in comment_map:
                line = f"{line}  # {comment_map[path_tuple]}"

        result.append(line)

    return "\n".join(result)


def sync_config(config_path: Optional[str] = None, verbose: bool = True) -> bool:
    """同步配置文件到 dataclass 定义的最新结构。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    existing_data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            if verbose:
                print(f"[Config Sync] 配置文件解析失败: {e}")
            return False

    default_data = asdict(Config())
    merged_data = _deep_merge(default_data, existing_data)
    has_changes = merged_data != existing_data

    if has_changes or not os.path.exists(config_path):
        if os.path.exists(config_path):
            backup_path = config_path + ".backup"
            shutil.copy2(config_path, backup_path)
            if verbose:
                print(f"[Config Sync] 已备份原配置到: {backup_path}")

        yaml_content = yaml.dump(merged_data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        yaml_content = _add_inline_comments(yaml_content)

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(_YAML_HEADER + yaml_content)

        if verbose:
            print(f"[Config Sync] 配置已同步到: {config_path}")
            if has_changes:
                added = set(default_data.keys()) - set(existing_data.keys())
                removed = set(existing_data.keys()) - set(default_data.keys())
                if added:
                    print(f"[Config Sync] 新增字段: {added}")
                if removed:
                    print(f"[Config Sync] 移除字段: {removed}")
    else:
        if verbose:
            print("[Config Sync] 配置已是最新，无需同步")

    return has_changes


def run_cli(argv: list[str]) -> None:
    """CLI 入口（`python config.py sync|generate|help`）。"""
    help_text = (
        "\nYukiV6 配置管理工具\n\n"
        "用法:\n    python config.py <command> [options]\n\n"
        "命令:\n"
        "    sync        同步配置文件到最新结构\n"
        "    generate    生成默认配置文件\n"
        "    help        显示此帮助信息\n"
    )
    if len(argv) < 2 or argv[1] in ("help", "--help", "-h"):
        print(help_text)
        sys.exit(0)

    command = argv[1]
    args = argv[2:]

    if command == "sync":
        path = None
        verbose = True
        i = 0
        while i < len(args):
            if args[i] == "--path" and i + 1 < len(args):
                path = args[i + 1]
                i += 2
            elif args[i] == "--quiet":
                verbose = False
                i += 1
            else:
                i += 1
        sys.exit(0 if sync_config(path, verbose) else 1)

    if command == "generate":
        path = None
        i = 0
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                path = args[i + 1]
                i += 2
            else:
                i += 1
        if path is None:
            path = os.path.join(BASE_DIR, "configs", "config.yaml")
        save_config(Config(), path)
        print(f"[Config] 默认配置已生成到: {path}")
        return

    print(f"未知命令: {command}")
    print(help_text)
    sys.exit(1)
