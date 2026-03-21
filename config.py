# config.py
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv(verbose=True)  # 显示加载信息
# ================= 安全配置 =================
MAX_MESSAGE_LENGTH: int = 200  # 最大消息长度，防止token炸弹

# ================= 日记触发配置 =================
DIARY_IDLE_SECONDS = 120          # 空闲触发时间（秒），2分钟
DIARY_MIN_TURNS = 10               # 最小对话轮数（非系统消息条数）
DIARY_MAX_LENGTH = 50             # 保底历史长度阈值（超过则强制写日记）

# ================= RAG 记忆配置 =================
VECTOR_DB_PATH = "before_refactor/yuki_memory"  # 向量数据库路径
# EMBED_MODEL = "shibing624/text2vec-base-chinese"  # 中文嵌入模型
EMBED_MODEL = "./models/text2vec-base-chinese"  # 本地模型路径
RETRIEVAL_TOP_K = 20                        # 每次检索返回日记条数
KEEP_LAST_DIALOGUE = 5                     # 保留最近对话条数（短期记忆）
# ================= API配置 =================
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
TEATOP_BASE_URL = "https://api.ytea.top/v1"
TEATOP_API_URL = "https://api.ytea.top/v1/chat/completions"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
TEATOP_API_KEY = os.getenv("TEATOP_API_KEY", "").strip()
if not TEATOP_API_KEY and not DEEPSEEK_API_KEY:
    print("Warning: 未检测到任何有效的 API KEY，请检查 .env 文件。")
# ================= 连接配置 =================
NAPCAT_WS_URL = "ws://127.0.0.1:3001"

# ================= 目标配置 =================
TARGET_QQ = 737337230
# TARGET_GROUP = 1034986009 #猫猫窝
TARGET_GROUPS = [1057020972, 782427668]   # 示例
# TARGET_GROUPS = [782427668]
# TARGET_GROUP = 1057020972 #ncbot乐园
# TARGET_GROUP = 1085409165 #测试群
# TARGET_GROUP = 818038143 #薄脆原味生态圈
# TARGET_GROUP = 742134223 #C406宿舍
# 1056258919 # downs群
# 1057868210 # mc群

# ================= 文件配置 =================
# HISTORY_FILE = "before_refactor/chat_history.json"
# LOG_FILE = "before_refactor/yuki_chat_all_319.log"
# CACHE_DIR = "before_refactor/meme_cache"
# CACHE_FILE = "before_refactor/meme_cache.json"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VECTOR_DB_PATH = os.path.join(BASE_DIR, "yuki_memory")
EMBED_MODEL = os.path.join(BASE_DIR, "models", "text2vec-base-chinese")

HISTORY_FILE = os.path.join(BASE_DIR,"data", "chat_history.json")
LOG_FILE = os.path.join(BASE_DIR,"data", "yuki_log.txt")
CACHE_DIR = os.path.join(BASE_DIR,"data")
CACHE_FILE = os.path.join(CACHE_DIR, "meme_cache.json")

# ================= 时间配置 =================
DEBOUNCE_TIME = 25
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

# ================= 精力值配置 =================
INITIAL_ENERGY = 100
MAX_ENERGY = 100.0
RECOVERY_PER_MIN = 0.8
COST_PER_REPLY = 5
MIN_ACTIVE_ENERGY = 25.0

SENSITIVITY = 0.2
DECAY_LEVEL = 0.6
SIGMOID_CENTRE = 50.00
SIGMOID_ALPHA = 0.08

# ================= 并发配置 =================
MAX_CONCURRENT_MEME = 1

# ================= 调试配置 =================
DEBUG = True