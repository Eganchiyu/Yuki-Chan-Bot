# main.py
# by: Eganchiyu
import asyncio
import sys
import time

from config import cfg, save_config
from core.brain import YukiState
from core.engine.engine import YukiEngine
from core.history_manager import HistoryManager
from core.prompts import sync_system_prompts
from core.session_pipeline import SessionPipeline
from init import load_group_state
from modules.QQNapcatListen.listen_main import configure_runtime, napcat_listen
from modules.message.CQParser import CQCodeParser
from modules.system_state.monitor import start_monitor_service, stop_monitor_service
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

    logger.info("[System] 开始初始化表情包系统...")
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
        "sticker_manager": sticker_manager,
        "engine": engine,
    }


def warmup_groups(yuki, history_manager):
    """预热群组：初始化巡检名单并预载历史缓存。"""
    history_manager.preload()
    now = time.time()
    for cid in cfg.TARGET_GROUPS:
        cid_str = str(cid)
        yuki.last_message_time[cid_str] = now
        current_e = yuki.update_energy(cid_str)
        yuki.update_desire_to_reply(cid_str)
        logger.info(
            f"[System] 预热群组 {cid_str}: 精力 {current_e:.1f}, "
            f"初始欲望 {yuki.desire_to_start_topic.get(cid_str, 0)}%"
        )
    logger.debug(f"已预载 {len(yuki.last_message_time)} 个群组到巡检名单")


def start_context_debug_webui_if_enabled():
    """按环境变量在主进程内启动 Context Debug WebUI。"""
    import os

    # enabled = os.getenv("YUKI_CONTEXT_DEBUG_WEBUI", "").strip().lower()

    host = os.getenv("YUKI_CONTEXT_DEBUG_HOST", "127.0.0.1")
    port = int(os.getenv("YUKI_CONTEXT_DEBUG_PORT", "8777"))
    try:
        from modules.debug.webui_server import start_background_server
        start_background_server(host=host, port=port)
        logger.info(f"[ContextDebug] WebUI 已启动: http://{host}:{port}/")
    except Exception as exc:
        logger.error(f"[ContextDebug] WebUI 启动失败: {exc}")


def start_desktop_pet_if_enabled(pipeline, pipeline_loop):
    """启动 Live2D 桌宠窗口，并把输入接入主会话管线。"""
    import os

    enabled = os.getenv("YUKI_DESKTOP_PET", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.info("[DesktopPet] 已通过 YUKI_DESKTOP_PET 关闭")
        return

    try:
        from modules.LiveYukiL2D.desktop import main as run_desktop_pet
        run_desktop_pet(session_pipeline=pipeline, pipeline_loop=pipeline_loop)
        logger.info("[DesktopPet] Live2D 桌宠已启动")
    except Exception as exc:
        logger.error(f"[DesktopPet] 启动失败: {exc}")


async def run_runtime() -> None:
    try:
        start_desktop_pet_if_enabled(session_pipeline, asyncio.get_running_loop())
        await napcat_listen("mixed")
    finally:
        from utils.llm_client import close_global_session
        await close_global_session()


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
        stop_monitor_service()
    except Exception as e:
        logger.error(f"[Main] 停止监控服务时出错: {e}")
    try:
        save_config(cfg)
        logger.info("[Main] 配置已自动对齐保存")
    except Exception as e:
        logger.error(f"[Main] 保存配置时出错: {e}")
    if session_pipeline is not None:
        try:
            session_pipeline.history_manager.flush()
        except Exception as e:
            logger.error(f"[Main] 刷新历史缓存时出错: {e}")
    logger.info("[Main] 资源清理完成")


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

        warmup_groups(components["yuki"], components["history_manager"])

        start_monitor_service()
        asyncio.run(run_runtime())

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
