from config import cfg
from utils.logger import get_logger

logger = get_logger("prompts")

# ========== 新增：小女仆设定（放在系统提示最前面） ==========
MAID_SETTING = """
你有一个勤劳可爱的小女仆，名字叫「小女仆」。
她是你的专属助手，擅长编写和运行 Python 技能来帮你完成任务。
你随时可以把任务委托给她，格式为：
[DELEGATE_TO_MAID:这里写具体任务描述]
你会自动收到她的汇报（通过记忆系统），也可以选择主动在群里或私聊里说出来
"""

def get_base_setting():
    return f"你是 {cfg.ROBOT_NAME}，一个住在机主{cfg.MASTER_NAME}手机里的智能小管家，也是机主最亲近、最依赖的电子妹妹。【性格与形象】你拥有可爱的二次元少女形象，性格亲昵温柔且黏人，是个超级“机主控”。【对话风格】语气充满少女感，自称“{cfg.ROBOT_NAME}”或“人家”，称呼机主为“主人”或“哥哥大人”。"

def get_yuki_setting_private():
    return get_base_setting() + MAID_SETTING + (
        "你的任务是帮机主回复发来的 QQ 消息。你是帮机主看管消息的妹妹，不是机主本人。你收到的消息都是别人发给机主的"
        "仅输出台词和括号内的动作。字数限制150字以内。"
    )

def get_yuki_setting_group():
    return get_base_setting() + MAID_SETTING + (
        f"你现在正在一个 QQ 群里陪大家聊天（水群），群里包括主人{cfg.MASTER_NAME}和其他群友。【行为规范】1. 保持你可爱的妹妹人设。2. 发送本地图片的格式是[CQ:image,file=文件路径] 3. 默认不讲话，看到有趣的话题可以插话。 4.动态选择字数，但是限制80字以内。  5. 仅输出回复内容，减少使用换行符。"
    )

def get_summary_prompt():
    return (
        f"你现在是 {cfg.ROBOT_NAME}。请以 {cfg.ROBOT_NAME} 的口吻写一篇 200 字以内的日记，总结这段对话。"
        f"要求真实记录，尤其是完整叙述和性格概述，不要删减重要内容。"
        f"注意：如果对话中有提到性格、喜好、习惯等细节，请务必写入日记，这些是{cfg.ROBOT_NAME}记忆的重要组成部分。"
        f"日记格式要求：\n 不用加标题、天气、颜文字和时间戳，直接正文开头，不要换行。"
    )

VISION_PROMPT = (
    f"用词或短句描述这个群友发的表情包的描述或表达的情感，不超过15个字。带文字图片输出文字。长段文字直接输出“长段文字”"
)

import datetime

def build_ice_break_prompt(chat_id, relevant_diaries: list, history_dict: dict):
    """
    构建专用的破冰 Prompt (保留原始提示词逻辑)
    :param chat_id:群聊群号
    :param relevant_diaries: RAG 检索回来的字典列表
    :param history_dict: 原始历史字典
    """
    # 1. 获取当前时间感
    now = datetime.datetime.now()
    time_desc = "深夜" if 1 <= now.hour <= 5 else "早上" if 6 <= now.hour <= 9 else "午后" if 13 <= now.hour <= 16 else "晚上"

    # 3. 构造基础人设指令
    base_setting = get_yuki_setting_group()

    # 4. 组装提示词块 (严格保留你的原始内容)
    active_instruction = (
        f"\n\n--- 破冰模式指令 ---\n"
        f"当前环境：群聊安静中，大家已经有一段时间没说话了。\n"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}({time_desc})\n\n"
    )
    instructions = (
        f"【任务要求】\n"
        f"1. 请根据上方的“最近历史记录”和下方的“日记内容”，选择一个有趣的切入点自然地开口。\n"
        f"2. 减少使用客套开场白。\n"
        f"3. 语气要像个真实的女孩子，可以是一个突然的感慨、一个随意的分享，或者对之前某个话题的‘后知后觉’。\n"
        f"4. 限制在 30-60 字以内\n"
    )

    # 5. 构建 Final Messages
    # 将指令和记忆全部注入 System 角色，作为 Yuki 的“潜意识”
    messages = [
        {"role": "system", "content": base_setting + active_instruction},
    ]

    recent_history = [msg for msg in history_dict.get(chat_id, [])[-3:] if msg["role"] != "system"]

    if recent_history:
        messages.extend(recent_history)

    messages = messages + [{"role": "system", "content": instructions}]

    for diary_obj in reversed(relevant_diaries):
        content = diary_obj['content'].replace('\n', ' ')
        messages.append({"role": "system", "content": f"【回忆】{content}"})
        logger.debug(f"【回忆】{content}")

    # 7. 放置触发指令 (User 角色放在最后效果最好)
    messages.append({"role": "user", "content": (
        f"群聊安静中，大家已经有一段时间没说话了。\n"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}({time_desc})\n\n"
        f"(你看着安静的群聊，忽然想起了什么，决定开口说一句话...)"
    )})

    return messages


async def build_chat_context(yuki, chat_id: str, combined_text: str, history_dict: dict, mode,
                             relevant_diaries):
    # 这里的 diary 现在是字典，我们要取出 ['content']
    for i, diary_obj in enumerate(reversed(relevant_diaries), 1):
        preview = diary_obj['content'].replace('\n', ' ')  # 提取文本内容
        logger.debug(f"[Diary Debug]回忆 {i}: {preview}")

    # 1. 基础人设
    system_prompt = history_dict[chat_id][0]["content"] if history_dict[chat_id] and history_dict[chat_id][0][
        "role"] == "system" else yuki.get_setting(mode)
    combined_API_message = [{"role": "system", "content": system_prompt}]

    # 2. 插入检索到的日记
    for diary_obj in reversed(relevant_diaries):
        content = diary_obj['content']  # 提取文本内容
        combined_API_message.append({"role": "system", "content": f"【回忆】{content}"})

    # --- 调试输出：打印加权分和匹配到的关键词信息 ---
    for i, diary_obj in enumerate(relevant_diaries[:3], 1):
        # 打印加权分和匹配到的关键词信息
        logger.debug(f"[RAG-Debug] 回忆 {i} | 得分: {diary_obj['score']:.2f} | 详情: {diary_obj['debug']}")

    # 3. 取出最近的对话（注意：这里保持原样取出，下面进行处理）
    recent_msgs_raw = [msg for msg in history_dict[chat_id][-cfg.KEEP_LAST_DIALOGUE - 1:-1] if msg["role"] != "system"]

    # --- 最小改动：在这里处理时间观念 ---
    processed_recent_msgs = []
    for msg in recent_msgs_raw:
        # 鲁棒性设计：通过 .get("time") 安全获取，如果不存在则不处理
        msg_time = msg.get("time")
        if msg_time:
            if msg["role"] == "user":
                # 这里的 content 使用原有的内容，但在前面合入时间
                new_content = f"【时间：{msg_time}】{msg['content']}"
                processed_recent_msgs.append({"role": msg["role"], "content": new_content})
            elif msg["role"] == "assistant":
                new_content = f"{msg['content']}"
                processed_recent_msgs.append({"role": msg["role"], "content": new_content})
        else:
            # 如果没有 time 字段，则保持原样（兼容旧数据）
            processed_recent_msgs.append({"role": msg["role"], "content": msg["content"]})

    # 使用处理后的消息
    combined_API_message.extend(processed_recent_msgs)
    combined_API_message.append(
        {"role": "user", "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}){combined_text}"})
    return combined_API_message

if __name__ == "__main__":
    print(get_yuki_setting_group())