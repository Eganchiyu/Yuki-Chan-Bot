"""配置系统 (config.py) 单元测试。"""
import os
import pytest

from config import (
    APIConfig,
    AttentionConfig,
    Config,
    ConnectionConfig,
    DiaryConfig,
    EnergyConfig,
    ModelConfig,
    PathsConfig,
    QZoneMonitorConfig,
    RAGConfig,
    TargetConfig,
    TimingConfig,
    _ATTR_MAP,
    _SECTION_HEADERS,
    _deep_merge,
    _dict_to_dataclass,
    cfg,
    generate_default_config,
    load_config,
    save_config,
)


def test_sub_config_defaults():
    """各子配置类默认值与关键约束符合预期。"""
    api = APIConfig()
    assert api.llm_base_url == "https://api.deepseek.com/v1"
    assert api.backup_base_url == "https://api.deepseek.com/v1"
    assert api.image_process_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert api.llm_api_key == ""

    model = ModelConfig()
    assert model.llm == "deepseek-chat"
    assert model.backup == "deepseek-chat"
    assert model.vision == "qwen3-vl-flash"
    assert model.thinking_effort == ""

    conn = ConnectionConfig()
    assert conn.napcat_ws_url == "ws://localhost:3001"
    assert conn.max_retries == 3

    target = TargetConfig()
    assert target.qq == 0 and target.groups == []

    diary = DiaryConfig()
    assert (diary.idle_seconds, diary.min_turns, diary.max_length) == (120, 15, 50)

    rag = RAGConfig()
    assert rag.retrieval_top_k == 20 and rag.keep_last_dialogue == 10 and rag.inject_top_k == 5

    energy = EnergyConfig()
    assert (energy.initial, energy.max, energy.cost_per_reply, energy.min_active) == (100, 100.0, 6, 25)

    attention = AttentionConfig()
    assert attention.keywords == ["主人", "哥哥"]

    timing = TimingConfig()
    assert timing.debounce_time == 32
    assert (timing.request_timeout.total, timing.request_timeout.connect, timing.request_timeout.sock_read) == (60, 10, 30)


def test_main_config_and_switches():
    """主配置类默认属性、可选监控默认关闭以及计算属性正确。"""
    c = Config()
    assert c.robot_name == "yuki"
    assert c.master_name == "主人"
    assert c.qzone_monitor.enabled is False
    assert c.github_monitor.enabled is False

    c.robot_name = "TestBot"
    c.target.groups = [123, 456]
    c.attention.keywords = ["主人", "哥哥"]
    assert c.ROBOT_NAME == "testbot"
    assert c.MASTER_NAME == "主人"
    assert c.TARGET_GROUPS == [123, 456]
    assert "testbot" in c.keywords and "主人" in c.keywords


def test_config_get_and_custom_init():
    """Config.get 支持扁平与嵌套访问，且支持自定义子配置初始化。"""
    c = Config(
        robot_name="CustomBot",
        debug=False,
        api=APIConfig(llm_api_key="custom-key"),
        model=ModelConfig(llm="gpt-4"),
        energy=EnergyConfig(initial=50, max=80.0),
    )
    assert c.get("robot_name") == "CustomBot"
    assert c.get("api", "llm_api_key") == "custom-key"
    assert c.get("nonexistent", default="fallback") == "fallback"
    assert c.model.llm == "gpt-4"
    assert c.energy.initial == 50 and c.energy.max == 80.0
    assert c.debug is False


def test_load_and_save_config_roundtrip(tmp_path):
    """YAML 配置保存、完整加载、部分配置合并、缺失文件与损坏文件备份。"""
    yaml_path = tmp_path / "subdir" / "config.yaml"
    to_save = Config(
        robot_name="SaveBot",
        api=APIConfig(llm_api_key="save-key", llm_base_url="https://custom.example.com"),
        energy=EnergyConfig(initial=60),
    )
    save_config(to_save, str(yaml_path))
    assert yaml_path.exists()

    loaded = load_config(str(yaml_path))
    assert loaded.robot_name == "SaveBot"
    assert loaded.api.llm_api_key == "save-key"
    assert loaded.api.llm_base_url == "https://custom.example.com"
    assert loaded.energy.initial == 60
    assert loaded.master_name == "主人"  # 未覆盖字段保持默认

    # 不存在的文件 -> 返回默认配置
    missing = load_config(str(tmp_path / "nonexistent.yaml"))
    assert missing.robot_name == "yuki" and missing.api.llm_api_key == ""

    # 损坏的 YAML -> 回退默认配置并生成 .bak 备份
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("invalid: yaml: content: [[[", encoding="utf-8")
    fallback = load_config(str(bad_yaml))
    assert fallback.robot_name == "yuki"
    assert (tmp_path / "bad.yaml.bak").exists()


def test_helper_functions_and_schema_structures():
    """_deep_merge、_dict_to_dataclass、默认配置模板及映射表结构正确。"""
    merged = _deep_merge({"a": 1, "b": {"c": 2, "d": 3}}, {"b": {"c": 4}, "e": 5})
    assert merged == {"a": 1, "b": {"c": 4, "d": 3}, "e": 5}

    converted = _dict_to_dataclass(
        Config,
        {"robot_name": "ConvertedBot", "api": {"llm_api_key": "k"}, "energy": {"initial": 75}},
    )
    assert converted.robot_name == "ConvertedBot"
    assert converted.api.llm_api_key == "k"
    assert converted.energy.initial == 75
    assert converted.model.llm == "deepseek-chat"

    yaml_text = generate_default_config()
    assert "YukiV6" in yaml_text and "robot_name" in yaml_text and "api:" in yaml_text

    for name, (path, _default, comment) in _ATTR_MAP.items():
        assert isinstance(name, str) and isinstance(path, tuple) and len(path) > 0
        assert isinstance(comment, str) or comment is None

    for key, header in _SECTION_HEADERS.items():
        assert isinstance(key, str) and header.startswith("#")


def test_path_resolution_and_global_cfg():
    """相对/绝对路径解析与全局 cfg 兼容接口可用。"""
    c = Config()
    assert os.path.isabs(c._resolve_path("./test/path"))
    assert c._resolve_path("/abs/path") == "/abs/path"
    assert c._resolve_path("") == ""
    assert c._resolve_path(None) is None

    for prop, expected_substr in (
        ("VECTOR_DB_PATH", "yuki_memory"),
        ("EMBED_MODEL", "text2vec-base-chinese"),
        ("HISTORY_FILE", "chat_history.json"),
        ("LOG_FILE", "yuki_log.txt"),
        ("CACHE_FILE", "meme_cache.json"),
    ):
        val = getattr(c, prop)
        assert os.path.isabs(val) and expected_substr in val

    assert os.path.isabs(c.CACHE_DIR)
    assert cfg.get("robot_name") is not None
    assert cfg.get("api", "llm_api_key") is not None
    assert callable(getattr(cfg, "reload", None))
    assert cfg.LLM_BASE_URL and cfg.BACKUP_BASE_URL and cfg.IMAGE_PROCESS_API_URL
