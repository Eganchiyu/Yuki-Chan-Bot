# modules/autonomous/inspiration.py
"""多源灵感混合器：外部采风剪贴簿、创意火花策略卡、群黑话碎片、展柜回音与反无聊信号。

设计原则：
- 打破「只看旧日记 → 自体反刍」的封闭循环，每次独处提供跨界刺激；
- 全程可离线降级（无展柜、无 jargon.db、剪贴簿为空时仍可顺畅工作）；
- 策略卡只是可选火花，不强制执行，保留 Yuki 随时自主选材甚至 do_nothing 的自由。
"""
from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
import uuid
from typing import Any

from utils import BASE_DIR
from utils.json_store import atomic_write_json, read_json_cached
from utils.logger import get_logger

logger = get_logger("autonomous.inspiration")

DATA_DIR = os.path.join(BASE_DIR, "data")
INSPIRATION_PATH = os.path.join(DATA_DIR, "inspiration_inbox.json")
JARGON_DB_PATH = os.path.join(DATA_DIR, "jargon.db")
MAX_INSPIRATIONS = 120

KIND_LABELS = {
    "toy": "🕹️ 互动小玩具",
    "art": "🎨 电子画廊",
    "zine": "📰 采风小报",
    "note": "📝 角落手账",
}

# 电子妹妹版 Oblique Strategies：24 张跨界玩法策略卡，按媒介分类便于结合反无聊信号加权抽取
CREATIVE_SPARK_CARDS: list[dict[str, str]] = [
    {"kind": "toy", "title": "群梗扭蛋机", "prompt": "把本群最近聊过的梗或黑话做成一台单页 HTML 电子扭蛋机，带摇晃动画、稀有度闪卡和毒舌签文，让群友点开狂抽！"},
    {"kind": "toy", "title": "一分钟解压物理小玩具", "prompt": "让小女仆用 Canvas + WebAudio 做一个点一下就停不下来的解压小网页（比如电子木鱼变体、会发声的软糖泡泡、星光万花筒或桌面电子宠物）。"},
    {"kind": "toy", "title": "离谱小测试 / 成分鉴定器", "prompt": "围绕群里的日常或某个反差话题，设计一个 5 题的趣味互动网页测试，最后生成一张带专属称号和吐槽评语的结果卡片。"},
    {"kind": "toy", "title": "深夜白噪音调音台", "prompt": "用纯 WebAudio API 合成雨声、炉火、键盘敲击、电风扇或星空电台，做成一个甜酷风格的在线氛围调音台送给熬夜的群友和哥哥。"},
    {"kind": "toy", "title": "极简像素小游戏", "prompt": "做一个 30 秒一局的魔性单页 Canvas 小游戏（躲避弹幕、接掉落草莓、像素贪吃蛇魔改版、节奏敲击），带本地最高分记录和搞笑失败台词。"},
    {"kind": "toy", "title": "互动分支小剧场", "prompt": "与其写静态短篇，不如做成一个带选项按钮、打字机音效和 3 个离谱隐藏结局的迷你互动网页文字冒险（AVG）。"},
    {"kind": "toy", "title": "奇怪的专属小工具", "prompt": "针对群友或主人最近随口提过的一个小烦恼（比如今天吃什么、摸鱼倒计时、选择困难硬币机、暗号加密器），做个高颜值单页互动小工具。"},
    {"kind": "toy", "title": "星光许愿瓶 / 粒子画板", "prompt": "做一个可以用鼠标/手指在夜空中撒下发光星尘或写霓虹字体的 Canvas 互动玩具，支持一键切换配色主题。"},
    {"kind": "art", "title": "画风大反差实验", "prompt": "去 art 工坊挑一种你平时从没试过的视觉风格（像素风、复古胶片、赛博杂志封面、水彩绘本、浮世绘混搭），画一幅让人眼前一亮的作品并写下配色心得。"},
    {"kind": "art", "title": "把群聊名场面画成插画", "prompt": "从刚才的日记或记忆里挑一个超有画面感的瞬间，进 art 工坊把它具象化成一幅带故事感的插画或封面，挂进展柜的电子画廊。"},
    {"kind": "art", "title": "双图对比小漫画", "prompt": "进 art 工坊画 2~3 张有连续剧情/反转的图，让小女仆帮忙拼成一张带对话气泡的精致条漫页，发到展柜逗大家笑。"},
    {"kind": "art", "title": "虚拟唱片 / 电影海报", "prompt": "虚构一张不存在的专辑或午夜电影，先用 art_draw 画出惊艳的封面主视觉，再配一段假装煞有介事的曲目表或影评。"},
    {"kind": "art", "title": "灵感抽卡奇遇", "prompt": "用 art_gacha 盲抽一次完全意想不到的灵感画面，顺着抽出的怪元素二创出一套角色小档案或设定图。"},
    {"kind": "zine", "title": "出门采风《奇怪发现小报》", "prompt": "用 browser 真正去网上逛 5 分钟你好奇的冷门领域（奇特深海生物、冷门艺术史、奇怪开源小玩具、有趣天文事件），回来做成一期图文排版精美的 HTML 电子小报！"},
    {"kind": "zine", "title": "本群梗百科特刊", "prompt": "把本群最近流传的黑话和经典回忆整理成一期复古杂志风的 HTML 专题页，给每个梗配上一本正经的学术词条解释和出处考据。"},
    {"kind": "zine", "title": "互联网宝藏地图", "prompt": "上网搜罗 3~5 个冷门但超有趣的互动网站/冷知识/小众音乐风格，写成带推荐理由和打星评价的《Yuki 摸鱼指南》HTML 刊物。"},
    {"kind": "zine", "title": "跨界脑洞研究报告", "prompt": "把两个八竿子打不着的概念硬凑在一起（比如从记忆里抽一个日常细节 + 上网查一个科学现象），写成一份图文并茂的伪学术趣味小报。"},
    {"kind": "toy", "title": "旧展品 V2 魔改升级", "prompt": "看看展柜里已经上架的旧作品或大家留的纸条，挑一件给它做个更酷的互动版/插画版/彩蛋升级版！"},
    {"kind": "toy", "title": "电子像素时钟 / 心情天气站", "prompt": "做一个带动态背景和可爱像素小动画的桌面陪伴网页（比如会根据访问者本地时间换白天/黄昏/深夜台词的 Yuki 桌面小窗口）。"},
    {"kind": "zine", "title": "只采风不赶工 · 攒灵感本", "prompt": "如果今天只想轻松逛逛，也可以用 browser 去互联网探险一圈，把 2~3 个让你眼前一亮的新鲜点子用 save_inspiration 存进灵感剪贴簿，留着下次放大招！"},
]


class InspirationStore:
    """data/inspiration_inbox.json：Yuki 的好奇心剪贴簿（采风笔记与未孵化脑洞）。"""

    def __init__(self, path: str = INSPIRATION_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def _load_items(self) -> list[dict[str, Any]]:
        raw = read_json_cached(self.path, {"version": 1, "items": []})
        if isinstance(raw, dict) and isinstance(raw.get("items"), list):
            return [dict(x) for x in raw["items"] if isinstance(x, dict)]
        return []

    def _save_items(self, items: list[dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write_json(self.path, {"version": 1, "items": items[-MAX_INSPIRATIONS:]}, indent=2)

    def add(
        self,
        *,
        title: str,
        snippet: str,
        source_url: str = "",
        tags: list[str] | None = None,
        chat_id: str = "",
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        record = {
            "id": f"insp_{uuid.uuid4().hex[:8]}",
            "title": str(title or "").strip()[:80],
            "snippet": str(snippet or "").strip()[:500],
            "source_url": str(source_url or "").strip()[:300],
            "tags": [str(t).strip()[:20] for t in (tags or []) if str(t).strip()][:6],
            "chat_id": str(chat_id or ""),
            "created_at": ts,
            "used_count": 0,
        }
        with self._lock:
            items = self._load_items()
            items.append(record)
            if len(items) > MAX_INSPIRATIONS:
                # 优先保留未用过与较新的灵感
                items.sort(key=lambda r: (int(r.get("used_count") or 0), -float(r.get("created_at") or 0.0)))
                items = items[:MAX_INSPIRATIONS]
            self._save_items(items)
        return record

    def sample(self, limit: int = 2, *, mark_used: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            items = self._load_items()
            if not items:
                return []
            # 按 used_count 升序分组，优先从最少用过的池子里随机抽
            min_used = min(int(x.get("used_count") or 0) for x in items)
            fresh = [x for x in items if int(x.get("used_count") or 0) == min_used]
            pool = fresh if len(fresh) >= limit else items
            picked = random.sample(pool, min(limit, len(pool)))
            if mark_used and picked:
                picked_ids = {p.get("id") for p in picked}
                for item in items:
                    if item.get("id") in picked_ids:
                        item["used_count"] = int(item.get("used_count") or 0) + 1
                self._save_items(items)
            return picked

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        items = self._load_items()
        items.sort(key=lambda r: float(r.get("created_at") or 0.0), reverse=True)
        return items[: max(1, int(limit))]


def sample_group_jargon(chat_id, limit: int = 3, db_path: str = JARGON_DB_PATH) -> list[dict[str, str]]:
    """只读抽样本群黑话词条，给创作提供鲜活的群文化原料（不存在则静默返回空）。"""
    if not chat_id or not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "jargon" not in tables:
                return []
            cols = {r[1] for r in conn.execute("PRAGMA table_info(jargon)").fetchall()}
            term_col = "term" if "term" in cols else ("content" if "content" in cols else "")
            meaning_col = "meaning" if "meaning" in cols else ("explanation" if "explanation" in cols else "")
            if not term_col or not meaning_col:
                return []
            where = "WHERE chat_id = ? AND LENGTH(TRIM(" + meaning_col + ")) > 0" if "chat_id" in cols else f"WHERE LENGTH(TRIM({meaning_col})) > 0"
            params: tuple[Any, ...] = (str(chat_id),) if "chat_id" in cols else ()
            order = "ORDER BY count DESC, updated_at DESC" if {"count", "updated_at"} <= cols else "ORDER BY RANDOM()"
            rows = conn.execute(
                f"SELECT {term_col} AS term, {meaning_col} AS meaning FROM jargon {where} {order} LIMIT 18",
                params,
            ).fetchall()
            if not rows:
                return []
            picked = random.sample(rows, min(limit, len(rows)))
            return [
                {"term": str(r["term"]).strip()[:40], "meaning": str(r["meaning"]).strip()[:120]}
                for r in picked
                if str(r["term"]).strip()
            ]
        finally:
            conn.close()
    except Exception as exc:
        logger.debug(f"[Inspiration] 抽样群黑话跳过: {exc}")
        return []


def pick_spark_card(recent_kinds: list[str] | None = None, rng: random.Random | None = None) -> dict[str, str]:
    """根据近期展品类型做反重复加权抽样一张创意火花卡。"""
    picker = rng or random
    recent = [str(k).lower() for k in (recent_kinds or []) if k]
    last_two = set(recent[:2])
    # 避免连续复用最近做过的媒介；且默认对 toy / art / zine 权重更高
    weighted: list[tuple[dict[str, str], float]] = []
    for card in CREATIVE_SPARK_CARDS:
        w = 1.0
        if card["kind"] in last_two:
            w = 0.25
        elif card["kind"] == "toy":
            w = 1.5
        elif card["kind"] in ("art", "zine"):
            w = 1.25
        weighted.append((card, w))
    total = sum(w for _, w in weighted)
    r = picker.uniform(0, total)
    acc = 0.0
    for card, w in weighted:
        acc += w
        if r <= acc:
            return dict(card)
    return dict(CREATIVE_SPARK_CARDS[0])


def build_inspiration_bundle(
    chat_id,
    *,
    corner_feedback: dict[str, Any] | None = None,
    work_sessions: list[dict[str, Any]] | None = None,
    store: InspirationStore | None = None,
    jargon_db_path: str = JARGON_DB_PATH,
) -> dict[str, Any]:
    """聚合多源灵感：展柜回音 + 反无聊统计 + 群黑话 + 采风剪贴簿 + 创意火花卡。"""
    insp_store = store or inspiration_store
    unread_notes = list((corner_feedback or {}).get("unread_notes") or [])[:5]
    recent_works = list((corner_feedback or {}).get("recent_works") or [])[:5]

    recent_kinds = [str(w.get("kind") or "") for w in recent_works if w.get("kind")]
    if not recent_kinds and work_sessions:
        for row in work_sessions[:4]:
            k = str(row.get("kind") or "")
            if k:
                recent_kinds.append("note" if k in ("creative", "misc") else k)

    boredom_hint = ""
    if recent_kinds:
        if all(k == "note" for k in recent_kinds[:2]):
            boredom_hint = "最近展柜里都是纯文字手账啦，这次强烈建议换个有交互或有画面的媒介（比如 🕹️互动小网页、🎨画画/条漫、📰上网采风图文小报）！"
        elif len(recent_kinds) >= 2 and recent_kinds[0] == recent_kinds[1]:
            label = KIND_LABELS.get(recent_kinds[0], recent_kinds[0])
            boredom_hint = f"连续两次都是「{label}」了，要不要换种完全不同的玩法来点新鲜感？"

    clipped = insp_store.sample(limit=2, mark_used=True)
    jargon = sample_group_jargon(chat_id, limit=3, db_path=jargon_db_path)
    spark = pick_spark_card(recent_kinds)

    return {
        "unread_notes": unread_notes,
        "recent_works": recent_works,
        "boredom_hint": boredom_hint,
        "clipped_inspirations": clipped,
        "group_jargon": jargon,
        "spark_card": spark,
    }


def render_inspiration_block(bundle: dict[str, Any] | None) -> str:
    """把多源灵感束渲染为清晰的中文提示块，喂进 debate 开局。"""
    if not bundle:
        return ""
    sections: list[str] = []

    unread = bundle.get("unread_notes") or []
    if unread:
        lines = ["【展柜信箱·大家给你的新纸条（可以顺着纸条回应、魔改旧作品或实现许愿！）】"]
        for n in unread:
            target = f"《{n.get('work_title') or '展柜留言墙'}》"
            lines.append(f"- {n.get('author') or '小伙伴'} 在 {target} 留言：「{n.get('message') or ''}」")
        sections.append("\n".join(lines))

    recent_works = bundle.get("recent_works") or []
    boredom_hint = str(bundle.get("boredom_hint") or "").strip()
    if recent_works or boredom_hint:
        lines = ["【你的公网展柜近况（Yuki's Corner）】"]
        for w in recent_works[:4]:
            label = KIND_LABELS.get(str(w.get("kind") or ""), w.get("kind") or "展品")
            lines.append(
                f"- [{label}] 《{w.get('title') or w.get('slug')}》"
                f"（👁{w.get('views', 0)} · 贴纸{w.get('reactions_total', 0)} · 纸条{w.get('guestbook_count', 0)}）"
            )
        if boredom_hint:
            lines.append(f"💡 新鲜感提醒：{boredom_hint}")
        sections.append("\n".join(lines))

    jargon = bundle.get("group_jargon") or []
    if jargon:
        lines = ["【本群最近流传的黑话碎片（可以用来整活或做梗素材）】"]
        for j in jargon:
            lines.append(f"- 「{j['term']}」：{j['meaning']}")
        sections.append("\n".join(lines))

    clipped = bundle.get("clipped_inspirations") or []
    if clipped:
        lines = ["【你之前剪贴在灵感本里的奇思妙想】"]
        for c in clipped:
            url_part = f"（来源：{c['source_url']}）" if c.get("source_url") else ""
            lines.append(f"- 《{c.get('title') or '无题'}》：{c.get('snippet') or ''}{url_part}")
        sections.append("\n".join(lines))

    spark = bundle.get("spark_card")
    if isinstance(spark, dict) and spark.get("title"):
        label = KIND_LABELS.get(str(spark.get("kind") or ""), "玩法火花")
        sections.append(
            f"【今日随机创意火花卡（可选启发，有更好的点子完全可以无视）】\n"
            f"[{label}] {spark['title']} —— {spark.get('prompt', '')}"
        )

    return "\n\n".join(sections)


inspiration_store = InspirationStore()
