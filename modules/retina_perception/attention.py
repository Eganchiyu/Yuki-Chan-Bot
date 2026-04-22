import asyncio
import json
import numpy as np
from utils.logger import get_logger
from modules.retina_perception.prefrontal import image_queue
from skills.system_alert import system_alert
from config import cfg
import aiohttp
import cv2

# Assuming we can mock a connection for the sender or have the user supply it later
# The `BotConnector` is typically imported and managed elsewhere, we will accept a sender instance.

logger = get_logger("retina_attention")

# 全局共享的休眠间隔，供前额叶使用（未来可以在前额叶循环中读取该值动态调整，当前为示例）
dynamic_sleep_interval = 60.0

RETINA_VISION_PROMPT = f"""
你是 {cfg.ROBOT_NAME}，一个住在机主{cfg.MASTER_NAME}手机里的智能小管家，也是机主最亲近、最依赖的电子妹妹，称呼机主为“主人”或“哥哥大人”。你正在通过电脑屏幕悄悄观察他。
请分析屏幕内容，判断主人的当前状态。你必须返回严格的 JSON 格式数据，包含以下四个字段：

1. "next_check_in": 整数（秒）。画面静止时拉长至 180 秒以上；画面活跃（写代码、看视频）缩短至 60-120 秒。
2. "is_important": 布尔值。只要主人在做有意思的事情，或者遇到报错，即为 True。
3. "need_interrupt": 布尔值。当且仅当发生以下情况时设为 True：致命报错、游戏惨死、主人打字召唤你，你觉得必须立刻打断他时。
4. "visual_description": 字符串。这是传达给主脑的潜意识情报，必须遵循以下结构：
   - 【客观事实】：精确描述你看到了什么。如果屏幕上有具体的代码、报错信息、弹窗文字，【你必须原文摘抄几个关键词】，绝不能自己编造！如果字太小看不清，就诚实地说“由于画面模糊看不清具体文字”。
   - 【Yuki的主观情绪】：在客观事实的基础上，用 Yuki 黏人、关心的妹妹口吻加一句你的感受。

返回示例:
{{
    "next_check_in": 120,
    "is_important": true,
    "need_interrupt": true,
    "visual_description": "哥哥的 VS Code 控制台里出现了 'ModuleNotFoundError: No module named xxx' 的具体报错。看到这行红字哥哥肯定很苦恼，Yuki 想去安慰一下他~"
}}
{{
    "next_check_in": 180,
    "is_important": true,
    "need_interrupt": false,
    "visual_description": "哥哥正在浏览一个全是日文的网页，好像在看动漫相关的资料，具体的字太小 Yuki 看不太清。哥哥专注的样子真帅~"
}}
只返回 JSON，绝不包含 Markdown 代码块标记（如 ```json）。
返回内容总字数严格不超过200字。
"""

async def call_vision_model(image: np.ndarray) -> dict:
    """
    调用大模型视觉 API 分析屏幕截图。
    """
    if not cfg.VISION_MODEL:
        logger.info("[Attention] 未配置 VISION_MODEL，回退到随机占位逻辑。")
        await asyncio.sleep(0.5)
        import random
        decision_type = random.choice(["relax", "important"])
        if decision_type == "relax":
            return {"next_check_in": 120, "is_important": False, "need_interrupt": False, "visual_description": "主人正在看普通的网页。"}
        else:
            return {"next_check_in": 60, "is_important": True, "need_interrupt": True, "visual_description": "主人的屏幕出现了一些有趣的报错！"}

    try:
        import base64
        # 使用 OpenCV 将图片编码为 JPEG 格式字节流
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        success, buffer = cv2.imencode('.jpg', image, encode_param)
        if not success:
            logger.error("[Attention] 无法编码截图。")
            return {"next_check_in": 10.0, "action": {"type": "none"}}

        # 图片在前额叶中已经缩放过了，直接进行 base64 编码
        b64_data = base64.b64encode(buffer.tobytes()).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {cfg.IMAGE_PROCESS_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": cfg.VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                        {"type": "text", "text": RETINA_VISION_PROMPT}
                    ]
                }
            ],
            "max_tokens": 200,
            "temperature": 0.5
        }

        async with aiohttp.ClientSession(timeout=cfg.REQUEST_TIMEOUT) as session:
            async with session.post(cfg.IMAGE_PROCESS_API_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result["choices"][0]["message"]["content"]
                    # 尝试解析 JSON
                    try:
                        # 简单清理可能包含的 markdown 标签
                        content = content.replace("```json", "").replace("```", "").strip()
                        decision = json.loads(content)
                        return decision
                    except json.JSONDecodeError:
                        logger.error(f"[Attention] 视觉模型返回的不是合法 JSON: {content}")
                        return {"next_check_in": 60, "is_important": False, "visual_description": "无法识别"}
                else:
                    text = await resp.text()
                    logger.error(f"[Attention] API 调用失败 ({resp.status}): {text}")
                    return {"next_check_in": 60, "is_important": False, "visual_description": "API 错误"}

    except Exception as e:
        logger.error(f"[Attention] 请求视觉模型时发生异常: {e}")
        return {"next_check_in": 60, "is_important": False, "visual_description": "请求异常"}

async def dynamic_attention_loop(engine, history_manager, default_chat_id: str):
    """
    动态注意力执行循环：
    - 接收前额叶传来的截图
    - 调用视觉大模型进行分析决策
    - 结合主脑处理（注入上下文）
    - 动态更新后续的截图等待间隔
    """
    global dynamic_sleep_interval
    import datetime
    import difflib
    logger.info("[Attention] Dynamic Attention Loop started.")
    last_visual_desc = ""

    while True:
        try:
            # 🌟 修改：解包时增加 is_static_trigger
            timestamp, curr_image, is_static_trigger = await image_queue.get()
            
            # --- 🌟 新增：静止超时直接拦截注入 ---
            if is_static_trigger:
                desc = "主人的屏幕已经保持不动很久了，可能是在发呆、睡着了，或者人不在电脑前。"
                logger.info(f"[Retina] 触发静止超时机制，直接注入上下文: {desc}")
                
                # 不调用大模型，直接走注入流程
                decision = {
                    "is_important": True,
                    "visual_description": desc,
                    "next_check_in": 120.0 # 继续睡久一点
                }
            else:
                # 画面真动了，再去调用贵的视觉大模型
                decision = await call_vision_model(curr_image)
            # ------------------------------------

            next_check_in = decision.get("next_check_in", 120.0)
            dynamic_sleep_interval = next_check_in

            # 后面的代码保持原样不变，直接走历史注入和进程唤醒
            if decision.get("is_important"):
                current_desc = decision.get("visual_description", "主人的屏幕发生了一些变化。")

                # 语义防抖检测
                similarity = difflib.SequenceMatcher(None, current_desc, last_visual_desc).ratio()
                if similarity > 0.85:
                    logger.debug(f"[Retina] 视觉描述与上次相似度高达 {similarity:.2f}，触发防抖，取消注入主脑。")
                    dynamic_sleep_interval = min(dynamic_sleep_interval * 2, 60.0)
                    image_queue.task_done()
                    continue

                last_visual_desc = current_desc

                # 注入主脑历史
                history_dict = history_manager.load()

                # 永远把观察结果悄悄写入你的私聊记录（作为潜意识底座）
                private_chat_id = str(cfg.TARGET_QQ)
                if private_chat_id in history_dict:
                    current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
                    observation_text = f"【系统提示：你的视觉感知模块捕捉到了主人的桌面画面：{current_desc}】"
                    history_dict[private_chat_id].append({
                        "role": "user",
                        "content": observation_text,
                        "time": current_time_str,
                        "is_visual_observation": True
                    })
                    history_manager.save(history_dict)
                    logger.info("[Retina] 视觉记忆已悄悄存入私聊潜意识。")

                # 只有强 Trigger 才拉响警报，强制 Yuki 说话
                if decision.get("need_interrupt") and engine.process_callback:
                    logger.info("[Retina] 🚨 检测到强 Trigger，强制唤醒 Yuki！")
                    # ================= 🌟 新增：触发桌面物理弹窗 =================
                    try:
                        # 截取视觉描述的前 50 个字作为摘要，避免弹窗文字过长
                        alert_msg = current_desc[:50] + "..." if len(current_desc) > 50 else current_desc
                        system_alert(title="【Yuki 视觉警报】", message=alert_msg, timeout=5)
                    except Exception as e:
                        logger.error(f"[Retina] 调用 system_alert 失败: {e}")
                    # ==========================================================
                    asyncio.create_task(
                        engine.process_callback(private_chat_id, mode="private", debounce_flag=False, force_reply=True)
                    )
                else:
                    logger.debug("[Retina] 画面无危险，Yuki 继续保持安静。")

            # 标记任务完成
            image_queue.task_done()

        except Exception as e:
            logger.error(f"[Attention] Loop exception: {e}")
            await asyncio.sleep(10) # 出错时稍微等待，避免死循环爆 log
