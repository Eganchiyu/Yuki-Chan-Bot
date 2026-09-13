# main.py
# by: Eganchiyu
import asyncio
import os
import sys
import time

from config import cfg, save_config
from core.brain import YukiState
from core.engine.engine import YukiEngine
from core.history_manager import HistoryManager
from core.prompts import sync_system_prompts
from core.session_pipeline import SessionPipeline
from init import load_group_state
from modules.QQNapcatListen.listen_main import napcat_listen
from core.tools.tools_status import start_monitor_service, stop_monitor_service
from modules.vision.processor import MemeProcessor
from network.napcat import NapCatGateway
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

    # NapCatGateway 一个对象同时承担收发；下游统一以 sender 这个名字使用它
    sender = NapCatGateway(cfg.NAPCAT_WS_URL, cfg.NAPCAT_WS_TOKEN)

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
        "sender": sender,
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
    """启动 Live2D 桌宠窗口，并把输入接入主会话管线。

    默认关闭。开启方式二选一：
    - 环境变量 YUKI_DESKTOP_PET=1（优先级最高，可临时开关）
    - modules/LiveYukiL2D/config.json 里把 desktopPet.enabled 改成 true

    任一处显式关闭都不会拉起 Electron 窗口。本函数会阻塞数秒（起 HTTP 服务 +
    拉起 Electron），调用方应放到线程里执行。
    """
    import os

    flag = os.getenv("YUKI_DESKTOP_PET", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        logger.info("[DesktopPet] 已通过 YUKI_DESKTOP_PET 关闭")
        return

    explicit_on = flag in {"1", "true", "yes", "on"}

    try:
        from modules.LiveYukiL2D import desktop as desktop_pet

        if not explicit_on and not desktop_pet.config_enabled():
            logger.info(
                "[DesktopPet] 桌宠默认关闭，跳过启动"
                "（开启：设置 YUKI_DESKTOP_PET=1，或把 "
                "modules/LiveYukiL2D/config.json 的 desktopPet.enabled 改为 true）"
            )
            return

        proc = desktop_pet.main(session_pipeline=pipeline, pipeline_loop=pipeline_loop)
        if proc is None:
            logger.error("[DesktopPet] Electron 窗口未能启动，详见上方日志；主程序继续运行")
        else:
            logger.info(f"[DesktopPet] Live2D 桌宠已启动 (pid={proc.pid})")
    except Exception as exc:
        logger.error(f"[DesktopPet] 启动失败: {exc}")


async def run_runtime() -> None:
    try:
        # 桌宠启动包含起 aiohttp 服务（最长等 3 秒）和拉起 Electron，
        # 放到线程里跑，避免阻塞消息管线的事件循环。
        await asyncio.to_thread(
            start_desktop_pet_if_enabled, session_pipeline, asyncio.get_running_loop()
        )
        await napcat_listen(session_pipeline.sender, session_pipeline, "mixed")
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


# ==================== 单实例守卫 ====================

_instance_lock = None  # 持有文件句柄，随进程退出自动释放锁


def acquire_single_instance_lock() -> bool:
    """同一台机器只允许一个 Yuki 实例，避免两个实例同时消费 NapCat 事件。

    用 data/yuki.lock 上的 flock：进程结束（含被 kill）自动释放，不会留下死锁文件。
    需要并行跑第二个实例调试时，设置 YUKI_ALLOW_MULTI_INSTANCE=1。
    """
    global _instance_lock
    if os.getenv("YUKI_ALLOW_MULTI_INSTANCE", "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.warning("[System] YUKI_ALLOW_MULTI_INSTANCE 已开启，跳过单实例检查")
        return True
    try:
        import fcntl
    except ImportError:
        return True  # 非 POSIX 平台不做限制

    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "yuki.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.write(str(os.getpid()))
    handle.flush()
    _instance_lock = handle
    return True


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    import atexit

    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    atexit.register(_do_cleanup)

    if not acquire_single_instance_lock():
        logger.critical(
            "[Main] 已有 Yuki 实例在运行（data/yuki.lock 被占用），本次启动中止。"
            "如需并行调试请设置 YUKI_ALLOW_MULTI_INSTANCE=1"
        )
        sys.exit(1)

    try:
        components = initialize_components()
        session_pipeline = SessionPipeline(components, group_active_state)
        components["engine"].process_callback = main_process
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
