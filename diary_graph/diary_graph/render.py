"""把 NetworkX 图渲染成离线单文件 HTML（vis-network 物理仿真 + 点击查看日记）。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
from pyvis.network import Network

from .graph import GraphBundle

# 甜酷千禧粉系霓虹调色板，按簇循环取色
PALETTE = [
    "#ff4fb8", "#b06bff", "#5ec8ff", "#6bffb8", "#ffd166", "#ff8e72",
    "#c68cff", "#5eead4", "#f472b6", "#a3e635", "#ffa8d8", "#8b9dff",
]


def _size(degree: int, weighted: float) -> float:
    return round(min(10 + 7 * math.log2(degree + 1) + math.log2(weighted + 1), 70), 2)


def render(bundle: GraphBundle, out_path: str | Path, *,
           title: str = "Yuki 日记图谱", height: str = "100vh") -> Path:
    G: nx.Graph = bundle.graph
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if G.number_of_nodes() == 0:
        out_path.write_text("<!doctype html><meta charset='utf-8'><h1>图为空</h1>",
                            encoding="utf-8")
        return out_path

    max_w = max((d["weight"] for _, _, d in G.edges(data=True)), default=1.0)

    net = Network(height=height, width="100%", bgcolor="#0e0916",
                  font_color="#ffe9f7", directed=False, cdn_resources="in_line")
    net.toggle_physics(True)

    for node, meta in bundle.metrics.items():
        cid = meta["community"]
        color = PALETTE[cid % len(PALETTE)]
        net.add_node(
            node,
            label=node,
            title=(f"{node}\n度 {meta['degree']} | 加权度 {meta['weighted_degree']}\n"
                   f"簇 {cid} | 跨簇桥接 {meta['bridging']} | 介数 {meta['betweenness']}"),
            size=_size(meta["degree"], meta["weighted_degree"]),
            color={"background": color, "border": "#ffffff33",
                   "highlight": {"background": "#ffffff", "border": color}},
            font={"size": 15 if meta["degree"] > 6 else 12},
            group=cid,
        )

    for u, v, d in G.edges(data=True):
        w = d["weight"]
        ratio = w / max_w
        net.add_edge(
            u, v,
            value=round(w, 3),
            width=round(min(0.6 + 1.1 * math.log2(w + 1), 7), 2),
            color={"opacity": round(0.18 + 0.5 * ratio, 3), "color": "#8b5cf6"},
            title=f"共现权重 {w:.2f}",
        )

    options = {
        "nodes": {"borderWidth": 1.5, "shape": "dot", "font": {"strokeWidth": 0}},
        "edges": {"smooth": {"enabled": True, "type": "continuous", "roundness": 0.15}},
        "physics": {
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -70, "centralGravity": 0.012,
                "springLength": 130, "springConstant": 0.06,
                "damping": 0.55, "avoidOverlap": 0.35,
            },
            "stabilization": {"enabled": True, "iterations": 400,
                              "updateInterval": 25, "fit": True},
            "minVelocity": 0.8,
            "maxVelocity": 60,
        },
        "interaction": {"hover": True, "tooltipDelay": 120, "navigationButtons": True,
                        "multiselect": True, "keyboard": {"enabled": True}},
    }
    net.set_options(json.dumps(options))

    html = net.generate_html(notebook=False)
    payload = json.dumps({
        "title": title,
        "meta": bundle.metrics,
        "docs": bundle.node_docs,
        "colors": PALETTE,
        "stats": {k: bundle.stats.get(k) for k in ("nodes", "edges", "communities")},
    }, ensure_ascii=False).replace("</", "<\\/")

    html = html.replace("</body>", _OVERLAY_HTML + f"<script>window.__GRAPH__={payload};</script>"
                        + _OVERLAY_JS + "</body>")
    out_path.write_text(html, encoding="utf-8")
    return out_path


_OVERLAY_HTML = """
<style>
  #dgPanel{position:fixed;top:0;right:-420px;width:400px;height:100vh;z-index:99;
    background:linear-gradient(180deg,rgba(32,16,42,.96),rgba(18,10,26,.97));
    border-left:1px solid #ff4fb855;box-shadow:-18px 0 48px #ff4fb833;
    backdrop-filter:blur(14px);transition:right .25s ease;color:#ffe9f7;
    font:13px/1.65 ui-monospace,"Sarasa Term SC",monospace;overflow-y:auto;padding:14px 16px}
  #dgPanel.open{right:0}
  #dgPanel h2{margin:2px 0 8px;font-size:17px;color:#ff8ed0;letter-spacing:.5px}
  #dgBadges span{display:inline-block;margin:0 6px 6px 0;padding:1px 8px;border-radius:99px;
    background:#ff4fb81f;border:1px solid #ff4fb855;font-size:11px}
  #dgPanel .doc{margin:11px 0;padding:9px 10px;border-radius:9px;
    background:#ffffff0d;border-left:2px solid #b06bff}
  #dgPanel .doc time{color:#5ec8ff;font-size:11px;letter-spacing:.4px}
  #dgPanel .doc p{margin:5px 0 0;white-space:pre-wrap;color:#e8d8f5}
  #dgClose{position:sticky;top:0;float:right;cursor:pointer;color:#ff4fb8;font-size:16px}
  #dgBar{position:fixed;left:14px;top:14px;z-index:98;display:flex;gap:8px;align-items:center;
    font:12px/1.4 ui-monospace,monospace;color:#ffe9f7}
  #dgBar input{width:190px;padding:6px 10px;border-radius:99px;border:1px solid #ff4fb866;
    background:#1c102aE6;color:#ffe9f7;outline:none}
  #dgBar button{padding:6px 12px;border-radius:99px;cursor:pointer;
    border:1px solid #b06bff77;background:#b06bff22;color:#ffe9f7}
  #dgBar button:hover{background:#ff4fb833;border-color:#ff4fb8}
  #dgHint{margin-left:4px;color:#c9a9dd88}
</style>
<div id="dgBar">
  <input id="dgSearch" placeholder="搜索概念…（回车定位）">
  <button id="dgPhysics">⏸ 冻结布局</button>
  <button id="dgFit">⟳ 复位视角</button>
  <span id="dgHint"></span>
</div>
<div id="dgPanel"><span id="dgClose">✕</span><div id="dgBody"></div></div>
"""

_OVERLAY_JS = """
<script>
(function(){
  const G = window.__GRAPH__;
  const panel = document.getElementById('dgPanel');
  const body  = document.getElementById('dgBody');
  const hint  = document.getElementById('dgHint');
  document.getElementById('dgHint').textContent =
    `${G.stats.nodes} 个概念 · ${G.stats.edges} 条关联 · ${G.stats.communities} 个簇 · 点节点看日记`;
  document.getElementById('dgClose').onclick = () => panel.classList.remove('open');

  function esc(s){return String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

  function show(node){
    const m = G.meta[node]; if(!m) return;
    const docs = G.docs[node] || [];
    const color = G.colors[m.community % G.colors.length];
    body.innerHTML =
      `<h2 style="color:${color}">${esc(node)}</h2>` +
      `<div id="dgBadges">` +
        `<span>度 ${m.degree}</span><span>加权度 ${m.weighted_degree}</span>` +
        `<span>簇 ${m.community}</span><span>跨簇 ${m.bridging}</span>` +
        `<span>介数 ${m.betweenness}</span><span>聚集 ${m.clustering}</span>` +
      `</div>` +
      `<div style="color:#c9a9dd99;margin:6px 0 2px">相关日记 ${docs.length} 篇</div>` +
      docs.map(d => `<div class="doc"><time>${esc(d.date)}</time><p>${esc(d.text)}</p></div>`).join('');
    panel.classList.add('open');
  }

  let net = null;
  const timer = setInterval(() => {
    if (typeof network !== 'undefined' && network && network.body) {
      net = network; clearInterval(timer); bind();
    }
  }, 120);

  function bind(){
    net.on('click', p => { if(p.nodes.length) show(p.nodes[0]); });
    net.on('hoverNode', p => {
      const m = G.meta[p.node];
      hint.textContent = m ? `${p.node} · 度 ${m.degree} · 跨簇 ${m.bridging}` : '';
    });
    document.getElementById('dgFit').onclick = () => net.fit({animation:true});
    let running = true;
    const btn = document.getElementById('dgPhysics');
    btn.onclick = () => {
      running = !running;
      if (running) net.startSimulation(); else net.stopSimulation();
      btn.textContent = running ? '⏸ 冻结布局' : '▶ 继续布局';
    };
    const search = document.getElementById('dgSearch');
    search.onkeydown = e => {
      if (e.key !== 'Enter') return;
      const q = search.value.trim();
      const hit = Object.keys(G.meta).find(k => k.toLowerCase() === q.toLowerCase())
               || Object.keys(G.meta).find(k => k.toLowerCase().includes(q.toLowerCase()));
      if (!hit) { hint.textContent = '没找到该概念'; return; }
      net.selectNodes([hit]);
      net.focus(hit, {scale:1.4, animation:{duration:600}});
      show(hit);
    };
  }
})();
</script>
"""
