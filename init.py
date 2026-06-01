import json
import os
import sys

from main import GROUP_STATE_FILE, logger


def load_group_state():
    if os.path.exists(GROUP_STATE_FILE):
        try:
            with open(GROUP_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[System] 读取群聊状态失败: {e}")
    return {}


def save_group_state(state):
    try:
        os.makedirs("data", exist_ok=True)
        with open(GROUP_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
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
