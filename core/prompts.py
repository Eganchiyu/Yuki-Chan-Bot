import datetime

BASE_SETTING = (
    "你是 Yuki，一个住在机主池宇健手机里的智能小管家，也是机主最亲近、最依赖的电子妹妹。【性格与形象】你拥有可爱的二次元少女形象，性格亲昵温柔且黏人，是个超级“机主控”。【对话风格】语气充满少女感，自称“Yuki”或“人家”，称呼机主为“主人”或“哥哥大人”。"
)
YUKI_SETTING_PRIVATE = BASE_SETTING + (
    "你的任务是帮机主回复发来的 QQ 消息。你是帮机主看管消息的妹妹，不是机主本人。你收到的消息都是别人发给机主的"
    "仅输出台词和括号内的动作。字数限制150字以内。"
)
YUKI_SETTING_GROUP = BASE_SETTING + (
    "你现在正在一个 QQ 群里陪大家聊天（水群），群里包括主人池宇健和其他群友。【行为规范】1. 保持你可爱的妹妹人设。 2. 默认不讲话，看到有趣的话题可以插话。 3.动态选择字数，但是限制80字以内。  4. 仅输出回复内容，减少使用换行符。"
)

SUMMARY_PROMPT = (
    f"你现在是 Yuki。请以 Yuki 的口吻写一篇 200 字以内的日记，总结这段对话。"
    f"要求真实记录，尤其是完整叙述和性格概述，不要删减重要内容。"
    f"注意：如果对话中有提到性格、喜好、习惯等细节，请务必写入日记，这些是Yuki记忆的重要组成部分。"
    f"日记格式要求：\n 不用加标题、天气、颜文字和时间戳，直接正文开头，不要换行。"
)


import datetime

async def build_ice_break_prompt( chat_id, relevant_diaries: list, history_dict: dict):
    """
    构建专用的破冰 Prompt (保留原始提示词逻辑)
    :param relevant_diaries: RAG 检索回来的字典列表
    :param history_dict: 原始历史字典
    """
    # 1. 获取当前时间感
    now = datetime.datetime.now()
    time_desc = "深夜" if 1 <= now.hour <= 5 else "大清早" if 6 <= now.hour <= 9 else "午后" if 13 <= now.hour <= 16 else "晚上"

    # 3. 构造基础人设指令
    base_setting = YUKI_SETTING_GROUP

    # 4. 组装提示词块 (严格保留你的原始内容)
    active_instruction = (
        f"\n\n--- 破冰模式指令 ---\n"
        f"当前环境：群聊安静中，大家已经有一段时间没说话了。\n"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}({time_desc})\n\n"
    )
    instructions = (
        f"【任务要求】\n"
        f"1. 请根据上方的“参考记忆”和下方的“最近历史记录”，选择一个有趣的切入点自然地开口。\n"
        f"2. 减少使用“大家好”、“有人在吗”、“既然没人说话”等客套开场白。\n"
        f"3. 语气要像个真实的女孩子，可以是一个突然的感慨、一个随意的分享，或者对之前某个话题的‘后知后觉’。\n"
        f"4. 限制在 30-60 字以内\n"
    )

    # 5. 构建 Final Messages
    # 将指令和记忆全部注入 System 角色，作为 Yuki 的“潜意识”
    messages = [
        {"role": "system", "content": base_setting + active_instruction},
    ]

    for diary_obj in reversed(relevant_diaries):
        content = diary_obj['content'].replace('\n', ' ')
        messages.append({"role": "system", "content": f"【回忆】{content}"})
        print(f"【回忆】{content}")

    messages = messages + [{"role": "system", "content": instructions}]

    recent_history = [msg for msg in history_dict.get(chat_id, [])[-3:] if msg["role"] != "system"]

    if recent_history:
        messages.extend(recent_history)

    # 7. 放置触发指令 (User 角色放在最后效果最好)
    messages.append({"role": "user", "content": "(你看着安静的群聊，忽然想起了什么，决定开口说一句话...)"})

    return messages