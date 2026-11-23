# config.py
"""YukiV6 配置系统顶层门面（实际 schema 与加载器已拆分至 core/config/）。

保持 `from config import cfg, Config, load_config, ...` 以及 `python config.py sync` 100% 向后兼容。
"""
import os
import sys


def _fix_invalid_ssl_env():
    """防止 httpx 因指向不存在的 SSL_CERT_FILE/DIR 而报 FileNotFoundError。"""
    for var in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        val = os.environ.get(var, "")
        if val and not os.path.exists(val):
            os.environ.pop(var, None)


_fix_invalid_ssl_env()

from core.config import (  # noqa: E402
    APIConfig,
    AttentionConfig,
    AutonomousConfig,
    Config,
    ConnectionConfig,
    DiaryConfig,
    EnergyConfig,
    GitHubMonitorConfig,
    GitHubMonitorRepoConfig,
    LLMProviderConfig,
    ModelConfig,
    PathsConfig,
    QZoneMonitorConfig,
    RAGConfig,
    RequestTimeoutConfig,
    SearchConfig,
    TargetConfig,
    TimingConfig,
    ToolsConfig,
    _ATTR_MAP,
    _LEGACY_ALIASES,
    _SECTION_HEADERS,
    _add_inline_comments,
    _build_attr_map,
    _deep_merge,
    _dict_to_dataclass,
    _get_section_for_field,
    config_field,
    config_field_factory,
    generate_default_config,
    load_config,
    run_cli,
    save_config,
    sync_config,
)

cfg = load_config()

if __name__ == "__main__":
    run_cli(sys.argv)
