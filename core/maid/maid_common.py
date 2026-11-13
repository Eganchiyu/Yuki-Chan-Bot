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

# 单任务墙钟上限，兜底失控任务。
# 容器侧总等待 = 本值 + 120s 收尾余量（见 core/maid/maid_harness.py 的 deadline），
# 机主 2026-11-12 要求总超时 1020s（900+120）→ 600s（480+120），故取 480。
MAID_MAX_WALL_SECONDS = 480
