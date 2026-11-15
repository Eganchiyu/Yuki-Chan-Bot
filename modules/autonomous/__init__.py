# modules/autonomous/__init__.py
"""自主沙盒：模式化多主循环下的 debate / workshop 两种非聊天模式。

依赖 `core/modes`（模式层）与 `core/focus`（子聚焦），不反向被它们依赖。
"""
from modules.autonomous.storage import (  # noqa: F401
    daily_memory_store,
    diary_seed_sampler,
    group_name_cache,
    init_data_dir,
    memo_store,
    state_store,
    work_diary_store,
    work_session_store,
)

__all__ = [
    "daily_memory_store",
    "diary_seed_sampler",
    "group_name_cache",
    "init_data_dir",
    "memo_store",
    "state_store",
    "work_diary_store",
    "work_session_store",
    "AutonomousCoordinator",
]


def __getattr__(name):
    """惰性导出 coordinator，避免 storage 之外的模块在导入期就拉起 LLM/网络依赖。"""
    if name == "AutonomousCoordinator":
        from modules.autonomous.coordinator import AutonomousCoordinator

        return AutonomousCoordinator
    raise AttributeError(name)
