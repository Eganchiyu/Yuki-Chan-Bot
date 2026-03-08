# config.py
import aiohttp
import os

# ================= 日记触发配置 =================
DIARY_IDLE_SECONDS = 120          # 空闲触发时间（秒），2分钟
DIARY_MIN_TURNS = 20               # 最小对话轮数（非系统消息条数）
DIARY_MAX_LENGTH = 100             # 保底历史长度阈值（超过则强制写日记）

# ================= RAG 记忆配置 =================
VECTOR_DB_PATH = "./yuki_memory"          # 向量数据库路径
EMBED_MODEL = "shibing624/text2vec-base-chinese"  # 中文嵌入模型
RETRIEVAL_TOP_K = 20                        # 每次检索返回日记条数
KEEP_LAST_DIALOGUE = 5                     # 保留最近对话条数（短期记忆）

# ================= API配置 =================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") # 填入自己的 API_KEY
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
SILICONFLOW_API_KEY = "sk-iasmjtktptrnmmhdxevwwlgyxdjfveixktnmkvhkcyrzocxr" # 填入自己的 API_KEY
SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

# ================= 连接配置 =================
NAPCAT_WS_URL = "ws://127.0.0.1:3001"

# ================= 目标配置 =================
TARGET_QQ = 2962538973
# TARGET_GROUP = 1034986009
TARGET_GROUPS = [1057020972, 1034986009, 1085409165]   # 示例
# TARGET_GROUP = 1057020972
# TARGET_GROUP = 1085409165 #测试群
# TARGET_GROUP = 818038143 #薄脆原味生态圈
# TARGET_GROUP = 742134223

# ================= 文件配置 =================
HISTORY_FILE = "chat_history.json"
LOG_FILE = "yuki_chat_all_nekonochi.log"
CACHE_DIR = "meme_cache"
CACHE_FILE = "meme_cache.json"

# ================= 时间配置 =================
DEBOUNCE_TIME = 8
DIARY_THRESHOLD = 50
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

# ================= 精力值配置 =================
INITIAL_ENERGY = 100.0
MAX_ENERGY = 100.0
RECOVERY_PER_MIN = 0.8
COST_PER_REPLY = 4
MIN_ACTIVE_ENERGY = 13.0

# ================= 并发配置 =================
MAX_CONCURRENT_MEME = 1

# ================= 调试配置 =================
DEBUG = True