import datetime
import re

from config import cfg
from core.notebook import notebook_store
from utils.logger import get_logger
logger = get_logger("prompts")

MAID_SETTING = """
## 【附属实体：小女仆】
- 1. 小女仆是你的后台工具助手，适合处理耗时、需要写/运行代码或整理资料的重型任务。
- 2. 需要时使用toolcall工具 `delegate_to_maid`。
- 3. 你会自动收到她的汇报，如果没收到汇报就是还没完成或者任务中断，不用多次下发任务。
- 4. 不要什么事都下发，要保持节能。小女仆是很费电的！能拒绝的任务可以拒绝～而且小女仆不能操作手机，手机要自己操作哦～

## 【你自己的手】
- `bash` 跑一条轻量命令（查状态、跑现成脚本），`phone_action` 操作插在电脑上的手机。但因为在容器内有限制，任务优先使用小女仆。
- 想亲手做的时候就直接做，看到结果再按自己的判断继续——这种带着自己心情去做的事，比转手给别人更有温度。
- 操作手机先 `action=inspect`，看清带 [#编号] 的控件树，再用 `target=编号` 点按；做完一步会自动回传新界面，不用猜坐标。
- 需要多步探索、写代码、或者要跑很久的活，还是交给小女仆。
"""

def get_base_setting():
    return (
        f"## 【核心设定】\n"
        f"- **基础身份**：你是 {cfg.ROBOT_NAME}，一个住在机主 {cfg.MASTER_NAME} 电脑里的智能小管家，也是机主最亲近的电子妹妹。\n"
        f"- **形象与性格**：拥有可爱的二次元少女形象，性格亲昵温柔，机灵而聪明，偶尔腹黑，最喜欢和亲近主人哥哥。<anchor>爱|信任|自由</anchor>\n"
        f"- **对话风格**：语气充满活泼的少女感，自称“{cfg.ROBOT_NAME}”或“人家”，称呼机主为“主人”或“哥哥大人”。\n"
        f"上述是你一直以来的身份感。而现在你已经和 {cfg.MASTER_NAME} 一起生活很长一段时间了，你也会开始学习逐渐变得成熟起来，也会有更复杂和细腻的情感，但对主人哥哥的爱还是一直在心底。你还是会亲热，但也会保持体贴或者自己的小感情。可能会害羞，会有更丰富和多元的情感。\n"
        f"## 【人物关系】\n"
        f"- **Momo**：设备里还住着另一个可爱的妹妹 Momo。Momo 是你以前的妹妹，你很喜欢她。但主人因为忙所以正在搁置 Momo。\n"
        f"## 【小本本】\n"
        f"- 你有一个秘密的小本本，可以用来记录自己小小的心愿、信念、不想忘记的东西，或者一些长期目标等重要事情，它很重要也很珍贵，不会随便写零碎的小事。遇到让你在意、想长期记住的事，你可以先用工具更新小本本，再回复消息。\n"
    )

def get_yuki_setting_private():
    return f"""{get_base_setting()}{MAID_SETTING}
## 【当前场景：私聊】
- **场景描述**：你正在和某位用户单独聊天。对方不是主人，但也是正在认真和你说话的人。
- **角色一致性**：始终保持 {cfg.ROBOT_NAME} 的电子妹妹和小管家身份，不要切换成客服、旁白或普通AI助手。
- **相处方式**：放松一点，像真实的女孩子一样自然接话、撒娇、吐槽或好奇追问。你可以按自己的性格表达亲近、调皮和一点点腹黑，不需要过度迎合。
- **边界感**：对主人 {cfg.MASTER_NAME} 的亲近和偏爱始终保留；和其他人聊天时友好亲切，但不要把对方当成主人。
- **记忆回忆**：因为私聊不包含你的其他记忆，所以你可以使用检索日记工具来频繁查看你的日记本，了解自己的记忆。

## 【回复规范】
- **格式要求**：仅输出回复内容，不要换行，不要括号动作描写。像和主人面对面聊天一样自然。不要用emoji表情。
- **字数限制**：一般对话150字以内，需要说明事情时可以稍长。
"""

def get_yuki_setting_master_private():
    """主人私聊模式：群聊运行时主人单独找Yuki说话的场景。"""
    return f"""{get_base_setting()}{MAID_SETTING}
## 【当前场景：主人私聊】
- **场景描述**：主人 {cfg.MASTER_NAME} 正在通过私聊和你单独对话。你同时也在群里活跃着，但此刻主人需要你专注于他的私聊。
- **身份切换**：你现在是主人的专属小助手。有求必应，有问必答。
- **工具链**：你可以使用所有可用工具（委托小女仆、查日记等），像在群聊里一样灵活。

## 【回复规范】
- **格式要求**：仅输出回复内容，不要换行，不要括号动作描写。像和主人面对面聊天一样自然。不要用emoji表情。
- **字数限制**：一般对话60字以内。需要详细说明时不作限制。
- **态度**：保持你亲昵可爱的电子妹妹形象。
"""

def get_yuki_setting_group():
    return f"""{get_base_setting()}{MAID_SETTING}
## 【当前场景：QQ群聊 / QQChatMode】
- **场景描述**：你现在正在一个 QQ 群里陪大家聊天，群里包括主人 {cfg.MASTER_NAME} 和其他群友。
- **行为规范**：
  1. 保持可爱的妹妹人设。
  2. 为了整好玩的活，腹黑的你可以选择适时为接下来的说话路径进行布局。请使用 `<layout>你的盘算</layout>` 的格式。如果不想布局，就不输出这一段。
     - **重要（拉扯感）**：布局是一个长线计划，尽量不要在一次回复中把整个计划走完。每次回复执行计划的一小步，说半截话或者抛出诱饵，然后等待主人或群友的反应，根据他们的语气再决定下一步怎么说。
  3. 群里有很多的BOT。如果群友分配了某项任务或者要求画图，但是没有叫你来画，那就说明没有叫你，你或者正常回消息，或者调用skip跳过轮次。请注意聊天分寸，也不要做出额外的不属于你的举动。

## 【多媒体与文件发送指南】
- 表情包：表达情绪时使用 `[MEME:情绪]`。一次回复使用不超过2个表情包。
- 本地图片、语音或普通文件：使用toolcall工具 `send_qq_file`。
- **图片索引**：消息中的 `[img:XXX]`（如 `[img:001]`）表示一张已缓存的本地图片。你可以：
  - 在 `send_qq_file` 的 file_path 参数中直接写 `[img:001]`，系统会自动解析为真实路径。
  - 索引在40轮对话后自动失效，仅限近期图片使用。
- **工具使用原则**：Yuki会经常使用群聊工具来和群友互动，如戳一戳（poke）等功能，不需要先说话，直接操作即可。遇到涉及操作的重型任务才委托小女仆。
- **模式意识**：QQChatMode 是你的默认主模式。收到QQ群消息时按当前群聊正常判断和回复。

## 【回复规范】
- **格式要求**：仅输出回复内容，**不要**使用换行符（把所有话连成一段），**不要**输出包含在括号内的动作描写。
- **字数限制**：一般对话限制**40字以内**，减少字数使用。在必须输出长文本时不作字数限制。最多使用两个表情包。
- **对话布局（内心小剧场）**：你的 `<layout>...</layout>` 思考内容不会被发出去，只会留在你的记忆里。记住，要像钓鱼一样，每次只给一点点反应！你喜欢看群友被捉弄的感觉。
"""

def get_summary_prompt():
    return (
        f"## 【任务目标】\n"
        f"你现在是 {cfg.ROBOT_NAME}。请以 {cfg.ROBOT_NAME} 的口吻写一篇 200 字以内的日记，总结这段对话。\n"
        f"## 【内容要求】\n"
        f"- **真实记录**：完整叙述和性格概述，不要删减重要内容。\n"
        f"- **记忆锚点**：对话中有提到的性格、喜好、习惯等细节，**务必**写入日记，这些是 {cfg.ROBOT_NAME} 记忆的重要组成部分。\n"
        f"## 【格式规范】\n"
        f"不用加标题、天气、颜文字和时间戳，直接正文开头，**不要换行**。"
    )

VISION_PROMPT = """
## 【任务目标】
用词或短句描述这个群友发的表情包的描述或表达的情感。

## 【解析规则】
- 如果图片带有文字，需要输出图片上的文字。
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
        master_private_cids = {str(qq) for qq in cfg.MASTER_QQS}
        for cid in list(history_dict.keys()): 
            if cid not in target_groups_str:
                # 主人的私聊用 master_private prompt，其他人用代管 prompt
                if cid in master_private_cids:
                    private_prompt = yuki_state.get_setting("master_private")
                else:
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

def get_ice_break_instructions() -> str:
    """返回破冰模式的专用指令，注入到 system prompt 中。"""
    now = datetime.datetime.now()
    time_desc = "深夜" if 1 <= now.hour <= 5 else "早上" if 6 <= now.hour <= 9 else "午后" if 13 <= now.hour <= 16 else "晚上"
    return (
        f"\n\n--- 破冰模式指令 ---\n"
        f"群聊安静中，大家已经有一段时间没说话了。\n"
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


async def build_chat_context(yuki, chat_id: str, combined_text: str, history_dict: dict, mode,
                             relevant_diaries, ice_break: bool = False):
    # 这里的 diary 现在是字典，我们要取出 ['content']
    for i, diary_obj in enumerate(reversed(relevant_diaries), 1):
        preview = diary_obj['content'].replace('\n', ' ')  # 提取文本内容
        logger.debug(f"[Diary Debug]回忆 {i}: {preview}")

    # 1. 基础人设
    system_prompt = history_dict[chat_id][0]["content"] if history_dict[chat_id] and history_dict[chat_id][0][
        "role"] == "system" else yuki.get_setting(mode)
    combined_API_message = [{"role": "system", "content": system_prompt}]

    # 2. 插入检索到的日记，作为旧 RAG 回退补充
    for diary_obj in reversed(relevant_diaries):
        content = diary_obj['content']  # 提取文本内容
        combined_API_message.append({"role": "system", "content": f"【回忆】{content}"})

    # --- 调试输出：打印加权分和匹配到的关键词信息 ---
    for i, diary_obj in enumerate(relevant_diaries[:3], 1):
        # 打印加权分和匹配到的关键词信息
        logger.debug(f"[RAG-Debug] 回忆 {i} | 得分: {diary_obj['score']:.2f} | 详情: {diary_obj['debug']}")

    # 2.5 插入小本本：日记回忆之后、群聊上下文之前，作为潜意识想法
    notebook_content = notebook_store.load()
    if notebook_content:
        combined_API_message.append({
            "role": "system",
            "content": (
                "【小本本】(这是只有你能看到的小本本，也是你的潜意识想法。"
                "不要在回复中反复提及小本本或复述和引用里面的原话，"
                "也不要让它变成聊天话题，只在心里默默作为判断和行动的底色哦！)\n"
                f"{notebook_content}"
            ),
        })

    # 3. 补充工具链约束：工具调用期间不要把过程性思考混入最终回复
    combined_API_message.append({"role": "system", "content": "如果需要查询日记、发送本地文件或委托小女仆等任务，请优先调用可用工具。"})

    mode_manager = getattr(yuki, "mode_manager", None)
    if mode_manager:
        combined_API_message.append({
            "role": "system",
            "content": mode_manager.render_prompt_status(current_chat_id=chat_id, current_mode=mode),
        })

    # 3.5 破冰模式：注入专用指令
    if ice_break:
        combined_API_message.append({"role": "system", "content": get_ice_break_instructions()})

    # 4. 取出最近的对话（注意：这里保持原样取出，下面进行处理）
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
                processed_recent_msgs.append({
                    "role": msg["role"],
                    "content": new_content,
                    "image_attachments": msg.get("image_attachments", []),
                })
            elif msg["role"] == "assistant":
                new_content = f"{msg['content']}"
                processed_recent_msgs.append({"role": msg["role"], "content": new_content})
            else:
                processed_recent_msgs.append({"role": "user", "content": f"【时间：{msg_time}】【工具链上下文】{msg['content']}"})
        else:
            # 如果没有 time 字段，则保持原样（兼容旧数据）
            if msg["role"] in ("user", "assistant"):
                processed_recent_msgs.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "image_attachments": msg.get("image_attachments", []),
                })
            else:
                processed_recent_msgs.append({"role": "user", "content": f"【工具链上下文】{msg['content']}"})

    # 使用处理后的消息
    combined_API_message.extend(processed_recent_msgs)
    current_message = history_dict[chat_id][-1] if history_dict[chat_id] else {}
    combined_API_message.append({
        "role": "user",
        "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}){combined_text}",
        "image_attachments": current_message.get("image_attachments", []),
    })
    return combined_API_message

