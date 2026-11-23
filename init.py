import os
import sys

from utils.json_store import atomic_write_json, read_json_cached
from utils.logger import get_logger

GROUP_STATE_FILE = "data/group_state.json"
logger = get_logger("init")


def load_group_state():
    data = read_json_cached(GROUP_STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def default_group_active() -> bool:
    """群应答开关的缺省值：**休眠**。

    历史教训（2026-11-16）：以前缺省 True，`data/group_state.json` 只要丢掉一个
    键，那个被 `/关闭` 过的群就会在重启后复活。缺省改成休眠后，任何丢失都只会
    变成「安静」，不会变成「乱说话」。
    """
    return False


def ensure_group_state(state: dict, groups) -> dict:
    """把目标群全量补齐并落盘：缺条目按休眠处理。

    `group_state.json` 是「部分映射」（只有被显式切过的群才有键），这里在启动时
    把 `TARGET_GROUPS` 全部写进去，既固化缺省值，也让文件本身可读、可人工核对。
    只在内容有变化时落盘。
    """
    state = dict(state or {})
    changed = False
    for gid in groups or []:
        key = str(gid)
        if key not in state:
            state[key] = default_group_active()
            changed = True
    if changed:
        save_group_state(state)
        logger.info(f"[System] 群开关状态已补齐到 {len(state)} 个群（缺省=休眠）")
    return state


def save_group_state(state):
    try:
        atomic_write_json(GROUP_STATE_FILE, state, indent=2, fsync=True)
    except Exception as e:
        logger.error(f"[System] 保存群聊状态失败: {e}")


def check_config():
    """在启动前进行最后的物理检查"""
    if not os.path.exists("configs/config.yaml"):
        env_choice = input("检测到尚未进行基础配置，是否现在运行配置向导？(y/n): ")
        if env_choice.lower() == 'y':
            from setup import quick_setup
            quick_setup(0)  # 以刷新模式运行
        else:
            logger.warning("请手动运行 python setup.py 后再启动。")
            sys.exit(0)

    required_files = ["configs/config.yaml", "blacklist.txt", "./models/text2vec-base-chinese/config.json"]
    for f in required_files:
        if not os.path.exists(f):
            # 抛出异常，触发下面的错误引导
            raise FileNotFoundError(f"关键配置文件或模型缺失: {f}")
