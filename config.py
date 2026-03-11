# config.py
import aiohttp
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()
# ================= 安全配置 =================
FILTER_LONG_MESSAGES = True  # 是否过滤过长消息，防止token炸弹
MAX_MESSAGE_LENGTH = 200  # 最大消息长度，防止token炸弹
MESSAGE_TRUNCATE_SUFFIX = "...（长消息）"

# ================= 日记触发配置 =================
DIARY_IDLE_SECONDS = 120          # 空闲触发时间（秒），2分钟
DIARY_MIN_TURNS = 20               # 最小对话轮数（非系统消息条数）
DIARY_MAX_LENGTH = 100             # 保底历史长度阈值（超过则强制写日记）

# ================= RAG 记忆配置 =================
VECTOR_DB_PATH = "./yuki_memory"          # 向量数据库路径
# EMBED_MODEL = "shibing624/text2vec-base-chinese"  # 中文嵌入模型
EMBED_MODEL = "./models/text2vec-base-chinese"  # 本地模型路径
RETRIEVAL_TOP_K = 20                        # 每次检索返回日记条数
KEEP_LAST_DIALOGUE = 5                     # 保留最近对话条数（短期记忆）
DIARY_THRESHOLD = 0.25                   # 日记相关性阈值（越低越严格）
# ================= API配置 =================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
# DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_BASE_URL = "https://api.ytea.top/v1"
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "").strip()
SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
OPENAI_API_KEY = DEEPSEEK_API_KEY  # 复用 DeepSeek 的 Key
OPENAI_API_URL = "https://api.ytea.top/v1/chat/completions"

# 调试输出（确认后可以删除）
if not DEEPSEEK_API_KEY:
    print("⚠️ 警告: DEEPSEEK_API_KEY 未设置")
if not SILICONFLOW_API_KEY:
    print("⚠️ 警告: SILICONFLOW_API_KEY 未设置")

# ================= 连接配置 =================
NAPCAT_WS_URL = "ws://127.0.0.1:3001"

# ================= 目标配置 =================
TARGET_QQ = 2962538973
# TARGET_GROUP = 1034986009
TARGET_GROUPS = [1057020972, 1034986009, 1085409165, 742134223]   # 示例
# TARGET_GROUPS = [1085409165]
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
DEBOUNCE_TIME = 18

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

# ================= 精力值配置 =================
INITIAL_ENERGY = 100
MAX_ENERGY = 100.0
RECOVERY_PER_MIN = 0.8
COST_PER_REPLY = 4
MIN_ACTIVE_ENERGY = 13.0

# ================= 并发配置 =================
MAX_CONCURRENT_MEME = 1

# ================= 调试配置 =================
DEBUG = True