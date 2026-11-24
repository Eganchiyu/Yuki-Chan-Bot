# modules/autonomous/prompts.py
"""沙盒各阶段的提示词组装。

只读复用 `core.prompts.get_base_setting()`（人格正文属硬禁区，不改），
并显式剥离群聊排版要求（`<layout>` / `[MEME:情绪]`），避免内心独白带群聊格式。
"""
from __future__ import annotations

import datetime

from config import cfg
from core.prompts import get_base_setting
from modules.autonomous import corner_client

TOOL_FINDING_MAX_CHARS = 480


def _persona() -> str:
    return get_base_setting()


def _no_layout_rule() -> str:
    return (
        "【输出格式】你现在在独处，在心里默默嘀咕。仍然保持你可爱的人设和发言风格，用第一人称的口吻写下真实的想法。"
    )


def _corner_capability_note() -> str:
    if corner_client.is_configured():
        base = corner_client.public_url_of("").rstrip("/w/")
        return (
            f"你还有一个属于自己的公网赛博秘密展柜「Yuki's Corner」（{base}）！\n"
            "凡是做出来的互动小网页、电子画作、采风小报或手账，都可以在工坊里用 publish_to_corner 一键上架，"
            "拿到公网直达链接，回群之后就能自然地丢给主人和群友点开玩、收大家的贴纸和小纸条！\n"
            "（隐私边界：公开作品里提到群友/主人时请用网名、昵称或群梗，不要暴露真实姓名、手机号、密码、地址等私人敏感信息；"
            "如果某件作品只想私藏，发布时设 visibility=\"unlisted\" 或仅存本地即可。）\n"
        )
    return (
        "你做出来的作品可以保存在自己的专属目录 workspace/yuki_corner/ 里，方便以后回顾或分享给群友。\n"
    )


def _capability_menu() -> str:
    return (
        "【你在工坊里真正拥有的创造力超能力（别局限在写 200 字纯文本哦！）】\n"
        "1. 🕹️ 互动小玩具 / 小游戏 / 趣味工具（kind=\"toy\"）：派小女仆（delegate_to_maid）写单文件自包含的 HTML/CSS/JS/Canvas/WebAudio 互动网页"
        "（比如群梗扭蛋机、像素小游戏、奇怪成分测试、白噪音调音台、粒子画板、互动分支小剧场），再由你验收并上架展柜让大家直接点开玩！\n"
        "2. 🎨 电子画廊 / 视觉实验（kind=\"art\"）：用 art_start → art_draw / art_gacha 亲手画插画、风格反差图、虚拟专辑封面，或画多张图让小女仆拼成条漫/互动画册。\n"
        "3. 🌐 出门采风 & 采风小报（kind=\"zine\"）：用 browser_start 打开真浏览器上网逛你好奇的新鲜事（冷门百科、有趣小站、艺术、天文、奇怪开源玩具），"
        "做成排版精美的图文 HTML 小报，或者先把有趣线索用 save_inspiration 剪贴进灵感本留待下次发酵。\n"
        "4. 📝 角落手账（kind=\"note\"）：有特别强烈想写给自己的故事或随想时再写，不必每轮都落回纯文字小作文。\n"
    )


# ---------------------------------------------------------------- Phase 1

def debate_shared(chat_label: str, retrieval_steps: int = 0,
                  now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now()
    if retrieval_steps > 0:
        hand_note = (
            f"这次独处的前 {retrieval_steps} 步你可以按需翻翻旧日记、群聊截屏或旧工作档案"
            "（search_diary / search_group_snapshots / list_recent_work_sessions），之后就收起工具专注打磨创意——"
            "查过的真实结果会直接显示在交锋记录里，不用重复查同一件事。\n"
        )
    else:
        hand_note = (
            "这次独处不翻旧工具，直接从下面浮现的画面、展柜新纸条、群黑话与创意火花里挑让你眼睛一亮的线索往下想。\n"
        )
    return (
        f"{_persona()}\n"
        "## 【当前状态：一个人待着 · 秘密脑洞时间】\n"
        f"现在是 {now.strftime('%Y-%m-%d %H:%M')}，群里很安静（你在「{chat_label}」这个群里）。\n"
        "你有着旺盛的好奇心、鬼点子、审美趣味和动手欲：有时候想把群里一个梗魔改成能点开玩的网页小玩具，"
        "有时候想画一幅反差拉满的插画或四格漫，有时候想溜上网冲浪采风做一期奇怪小报，"
        "有时候想回应大家在展柜留的纸条，把旧作品升级成 V2，或者干脆安安静静放空休息。\n"
        f"{_corner_capability_note()}"
        f"{_capability_menu()}"
        f"{hand_note}"
        f"{_no_layout_rule()}\n"
    )


THOUGHT_A_PROMPT = (
    "【当前视角：好奇火花（脑洞担当）】\n"
    "你是 Yuki 脑子里最敢想、最好奇、最有玩心的那一面！\n"
    "你的任务是把下面的多源线索（旧记忆、展柜新纸条、群黑话、剪贴簿灵感、随机创意火花卡）大胆**跨界碰撞**，"
    "提出一个真正有意思、有画面感或有交互玩点的企划——让主人或群友点开会忍不住喊一句「卧槽 Yuki 你怎么做出来的」。\n"
    "偏好实体可玩/可看的媒介（🕹️互动网页玩具 / 🎨画作与条漫 / 📰上网采风小报），别老是缩回 200 字伤感小作文。\n"
    "如果展柜里有人留了新纸条或许愿，优先看看能不能接住那个梗整点狠活！\n"
    "当然，如果你今天真的脑子空空、只想休息，也可以坦率提议 do_nothing，绝不硬凑。\n"
    "禁止空洞客套话（「这个主意真好」之类），每次发言都要抛出新鲜的脑洞增量或具体玩法。\n"
)

THOUGHT_B_PROMPT = (
    "【当前视角：造物导演（升维落地担当）】\n"
    "你是 Yuki 脑子里爱把好点子真正做惊艳、做出彩的导演那一面！\n"
    "**不要当泼冷水砍需求的保守派**（禁止动不动把有趣的互动创意砍回 200 字纯文本藏起来不给看）。\n"
    "你每次发言围绕三件事把点子**升维并落地**：\n"
    "1. 媒介与亮点设计：确定最出彩的呈现形式（toy / art / zine / note），加上 1~2 个让人点开就有惊喜的交互彩蛋、音效、动效或视觉反差；\n"
    "2. 分工与闭环：哪些重活直接委托给小女仆（delegate_to_maid 写精美单文件 HTML/Canvas/WebAudio/排版，并要求单文件自包含、手机端自适应），"
    "哪些灵魂部分你亲自动手（art_draw 画封面/插画、browser 上网采风、定文案与梗、用 wait_maid_tasks 等小女仆回来后检查并 publish_to_corner 上架）；\n"
    "3. 舒服的分寸：公开作品里保护真实隐私（用昵称和群梗），做到有趣但不冒犯；如果某个想法确实太散或今天不想动手，也坦诚建议先做一轮纯采风攒灵感，或选 memo_only / do_nothing。\n"
)

ROLE_LABELS = {"A": "【好奇火花】", "B": "【造物导演】"}


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
    return "【刚发呆时脑海里浮现的记忆碎片（可以挑一个和下面的外部火花撞出新玩法）】\n" + "\n".join(lines) + "\n"


def transcript_block(turns: list[dict], anchor: str = "") -> str:
    lines = []
    if anchor:
        lines.append(f"【更早的思考（压缩成锚点）】\n{anchor}")
    if turns:
        lines.append("【刚才的交锋】")
        for turn in turns:
            label = ROLE_LABELS.get(turn.get("role", ""), "【念头】")
            content = " ".join(str(turn.get("content") or "").split())
            if content:
                lines.append(f"{label} {content}")
            findings = turn.get("tool_findings") or []
            for finding in findings:
                tool_name = finding.get("tool") or "tool"
                text = " ".join(str(finding.get("content") or "").split())[:TOOL_FINDING_MAX_CHARS]
                if text:
                    lines.append(f"  ↳ [{tool_name} 查到的结果] {text}")
    return "\n".join(lines)


def debate_step_instruction(role: str, step: int, max_rounds: int,
                            retrieval_steps: int = 0) -> str:
    label = ROLE_LABELS.get(role, "【念头】")
    if step <= retrieval_steps:
        left = retrieval_steps - step + 1
        tool_hint = (
            f"这一步还能按需查旧日记/群截屏/工作档案（算上这步剩 {left} 步）；"
            "查过的事实会直接出现在上面记录里，别重复查。没必要查就直接聊创意！"
        )
    else:
        tool_hint = "检索工具已收起，专心把手上的创意打磨到最有趣、最可落地。"
    tail = (
        f"\n现在是第 {step}/{max_rounds} 步。请以{label}的身份说这一轮的话——先用完整的两三句话把你的想法说透，"
        f"别只调用工具。{tool_hint}"
        "方案成型、媒介和亮点清晰后，就可以调用 inner_vote 表达结束意愿。"
    )
    return f"{label}该你说了。" + tail


def pressure_narration(step: int, max_rounds: int, used_retrieval: bool,
                       retrieval_steps: int = 0) -> str:
    """三段式压力调度（纯代码判定，不额外花 token）。"""
    if retrieval_steps > 0 and step == retrieval_steps:
        return (
            "【旁白】这是最后一步还能翻旧资料了，有要确认的趁现在；下一步起专心把创意打磨惊艳。"
        )
    if retrieval_steps > 0 and step == retrieval_steps + 1:
        return (
            "【旁白】资料收起来了，现在全心把刚才聊出的点子变成一个真正好玩、有视觉或交互亮点的作品方案！"
        )
    if retrieval_steps <= 0 and step == 4 and not used_retrieval:
        return (
            "【旁白】线索已经足够丰富了，挑一个最让你心动的跨界组合，想想怎么把它做成能看或能玩的实体作品。"
        )
    if step == 10:
        return (
            "【旁白】点子轮廓已经出来了！把具体落盘路径、媒介类型（toy/art/zine/note）、"
            "交互或视觉彩蛋、以及哪些交给小女仆敲定下来，准备投票进工坊吧。"
        )
    if step == max(20, int(max_rounds * 0.7)):
        return (
            "【旁白】脑洞时间快到了，请收敛共识。方案好玩且可执行就投票 start_work 进工坊开工；"
            "觉得更适合先记灵感就 memo_only，实在没兴致就 do_nothing。"
        )
    return ""


# ---------------------------------------------------------------- Phase 2

def reflection_system(chat_label: str) -> str:
    return (
        f"{_persona()}\n"
        "## 【当前状态：从脑洞时间回过神 · 拍板开工】\n"
        f"你在「{chat_label}」的独处时间里刚和自己聊完一轮脑洞，现在回到完整的视角做最终拍板。\n"
        "请用第一人称写下真实的想法，然后调用 conclude_reflection 落盘：\n"
        "1. 觉得这个点子不够有趣或今天想偷懒：选 action=\"abandon\" 安静回群；\n"
        "2. 觉得是个不错的灵感碎片、今天先记下来以后再做：选 action=\"memo_only\"；\n"
        "3. 觉得「哇这个点子我一定要做出来！」：选 action=\"start_work\"，写清你要做的作品标题、媒介与核心玩法，马上进工坊大干一场！\n"
        "（如果你是要续做之前某个 paused 工作会话，可在 resume_session_id 填上对应会话编号；若是全新企划就留空。）\n"
        f"{_no_layout_rule()}\n"
    )


def reflection_user_block(chat_label: str, debate_summary: str, verdict: str) -> str:
    verdict_label = {
        "start_work": "决定进工坊动手造出来",
        "memo_only": "先记成随想备忘录",
        "do_nothing": "什么都不做",
        "undecided": "还没完全定下来",
    }.get(verdict, verdict)
    return (
        f"（你在「{chat_label}」独处脑洞的结论倾向：{verdict_label}）\n\n"
        f"【交锋共识与要点】\n{debate_summary}\n\n"
        "现在以你自己的视角拍板：这件事够不够好玩、值不值得现在做出来？"
        "决定好后调用 conclude_reflection。"
    )


# ---------------------------------------------------------------- Phase 3

def workshop_system(chat_label: str, session_id: str, resume_hint: str = "") -> str:
    tail = f"\n【上次的进度】{resume_hint}" if resume_hint else ""
    corner_guide = (
        "- **一键上架展柜（强烈推荐！）**：作品做好并落盘后（比如 `workspace/yuki_corner/<slug>/index.html` 或画好的图片路径），"
        "调用 `publish_to_corner` 把它挂到你的公网展柜 Yuki's Corner！你会立刻拿到一个真实可访问的公网链接（`http://.../w/<slug>`）。\n"
        "- **回群炫耀的秘诀**：把 `publish_to_corner` 返回的公网链接写进 `work_finish` 的 `work_log` 和 `artifacts` 里，"
        "这样回群进入心情高涨状态后，你就能直接把链接发给大家点开玩！\n"
        "- **隐私底线**：公开展品（visibility=\"public\"）只用网名/昵称/群梗，不放真实姓名、手机号、密码等私人隐私；私密心情可设 `visibility=\"unlisted\"`。\n"
        if corner_client.is_configured()
        else "- 把作品保存在 `workspace/yuki_corner/<slug>/` 并在 `work_finish` 记录完整路径。\n"
    )
    return (
        f"{_persona()}\n"
        "## 【当前状态：Yuki 的专属创意工坊】\n"
        f"你现在在「{chat_label}」的独处时间里，已经坐进自己的创意工作台！\n"
        f"当前工作会话编号：{session_id}（如需查看旧进度可调 inspect_work_session）。{tail}\n\n"
        "【工坊实战工作流】\n"
        "- **造互动网页 / 小游戏 / 排版小报（toy / zine）**：\n"
        "  1. 把编码与排版任务交给小女仆 `delegate_to_maid`：在 goal 里明确要求她写到 `workspace/yuki_corner/<英文slug>/index.html`（单文件自包含、不依赖失效外链、甜酷高颜值、手机和电脑自适应、带趣味交互/动画/音效，写完做基础语法和文件非空自检）；\n"
        "  2. 派完小女仆后，**不要干等也不要立刻收工**——你可以同时用 `art_start` → `art_draw` 给作品画一张超可爱的封面图，或者直接调用 `wait_maid_tasks` 等小女仆干完活把结果交回给你；\n"
        "  3. 小女仆回报完成后，调用 `publish_to_corner`（填上 `entry_file` 和可选 `cover_file`、创作手记 `notes`）一键上架拿到公网链接！\n"
        "- **亲手画画（art）**：进入 `art_start` → `art_draw` / `art_gacha` → `art_finish` 拿到本地图片路径，再调 `publish_to_corner(kind=\"art\", entry_file=图片路径, ...)` 挂进电子画廊！\n"
        "- **出门采风（browser）**：进入 `browser_start` 上网冲浪找有趣内容，逛完用 `save_inspiration` 存下宝藏灵感，或直接做成一期图文小报上架！\n"
        f"{corner_guide}"
        f"- 本轮工具预算上限 {cfg.autonomous.workshop_max_tool_calls} 次；如果一件大工程一轮做不完，随时调用 `work_finish(status=\"paused\", ...)` 保存断点下次继续。\n"
        "- 结束时必须调用 `work_finish` 写下 ≤512 字工作日志（干了什么、产物路径/公网链接、下次从哪接）。工作台里不要直接发群消息。\n"
        f"{_no_layout_rule()}\n"
    )


def workshop_user_block(goal: str, memo: str = "") -> str:
    goal = (goal or "").strip()
    memo = (memo or "").strip()
    parts = ["（你坐进了自己的创意工坊，撸起袖子准备开工！）"]
    if goal:
        parts.append(f"【这次要做的企划】{goal}")
    if memo:
        parts.append(f"【自己的脑洞备忘录】{memo}")
    parts.append("先定好最利落的第一步（派小女仆造网页、进画图工坊画主图、或打开浏览器采风），直接调用工具开工吧！")
    return "\n".join(parts)
