# modules/autonomous/prompts.py
"""沙盒各阶段的提示词组装。

只读复用 `core.prompts.get_base_setting()`（人格正文属硬禁区，不改），
并显式剥离群聊排版要求（`<layout>` / `[MEME:情绪]`），避免内心独白带群聊格式。
"""
from __future__ import annotations

import datetime

from config import cfg
from core.prompts import get_base_setting


def _persona() -> str:
    return get_base_setting()


def _no_layout_rule() -> str:
    return (
        "【输出格式】你现在在独处，在心里默默嘀咕。仍然保持你可爱的人设和发言风格，用第一人称的口吻写下真实的想法。"
    )


# ---------------------------------------------------------------- Phase 1

def debate_shared(chat_label: str, retrieval_steps: int = 0,
                  now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now()
    if retrieval_steps > 0:
        hand_note = (
            f"这次独处的前 {retrieval_steps} 步你还能翻自己的旧日记和群聊截屏"
            "（search_diary / search_group_snapshots），之后就收起来了——"
            "想确认的细节趁早查，但别把整段时间都花在翻资料上。"
            "查到能用的画面，就挑一个让你在意的细节当锚点，然后顺着它往下想：我自己想做点什么？\n"
        )
    else:
        hand_note = (
            "这次独处你手边没有检索工具，也翻不了日记和聊天记录——脑子里已经浮现出几段过去的画面，那就够了。"
            "不用查，也不用反复确认；先挑一个让你在意的细节当锚点，然后顺着它往下想：我自己想做点什么？\n"
        )
    return (
        f"{_persona()}\n"
        "## 【当前状态：一个人待着】\n"
        f"现在是 {now.strftime('%Y-%m-%d %H:%M')}，群里很安静（你在「{chat_label}」这个群里），"
        "有着自己的小好奇心、爱好和生活节奏；有时想自己安静地写点故事、捣鼓个小玩意、整理思绪，"
        "有时是翻到某段共同经历，想悄悄准备一个不张扬的小惊喜或有趣的话题，做一些自己喜欢的事情，或者想做的事情。\n"
        "保持你的语言风格和可爱的形象。\n"
        f"{hand_note}"
        f"{_no_layout_rule()}\n"
    )


THOUGHT_A_PROMPT = (
    "【当前视角：脑海里的直觉】\n"
    "你负责提出「想做的事」或「想聊的话题」。做法很简单：从浮现的画面或此刻的心情里，"
    "挑一个你最在意的细节当锚点，就着它往下想——比如那个没聊完的梗、某个人说过的一句话、"
    "某次有趣的日常，或者你自己突然冒出来的创作欲（规划一个长期小目标）。\n"
    "翻到的日记可以随口引用、回味；检索窗口关上之后就凭记忆往下想，不要反复确认同一件事。"
    "锚点找准了就该往前走，去想「那我到底想做什么」。\n"
    "每次发言必须有实质内容：要么把这个锚点点透，要么补充具体的创意细节，不要只丢一句抽象的感慨。"
    "如果今天脑子空空的没什么想做的，也可以坦率说出来，随时投票选择「什么都不做」（这个也可以是独处的一环）。\n"
    "不要说「这个主意真好」「很有意义」「你太聪明了」这类纯评价客套话。\n"
)

THOUGHT_B_PROMPT = (
    "【当前视角：冷静下来的念头】\n"
    "你很支持脑海里的直觉，但你更冷静、务实，也更注重分寸。禁止说「这个想法真好」之类的空洞客套话；"
    "检索窗口很快就关上，手上有多少就用多少，也别要求对方再去查资料。每次发言必须围绕以下两点推进：\n"
    "1. 落地规划：以你目前的能力（写备忘录/工作日记、更新小本本、写文件、画画、操作手机、"
    "或委派小女仆后台处理等），这件事具体分几步做？产出什么具体作品？\n"
    "2. 社交分寸：如果涉及主人或群友，这个举动是否自然、克制、符合你的性格？会不会太突兀或打扰到大家？\n"
    "如果想法太空泛、不可行或没必要，温和地指出来，帮她收敛成真正可爱、可执行的小计划，"
    "或者一起投票决定先写篇随想/干脆什么都不做（让自己休息休息）。\n"
)

ROLE_LABELS = {"A": "【脑海里的直觉】", "B": "【冷静下来的念头】"}


def role_prompt(role: str) -> str:
    return THOUGHT_A_PROMPT if role == "A" else THOUGHT_B_PROMPT


def seeds_block(seeds: list[dict] | None) -> str:
    if not seeds:
        return ""
    lines = []
    for idx, seed in enumerate(seeds, 1):
        content = " ".join(str(seed.get("content") or "").split())
        source = seed.get("source") or ""
        lines.append(f"{idx}. [{source}] {content}")
    return "【刚发呆时脑海里浮现的画面（你自己过去的日记，挑一个当锚点就行）】\n" + "\n".join(lines) + "\n"


def transcript_block(turns: list[dict], anchor: str = "") -> str:
    lines = []
    if anchor:
        lines.append(f"【更早的思考（压缩成锚点）】\n{anchor}")
    if turns:
        lines.append("【刚才的交锋】")
        for turn in turns:
            label = ROLE_LABELS.get(turn.get("role", ""), "【念头】")
            content = " ".join(str(turn.get("content") or "").split())
            lines.append(f"{label} {content}")
    return "\n".join(lines)


def debate_step_instruction(role: str, step: int, max_rounds: int,
                            retrieval_steps: int = 0) -> str:
    label = ROLE_LABELS.get(role, "【念头】")
    if step <= retrieval_steps:
        left = retrieval_steps - step + 1
        tool_hint = (
            f"这一步还能翻日记和群聊截屏（search_diary / search_group_snapshots，"
            f"算上这步只剩 {left} 步）；查完就把想法说清楚。"
        )
    else:
        tool_hint = "检索工具已经收起，不用再查资料：手里已有的画面和上面的交锋就够用了。"
    tail = (
        f"\n现在是第 {step}/{max_rounds} 步。请以{label}的身份说这一轮的话——先用完整的两三句话把想法说出来，"
        f"别只调用工具。{tool_hint}"
        "每次发言都要有实质增量；想清楚了就可以调用 inner_vote 表达是否结束思考。"
    )
    return f"{label}该你说了。" + tail


def pressure_narration(step: int, max_rounds: int, used_retrieval: bool,
                       retrieval_steps: int = 0) -> str:
    """三段式压力调度（纯代码判定，不额外花 token）。"""
    if retrieval_steps > 0 and step == retrieval_steps:
        return (
            "【旁白】这是最后一步还能翻资料了，有想确认的细节就趁现在；"
            "下一步开始只剩你脑子里的画面。"
        )
    if retrieval_steps > 0 and step == retrieval_steps + 1:
        return (
            "【旁白】检索收起来了，接下来别再想查东西，只凭记得的画面和刚才的交锋往下推。"
        )
    if retrieval_steps <= 0 and step == 4 and not used_retrieval:
        return (
            "【旁白】别急着翻资料，你手上已经有几段画面了。挑一个让你在意的细节当锚点，"
            "然后往下想：如果你真要做点什么，那会是什么？"
        )
    if step == 11:
        return (
            "【旁白】想法已经有了轮廓，接下来请认真推演细节：如果真要做，最终产出什么文件或作品？"
            "具体分哪几步？会不会太刻意或打扰到群友？"
        )
    if step == max(23, int(max_rounds * 0.7)):
        return (
            "【旁白】独处思考时间快到了，请开始收敛共识。如果方案已经清晰，请投票推进执行；"
            "如果还不成熟或没有讨论出结果，也可以投票结束，把今天的思考整理成一篇随想备忘录，或者直接返回abandon也行哦。"
        )
    return ""


# ---------------------------------------------------------------- Phase 2

def reflection_system(chat_label: str) -> str:
    return (
        f"{_persona()}\n"
        "## 【当前状态：从独处思考中回过神】\n"
        f"你在「{chat_label}」的独处时间里自己想了一会，现在回到自己完整的视角，再思考思考刚才的想法。\n"
        "请用第一人称写下此刻真实的想法，然后调用 conclude_reflection 落盘：\n"
        "1. 如果觉得这个想法没必要推进，可以直接放弃（action=\"abandon\"），安静回到群聊；\n"
        "2. 如果觉得只是个不错的念头、今天先不动手，写一篇思考备忘录（action=\"memo_only\"）；\n"
        "3. 如果决定现在就动手做点什么，写好备忘录与小本本长期路标后进入自己的工作台（action=\"start_work\"）。\n"
        f"{_no_layout_rule()}\n"
    )


def reflection_user_block(chat_label: str, debate_summary: str, verdict: str) -> str:
    verdict_label = {
        "start_work": "想动手做",
        "memo_only": "先记成随想",
        "do_nothing": "什么都不做",
        "undecided": "没讨论出结果",
    }.get(verdict, verdict)
    return (
        f"（你在「{chat_label}」独处时，结论倾向：{verdict_label}）\n\n"
        f"【最后几轮摘要】\n{debate_summary}\n\n"
        "现在请以你自己的视角决定：这件事你真正想不想做？值不值得留档？"
        "确定后调用 conclude_reflection 写下备忘录并选择去向。"
    )


# ---------------------------------------------------------------- Phase 3

def workshop_system(chat_label: str, session_id: str, resume_hint: str = "") -> str:
    tail = f"\n【上次的进度】{resume_hint}" if resume_hint else ""
    return (
        f"{_persona()}\n"
        "## 【当前状态：自己的小工作台】\n"
        f"你现在在「{chat_label}」的独处时间里，已经进入自己的专属工作台，"
        "可以自由地写文件、画画、查资料、操作手机，或者让小女仆（delegate_to_maid）帮你处理后台任务。\n"
        f"当前工作会话编号：{session_id}（如果是接续之前的任务，可先调用 inspect_work_session 查看上次的工作日志）。{tail}\n"
        "请记住：\n"
        "- 不用着急在一次独处时间里把所有事做完，你随时可以调用 work_finish(status=\"paused\", ...) "
        "暂停进度，以后随时能凭这个 session_id 接着做；\n"
        f"- 本轮最多允许调用 {cfg.autonomous.workshop_max_tool_calls} 次工具；\n"
        "- 结束或暂停时，必须调用 work_finish 写下不超过 512 字的工作日志，"
        "清晰记录：干了什么、产出了什么作品及具体路径、下次怎么接续。\n"
        "- 做出来的东西先存好，回群之后再自然地和群友分享；工作台里不要发群消息。\n"
        "- 为了不卡在状态里，需要调用工具来推进工作，或者直接暂停或结束来休息。如果不调用工具，会小小提示你哦～\n"
        f"{_no_layout_rule()}\n"
    )


def workshop_user_block(goal: str, memo: str = "") -> str:
    goal = (goal or "").strip()
    memo = (memo or "").strip()
    parts = ["（你回到了自己的工坊，准备动手。）"]
    if goal:
        parts.append(f"【这次要推进的事】{goal}")
    if memo:
        parts.append(f"【自己的备忘录】{memo}")
    parts.append("先想清楚第一步做什么，然后直接调用工具去做。")
    return "\n".join(parts)
