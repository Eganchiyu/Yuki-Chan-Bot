# config.py
import aiohttp
import os
from dotenv import load_dotenv
load_dotenv(verbose=True)  # 显示加载信息

# ================= 安全配置 =================
MAX_MESSAGE_LENGTH: int = 150  # 最大消息长度，防止token炸弹

# ================= 日记触发配置 =================
DIARY_IDLE_SECONDS = 120          # 空闲触发时间（秒），2分钟
DIARY_MIN_TURNS = 15               # 最小对话轮数（非系统消息条数）
DIARY_MAX_LENGTH = 50             # 保底历史长度阈值（超过则强制写日记）

# ================= RAG 记忆配置 =================

RETRIEVAL_TOP_K = 20                        # 每次检索返回日记条数
KEEP_LAST_DIALOGUE = 10                     # 保留最近对话条数（短期记忆）
# ================= API配置 =================
LLM_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
IMAGE_PROCESS_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

BACKUP_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
IMAGE_PROCESS_API_KEY = os.getenv("IMAGE_PROCESS_API_KEY", "").strip()
MASTER_NAME = os.getenv("MASTER_NAME", "主人") # 默认叫主人，也可以改

# 主对话模型 (例如: deepseek-chat, gpt-4o)
LLM_MODEL = "deepseek-chat"
BACKUP_MODEL = "deepseek-chat"

# 图像分析模型 (如果有专门的视觉模型需求)
# 注意！！如果没有多模态模型，想关闭视觉识别，就将字段留空。如下面所示：
#VISION_MODEL = ""
VISION_MODEL = "qwen3-vl-flash"

ROBOT_NAME = os.getenv("ROBOT_NAME", "yuki").lower()

# ================= 连接配置 =================
NAPCAT_WS_URL = "ws://127.0.0.1:3001"
MAX_RETRIES = 3
# ================= 目标配置 =================
TARGET_QQ = int(os.getenv("TARGET_QQ"))

# --- 数组（列表）转换 ---
raw_groups = os.getenv("TARGET_GROUPS", "")
if raw_groups:
    # 逻辑：分割字符串 -> 去除空格 -> 转换为 int -> 转为 list
    TARGET_GROUPS = [int(g.strip()) for g in raw_groups.split(",") if g.strip()]
else:
    # 如果 env 里没写，给一个默认列表
    TARGET_GROUPS = []
# ================= 文件配置 =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VECTOR_DB_PATH = os.path.join(BASE_DIR, "yuki_memory")
EMBED_MODEL = os.path.join(BASE_DIR, "models", "text2vec-base-chinese")

HISTORY_FILE = os.path.join(BASE_DIR,"data", "chat_history.json")
LOG_FILE = os.path.join(BASE_DIR,"data", "yuki_log.txt")
CACHE_DIR = os.path.join(BASE_DIR,"data")
CACHE_FILE = os.path.join(CACHE_DIR, "meme_cache.json")

# ================= 时间配置 =================
DEBOUNCE_TIME = 32
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

# ================= 精力值配置 =================
INITIAL_ENERGY = 100
MAX_ENERGY = 100.0
RECOVERY_PER_MIN = 0.8
COST_PER_REPLY = 6
MIN_ACTIVE_ENERGY = 25

SENSITIVITY = 0.12
DECAY_LEVEL = 0.65
SIGMOID_CENTRE = 50.00
SIGMOID_ALPHA = 0.08

keywords = ["主人", "哥哥", ROBOT_NAME]
# ================= 并发配置 =================
MAX_CONCURRENT_MEME = 3

# ================= 调试配置 =================
DEBUG = True

