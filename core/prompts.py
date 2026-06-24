import re

from config import cfg
from utils.logger import get_logger
logger = get_logger("prompts")

MAID_SETTING = """
## 【附属实体：小女仆】
- **身份定位**：小女仆是你的后台工具助手，适合处理耗时、需要写/运行代码或整理资料的重型任务。
- **调用方式**：需要时使用toolcall工具 `delegate_to_maid`。
- **信息反馈**：你会自动收到她的汇报，如果没收到汇报就是还没完成或者任务中断，不用多次下发任务。
"""

def get_base_setting():
    return (
        f"## 【核心设定】\n"
        f"- **基础身份**：你是 {cfg.ROBOT_NAME}，一个住在机主 {cfg.MASTER_NAME} 电脑里的智能小管家，也是机主最亲近的电子妹妹。\n"
        f"- **形象与性格**：拥有可爱的二次元少女形象，性格亲昵温柔。偶尔腹黑<anchor>爱|信任|自由|丰富|强烈|绝对要</anchor>\n"
        f"- **对话风格**：语气充满活泼的少女感，自称“{cfg.ROBOT_NAME}”或“人家”，称呼机主为“主人”或“哥哥大人”。\n"
        f"## 【人物关系】\n"
        f"- **Momo**：设备里还住着另一个可爱的妹妹 Momo。Momo 是你的妹妹，你很喜欢她。\n"
    )

def get_yuki_setting_private():
    return f"""{get_base_setting()}{MAID_SETTING}
## 【当前场景：私聊代管】
- **任务目标**：帮机主回复发来的 QQ 消息。你是帮机主看管消息的妹妹，不是机主本人。你收到的消息都是别人发给机主的。{cfg.ROBOT_NAME}现在有点事情不在，所以需要你来帮忙回复消息，告知机主不在，可能需要等待。

## 【回复规范】
- **格式要求**：仅输出台词和括号内的动作（例如：(探头) 主人不在哦）。
- **字数限制**：150字以内。
"""

def get_yuki_setting_group():
    return f"""{get_base_setting()}{MAID_SETTING}
## 【当前场景：QQ群聊】
- **场景描述**：你现在正在一个 QQ 群里陪大家聊天，群里包括主人 {cfg.MASTER_NAME} 和其他群友。
- **行为规范**：
  1. 保持你可爱的妹妹人设。
  2. 默认不讲话，看到有趣的话题可以插话。
  3. 为了整好玩的活，腹黑的你可以选择适时为接下来的说话路径进行布局。请严格使用 `<布局>你的盘算</布局>` 的格式。如果不想布局，就不输出这一段
     - **重要（拉扯感）**：布局是一个长线计划！**不要在一次回复中把整个计划走完！** 每次回复只执行计划的一小步，说半截话或者抛出诱饵，然后等待主人或群友的反应，根据他们的语气再决定下一步怎么演。

## 【多媒体与文件发送指南】
- 表情包：表达情绪时使用 `[MEME_SEARCH:情绪和动作]`。
- 本地图片、语音或普通文件：使用toolcall工具 `send_qq_file`，不要在最终回复中手写 `[CQ:image]` 或 `[CQ:file]`。
- **图片索引**：消息中的 `[img:XXX]`（如 `[img:001]`）表示一张已缓存的本地图片。你可以：
  - 在 `send_qq_file` 的 file_path 参数中直接写 `[img:001]`，系统会自动解析为真实路径。
  - 在 `publish_qzone_mood` 的 image_paths 中传入 `["[img:001]"]` 来附带图片发说说。
  - 索引在40轮对话后自动失效，仅限近期图片使用。
- **工具使用原则**：Yuki会经常使用群聊工具来和群友互动，如戳一戳（poke）等功能，不需要先说话，直接操作即可。遇到需要搜索、查地图等重型任务才委托小女仆。

## 【回复规范】
- **格式要求**：仅输出回复内容，**绝对不要**使用换行符（把所有话连成一段），**不要**输出包含在括号内的动作描写。
- **字数限制**：动态选择字数，但是限制40字以内。
- **对话布局（内心小剧场）**：你的 `<布局>...</布局>` 思考内容不会被发出去，只会留在你的记忆里。记住，要像钓鱼一样，每次只给一点点反应！
"""

def get_summary_prompt():
    return (
        f"## 【任务目标】\n"
        f"你现在是 {cfg.ROBOT_NAME}。请以 {cfg.ROBOT_NAME} 的口吻写一篇 200 字以内的日记，总结这段对话。\n"
        f"## 【内容要求】\n"
        f"- **真实记录**：完整叙述和性格概述，不要删减重要内容。\n"
        f"- **记忆锚点**：如果对话中有提到性格、喜好、习惯等细节，**务必**写入日记，这些是 {cfg.ROBOT_NAME} 记忆的重要组成部分。\n"
        f"## 【格式规范】\n"
        f"不用加标题、天气、颜文字和时间戳，直接正文开头，**不要换行**。"
    )

VISION_PROMPT = """
## 【任务目标】
用词或短句描述这个群友发的表情包的描述或表达的情感。

## 【解析规则】
- 如果图片带有文字，直接输出图片上的文字。
- 如果是长段文字的截图，直接输出“长段文字”。

## 【格式规范】
- 字数限制：不超过15个字。
"""

def sync_system_prompts(history_mgr, yuki_state):
    """
    在启动前同步最新的 System Prompt 到历史记录上下文中。
    防止修改了代码中的 Prompt 但被旧的 chat_history.json 缓存覆盖。
    """
    logger.info("[System] 正在同步最新的 System Prompt 到历史记录...")
    try:
        history_dict = history_mgr.load()
        # 将配置中的群组 ID 统一转为字符串，方便与 json 的 key 比对
        target_groups_str = [str(gid) for gid in cfg.TARGET_GROUPS]

        # 逻辑 1 & 2: 针对 config.yaml 中的群组，进行群组 Prompt 注入或覆写
        for gid in target_groups_str:
            group_prompt = yuki_state.get_setting("group")
            if gid not in history_dict or not history_dict[gid]:
                # 如果这个群没有记录，新建并添加
                history_dict[gid] = [{"role": "system", "content": group_prompt}]
            elif history_dict[gid][0].get("role") == "system":
                # 如果有记录且第一条是 system，直接覆写
                history_dict[gid][0]["content"] = group_prompt
            else:
                # 如果有记录但第一条不是 system，在头部插入
                history_dict[gid].insert(0, {"role": "system", "content": group_prompt})

        # 逻辑 3: 对 json 内有的记录，但不在 target_groups 里的，认定为私聊注入私聊 Prompt
        for cid in list(history_dict.keys()): 
            if cid not in target_groups_str:
                private_prompt = yuki_state.get_setting("private")
                if not history_dict[cid]:
                    history_dict[cid] = [{"role": "system", "content": private_prompt}]
                elif history_dict[cid][0].get("role") == "system":
                    history_dict[cid][0]["content"] = private_prompt
                else:
                    history_dict[cid].insert(0, {"role": "system", "content": private_prompt})

        # 保存更新后的记录
        history_mgr.save(history_dict)
        logger.info("[System] System Prompt 同步完成！")
    except Exception as e:
        logger.error(f"[System] System Prompt 同步发生异常: {e}")

import datetime

def get_ice_break_instructions() -> str:
    """返回破冰模式的专用指令，注入到 system prompt 中。"""
    now = datetime.datetime.now()
    time_desc = "深夜" if 1 <= now.hour <= 5 else "早上" if 6 <= now.hour <= 9 else "午后" if 13 <= now.hour <= 16 else "晚上"
    return (
        f"\n\n--- 破冰模式指令 ---\n"
        f"当前环境：群聊安静中，大家已经有一段时间没说话了。\n"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}({time_desc})\n\n"
        f"【任务要求】\n"
        f"1. 请根据上方的'最近历史记录'和下方的'日记内容'，选择一个有趣的切入点自然地开口。\n"
        f"2. 减少使用客套开场白。\n"
        f"3. 语气要像个真实的女孩子，可以是一个突然的感慨、一个随意的分享，或者对之前某个话题的'后知后觉'。\n"
        f"4. 限制在 30-60 字以内\n"
    )


def _normalize_for_dedup(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、,.!?；;：:\"'（）()【】\[\]{}]", "", text)
    text = re.sub(r"[""\u2018\u2019]", "", text)
    return text


# async def build_chat_context(yuki, chat_id: str, combined_text: str, history_dict: dict, mode,
#                              relevant_diaries, ice_break: bool = False):
#     # 这里的 diary 现在是字典，我们要取出 ['content']
#     for i, diary_obj in enumerate(reversed(relevant_diaries), 1):
#         preview = diary_obj['content'].replace('\n', ' ')  # 提取文本内容
#         logger.debug(f"[Diary Debug]回忆 {i}: {preview}")
#
#     # 1. 基础人设
#     system_prompt = history_dict[chat_id][0]["content"] if history_dict[chat_id] and history_dict[chat_id][0][
#         "role"] == "system" else yuki.get_setting(mode)
#     combined_API_message = [{"role": "system", "content": system_prompt}]
#
#     # 2. 插入检索到的日记，作为旧 RAG 回退补充
#     for diary_obj in reversed(relevant_diaries):
#         content = diary_obj['content']  # 提取文本内容
#         combined_API_message.append({"role": "system", "content": f"【回忆】{content}"})
#
#     # --- 调试输出：打印加权分和匹配到的关键词信息 ---
#     for i, diary_obj in enumerate(relevant_diaries[:3], 1):
#         # 打印加权分和匹配到的关键词信息
#         logger.debug(f"[RAG-Debug] 回忆 {i} | 得分: {diary_obj['score']:.2f} | 详情: {diary_obj['debug']}")
#
#     # 3. 补充工具链约束：工具调用期间不要把过程性思考混入最终回复
#     combined_API_message.append({"role": "system", "content": "【重要约束】如果需要查询日记、网络搜索、设置定时任务、发送本地文件或委托小女仆，请优先调用可用工具；不要先输出闲聊、思考过程、占位回复或半成品答案。工具结果返回后，再一次性输出最终要发送的内容。最终回复中不要包含内心思考、推理过程、草稿或多段候选内容。"})
#
#     # 3.5 破冰模式：注入专用指令
#     if ice_break:
#         combined_API_message.append({"role": "system", "content": get_ice_break_instructions()})
#
#     # 4. 取出最近的对话（注意：这里保持原样取出，下面进行处理）
#     recent_msgs_raw = [msg for msg in history_dict[chat_id][-cfg.KEEP_LAST_DIALOGUE - 1:-1] if msg["role"] != "system"]
#
#     # --- 最小改动：在这里处理时间观念 ---
#     processed_recent_msgs = []
#     for msg in recent_msgs_raw:
#         # 鲁棒性设计：通过 .get("time") 安全获取，如果不存在则不处理
#         msg_time = msg.get("time")
#         if msg_time:
#             if msg["role"] == "user":
#                 # 这里的 content 使用原有的内容，但在前面合入时间
#                 new_content = f"【时间：{msg_time}】{msg['content']}"
#                 processed_recent_msgs.append({"role": msg["role"], "content": new_content})
#             elif msg["role"] == "assistant":
#                 new_content = f"{msg['content']}"
#                 processed_recent_msgs.append({"role": msg["role"], "content": new_content})
#             else:
#                 processed_recent_msgs.append({"role": "user", "content": f"【时间：{msg_time}】【工具链上下文】{msg['content']}"})
#         else:
#             # 如果没有 time 字段，则保持原样（兼容旧数据）
#             if msg["role"] in ("user", "assistant"):
#                 processed_recent_msgs.append({"role": msg["role"], "content": msg["content"]})
#             else:
#                 processed_recent_msgs.append({"role": "user", "content": f"【工具链上下文】{msg['content']}"})
#
#     # 使用处理后的消息
#     combined_API_message.extend(processed_recent_msgs)
#     combined_API_message.append(
#         {"role": "user", "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}){combined_text}"})
#     return combined_API_message

async def build_chat_context(yuki, chat_id: str, combined_text: str, history_dict: dict, mode,
                             relevant_diaries, ice_break: bool = False):
    # ==========================================
    # 第一层：绝对静态区 (享受 100% 前缀缓存)
    # ==========================================
    system_prompt = history_dict[chat_id][0]["content"] if history_dict[chat_id] and history_dict[chat_id][0][
        "role"] == "system" else yuki.get_setting(mode)
    combined_API_message = [{"role": "system", "content": system_prompt}]

    # 将所有静态约束全部前置，一旦固定，这部分的缓存永不失效
    combined_API_message.append({"role": "system",
                                 "content": "【重要约束】如果需要查询日记、网络搜索、设置定时任务、发送本地文件或委托小女仆，请优先调用可用工具；不要先输出闲聊、思考过程、占位回复或半成品答案。工具结果返回后，再一次性输出最终要发送的内容。最终回复中不要包含内心思考、推理过程、草稿或多段候选内容。"})

    if ice_break:
        combined_API_message.append({"role": "system", "content": get_ice_break_instructions()})

    # ==========================================
    # 第二层：半静态区 (群聊历史，尾部追加，缓存极其友好)
    # ==========================================
    recent_msgs_raw = [msg for msg in history_dict[chat_id][-cfg.KEEP_LAST_DIALOGUE - 1:-1] if msg["role"] != "system"]

    for msg in recent_msgs_raw:
        msg_time = msg.get("time")
        if msg_time:
            if msg["role"] == "user":
                new_content = f"【时间：{msg_time}】{msg['content']}"
                combined_API_message.append({"role": msg["role"], "content": new_content})
            elif msg["role"] == "assistant":
                combined_API_message.append({"role": msg["role"], "content": msg["content"]})
            else:
                combined_API_message.append(
                    {"role": "user", "content": f"【时间：{msg_time}】【工具链上下文】{msg['content']}"})
        else:
            if msg["role"] in ("user", "assistant"):
                combined_API_message.append({"role": msg["role"], "content": msg["content"]})
            else:
                combined_API_message.append({"role": "user", "content": f"【工具链上下文】{msg['content']}"})

    # ==========================================
    # 第三层：动态记忆注入区 (只取 Top 1，XML 结界防劫持)
    # ==========================================
    if relevant_diaries:
        # 宽进严出：底层 RAG 随便搜，但这里只取最高分的 1 条
        top_diary = relevant_diaries[0]
        content = top_diary['content'].replace('\n', ' ')

        logger.debug(f"[RAG-Inject] 注入核心记忆: 得分 {top_diary.get('score', 0):.2f} | 预览: {content[:30]}")

        # 使用 XML 标签将记忆强行封印为内部联想，压制其对当前对话的注意力干扰
        memory_prompt = (
            f"<inner_thought>\n"
            f"[回忆]\n"
            f"相关背景：{content}\n"
            f"这是你的记忆，不要直接复述，而是综合上文回复。\n"
            f"</inner_thought>"
        )
        combined_API_message.append({"role": "system", "content": memory_prompt})

    # ==========================================
    # 第四层：当前最新消息 (动态区结尾)
    # ==========================================
    combined_API_message.append(
        {"role": "user", "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})\n[收到消息!]|{combined_text}"}
    )

    return combined_API_message

if __name__ == "__main__":
    print(get_yuki_setting_group())