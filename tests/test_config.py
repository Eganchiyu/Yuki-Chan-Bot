"""
配置系统单元测试

测试新的 dataclass 配置系统的正确性和稳定性
"""
import os
import sys
import tempfile
import pytest
from dataclasses import asdict

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    Config, APIConfig, ModelConfig, ConnectionConfig, TargetConfig,
    DiaryConfig, RAGConfig, EnergyConfig, AttentionConfig, PathsConfig,
    TimingConfig, RequestTimeoutConfig, QZoneMonitorConfig,
    load_config, save_config, _deep_merge, _dict_to_dataclass,
    generate_default_config, _ATTR_MAP, _SECTION_HEADERS
)


class TestConfigDataclasses:
    """测试配置数据类"""

    def test_api_config_defaults(self):
        """测试 APIConfig 默认值"""
        api = APIConfig()
        assert api.llm_base_url == "https://api.deepseek.com/v1"
        assert api.backup_base_url == "https://api.deepseek.com/v1"
        assert api.image_process_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert api.llm_api_key == ""
        assert api.backup_api_key == ""
        assert api.image_process_api_key == ""

    def test_model_config_defaults(self):
        """测试 ModelConfig 默认值"""
        model = ModelConfig()
        assert model.llm == "deepseek-chat"
        assert model.backup == "deepseek-chat"
        assert model.vision == "qwen3-vl-flash"
        assert model.disable_thinking is True

    def test_connection_config_defaults(self):
        """测试 ConnectionConfig 默认值"""
        conn = ConnectionConfig()
        assert conn.napcat_ws_url == "ws://localhost:3001"
        assert conn.napcat_ws_token == ""
        assert conn.max_retries == 3

    def test_target_config_defaults(self):
        """测试 TargetConfig 默认值"""
        target = TargetConfig()
        assert target.qq == 0
        assert target.groups == []

    def test_diary_config_defaults(self):
        """测试 DiaryConfig 默认值"""
        diary = DiaryConfig()
        assert diary.idle_seconds == 120
        assert diary.min_turns == 15
        assert diary.max_length == 50

    def test_rag_config_defaults(self):
        """测试 RAGConfig 默认值"""
        rag = RAGConfig()
        assert rag.retrieval_top_k == 20
        assert rag.keep_last_dialogue == 10

    def test_energy_config_defaults(self):
        """测试 EnergyConfig 默认值"""
        energy = EnergyConfig()
        assert energy.initial == 100
        assert energy.max == 100.0
        assert energy.recovery_per_min == 0.8
        assert energy.cost_per_reply == 6
        assert energy.min_active == 25

    def test_attention_config_defaults(self):
        """测试 AttentionConfig 默认值"""
        attention = AttentionConfig()
        assert attention.sensitivity == 0.12
        assert attention.decay_level == 0.65
        assert attention.sigmoid_centre == 50.0
        assert attention.sigmoid_alpha == 0.08
        assert attention.keywords == ["主人", "哥哥"]

    def test_paths_config_defaults(self):
        """测试 PathsConfig 默认值"""
        paths = PathsConfig()
        assert paths.vector_db == "./yuki_memory"
        assert paths.embed_model == "./models/text2vec-base-chinese"
        assert paths.history_file == "./data/chat_history.json"
        assert paths.log_file == "./data/yuki_log.txt"
        assert paths.cache_dir == "./data"
        assert paths.cache_file == "./data/meme_cache.json"

    def test_qzone_monitor_config_defaults(self):
        """测试 QZoneMonitorConfig 默认值（默认关闭）"""
        qzone = QZoneMonitorConfig()
        assert qzone.enabled is False

    def test_timing_config_defaults(self):
        """测试 TimingConfig 默认值"""
        timing = TimingConfig()
        assert timing.debounce_time == 32
        assert timing.request_timeout.total == 60
        assert timing.request_timeout.connect == 10
        assert timing.request_timeout.sock_read == 30


class TestMainConfig:
    """测试主配置类"""

    def test_config_defaults(self):
        """测试 Config 默认值"""
        config = Config()
        assert config.robot_name == "yuki"
        assert config.master_name == "主人"
        assert config.max_message_length == 150
        assert config.max_concurrent_meme == 3
        assert config.debug is True

    def test_config_sub_configs(self):
        """测试子配置组初始化"""
        config = Config()
        assert isinstance(config.api, APIConfig)
        assert isinstance(config.model, ModelConfig)
        assert isinstance(config.connection, ConnectionConfig)
        assert isinstance(config.target, TargetConfig)
        assert isinstance(config.diary, DiaryConfig)
        assert isinstance(config.rag, RAGConfig)
        assert isinstance(config.energy, EnergyConfig)
        assert isinstance(config.attention, AttentionConfig)
        assert isinstance(config.paths, PathsConfig)
        assert isinstance(config.timing, TimingConfig)

    def test_monitor_switches_default_off(self):
        """两个可选监控的开关默认必须关闭"""
        config = Config()
        assert config.qzone_monitor.enabled is False
        assert config.github_monitor.enabled is False

    def test_config_computed_properties(self):
        """测试计算属性"""
        config = Config()
        config.robot_name = "TestBot"
        config.master_name = "主人"
        config.target.groups = [123, 456]
        config.attention.keywords = ["主人", "哥哥"]

        # ROBOT_NAME
        assert config.ROBOT_NAME == "testbot"

        # MASTER_NAME
        assert config.MASTER_NAME == "主人"

        # TARGET_GROUPS
        assert config.TARGET_GROUPS == [123, 456]

        # keywords
        assert "testbot" in config.keywords
        assert "主人" in config.keywords

    def test_config_get_method(self):
        """测试 get() 方法"""
        config = Config()
        config.api.llm_api_key = "test-key"

        # 简单访问
        assert config.get("robot_name") == "yuki"

        # 嵌套访问
        assert config.get("api", "llm_api_key") == "test-key"

        # 默认值
        assert config.get("nonexistent", default="default") == "default"

    def test_config_custom_values(self):
        """测试自定义值"""
        config = Config(
            robot_name="CustomBot",
            master_name="Master",
            max_message_length=200,
            debug=False
        )
        assert config.robot_name == "CustomBot"
        assert config.master_name == "Master"
        assert config.max_message_length == 200
        assert config.debug is False

    def test_config_sub_config_custom_values(self):
        """测试子配置自定义值"""
        config = Config(
            api=APIConfig(llm_api_key="custom-key"),
            model=ModelConfig(llm="gpt-4"),
            energy=EnergyConfig(initial=50, max=80.0)
        )
        assert config.api.llm_api_key == "custom-key"
        assert config.model.llm == "gpt-4"
        assert config.energy.initial == 50
        assert config.energy.max == 80.0


class TestConfigLoading:
    """测试配置加载"""

    def test_load_config_from_yaml(self):
        """测试从 YAML 加载配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("""
robot_name: TestBot
master_name: Master
api:
  llm_api_key: test-key-123
  llm_base_url: https://custom-api.example.com
model:
  llm: gpt-4
energy:
  initial: 50
  max: 80.0
""")
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.robot_name == "TestBot"
            assert config.master_name == "Master"
            assert config.api.llm_api_key == "test-key-123"
            assert config.api.llm_base_url == "https://custom-api.example.com"
            assert config.model.llm == "gpt-4"
            assert config.energy.initial == 50
            assert config.energy.max == 80.0
        finally:
            os.unlink(temp_path)

    def test_load_config_missing_file(self):
        """测试加载不存在的配置文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "nonexistent.yaml")
            config = load_config(temp_path)
            # 应该返回默认配置
            assert config.robot_name == "yuki"
            assert config.api.llm_api_key == ""

    def test_load_config_invalid_yaml(self):
        """测试加载无效 YAML"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("invalid: yaml: content: [[[")
            temp_path = f.name

        try:
            config = load_config(temp_path)
            # 应该返回默认配置
            assert config.robot_name == "yuki"
            # 应该创建备份文件
            assert os.path.exists(temp_path + ".bak")
        finally:
            os.unlink(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.unlink(temp_path + ".bak")

    def test_load_config_partial_yaml(self):
        """测试加载部分配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("""
robot_name: PartialBot
api:
  llm_api_key: partial-key
""")
            temp_path = f.name

        try:
            config = load_config(temp_path)
            # 应该有自定义值
            assert config.robot_name == "PartialBot"
            assert config.api.llm_api_key == "partial-key"
            # 应该有默认值
            assert config.master_name == "主人"
            assert config.api.backup_api_key == ""
            assert config.model.llm == "deepseek-chat"
        finally:
            os.unlink(temp_path)


class TestConfigSaving:
    """测试配置保存"""

    def test_save_config(self):
        """测试保存配置"""
        config = Config(
            robot_name="SaveBot",
            api=APIConfig(llm_api_key="save-key")
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            temp_path = f.name

        try:
            save_config(config, temp_path)

            # 重新加载验证
            loaded_config = load_config(temp_path)
            assert loaded_config.robot_name == "SaveBot"
            assert loaded_config.api.llm_api_key == "save-key"
        finally:
            os.unlink(temp_path)

    def test_save_config_creates_directory(self):
        """测试保存配置时自动创建目录"""
        config = Config()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "subdir", "config.yaml")
            save_config(config, temp_path)
            assert os.path.exists(temp_path)


class TestHelperFunctions:
    """测试辅助函数"""

    def test_deep_merge(self):
        """测试深度合并"""
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 4}, "e": 5}
        result = _deep_merge(base, override)

        assert result["a"] == 1
        assert result["b"]["c"] == 4
        assert result["b"]["d"] == 3
        assert result["e"] == 5

    def test_dict_to_dataclass(self):
        """测试字典转 dataclass"""
        data = {
            "robot_name": "ConvertedBot",
            "api": {"llm_api_key": "converted-key"},
            "energy": {"initial": 75}
        }
        config = _dict_to_dataclass(Config, data)

        assert config.robot_name == "ConvertedBot"
        assert config.api.llm_api_key == "converted-key"
        assert config.energy.initial == 75
        # 默认值应该保留
        assert config.master_name == "主人"
        assert config.model.llm == "deepseek-chat"

    def test_generate_default_config(self):
        """测试生成默认配置"""
        yaml_text = generate_default_config()
        assert "YukiV6" in yaml_text
        assert "robot_name" in yaml_text
        assert "api:" in yaml_text
        assert "model:" in yaml_text

    def test_attr_map_structure(self):
        """测试 _ATTR_MAP 结构"""
        for name, (path, default, comment) in _ATTR_MAP.items():
            assert isinstance(name, str)
            assert isinstance(path, tuple)
            assert len(path) > 0
            assert isinstance(comment, str) or comment is None

    def test_section_headers_structure(self):
        """测试 _SECTION_HEADERS 结构"""
        for key, header in _SECTION_HEADERS.items():
            assert isinstance(key, str)
            assert isinstance(header, str)
            assert header.startswith("#")


class TestPathResolution:
    """测试路径解析"""

    def test_resolve_path_relative(self):
        """测试相对路径解析"""
        config = Config()
        # 相对路径应该被解析
        resolved = config._resolve_path("./test/path")
        assert os.path.isabs(resolved)

    def test_resolve_path_absolute(self):
        """测试绝对路径"""
        config = Config()
        # 绝对路径应该原样返回
        abs_path = "/absolute/path"
        resolved = config._resolve_path(abs_path)
        assert resolved == abs_path

    def test_resolve_path_empty(self):
        """测试空路径"""
        config = Config()
        assert config._resolve_path("") == ""
        assert config._resolve_path(None) is None

    def test_vector_db_path(self):
        """测试向量数据库路径"""
        config = Config()
        path = config.VECTOR_DB_PATH
        assert os.path.isabs(path)
        assert "yuki_memory" in path

    def test_embed_model_path(self):
        """测试嵌入模型路径"""
        config = Config()
        path = config.EMBED_MODEL
        assert os.path.isabs(path)
        assert "text2vec-base-chinese" in path

    def test_history_file_path(self):
        """测试历史记录文件路径"""
        config = Config()
        path = config.HISTORY_FILE
        assert os.path.isabs(path)
        assert "chat_history.json" in path

    def test_log_file_path(self):
        """测试日志文件路径"""
        config = Config()
        path = config.LOG_FILE
        assert os.path.isabs(path)
        assert "yuki_log.txt" in path

    def test_cache_dir_path(self):
        """测试缓存目录路径"""
        config = Config()
        path = config.CACHE_DIR
        assert os.path.isabs(path)

    def test_cache_file_path(self):
        """测试缓存文件路径"""
        config = Config()
        path = config.CACHE_FILE
        assert os.path.isabs(path)
        assert "meme_cache.json" in path


class TestCompatibility:
    """测试向后兼容性"""

    def test_backward_compatible_imports(self):
        """测试向后兼容的导入"""
        from config import cfg, _ATTR_MAP, _SECTION_HEADERS
        assert cfg is not None
        assert _ATTR_MAP is not None
        assert _SECTION_HEADERS is not None

    def test_backward_compatible_access(self):
        """测试向后兼容的访问方式"""
        from config import cfg

        # 旧版访问方式应该仍然工作
        assert hasattr(cfg, 'robot_name')
        assert hasattr(cfg, 'master_name')
        assert hasattr(cfg, 'api')
        assert hasattr(cfg, 'model')

        # 计算属性
        assert hasattr(cfg, 'ROBOT_NAME')
        assert hasattr(cfg, 'MASTER_NAME')
        assert hasattr(cfg, 'TARGET_GROUPS')
        assert hasattr(cfg, 'keywords')
        assert hasattr(cfg, 'VECTOR_DB_PATH')
        assert hasattr(cfg, 'EMBED_MODEL')
        assert hasattr(cfg, 'HISTORY_FILE')
        assert hasattr(cfg, 'LOG_FILE')
        assert hasattr(cfg, 'CACHE_DIR')
        assert hasattr(cfg, 'CACHE_FILE')

    def test_backward_compatible_get_method(self):
        """测试向后兼容的 get() 方法"""
        from config import cfg

        # 旧版 get() 方法应该仍然工作
        robot_name = cfg.get("robot_name")
        assert robot_name is not None

        # 嵌套访问
        llm_api_key = cfg.get("api", "llm_api_key")
        assert llm_api_key is not None

    def test_backward_compatible_reload(self):
        """测试向后兼容的 reload() 方法"""
        from config import cfg
        # reload() 方法应该存在
        assert hasattr(cfg, 'reload')
        assert callable(cfg.reload)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
