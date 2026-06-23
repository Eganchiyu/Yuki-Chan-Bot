# main.py
# by: Eganchiyu
import asyncio
import sys
import time

from config import cfg
from core.brain import YukiState
from core.engine import YukiEngine
from core.history_manager import HistoryManager
from core.prompts import sync_system_prompts
from core.session_pipeline import SessionPipeline
from init import load_group_state
from modules.QQNapcatListen.listen_main import configure_runtime, napcat_listen
from modules.message.CQParser import CQCodeParser
from modules.vision.processor import MemeProcessor
from network.ws_connection import BotConnector
from network.ws_sender import MessageSender
from utils.logger import get_logger, setup_logging

setup_logging(debug=cfg.DEBUG)
logger = get_logger("main")

group_active_state = load_group_state()
session_pipeline = None


# ==================== 初始化函数 ====================

def initialize_components():
    """初始化所有组件，返回组件字典。"""
    logger.info("[System] 请确保已运行setup.py进行初始化配置！")
    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在初始化...")
    start_time = time.time()

    connector = BotConnector(cfg.NAPCAT_WS_URL, cfg.NAPCAT_WS_TOKEN)
    sender = MessageSender(connector)
    parser = CQCodeParser(connector)

    from modules.vision.image_store import ImageStore
    image_store = ImageStore()
    meme_processor = MemeProcessor(image_store=image_store)

    yuki = YukiState()
    history_manager = HistoryManager()
    sync_system_prompts(history_manager, yuki)

    logger.info("[System] 开始初始化记忆系统（RAG）...")
    from modules.memory.rag import MemoryRAG
    memory_rag = MemoryRAG()

    logger.info("[System] 开始初始化 Yuki-Memory 结构化检索器...")
    from modules.yuki_memory.retriever import YukiMemoryRetriever
    yuki_memory_retriever = YukiMemoryRetriever()

    from modules.stickers.manager import StickerManager
    sticker_manager = StickerManager()

    engine = YukiEngine(memory_rag, history_manager, yuki, sender)
    engine.sticker_manager = sticker_manager
    engine.image_store = image_store

    end_time = time.time()
    logger.info(f"[System] 初始化完成，耗时 {end_time - start_time:.1f} 秒")

    return {
        "connector": connector,
        "sender": sender,
        "parser": parser,
        "meme_processor": meme_processor,
        "image_store": image_store,
        "yuki": yuki,
        "history_manager": history_manager,
        "memory_rag": memory_rag,
        "yuki_memory_retriever": yuki_memory_retriever,
        "sticker_manager": sticker_manager,
        "engine": engine,
    }


def warmup_groups(yuki, history_manager):
    """预热群组：初始化巡检名单，预载历史中的群聊 ID 和最后消息时间。"""
    history_manager.load()
    for cid in cfg.TARGET_GROUPS:
        yuki.last_message_time[str(cid)] = time.time()
        current_e = yuki.update_energy(str(cid))
        yuki.update_desire_to_reply(str(cid))
        logger.info(
            f"[System] 预热群组 {str(cid)}: 精力 {current_e:.1f}, "
            f"初始欲望 {yuki.desire_to_start_topic.get(str(cid), 0)}%"
        )
    logger.debug(f"已预载 {len(yuki.last_message_time)} 个群组到巡检名单")


def start_context_debug_webui_if_enabled():
    """按环境变量在主进程内启动 Context Debug WebUI。"""
    import os

    enabled = os.getenv("YUKI_CONTEXT_DEBUG_WEBUI", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return
    host = os.getenv("YUKI_CONTEXT_DEBUG_HOST", "127.0.0.1")
    port = int(os.getenv("YUKI_CONTEXT_DEBUG_PORT", "8777"))
    try:
        from modules.debug.webui_server import start_background_server
        start_background_server(host=host, port=port)
        logger.info(f"[ContextDebug] WebUI 已启动: http://{host}:{port}/")
    except Exception as exc:
        logger.error(f"[ContextDebug] WebUI 启动失败: {exc}")


async def main_process(
    chat_id,
    mode,
    debounce_flag=True,
    force_reply=None,
    ice_break=False,
    message_obj=None,
):
    """兼容旧入口：把处理请求交给按 chat_id 串行运行的会话泵。"""
    if session_pipeline is None:
        logger.error("[Pipeline] session_pipeline 尚未初始化，无法处理消息。")
        return
    task = await session_pipeline.enqueue_message(
        chat_id,
        mode,
        message_obj=message_obj,
        debounce_flag=debounce_flag,
        force_reply=force_reply,
        ice_break=ice_break,
    )
    if task:
        await task


# ==================== 资源清理 ====================

_cleanup_done = False


def _do_cleanup():
    """同步清理资源：关闭全局 aiohttp Session。"""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    logger.info("[Main] 正在清理资源...")
    try:
        cfg._save_raw()
        logger.info("[Main] 配置已自动对齐保存")
    except Exception as e:
        logger.error(f"[Main] 保存配置时出错: {e}")
    try:
        from utils.llm_client import close_global_session
        loop = asyncio.new_event_loop()
        loop.run_until_complete(close_global_session())
        loop.close()
        logger.info("[Main] 资源清理完成")
    except Exception as e:
        logger.error(f"[Main] 清理资源时出错: {e}")


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    import atexit
    import os

    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    atexit.register(_do_cleanup)

    try:
        components = initialize_components()
        session_pipeline = SessionPipeline(components, group_active_state)
        components["engine"].process_callback = main_process
        configure_runtime(components, session_pipeline, group_active_state, logger)
        start_context_debug_webui_if_enabled()

        choice = input("[System] 选择模式：1. 私聊模式  2. 群聊模式（默认）\n请输入数字: ").strip()
        mode = "private" if choice == "1" else "group"

        if mode == "group":
            warmup_groups(components["yuki"], components["history_manager"])

        asyncio.run(napcat_listen(mode))

    except KeyboardInterrupt:
        logger.info("[Main] 收到中断信号，正在退出...")
        sys.exit(0)

    except (FileNotFoundError, ImportError, KeyError) as e:
        logger.error("=" * 50)
        logger.error("启动失败: 环境配置不完整")
        logger.error(f"错误详情: {e}")
        logger.error("-" * 50)
        logger.error("建议操作:")
        logger.error("  请运行 [ python setup.py ] 进行一键修复/配置")
        logger.error("  该脚本会自动安装依赖、生成配置文件并下载模型")
        logger.error("=" * 50 + "\n")
        sys.exit(1)

    except Exception as e:
        logger.critical(f"发生未知致命错误: {e}")
        sys.exit(1)

    finally:
        _do_cleanup()
