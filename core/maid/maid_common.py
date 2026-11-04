import os

from utils.logger import get_logger

logger = get_logger("maid")

# --- 目录初始化 ---
SKILLS_DIR = "skills"
WORKSPACE_DIR = "workspace"
TASKS_DIR = "tasks"
LOGS_DIR = "logs"

TASK_STATE_DIR = os.path.join(TASKS_DIR, "state")
TASK_INDEX_FILE = os.path.join(LOGS_DIR, "task_index.jsonl")

for d in [SKILLS_DIR, WORKSPACE_DIR, TASKS_DIR, LOGS_DIR, TASK_STATE_DIR]:
    os.makedirs(d, exist_ok=True)

MAID_MAX_WALL_SECONDS = 900   # 单任务墙钟上限，兜底失控任务
