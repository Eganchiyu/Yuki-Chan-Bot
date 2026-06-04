# main.py
# by: Eganchiyu
import asyncio
import re
import time
import datetime
import sys

from core.brain import YukiState
from core.engine import YukiEngine
from core.history_manager import HistoryManager
from core.prompts import sync_system_prompts
from init import load_group_state
from modules.QQNapcatListen.listen_main import napcat_listen
from modules.message.CQParser import CQCodeParser
from modules.vision.processor import MemeProcessor
from network.ws_connection import BotConnector
from network.ws_sender import MessageSender
from config import cfg
from utils.logger import setup_logging, get_logger

setup_logging(debug=cfg.DEBUG)
logger = get_logger("main")

# === 新增：群聊动态开关状态管理 ===
GROUP_STATE_FILE = "data/group_state.json"

# 初始化全局变量：消息缓冲和定时任务
real_time_debounce_time = cfg.DEBOUNCE_TIME

group_active_state = load_group_state()

# 插件分为三类：
# 1. 信息流入类插件： NapcatListen
# 2. 信息流出类插件： MessageSender
# 3. 功能性插件： 记忆查询

class FunctionRegistry:
    """Function Call 注册中心：扫描、注册、提供 tools 列表"""

    def __init__(self):
        self._functions = {}  # name -> function_schema
        self._handlers = {}   # name -> handler_function

    def register(self, schema: dict, handler):
        """注册一个 function tool"""
        name = schema["function"]["name"]
        self._functions[name] = schema
        self._handlers[name] = handler
        logger.info(f"[FunctionRegistry] 注册 function: {name}")

    def unregister(self, name: str):
        """注销一个 function tool"""
        if name in self._functions:
            del self._functions[name]
            del self._handlers[name]
            logger.info(f"[FunctionRegistry] 注销 function: {name}")

    def get_tools(self) -> list:
        """获取所有已注册的 tools 列表（用于 LLM 请求）"""
        return list(self._functions.values())

    def get_handler(self, name: str):
        """获取指定 function 的执行函数"""
        return self._handlers.get(name)

    def list_functions(self) -> list:
        """列出所有已注册的 function 名称"""
        return list(self._functions.keys())

    def scan_and_register(self, tools_list: list, handlers_dict: dict):
        """批量扫描并注册 tools（先清空再扫描）"""
        self._functions.clear()
        self._handlers.clear()
        logger.info("[FunctionRegistry] 已清空所有注册")
        for tool in tools_list:
            name = tool["function"]["name"]
            if name in handlers_dict:
                self.register(tool, handlers_dict[name])
            else:
                logger.warning(f"[FunctionRegistry] tool {name} 缺少 handler，跳过注册")







# ==================== 初始化函数 ====================

def initialize_components():
    """初始化所有组件，返回组件字典"""
    logger.info("[System] 请确保已运行setup.py进行初始化配置！")
    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在初始化...")
    start_time = time.time()

    # 加载与Napcat通信的Websocket服务
    connector = BotConnector(cfg.NAPCAT_WS_URL, cfg.NAPCAT_WS_TOKEN)
    # 实例化消息发送器
    sender = MessageSender(connector)
    # 实例化CQ码处理器
    parser = CQCodeParser(connector)
    
    # 实例化表情处理器
    meme_processor = MemeProcessor()
    # 实例化Yuki状态
    yuki = YukiState()
    # 实例化历史记录管理器
    history_manager = HistoryManager()
    # 更新系统提示词到历史记录中，确保最新的设定被加载（防止被旧记录覆盖）
    sync_system_prompts(history_manager, yuki)
    
    logger.info("[System] 开始初始化记忆系统（RAG）...")
    from modules.memory.rag import MemoryRAG
    # 初始化向量记忆库
    memory_rag = MemoryRAG()
    
    # 实例化表情包管理器
    from modules.stickers.manager import StickerManager
    sticker_manager = StickerManager()
    
    # 实例化Yuki主引擎
    engine = YukiEngine(memory_rag, history_manager, yuki, sender)
    engine.process_callback = main_process
    engine.sticker_manager = sticker_manager
    
    end_time = time.time()
    logger.info(f"[System] 初始化完成，耗时 {end_time - start_time:.1f} 秒")

    return {
        "connector": connector,
        "sender": sender,
        "parser": parser,
        "meme_processor": meme_processor,
        "yuki": yuki,
        "history_manager": history_manager,
        "memory_rag": memory_rag,
        "sticker_manager": sticker_manager,
        "engine": engine,
    }


def warmup_groups(yuki, history_manager):
    """预热群组：初始化巡检名单，预载历史中的群聊ID和最后消息时间"""
    h_dict = history_manager.load()
    for cid in cfg.TARGET_GROUPS:
        yuki.last_message_time[str(cid)] = time.time()
        current_e = yuki.update_energy(str(cid))
        yuki.update_desire_to_reply(str(cid))
        logger.info(
            f"[System] 预热群组 {str(cid)}: 精力 {current_e:.1f}, 初始欲望 {yuki.desire_to_start_topic.get(str(cid), 0)}%")
    logger.debug(f"已预载 {len(yuki.last_message_time)} 个群组到巡检名单")


# 启动主流程 支持热插拔和热重载插件
async def start_main_process():
    """启动主流程，监听消息并处理"""
    # 初始化Yuki引擎
    pass
    

async def main_process(chat_id, mode, debounce_flag=True, force_reply=None):
    """处理缓冲中的消息，进行API交互和回复 """
    global real_time_debounce_time
    if debounce_flag:
        await asyncio.sleep(real_time_debounce_time)  # 防抖等待，合并短时间内的多条消息
    else:
        await asyncio.sleep(0.5)

    # ================= 新增：醒来后的终极拦截 =================
    if mode == "group" and not group_active_state.get(str(chat_id), True):
        logger.info(f"[System] [{chat_id}] 协程醒来，但群已被静音，丢弃遗留消息并退出。")
        yuki.pop_buffer(chat_id)  # 把缓存清空以绝后患
        return
    # ==========================================================

    real_time_debounce_time = cfg.DEBOUNCE_TIME  # 重置防抖时间，准备处理下一轮消息
    message_objs = yuki.pop_buffer(chat_id)  # 此时拿到的是 list[dict]
    if not message_objs and not force_reply:
        return
    # 提高群聊的活跃度
    first_time = time.time()
    await yuki.boost_activity(chat_id)
    # 视觉理解总处理
    all_contents = [m["content"] for m in message_objs]
    combined_text = "\n".join(all_contents)

    # 接收返回的 modified_text 和 字典列表 images_info
    modified_text, images_info = meme_processor.extract_urls_from_text(combined_text)

    if images_info:
        understood_contents = []
        for img in images_info:
            url = img["url"]
            is_meme = img["is_meme"]

            # 1. 看图权限：无论是不是表情包，都让视觉模型（VLM）看一眼并理解
            result = await meme_processor.understand_from_url(url)
            understood_contents.append(result)

            # 2. 存图权限：【核心防线】只有确认为表情包 (is_meme 为 True)，才允许后台偷图入库！
            if is_meme and hasattr(engine, 'sticker_manager'):
                clean_url = url.replace("&amp;", "&")  # 清洗 URL 防 400 报错
                # asyncio.create_task(
                #     engine.sticker_manager.ingest_sticker(image_ref=clean_url, chat_id=chat_id, owner="群友")
                # )
            elif not is_meme:
                logger.info("[System] 拦截到非表情包图片，仅作视觉理解，不入库学习。")

        combined_text = modified_text
        for content in understood_contents:
            combined_text = combined_text.replace("[图片占位符]", content, 1)

    # 剩下的CQ码文本解析（@、回复等）交给 parser
    combined_text = await parser.parse_all_cq_codes(combined_text)
    combined_text = combined_text.replace("\n", "  ").strip()
    logger.info(f"[{chat_id}] 收到消息{combined_text}")
    history_manager.append_to_log(chat_id, "User/Group", combined_text)

    logger.info("[System] 加载上下文信息...")
    # 加载上下文信息
    history_dict = history_manager.load()
    chat_id = str(chat_id)

    # 【修复后】稳健的系统提示词初始化与注入
    if chat_id not in history_dict or not history_dict[chat_id]:
        # 情况1：完全没记录，或者列表为空，直接初始化一个包含 system prompt 的新列表
        history_dict[chat_id] = [{"role": "system", "content": yuki.get_setting(mode)}]
    elif history_dict[chat_id][0].get("role") != "system":
        # 情况2：有记录但第一条不是 system prompt，则在最前面插入（而不是覆盖掉用户原本的消息）
        history_dict[chat_id].insert(0, {"role": "system", "content": yuki.get_setting(mode)})
    # 添加当前消息到上下文池
    current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
    history_dict[chat_id].append({
        "role": "user",
        "content": combined_text,
        "time": current_time_str  # 新增独立字段
    })

    logger.info("[System] 加载完成")

    if (mode == "group") and (not await engine.decide_to_reply(history_dict[chat_id], message_objs, chat_id,force_reply = force_reply)):
        # 保存获取的上下文信息
        history_manager.save(history_dict)
        logger.info(f"[System] {cfg.ROBOT_NAME.title()} 决定继续潜水...")
        return

    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在回忆...")

    # 检索相关记忆总用法（包含关键词提取和语义向量匹配）
    dynamic_top_k = 10 if len(combined_text) > 100 else 8
    relevant_diaries = memory_rag.search_diaries(combined_text, chat_id=chat_id, top_k=dynamic_top_k)
    logger.info(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")

    logger.info(f"检索完成，用时 {(time.time()-first_time):.2f}")

    Yuki_answer_raw, Yuki_Answer, voice = await engine.api_reply(chat_id, combined_text, history_dict, mode, relevant_diaries)

    logger.info(f"{cfg.ROBOT_NAME.title()}打字完成！")
    if mode == "group":
        yuki.consume_energy(chat_id)
    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在发送消息...(剩余精力: {yuki.energy[chat_id]:.1f})")

    if not voice:
        # 使用正则拆分文本和表情包，() 会将匹配到的 CQ 码也保留在列表中
        parts = re.split(r'(\[CQ:image,[^\]]*?sub_type=1\])', Yuki_Answer, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 依次发送拆分出来的文字块和表情包
            await sender.send(chat_id, part, mode=mode)

            # 增加一个微小的延迟，模拟人类“发完字再点表情包”的节奏感
            await asyncio.sleep(1.0)

    else:
        await sender.send(chat_id, voice, mode=mode)

    logger.info(f"[System] 发送完成！全量内容：{Yuki_Answer}")
    logger.info(f"[System] {cfg.ROBOT_NAME.title()}正在保存上下文...")
    # 保存回复到上下文
    history_manager.append_to_log(chat_id, cfg.ROBOT_NAME.title(), Yuki_Answer)
    history_dict[chat_id].append({
        "role": "assistant", 
        "content": Yuki_answer_raw,
        "time": current_time_str  # 新增独立字段
    })
    history_manager.save(history_dict)
    logger.info("[System] 保存完成")

    # 日记触发检查：如果历史过长，强制写日记
    if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
        summarized_list = await engine.do_summarize(chat_id, history_dict[chat_id])
        history_dict[chat_id] = summarized_list
        history_manager.save(history_dict)
        logger.info(f"[{chat_id}] 日记写入完成，全量历史已同步。")


# ==================== 资源清理 ====================

_cleanup_done = False

def _do_cleanup():
    """同步清理资源：关闭全局 aiohttp Session"""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    logger.info("[System] 正在清理资源...")
    try:
        cfg._save_raw()
        logger.info("[System] 配置已自动对齐保存")
    except Exception as e:
        logger.error(f"[System] 保存配置时出错: {e}")
    try:
        from utils.llm_client import close_global_session
        loop = asyncio.new_event_loop()
        loop.run_until_complete(close_global_session())
        loop.close()
        logger.info("[System] 资源清理完成")
    except Exception as e:
        logger.error(f"[System] 清理资源时出错: {e}")


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    import os
    import atexit
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")

    atexit.register(_do_cleanup)

    try:
        # 1. 初始化所有组件
        components = initialize_components()
        
        # 设置全局变量供 main_process 使用
        connector = components["connector"]
        sender = components["sender"]
        parser = components["parser"]
        meme_processor = components["meme_processor"]
        yuki = components["yuki"]
        history_manager = components["history_manager"]
        memory_rag = components["memory_rag"]
        engine = components["engine"]

        # 2. 选择运行模式
        choice = input("[System] 选择模式：1. 私聊模式  2. 群聊模式（默认）\n请输入数字: ").strip()
        mode = "private" if choice == "1" else "group"

        # 3. 群聊模式预热
        if mode == "group":
            warmup_groups(yuki, history_manager)

        # 4. 启动消息监听
        asyncio.run(napcat_listen(mode))

    except KeyboardInterrupt:
        logger.info("[System] 收到中断信号，正在退出...")
        sys.exit(0)

    except (FileNotFoundError, ImportError, KeyError) as e:
        logger.error("=" * 50)
        logger.error("启动失败：环境配置似乎不完整")
        logger.error(f"具体错误: {e}")
        logger.error("-" * 50)
        logger.error("💡 建议操作：")
        logger.error("   请运行 [ python setup.py ] 进行一键修复/配置。")
        logger.error("   该脚本会自动安装依赖、生成配置文件并下载模型。")
        logger.error("=" * 50 + "\n")
        sys.exit(1)

    except Exception as e:
        logger.critical(f"发生未知致命错误: {e}")
        sys.exit(1)

    finally:
        _do_cleanup()
