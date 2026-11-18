# core/browser_tree.py
"""浏览器主视觉交互树：视口探针、Main/Bar 配额降序排序、文本提炼、明确性判定与大号截图标注。"""
from __future__ import annotations

import io
import math
import os
import re
from typing import Any

from config import cfg
from utils.logger import get_logger

logger = get_logger("tools")

_ICONFONT_RE = re.compile(r"[\ua000-\uf8ff]+")
_ACTION_KEYWORDS_RE = re.compile(
    r"(开始|测试|进入|继续|下一步|确认|确定|提交|发送|搜索|登录|注册|播放|暂停|下载|购买|下单|加入|保存|关闭|取消|跳过|重试|刷新|展开)"
)
_BAR_ACCOUNT_RE = re.compile(r"(个人空间|头像|登录|注册|账号)")
_BAR_HIGH_VALUE_RE = re.compile(
    r"(搜索|关注|点赞|收藏|评论|分享|首页|主页|返回|关闭|详情|菜单|设置|动态|历史|消息|通知|购物车)"
)
_BAR_LOW_VALUE_RE = re.compile(
    r"(隐私|协议|条款|备案|icp|copyright|关于我们|帮助中心|友情链接|营业执照|举报)"
)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

# 注入到每个可见 Frame 的只读探针：提取视口内未遮挡控件 + 非交互文本 + 真交互画布占比
VIEWPORT_PROBE_JS = r"""(function() {
  var vw = window.innerWidth || document.documentElement.clientWidth || 0;
  var vh = window.innerHeight || document.documentElement.clientHeight || 0;
  var docEl = document.documentElement;
  var body = document.body;
  var scrollY = window.scrollY || window.pageYOffset || 0;
  var scrollH = Math.max(docEl ? docEl.scrollHeight : 0, body ? body.scrollHeight : 0, vh);
  var maxScroll = Math.max(0, scrollH - vh);
  var pctY = maxScroll > 0 ? Math.min(100, Math.round((scrollY / maxScroll) * 100)) : 0;

  function cleanText(s) {
    return String(s || '').replace(/[\uA000-\uF8FF]/g, '').replace(/\s+/g, ' ').trim();
  }

  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    var cs = window.getComputedStyle(el);
    if (!cs || cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity || '1') <= 0.02) {
      return false;
    }
    var cur = el;
    while (cur && cur.nodeType === 1) {
      if (cur.hasAttribute('hidden') || cur.getAttribute('aria-hidden') === 'true') return false;
      var pcs = window.getComputedStyle(cur);
      if (pcs && (pcs.display === 'none' || pcs.visibility === 'hidden' || parseFloat(pcs.opacity || '1') <= 0.02)) {
        return false;
      }
      cur = cur.parentElement;
    }
    return true;
  }

  function inViewportRect(r) {
    if (!r || r.width < 6 || r.height < 6) return null;
    var x1 = Math.max(0, r.left);
    var y1 = Math.max(0, r.top);
    var x2 = Math.min(vw, r.right);
    var y2 = Math.min(vh, r.bottom);
    if ((x2 - x1) < 4 || (y2 - y1) < 4) return null;
    return [x1, y1, x2, y2];
  }

  function hitTestVisible(el, rectBox) {
    var x1 = rectBox[0], y1 = rectBox[1], x2 = rectBox[2], y2 = rectBox[3];
    var pts = [
      [(x1 + x2) / 2, (y1 + y2) / 2],
      [x1 + Math.min(8, (x2 - x1) * 0.25), y1 + Math.min(8, (y2 - y1) * 0.25)]
    ];
    for (var i = 0; i < pts.length; i++) {
      var hit = document.elementFromPoint(pts[i][0], pts[i][1]);
      if (!hit) continue;
      if (hit === el || el.contains(hit) || hit.contains(el)) return true;
      // 同一自定义组件内的重叠层（如 <label> 盖在 <input> 上）
      if (el.labels && el.labels.length) {
        for (var j = 0; j < el.labels.length; j++) {
          if (el.labels[j] === hit || el.labels[j].contains(hit)) return true;
        }
      }
    }
    return false;
  }

  function detectModalRoot() {
    var cand = document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"], .modal.show, .modal--sm, .modal');
    var best = null;
    var bestArea = 0;
    for (var i = 0; i < cand.length; i++) {
      var m = cand[i];
      if (!isVisible(m)) continue;
      var r = m.getBoundingClientRect();
      if (r.width >= 120 && r.height >= 80 && r.left < vw && r.right > 0 && r.top < vh && r.bottom > 0) {
        var a = r.width * r.height;
        if (a > bestArea) {
          bestArea = a;
          best = m;
        }
      }
    }
    return best;
  }

  var modalRoot = detectModalRoot();

  function classifyRegion(el, rectBox) {
    if (modalRoot && (modalRoot === el || modalRoot.contains(el))) return 'modal';
    var inMainContainer = !!el.closest('main, article, section');
    var cur = el;
    while (cur && cur.nodeType === 1) {
      var tag = cur.tagName;
      var role = (cur.getAttribute('role') || '').toLowerCase();
      if (tag === 'DIALOG' || role === 'dialog' || cur.getAttribute('aria-modal') === 'true') {
        return 'modal';
      }
      if (tag === 'HEADER' || tag === 'FOOTER' || tag === 'ASIDE' ||
          role === 'banner' || role === 'contentinfo' || role === 'complementary' || role === 'toolbar') {
        return 'bar';
      }
      if (tag === 'NAV' || role === 'navigation') {
        var nr = cur.getBoundingClientRect();
        var nearEdge = (nr.top <= 90 && nr.height <= 120) || (nr.bottom >= vh - 90 && nr.height <= 120) ||
                       (nr.left <= 90 && nr.width <= 140) || (nr.right >= vw - 90 && nr.width <= 140);
        if (!inMainContainer || nearEdge) return 'bar';
      }
      var cs = window.getComputedStyle(cur);
      if (cs && (cs.position === 'fixed' || cs.position === 'sticky')) {
        var r = cur.getBoundingClientRect();
        var isTopBottomStrip = r.height <= 125 && r.width >= vw * 0.45 && (r.top <= 40 || r.bottom >= vh - 40);
        var isSideStrip = r.width <= 125 && r.height >= vh * 0.35 && (r.left <= 30 || r.right >= vw - 30);
        if (isTopBottomStrip || isSideStrip) return 'bar';
      }
      cur = cur.parentElement;
    }
    // 贴顶窄栏兜底（避免非 fixed 的顶栏漏判；底栏仅靠 footer/fixed 判定，以免误伤瀑布流底部卡片）
    var x1 = rectBox[0], y1 = rectBox[1], x2 = rectBox[2], y2 = rectBox[3];
    if (y1 <= 20 && y2 <= 80 && (y2 - y1) <= 72) return 'bar';
    return 'main';
  }

  function isInteractiveEl(el) {
    var tag = el.tagName;
    if (tag === 'INPUT') return (el.getAttribute('type') || '').toLowerCase() !== 'hidden';
    if (tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON') return true;
    if (tag === 'A' && (el.hasAttribute('href') || el.getAttribute('role') === 'button')) return true;
    if (el.isContentEditable) return true;
    var role = (el.getAttribute('role') || '').toLowerCase();
    if (/^(button|link|tab|menuitem|checkbox|switch|radio|combobox|searchbox|option)$/.test(role)) return true;
    if (el.hasAttribute('onclick')) return true;
    var cs = window.getComputedStyle(el);
    if (cs && cs.cursor === 'pointer') {
      // 忽略从父级按钮/链接继承来的 cursor: pointer（防止按钮内部的计数器 span 被重复抓成第二个按钮）
      if (el.parentElement && el.parentElement.closest('a[href], button, input, textarea, select, [role="button"], [role="link"], [onclick]')) {
        return false;
      }
      // 避免把包含很多子交互节点的大容器 div 当按钮
      var inner = el.querySelectorAll('a[href], button, input, textarea, select, [role="button"], [role="link"]');
      if (inner.length === 0) return true;
    }
    return false;
  }

  function controlKind(el) {
    var tag = el.tagName;
    var role = (el.getAttribute('role') || '').toLowerCase();
    var itype = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'INPUT') {
      if (itype === 'submit' || itype === 'button' || itype === 'reset') return '按钮';
      if (itype === 'checkbox' || itype === 'radio') return '切换';
      return '输入';
    }
    if (tag === 'TEXTAREA' || el.isContentEditable || role === 'searchbox') return '输入';
    if (tag === 'SELECT' || role === 'combobox') return '选择';
    if (role === 'checkbox' || role === 'switch' || role === 'radio') return '切换';
    if (tag === 'A' && role !== 'button') return '链接';
    return '按钮';
  }

  function controlLabel(el) {
    var parts = [
      el.getAttribute('aria-label'),
      el.innerText,
      el.textContent,
      el.getAttribute('placeholder'),
      el.getAttribute('title'),
      el.getAttribute('alt')
    ];
    if (el.tagName === 'INPUT') {
      var itype = (el.getAttribute('type') || '').toLowerCase();
      if (itype === 'submit' || itype === 'button' || itype === 'reset') {
        parts.unshift(el.value);
      }
    }
    for (var i = 0; i < parts.length; i++) {
      var t = cleanText(parts[i]);
      if (t) return t.slice(0, 80);
    }
    var img = el.querySelector('img[alt]');
    if (img) {
      var alt = cleanText(img.getAttribute('alt'));
      if (alt) return alt.slice(0, 80);
    }
    var svgTitle = el.querySelector('svg title');
    if (svgTitle) {
      var st = cleanText(svgTitle.textContent);
      if (st) return st.slice(0, 80);
    }
    // 对无文案的图标/头像链接，从 class / href 提取轻量语义提示，避免在控件树里失明
    var hintBlob = ((typeof el.className === 'string' ? el.className : '') + ' ' + (el.getAttribute('href') || '')).toLowerCase();
    if (/avatar|profile|space\.bilibili|\/u\/|\/user|account/.test(hintBlob)) return '个人空间/头像';
    if (/search|magnifier/.test(hintBlob)) return '搜索';
    if (/login|signin/.test(hintBlob)) return '登录';
    if (/message|notify|bell|msg/.test(hintBlob)) return '消息';
    if (/close|dismiss/.test(hintBlob)) return '关闭';
    return '';
  }

  function controlState(el) {
    var st = {};
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') st.disabled = true;
    if (typeof el.checked === 'boolean' && (el.type === 'checkbox' || el.type === 'radio')) {
      st.checked = el.checked;
    }
    if (el.getAttribute('aria-checked') === 'true') st.checked = true;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      var itype = (el.getAttribute('type') || '').toLowerCase();
      if (itype !== 'password' && itype !== 'submit' && itype !== 'button') {
        var val = cleanText(el.value || '');
        if (val) st.value = val.slice(0, 40);
      }
      var ph = cleanText(el.getAttribute('placeholder') || '');
      if (ph) st.placeholder = ph.slice(0, 40);
    }
    return st;
  }

  // 1. 收集可交互控件
  var rawInteractive = [];
  var allEls = document.querySelectorAll('a, button, input, textarea, select, [role], [onclick], [tabindex], [contenteditable], div, span, li, label');
  var visited = new Set();
  for (var idx = 0; idx < allEls.length; idx++) {
    var el = allEls[idx];
    if (visited.has(el)) continue;
    visited.add(el);
    if (!isInteractiveEl(el)) continue;
    if (!isVisible(el)) continue;
    var r = el.getBoundingClientRect();
    var vbox = inViewportRect(r);
    if (!vbox) continue;
    if ((vbox[2] - vbox[0]) * (vbox[3] - vbox[1]) > vw * vh * 0.85) continue;
    if (!hitTestVisible(el, vbox)) continue;

    // 跳过内部套了按钮的纯链接/容器外框
    var innerBtns = el.querySelectorAll('button, input, select, textarea, [role="button"]');
    if (innerBtns.length > 0 && el.tagName !== 'BUTTON') continue;

    var label = controlLabel(el);
    var region = classifyRegion(el, vbox);
    // 跳过整条横跨页面顶部的大背景图链接（如 B站 1920px 宽无文案头图），避免框住整个顶部导航
    if (!label && (vbox[2] - vbox[0]) >= vw * 0.70 && (vbox[3] - vbox[1]) >= 80) continue;
    var kind = controlKind(el);
    var clsName = typeof el.className === 'string' ? el.className : '';
    var isPrimary = /primary|cta|submit|confirm|start/i.test(clsName) || (el.getAttribute('type') || '').toLowerCase() === 'submit';
    var hasGraphic = !!el.querySelector('svg, img, i');
    var href = el.tagName === 'A' ? (el.getAttribute('href') || '') : '';

    rawInteractive.push({
      kind: kind,
      tag: el.tagName.toLowerCase(),
      role: (el.getAttribute('role') || '').toLowerCase(),
      label: label,
      state: controlState(el),
      region: region,
      bounds: [Math.round(vbox[0]), Math.round(vbox[1]), Math.round(vbox[2]), Math.round(vbox[3])],
      area: Math.round((vbox[2] - vbox[0]) * (vbox[3] - vbox[1])),
      is_primary: isPrimary,
      has_graphic: hasGraphic,
      href: href.slice(0, 120)
    });
  }

  // 2. 识别真正会阻挡/主导交互的 Canvas / Video（忽略 aria-hidden / pointer-events:none 背景动画画布）
  var vpArea = Math.max(1, vw * vh);
  var canvasArea = 0;
  var canvases = document.querySelectorAll('canvas, video');
  for (var c = 0; c < canvases.length; c++) {
    var cv = canvases[c];
    if (!isVisible(cv)) continue;
    var ccs = window.getComputedStyle(cv);
    if (ccs && ccs.pointerEvents === 'none') continue;
    var cr = cv.getBoundingClientRect();
    var cbox = inViewportRect(cr);
    if (!cbox) continue;
    var hitCv = document.elementFromPoint((cbox[0] + cbox[2]) / 2, (cbox[1] + cbox[3]) / 2);
    if (hitCv === cv || cv.contains(hitCv)) {
      canvasArea += (cbox[2] - cbox[0]) * (cbox[3] - cbox[1]);
    }
  }

  // 3. 抽取视口内可见的非交互页面文本（按阅读流，自动排除被控件捕获的按钮文本）
  var textBlocks = [];
  var seenTexts = new Set();
  var textEls = document.querySelectorAll('h1, h2, h3, h4, p, li, dt, dd, figcaption, blockquote, td, th, label, span, div');
  for (var t = 0; t < textEls.length; t++) {
    var te = textEls[t];
    if (te.closest('button, a, select, textarea, input, [role="button"], [role="link"], script, style, svg, canvas')) continue;
    if (te.querySelector('button, a[href], select, textarea, input, [role="button"], [role="link"]')) continue;
    if (!isVisible(te)) continue;
    // 只取直接文本叶子或不含深层子块级标签的段落，避免大容器把整页粘成一条
    var hasBlockChild = false;
    for (var k = 0; k < te.children.length; k++) {
      var ctag = te.children[k].tagName;
      if (/^(DIV|P|SECTION|ARTICLE|HEADER|FOOTER|NAV|UL|OL|LI|H1|H2|H3|H4|TABLE|FORM)$/.test(ctag)) {
        hasBlockChild = true;
        break;
      }
    }
    if (hasBlockChild) continue;
    var txt = cleanText(te.innerText || te.textContent);
    if (!txt || txt.length < 2) continue;
    var tr = te.getBoundingClientRect();
    var tbox = inViewportRect(tr);
    if (!tbox) continue;
    if (!hitTestVisible(te, tbox)) continue;
    if (seenTexts.has(txt)) continue;
    seenTexts.add(txt);
    var lvl = /^H([1-4])$/.test(te.tagName) ? parseInt(te.tagName.slice(1), 10) : 0;
    textBlocks.push({
      text: txt.slice(0, 220),
      level: lvl,
      region: classifyRegion(te, tbox),
      x: Math.round(tbox[0]),
      y: Math.round(tbox[1])
    });
    if (textBlocks.length >= 120) break;
  }

  return {
    title: cleanText(document.title || ''),
    url: String(location.href || ''),
    viewport: [vw, vh],
    scroll: {
      pct_y: pctY,
      can_down: maxScroll > 0 && scrollY < maxScroll - 8,
      can_up: scrollY > 8
    },
    has_modal: !!modalRoot,
    interactive_canvas_ratio: Math.min(1.0, canvasArea / vpArea),
    controls: rawInteractive,
    text_blocks: textBlocks
  };
})()"""


def _tools_cfg():
    return getattr(cfg, "tools", None)


def clean_label(raw: str) -> str:
    cleaned = _ICONFONT_RE.sub("", raw or "").strip()
    return re.sub(r"\s+", " ", cleaned)


def _score_control(node: dict[str, Any], vw: int, vh: int) -> float:
    """计算交互控件显著度得分（降序排列，分数最高者编号为 #1）。"""
    x1, y1, x2, y2 = node["bounds"]
    area = max(1, (x2 - x1) * (y2 - y1))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    region = node.get("region") or "main"
    kind = node.get("kind") or "按钮"
    label = (node.get("label") or "").strip()

    score = 0.0
    # 1. 视觉尺寸得分（主页面大控件显著优先，上限 280）
    score += min(280.0, math.sqrt(area) * 1.45)

    # 2. 控件类型基础分
    if kind in ("输入", "选择"):
        score += 240.0
    elif kind in ("按钮", "切换"):
        score += 170.0
        if node.get("is_primary"):
            score += 80.0
    elif kind == "链接":
        score += 75.0
    else:
        score += 45.0

    # 3. 区域与焦点权重
    if region == "modal":
        score += 1200.0
    elif region == "main":
        score += 140.0
        if vw * 0.10 <= cx <= vw * 0.90 and vh * 0.10 <= cy <= vh * 0.88:
            score += 75.0
    elif region == "bar":
        if kind in ("输入", "选择") or "search" in (node.get("role") or ""):
            score += 360.0
        elif _BAR_ACCOUNT_RE.search(label):
            score += 290.0
        elif _BAR_HIGH_VALUE_RE.search(label):
            score += 180.0
        elif _BAR_LOW_VALUE_RE.search(label) or _BAR_LOW_VALUE_RE.search(node.get("href") or ""):
            score -= 150.0
        else:
            score += 40.0

    # 4. 动作语义关键词加分
    if label and _ACTION_KEYWORDS_RE.search(label):
        score += 95.0

    # 5. 无文案极小图标略微降权；禁用状态降权
    if not label and area < 1400:
        score -= 55.0
    if (node.get("state") or {}).get("disabled"):
        score -= 120.0

    return round(score, 2)


def _dedupe_controls(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按中心点和文案去重，优先保留面积更精准或分数更高的控件。"""
    kept: list[dict[str, Any]] = []
    for item in items:
        x1, y1, x2, y2 = item["bounds"]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        norm_lbl = (item.get("label") or "").replace(" ", "").lower()
        replaced = False
        skip = False
        for idx, prev in enumerate(kept):
            px1, py1, px2, py2 = prev["bounds"]
            pcx, pcy = prev["cx"], prev["cy"]
            prev_lbl = (prev.get("label") or "").replace(" ", "").lower()
            near_center = abs(cx - pcx) <= 10 and abs(cy - pcy) <= 10
            same_text = bool(norm_lbl and norm_lbl == prev_lbl)
            # 若中心重合或同文案嵌套，保留更紧凑/高分者
            if near_center or (same_text and (
                (x1 >= px1 - 4 and y1 >= py1 - 4 and x2 <= px2 + 4 and y2 <= py2 + 4)
                or (px1 >= x1 - 4 and py1 >= y1 - 4 and px2 <= x2 + 4 and py2 <= y2 + 4)
            )):
                if item["score"] > prev["score"] or (
                    item["score"] == prev["score"] and item["area"] < prev["area"]
                ):
                    kept[idx] = item
                    replaced = True
                else:
                    skip = True
                break
        if not skip and not replaced:
            kept.append(item)
    return kept


def _compact_text_blocks(
    raw_blocks: list[dict[str, Any]],
    selected_controls: list[dict[str, Any]],
    *,
    max_chars: int = 900,
) -> list[str]:
    """提炼页面非交互文本（弹窗 > 主视觉区），去重并剥离已被控件标签覆盖的文案。"""
    ctrl_labels = {
        (c.get("label") or "").replace(" ", "").lower()
        for c in selected_controls
        if c.get("label")
    }
    ordered = sorted(
        raw_blocks,
        key=lambda b: (
            0 if b.get("region") == "modal" else (1 if b.get("region") == "main" else 2),
            b.get("y", 0),
            b.get("x", 0),
        ),
    )

    has_primary = any(b.get("region") in ("modal", "main") for b in ordered)
    seen_norm: list[str] = []
    lines: list[str] = []
    total_len = 0

    for blk in ordered:
        region = blk.get("region") or "main"
        if has_primary and region == "bar":
            continue
        txt = re.sub(r"\s+", " ", str(blk.get("text") or "")).strip()
        if not txt:
            continue
        norm = txt.replace(" ", "").lower()
        if norm in ctrl_labels:
            continue
        if any(norm == s or (len(norm) >= 6 and norm in s) for s in seen_norm):
            continue
        seen_norm.append(norm)

        lvl = int(blk.get("level") or 0)
        prefix = "[弹窗] " if region == "modal" else (f"[H{lvl}] " if 1 <= lvl <= 4 else "")
        line = f"{prefix}{txt}"
        if total_len + len(line) > max_chars:
            remain = max(0, max_chars - total_len)
            if remain >= 24:
                lines.append(line[:remain] + "...")
            break
        lines.append(line)
        total_len += len(line) + 1
    return lines


def build_browser_tree(
    frames: list[dict[str, Any]],
    *,
    max_nodes: int | None = None,
    bar_quota: int | None = None,
) -> dict[str, Any]:
    """合并多 Frame 探针快照，按「主区大控件优先 + Bar 按比例注入 + 降序编号」产出 Top N 控件树与页面文本。"""
    tcfg = _tools_cfg()
    limit = max(1, int(max_nodes or getattr(tcfg, "browser_max_nodes", 24) or 24))
    bar_cap = max(0, min(limit, int(bar_quota if bar_quota is not None else (getattr(tcfg, "browser_bar_quota", 5) or 5))))

    root = next((f for f in frames if f.get("_is_root")), frames[0] if frames else {})
    vw, vh = root.get("viewport") or [1280, 720]
    vw = max(1, int(vw or 1280))
    vh = max(1, int(vh or 720))

    title = str(root.get("title") or "")
    url = str(root.get("url") or "")
    scroll = root.get("scroll") or {}
    has_modal = any(bool(f.get("has_modal")) for f in frames)
    canvas_ratio = max((float(f.get("interactive_canvas_ratio") or 0.0) for f in frames), default=0.0)

    merged_controls: list[dict[str, Any]] = []
    merged_texts: list[dict[str, Any]] = []

    for frame in frames:
        ox = float(frame.get("_offset_x") or 0.0)
        oy = float(frame.get("_offset_y") or 0.0)
        is_root = bool(frame.get("_is_root"))
        for c in frame.get("controls") or []:
            bx1, by1, bx2, by2 = c.get("bounds") or [0, 0, 0, 0]
            x1 = max(0, int(round(bx1 + ox)))
            y1 = max(0, int(round(by1 + oy)))
            x2 = min(vw, int(round(bx2 + ox)))
            y2 = min(vh, int(round(by2 + oy)))
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            region = str(c.get("region") or "main")
            # 顶层 shell 里的窄侧栏/顶栏同样按 bar 归类
            if is_root and region == "main":
                if (x2 - x1) <= 100 and (x1 <= 16 or x2 >= vw - 16):
                    region = "bar"
            item = {
                "kind": str(c.get("kind") or "按钮"),
                "tag": str(c.get("tag") or ""),
                "role": str(c.get("role") or ""),
                "label": clean_label(str(c.get("label") or "")),
                "state": c.get("state") or {},
                "region": region,
                "bounds": (x1, y1, x2, y2),
                "cx": cx,
                "cy": cy,
                "area": (x2 - x1) * (y2 - y1),
                "is_primary": bool(c.get("is_primary")),
                "has_graphic": bool(c.get("has_graphic")),
                "href": str(c.get("href") or ""),
            }
            item["score"] = _score_control(item, vw, vh)
            merged_controls.append(item)

        for tb in frame.get("text_blocks") or []:
            tx = int(round(float(tb.get("x") or 0) + ox))
            ty = int(round(float(tb.get("y") or 0) + oy))
            if 0 <= tx <= vw and 0 <= ty <= vh:
                merged_texts.append({
                    "text": clean_label(str(tb.get("text") or "")),
                    "level": int(tb.get("level") or 0),
                    "region": str(tb.get("region") or "main"),
                    "x": tx,
                    "y": ty,
                })

    deduped = _dedupe_controls(merged_controls)

    # 分桶并按「弹窗优先 + 主视觉区大控件优先 + Bar 按比例注入」分配 <= limit 个名额
    modal_pool = sorted((n for n in deduped if n["region"] == "modal"), key=lambda x: (-x["score"], x["cy"], x["cx"]))
    main_pool = sorted((n for n in deduped if n["region"] == "main"), key=lambda x: (-x["score"], x["cy"], x["cx"]))
    bar_pool = sorted((n for n in deduped if n["region"] == "bar"), key=lambda x: (-x["score"], x["cy"], x["cx"]))

    selected: list[dict[str, Any]] = []
    if modal_pool:
        selected.extend(modal_pool[:limit])
        rem = limit - len(selected)
        if rem > 0:
            bar_n = min(len(bar_pool), min(bar_cap, max(1, rem // 4))) if bar_pool else 0
            main_n = min(len(main_pool), rem - bar_n)
            selected.extend(main_pool[:main_n])
            selected.extend(bar_pool[:bar_n])
            left = rem - main_n - bar_n
            if left > 0:
                extra = main_pool[main_n:] + bar_pool[bar_n:]
                selected.extend(extra[:left])
    else:
        bar_target = min(len(bar_pool), bar_cap)
        main_target = min(len(main_pool), limit - bar_target)
        selected.extend(main_pool[:main_target])
        selected.extend(bar_pool[:bar_target])
        left = limit - len(selected)
        if left > 0:
            surplus = main_pool[main_target:] + bar_pool[bar_target:]
            selected.extend(surplus[:left])

    # 严格降序编号：#1 是最显著/最可能被点击的控件
    selected.sort(key=lambda x: (-x["score"], x["cy"], x["cx"]))
    for idx, node in enumerate(selected, 1):
        node["index"] = idx

    text_lines = _compact_text_blocks(merged_texts, selected)
    return {
        "title": title,
        "url": url,
        "size": (vw, vh),
        "scroll": scroll,
        "has_modal": has_modal,
        "interactive_canvas_ratio": round(canvas_ratio, 3),
        "total_candidates": len(deduped),
        "nodes": selected,
        "text_lines": text_lines,
    }


def assess_visual_clarity(tree: dict[str, Any], *, is_entry: bool = False) -> tuple[bool, str]:
    """判定当前界面控件是否足够明确：明确则跳过截图，不明确（或首屏）则附带 720p 截图。"""
    if is_entry:
        return False, "first_screen"
    if float(tree.get("interactive_canvas_ratio") or 0.0) >= 0.15:
        return False, "interactive_canvas"
    nodes = tree.get("nodes") or []
    if len(nodes) < 3:
        return False, "few_controls"
    labeled = sum(1 for n in nodes if (n.get("label") or "").strip())
    if labeled / max(1, len(nodes)) < 0.6:
        return False, "many_unlabeled"
    return True, "clear"


def format_browser_tree(tree: dict[str, Any]) -> str:
    """把控件树与页面文本渲染成紧凑、可读的提示文本。"""
    vw, vh = tree.get("size") or (1280, 720)
    title = tree.get("title") or "未命名页面"
    url = tree.get("url") or ""
    scroll = tree.get("scroll") or {}
    pct = scroll.get("pct_y", 0)
    scroll_hint = []
    if scroll.get("can_up"):
        scroll_hint.append("可上滚")
    if scroll.get("can_down"):
        scroll_hint.append("可下滚")
    scroll_str = f"滚动 {pct}%" + (f" ({'/'.join(scroll_hint)})" if scroll_hint else "")

    header = f"[网页] {title} | {url} | 视口 {vw}x{vh} | {scroll_str}"
    parts = [header]

    text_lines = tree.get("text_lines") or []
    if text_lines:
        parts.append("[页面文本]\n" + "\n".join(text_lines))

    nodes = tree.get("nodes") or []
    total = int(tree.get("total_candidates") or len(nodes))
    cap_note = f"（从视口 {total} 个候选中按重要性降序精选）" if total > len(nodes) else "（按重要性降序）"
    parts.append(f"[可交互控件 {len(nodes)}/{total}] {cap_note}")
    if not nodes:
        parts.append("（当前视口内未检测到明确 DOM 控件，可能需要截图确认画面坐标，或向下滚动加载）")
    else:
        for item in nodes:
            region_tag = "[弹窗] " if item["region"] == "modal" else ("[Bar] " if item["region"] == "bar" else "")
            label = item["label"] or "(无文字图标)"
            st = item.get("state") or {}
            extra_bits: list[str] = []
            if st.get("disabled"):
                extra_bits.append("disabled")
            if st.get("checked") is True:
                extra_bits.append("checked")
            if st.get("value"):
                extra_bits.append(f"val={st['value']}")
            elif st.get("placeholder") and st["placeholder"] not in label:
                extra_bits.append(f"ph={st['placeholder']}")
            extra = f" ({', '.join(extra_bits)})" if extra_bits else ""
            parts.append(
                f"[#{item['index']}] {region_tag}[{item['kind']}] {label}{extra} @({item['cx']},{item['cy']})"
            )
    return "\n".join(parts)


def _load_badge_font(font_size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def annotate_browser_screenshot(
    png_bytes: bytes,
    tree: dict[str, Any],
    *,
    high_res: bool = False,
) -> bytes | None:
    """无高斯模糊：按 720p/高清宽度缩放，并用大号高对比红框 [#编号] 标注控件。"""
    if not png_bytes:
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("[Browser] 缺少 Pillow，跳过截图标注")
        return None

    tcfg = _tools_cfg()
    if high_res:
        max_width = int(getattr(tcfg, "browser_screenshot_high_width", 1600) or 1600)
        quality = int(getattr(tcfg, "browser_screenshot_high_quality", 88) or 88)
    else:
        max_width = int(getattr(tcfg, "browser_screenshot_max_width", 1280) or 1280)
        quality = int(getattr(tcfg, "browser_screenshot_quality", 55) or 55)

    try:
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception as exc:
        logger.warning(f"[Browser] 截图解码失败: {exc}")
        return None

    vp_w, _ = tree.get("size") or (image.width, image.height)
    # 兼容 HiDPI / deviceScaleFactor：控件坐标基于 CSS 视口，需映射回当前缩放后图像坐标
    css_to_img = image.width / max(1, vp_w)
    scale = min(1.0, max_width / max(1, image.width))
    if scale < 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    coord_scale = css_to_img * scale

    font_size = max(20, int(image.width * 0.0185))
    font = _load_badge_font(font_size)
    draw = ImageDraw.Draw(image)
    placed_badges: list[tuple[int, int, int, int]] = []

    for item in tree.get("nodes") or []:
        bx1, by1, bx2, by2 = item["bounds"]
        x1 = max(0, int(round(bx1 * coord_scale)))
        y1 = max(0, int(round(by1 * coord_scale)))
        x2 = min(image.width - 1, int(round(bx2 * coord_scale)))
        y2 = min(image.height - 1, int(round(by2 * coord_scale)))
        if x2 <= x1 or y2 <= y1:
            continue

        is_bar = item.get("region") == "bar"
        box_color = (234, 138, 15) if is_bar else (235, 38, 66)
        draw.rectangle([x1, y1, x2, y2], outline=box_color, width=3)

        tag_text = f"#{item['index']}"
        tb = draw.textbbox((0, 0), tag_text, font=font)
        tw, th = max(12, tb[2] - tb[0]), max(14, tb[3] - tb[1])
        pad_x, pad_y = 6, 4
        bw, bh = tw + pad_x * 2, th + pad_y * 2

        if is_bar and x2 >= image.width - 100 and x1 >= bw + 4:
            candidates = [
                (x1 - bw - 4, y1),
                (x1, max(0, y1 - bh - 2)),
                (x1, min(image.height - bh, y1 + 2)),
            ]
        else:
            candidates = [
                (x1, max(0, y1 - bh - 2)),
                (x1 - bw - 4, y1) if x1 >= bw + 4 else (x2 + 4, y1),
                (x1, min(image.height - bh, y1 + 2)),
                (max(0, x2 - bw), max(0, y1 - bh - 2)),
                (x1, min(image.height - bh, y2 + 2)),
                (max(0, x2 - bw), min(image.height - bh, y2 - bh)),
            ]
        chosen = None
        for cx, cy in candidates:
            cx = max(0, min(image.width - bw, cx))
            cy = max(0, min(image.height - bh, cy))
            rect = (cx, cy, cx + bw, cy + bh)
            if not any(_rects_overlap(rect, prev) for prev in placed_badges):
                chosen = rect
                break
        if chosen is None:
            cx = max(0, min(image.width - bw, candidates[0][0]))
            cy = max(0, min(image.height - bh, candidates[0][1]))
            chosen = (cx, cy, cx + bw, cy + bh)
        placed_badges.append(chosen)

        # 白边 + 高饱和底色 + 白色大号数字
        draw.rectangle([chosen[0] - 1, chosen[1] - 1, chosen[2] + 1, chosen[3] + 1], fill=(255, 255, 255))
        draw.rectangle(list(chosen), fill=box_color)
        draw.text((chosen[0] + pad_x - tb[0], chosen[1] + pad_y - tb[1]), tag_text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
