import argparse
import datetime
import html
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CANDIDATE_FILE = "data/memory_exports/mimo_1057020972_candidates.jsonl"
DEFAULT_ERROR_FILE = "data/memory_exports/mimo_1057020972_errors.jsonl"
DEFAULT_TOTAL = 1955

AUTO_APPROVE_TYPES = {"fact", "preference", "relationship", "event"}
NEEDS_REVIEW_TYPES = {"profile_candidate", "todo"}


def estimate_review_status(memory, min_confidence=0.75):
    """预估阶段 D 审核结果，不写文件，仅用于看板展示。"""
    content = str(memory.get("content", "")).strip()
    subject = str(memory.get("subject", "")).strip()
    evidence = str(memory.get("evidence", "")).strip()
    memory_type = memory.get("type")
    risk = memory.get("risk", "medium")
    confidence = float(memory.get("confidence", 0) or 0)
    importance = int(memory.get("importance", 1) or 1)

    if not content or not subject or not evidence:
        return "rejected", "missing_fields"
    if len(content) < 8:
        return "rejected", "too_short"
    if risk == "high":
        return "rejected", "high_risk"
    if confidence < min_confidence:
        return "rejected", "low_confidence"
    if memory_type == "event" and importance <= 2:
        return "rejected", "low_value_event"
    if risk == "medium":
        return "needs_review", "medium_risk"
    if memory_type in NEEDS_REVIEW_TYPES:
        return "needs_review", f"{memory_type}_requires_review"
    if memory_type in AUTO_APPROVE_TYPES:
        return "approved", "auto_approved"
    return "needs_review", "unknown_type"


class DashboardState:
    def __init__(self, candidate_file, error_file, total):
        self.candidate_file = Path(candidate_file)
        self.error_file = Path(error_file)
        self.total = total

    def collect_stats(self):
        entries = []
        memories = []
        parse_errors = []

        if self.candidate_file.exists():
            with self.candidate_file.open("r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as exc:
                        parse_errors.append({"line": line_number, "error": str(exc)})
                        continue
                    entries.append(item)
                    for memory in item.get("memories") or []:
                        if isinstance(memory, dict):
                            memories.append(memory)

        error_entries = []
        if self.error_file.exists():
            with self.error_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        error_entries.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        error_entries.append({"error": str(exc)})

        by_type = Counter(str(item.get("type") or "unknown") for item in memories)
        by_risk = Counter(str(item.get("risk") or "unknown") for item in memories)
        by_scope = Counter(str(item.get("time_scope") or "unknown") for item in memories)
        by_importance = Counter(str(item.get("importance") or "unknown") for item in memories)
        top_subjects = Counter(str(item.get("subject") or "unknown") for item in memories)
        empty_entries = sum(1 for item in entries if not item.get("memories"))
        confidences = [float(item.get("confidence") or 0) for item in memories]
        importances = [float(item.get("importance") or 0) for item in memories]
        last_entry = entries[-1] if entries else {}
        candidate_stat = self.candidate_file.stat() if self.candidate_file.exists() else None
        error_stat = self.error_file.stat() if self.error_file.exists() else None

        # 阶段 D 预审统计（只读内存计算，不写文件）
        review_status = Counter()
        review_reasons = Counter()
        for memory in memories:
            status, reason = estimate_review_status(memory)
            review_status[status] += 1
            review_reasons[reason] += 1

        processed = len(entries)
        progress = round(processed / self.total * 100, 2) if self.total else 0
        progress = max(0, min(progress, 100))

        return {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "candidate_file": str(self.candidate_file),
            "error_file": str(self.error_file),
            "target_total": self.total,
            "processed": processed,
            "progress": progress,
            "memories": len(memories),
            "empty_entries": empty_entries,
            "error_lines": len(error_entries),
            "parse_errors": parse_errors[:20],
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0,
            "avg_importance": round(sum(importances) / len(importances), 2) if importances else 0,
            "avg_memories_per_entry": round(len(memories) / processed, 2) if processed else 0,
            "by_type": to_pairs(by_type),
            "by_risk": to_pairs(by_risk),
            "by_scope": to_pairs(by_scope),
            "by_importance": to_pairs(by_importance, sort_by_name=True),
            "top_subjects": to_pairs(top_subjects, limit=15),
            "last_source_diary_id": last_entry.get("source_diary_id", ""),
            "last_extracted_at": last_entry.get("extracted_at", ""),
            "candidate_mtime": format_mtime(candidate_stat),
            "candidate_size": candidate_stat.st_size if candidate_stat else 0,
            "error_mtime": format_mtime(error_stat),
            "latest_errors": error_entries[-5:],
            # 阶段 D 预审预测
            "review_status": dict(review_status),
            "review_approved": review_status.get("approved", 0),
            "review_needs_review": review_status.get("needs_review", 0),
            "review_rejected": review_status.get("rejected", 0),
            "review_reasons": to_pairs(review_reasons),
        }


def to_pairs(counter, limit=None, sort_by_name=False):
    items = sorted(counter.items(), key=lambda item: item[0]) if sort_by_name else counter.most_common(limit)
    if limit and sort_by_name:
        items = items[:limit]
    return [{"name": name, "count": count} for name, count in items]


def format_mtime(stat_result):
    if not stat_result:
        return ""
    return datetime.datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def build_html():
    return """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Yuki-Memory 实时看板</title>
  <style>
    :root{color-scheme:dark;--bg:#090f1f;--card:rgba(255,255,255,.08);--line:rgba(255,255,255,.14);--text:#eef4ff;--muted:#aab7d4;--cyan:#65e4ff;--blue:#7aa7ff;--purple:#c084fc;--pink:#f0abfc;--green:#8bf5c2;--yellow:#fde68a;--red:#fca5a5}
    *{box-sizing:border-box} body{margin:0;min-height:100vh;font-family:\"Microsoft YaHei\",\"Segoe UI\",system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 12% 8%,rgba(101,228,255,.22),transparent 34%),radial-gradient(circle at 82% 16%,rgba(192,132,252,.2),transparent 32%),radial-gradient(circle at 50% 100%,rgba(139,245,194,.14),transparent 38%),var(--bg)}
    .page{width:min(1280px,calc(100vw - 40px));margin:0 auto;padding:32px 0 48px}.hero,.card{border:1px solid var(--line);background:var(--card);box-shadow:0 24px 80px rgba(0,0,0,.32);backdrop-filter:blur(18px)}.hero{border-radius:28px;padding:28px;position:relative;overflow:hidden}.hero:after{content:\"\";position:absolute;right:-90px;top:-120px;width:320px;height:320px;background:radial-gradient(circle,rgba(101,228,255,.36),transparent 68%)}
    h1{margin:0 0 10px;font-size:clamp(30px,4vw,50px);letter-spacing:-.04em}.sub{margin:0;color:var(--muted);line-height:1.8}.row{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.pill{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.07);color:var(--muted);font-size:13px}.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green)}
    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px;margin-top:18px}.card{border-radius:24px;padding:20px}.s3{grid-column:span 3}.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s12{grid-column:span 12}.label{color:var(--muted);font-size:13px;margin-bottom:10px}.value{font-size:34px;font-weight:850;line-height:1;letter-spacing:-.04em}.note{margin-top:10px;color:var(--muted);font-size:12px;line-height:1.6}.progress{height:12px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.1);margin-top:16px}.progress>i{display:block;height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,var(--cyan),var(--purple));box-shadow:0 0 22px rgba(101,228,255,.48);transition:width .6s ease}
    h2{margin:0 0 18px;font-size:18px}.bars{display:grid;gap:12px}.bar{display:grid;grid-template-columns:120px 1fr 54px;gap:12px;align-items:center;color:var(--muted);font-size:13px}.track{height:10px;overflow:hidden;border-radius:999px;background:rgba(255,255,255,.1)}.fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--blue),var(--cyan));transition:width .6s ease}.fill.purple{background:linear-gradient(90deg,var(--purple),var(--pink))}.fill.green{background:linear-gradient(90deg,var(--green),var(--cyan))}.fill.yellow{background:linear-gradient(90deg,var(--yellow),var(--pink))}
    .donut-area{display:grid;grid-template-columns:190px 1fr;gap:22px;align-items:center}.donut{width:180px;height:180px;border-radius:50%;background:conic-gradient(var(--cyan) 0 0);position:relative;box-shadow:inset 0 0 30px rgba(255,255,255,.06),0 0 38px rgba(101,228,255,.16)}.donut:after{content:attr(data-total);position:absolute;inset:34px;display:grid;place-items:center;border-radius:50%;background:#10162b;font-size:30px;font-weight:850}.legend{display:grid;gap:10px}.legend-row{display:flex;justify-content:space-between;gap:16px;color:var(--muted);font-size:13px}.legend-name{display:inline-flex;align-items:center;gap:8px}.swatch{width:10px;height:10px;border-radius:3px}
    table{width:100%;border-collapse:collapse}th,td{padding:11px 10px;border-bottom:1px solid rgba(255,255,255,.09);text-align:left;font-size:13px}th{color:var(--muted);font-weight:500}td:last-child,th:last-child{text-align:right}.warn{padding:14px 16px;border-radius:18px;background:rgba(253,230,138,.1);border:1px solid rgba(253,230,138,.24);color:#fff4c2;line-height:1.7;font-size:13px}.ok{background:rgba(139,245,194,.1);border-color:rgba(139,245,194,.24);color:#d5ffe9}code{color:#d8e8ff;background:rgba(255,255,255,.08);padding:2px 6px;border-radius:8px}
    @media(max-width:900px){.s3,.s5,.s6,.s7{grid-column:span 12}.donut-area{grid-template-columns:1fr}.bar{grid-template-columns:88px 1fr 44px}}
  </style>
</head>
<body>
  <main class=\"page\">
    <section class=\"hero\">
      <h1>Yuki-Memory 实时提取看板</h1>
      <p class=\"sub\">后端只读扫描 JSONL，前端每 <code id=\"interval\">3</code> 秒刷新一次。不会写入、截断或锁定后台转换文件。</p>
      <div class=\"row\"><span class=\"pill\"><span class=\"dot\"></span>实时监控中</span><span class=\"pill\">刷新时间：<span id=\"generatedAt\">-</span></span><span class=\"pill\">文件更新时间：<span id=\"mtime\">-</span></span><span class=\"pill\">文件大小：<span id=\"fileSize\">-</span></span></div>
    </section>
    <section class=\"grid\">
      <div class=\"card s3\"><div class=\"label\">已处理旧日记</div><div class=\"value\" id=\"processed\">-</div><div class=\"note\"><span id=\"progressText\">-</span></div><div class=\"progress\"><i id=\"progressBar\"></i></div></div>
      <div class=\"card s3\"><div class=\"label\">结构化候选</div><div class=\"value\" id=\"memories\">-</div><div class=\"note\">平均每条日记 <span id=\"avgPer\">-</span> 条候选</div></div>
      <div class=\"card s3\"><div class=\"label\">空候选日记</div><div class=\"value\" id=\"empty\">-</div><div class=\"note\">被判断为无长期沉淀价值</div></div>
      <div class=\"card s3\"><div class=\"label\">错误记录</div><div class=\"value\" id=\"errors\">-</div><div class=\"note\">来自 error JSONL</div></div>
      <div class=\"card s4\"><h2>阶段 D 预审预测</h2><div class=\"bars\" id=\"reviewBars\"></div><p class=\"note\">approved 可直接导入，needs_review 需人工抽查，rejected 被过滤。</p></div>
      <div class=\"card s8\"><h2>候选类型分布</h2><div class=\"donut-area\"><div class=\"donut\" id=\"donut\" data-total=\"-\"></div><div class=\"legend\" id=\"typeLegend\"></div></div></div>
      <div class=\"card s5\"><h2>质量概览</h2><div class=\"bars\" id=\"qualityBars\"></div><p class=\"note\">重点观察 medium risk、profile_candidate、todo，后续阶段 D 用于人工抽查。</p></div>
      <div class=\"card s7\"><h2>时间范围</h2><div class=\"bars\" id=\"scopeBars\"></div></div>
      <div class=\"card s6\"><h2>重要性分布</h2><div class=\"bars\" id=\"importanceBars\"></div></div>
      <div class=\"card s6\"><h2>高频主体 Top 15</h2><table><thead><tr><th>主体</th><th>候选数</th></tr></thead><tbody id=\"subjects\"></tbody></table></div>
      <div class=\"card s12\"><h2>预审拒绝原因 Top 10</h2><div class=\"bars\" id=\"rejectReasonBars\"></div></div>
      <div class=\"card s12\"><h2>当前检查结论</h2><div class=\"warn ok\" id=\"parseStatus\">等待首次扫描。</div><br><div class=\"warn\" id=\"errorStatus\">等待错误文件扫描。</div><p class=\"note\">最后已读源日记：<code id=\"lastId\">-</code><br>最后提取时间：<code id=\"lastAt\">-</code></p></div>
    </section>
  </main>
  <script>
    const colors = ['#65e4ff','#7aa7ff','#c084fc','#f0abfc','#8bf5c2','#fde68a','#fca5a5'];
    const refreshMs = 3000;
    document.getElementById('interval').textContent = refreshMs / 1000;
    function esc(value){return String(value ?? '').replace(/[&<>'\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));}
    function num(value){return Number(value || 0).toLocaleString('zh-CN');}
    function renderBars(id, rows, cls=''){
      const max = Math.max(1, ...rows.map(x => x.count));
      document.getElementById(id).innerHTML = rows.map(x => `<div class=\"bar\"><span>${esc(x.name)}</span><div class=\"track\"><div class=\"fill ${cls}\" style=\"width:${Math.max(2, x.count / max * 100)}%\"></div></div><strong>${num(x.count)}</strong></div>`).join('');
    }
    function renderDonut(rows, total){
      let acc = 0;
      const parts = rows.map((row, index) => {
        const start = acc;
        acc += total ? row.count / total * 100 : 0;
        return `${colors[index % colors.length]} ${start}% ${acc}%`;
      });
      const donut = document.getElementById('donut');
      donut.style.background = `conic-gradient(${parts.join(',') || '#65e4ff 0 100%'})`;
      donut.dataset.total = num(total);
      document.getElementById('typeLegend').innerHTML = rows.map((row, index) => `<div class=\"legend-row\"><span class=\"legend-name\"><span class=\"swatch\" style=\"background:${colors[index % colors.length]}\"></span>${esc(row.name)}</span><strong>${num(row.count)}</strong></div>`).join('');
    }
    async function refresh(){
      const res = await fetch('/api/stats?ts=' + Date.now());
      const data = await res.json();
      document.getElementById('generatedAt').textContent = data.generated_at;
      document.getElementById('mtime').textContent = data.candidate_mtime || '-';
      document.getElementById('fileSize').textContent = num(data.candidate_size) + ' bytes';
      document.getElementById('processed').textContent = num(data.processed);
      document.getElementById('progressText').textContent = `${data.processed} / ${data.target_total}，约 ${data.progress}%`;
      document.getElementById('progressBar').style.width = data.progress + '%';
      document.getElementById('memories').textContent = num(data.memories);
      document.getElementById('avgPer').textContent = data.avg_memories_per_entry;
      document.getElementById('empty').textContent = num(data.empty_entries);
      document.getElementById('errors').textContent = num(data.error_lines);
      document.getElementById('lastId').textContent = data.last_source_diary_id || '-';
      document.getElementById('lastAt').textContent = data.last_extracted_at || '-';
      renderDonut(data.by_type || [], data.memories || 0);
      renderBars('scopeBars', data.by_scope || []);
      renderBars('importanceBars', data.by_importance || [], 'purple');
      const low = (data.by_risk || []).find(x => x.name === 'low')?.count || 0;
      const medium = (data.by_risk || []).find(x => x.name === 'medium')?.count || 0;
      renderBars('qualityBars', [{name:'平均置信度',count:Math.round(data.avg_confidence * 100)}, {name:'low risk',count:low}, {name:'medium risk',count:medium}, {name:'平均重要性×20',count:Math.round(data.avg_importance * 20)}], 'green');
      document.getElementById('subjects').innerHTML = (data.top_subjects || []).map(x => `<tr><td>${esc(x.name)}</td><td>${num(x.count)}</td></tr>`).join('');
      document.getElementById('parseStatus').textContent = data.parse_errors?.length ? `候选文件存在 ${data.parse_errors.length} 条解析异常，可能是读取到半写入行。刷新后通常会恢复。` : '候选文件 JSONL 当前可正常解析。';
      document.getElementById('errorStatus').textContent = data.error_lines ? `错误文件当前 ${data.error_lines} 条，结束后可单独重跑失败项。` : '错误文件暂无记录。';
      // 阶段 D 预审预测
      renderBars('reviewBars', [{name:'approved',count:data.review_approved||0}, {name:'needs_review',count:data.review_needs_review||0}, {name:'rejected',count:data.review_rejected||0}], 'green');
      const rejectReasons = (data.review_reasons || []).filter(x => ['missing_fields','too_short','high_risk','low_confidence','low_value_event'].includes(x.name)).slice(0, 10);
      renderBars('rejectReasonBars', rejectReasons, 'yellow');
    }
    refresh().catch(console.error);
    setInterval(() => refresh().catch(console.error), refreshMs);
  </script>
</body>
</html>"""


def make_handler(state):
    class LiveDashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                self.write_response(build_html(), "text/html; charset=utf-8")
                return
            if path == "/api/stats":
                payload = json.dumps(state.collect_stats(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(404)

        def write_response(self, text, content_type):
            payload = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            safe_path = html.escape(self.path)
            print(f"[Dashboard] {self.address_string()} {safe_path} {format % args}")

    return LiveDashboardHandler


def main():
    parser = argparse.ArgumentParser(description="Yuki-Memory 结构化候选实时只读看板")
    parser.add_argument("--candidate-file", default=DEFAULT_CANDIDATE_FILE, help="候选 JSONL 文件")
    parser.add_argument("--error-file", default=DEFAULT_ERROR_FILE, help="错误 JSONL 文件")
    parser.add_argument("--total", type=int, default=DEFAULT_TOTAL, help="目标日记总数，用于计算进度")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    state = DashboardState(args.candidate_file, args.error_file, args.total)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"[Dashboard] 只读实时看板已启动: http://{args.host}:{args.port}/")
    print(f"[Dashboard] candidate={Path(args.candidate_file).resolve()}")
    print(f"[Dashboard] error={Path(args.error_file).resolve()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
