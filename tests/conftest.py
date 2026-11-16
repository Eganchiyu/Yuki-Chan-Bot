# tests/conftest.py
"""pytest 公共配置：把项目根目录放上 sys.path，统一控制台编码。

各测试文件不再需要自己写 sys.path hack。
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


@pytest.fixture(autouse=True)
def isolate_group_state(tmp_path, monkeypatch):
    """测试不许碰生产 `data/group_state.json`。

    背景（2026-11-16）：`/关闭` `/强制关闭` 的用例会走 `_set_group_active` →
    `save_group_state`，在容器里跑 pytest 时直接把生产的群开关文件覆盖成测试数据。
    这里把落盘路径指到临时文件。
    """
    import init
    from core import sft_logger

    monkeypatch.setattr(init, "GROUP_STATE_FILE", str(tmp_path / "group_state.json"))
    monkeypatch.setattr(sft_logger.sft_trace_logger, "base_dir", str(tmp_path / "sft"))
