import argparse
import datetime
import html
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_EXPORT_STATS_FILE = "data/memory_exports/diaries_stats_20260608_234723.json"
DEFAULT_EXPORT_DIR = "data/memory_exports"
DEFAULT_PREFIX = "mimo"
DEFAULT_TOTAL = 3244

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


def to_pairs(counter, limit=None, sort_by_name=False):
    items = sorted(counter.items(), key=lambda item: item[0]) if sort_by_name else counter.most_common(limit)
    if limit and sort_by_name:
        items = items[:limit]
    return [{"name": name, "count": count} for name, count in items]


def format_mtime(stat_result):
    if not stat_result:
        return ""
    return datetime.datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def read_jsonl(path):
    entries = []
    parse_errors = []
    if not path.exists():
        return entries, parse_errors

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                parse_errors.append({"file": str(path), "line": line_number, "error": str(exc)})
    return entries, parse_errors


def load_chat_totals(stats_file, fallback_total):
    path = Path(stats_file)
    if not path.exists():
        return {}, fallback_total
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    by_chat_id = payload.get("by_chat_id") or {}
    total = int(payload.get("total") or fallback_total or sum(by_chat_id.values()))
    return {str(chat_id): int(count) for chat_id, count in by_chat_id.items()}, total


class DashboardState:
    def __init__(self, export_dir, prefix, stats_file, total):
        self.export_dir = Path(export_dir)
        self.prefix = prefix
        self.stats_file = Path(stats_file)
        self.fallback_total = total

    def collect_stats(self):
        chat_totals, target_total = load_chat_totals(self.stats_file, self.fallback_total)
        chat_ids = list(chat_totals.keys())
        if not chat_ids:
            chat_ids = sorted(
                path.name.removeprefix(f"{self.prefix}_").removesuffix("_candidates.jsonl")
                for path in self.export_dir.glob(f"{self.prefix}_*_candidates.jsonl")
            )

        all_entries = []
        all_memories = []
        all_parse_errors = []
        all_error_entries = []
        chat_rows = []
        latest_mtime = ""
        total_candidate_size = 0
        latest_source_id = ""
        latest_extracted_at = ""

        for chat_id in chat_ids:
            candidate_file = self.export_dir / f"{self.prefix}_{chat_id}_candidates.jsonl"
            error_file = self.export_dir / f"{self.prefix}_{chat_id}_errors.jsonl"
            report_file = self.export_dir / f"{self.prefix}_{chat_id}_report.json"
            entries, parse_errors = read_jsonl(candidate_file)
            error_entries, error_parse_errors = read_jsonl(error_file)
            all_parse_errors.extend(parse_errors)
            all_parse_errors.extend(error_parse_errors)
            all_error_entries.extend(error_entries)

            memories = []
            for item in entries:
                for memory in item.get("memories") or []:
                    if isinstance(memory, dict):
                        memories.append(memory)

            candidate_stat = candidate_file.stat() if candidate_file.exists() else None
            error_stat = error_file.stat() if error_file.exists() else None
            report = {}
            if report_file.exists():
                try:
                    with report_file.open("r", encoding="utf-8") as f:
                        report = json.load(f)
                except json.JSONDecodeError:
                    report = {"stopped_reason": "report_parse_error"}

            selected_total = int(chat_totals.get(chat_id) or report.get("stats", {}).get("selected_total") or 0)
            processed = len(entries) + len(error_entries)
            progress = round(processed / selected_total * 100, 2) if selected_total else 0
            progress = max(0, min(progress, 100))
            status = "完成" if selected_total and processed >= selected_total else "进行中" if processed else "等待"
            stopped_reason = report.get("stopped_reason") or report.get("stats", {}).get("stopped_reason") or ""
            if stopped_reason:
                status = "暂停/异常"

            if candidate_stat:
                total_candidate_size += candidate_stat.st_size
                mtime = format_mtime(candidate_stat)
                if not latest_mtime or mtime > latest_mtime:
                    latest_mtime = mtime
            if entries:
                last_entry = entries[-1]
                last_time = str(last_entry.get("extracted_at") or "")
                if not latest_extracted_at or last_time > latest_extracted_at:
                    latest_extracted_at = last_time
                    latest_source_id = str(last_entry.get("source_diary_id") or "")

            chat_rows.append({
                "chat_id": chat_id,
                "target_total": selected_total,
                "processed": processed,
                "candidate_lines": len(entries),
                "error_lines": len(error_entries),
                "memories": len(memories),
                "progress": progress,
                "status": status,
                "stopped_reason": stopped_reason,
                "candidate_mtime": format_mtime(candidate_stat),
                "error_mtime": format_mtime(error_stat),
            })
            all_entries.extend(entries)
            all_memories.extend(memories)

        by_type = Counter(str(item.get("type") or "unknown") for item in all_memories)
        by_risk = Counter(str(item.get("risk") or "unknown") for item in all_memories)
        by_scope = Counter(str(item.get("time_scope") or "unknown") for item in all_memories)
        by_importance = Counter(str(item.get("importance") or "unknown") for item in all_memories)
        top_subjects = Counter(str(item.get("subject") or "unknown") for item in all_memories)
        empty_entries = sum(1 for item in all_entries if not item.get("memories"))
        confidences = [float(item.get("confidence") or 0) for item in all_memories]
        importances = [float(item.get("importance") or 0) for item in all_memories]

        review_status = Counter()
        review_reasons = Counter()
        for memory in all_memories:
            status, reason = estimate_review_status(memory)
            review_status[status] += 1
            review_reasons[reason] += 1

        processed_total = sum(row["processed"] for row in chat_rows)
        progress = round(processed_total / target_total * 100, 2) if target_total else 0
        progress = max(0, min(progress, 100))
        completed_chats = sum(1 for row in chat_rows if row["status"] == "完成")
        active_chat = next((row for row in chat_rows if row["status"] == "进行中"), None)

        return {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "export_dir": str(self.export_dir),
            "stats_file": str(self.stats_file),
            "target_total": target_total,
            "processed": processed_total,
            "progress": progress,
            "chat_count": len(chat_rows),
            "completed_chats": completed_chats,
            "active_chat": active_chat,
            "chat_rows": chat_rows,
            "memories": len(all_memories),
            "empty_entries": empty_entries,
            "error_lines": len(all_error_entries),
            "parse_errors": all_parse_errors[:20],
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0,
            "avg_importance": round(sum(importances) / len(importances), 2) if importances else 0,
            "avg_memories_per_entry": round(len(all_memories) / len(all_entries), 2) if all_entries else 0,
            "by_type": to_pairs(by_type),
            "by_risk": to_pairs(by_risk),
            "by_scope": to_pairs(by_scope),
            "by_importance": to_pairs(by_importance, sort_by_name=True),
            "top_subjects": to_pairs(top_subjects, limit=15),
            "last_source_diary_id": latest_source_id,
            "last_extracted_at": latest_extracted_at,
            "candidate_mtime": latest_mtime,
            "candidate_size": total_candidate_size,
            "latest_errors": all_error_entries[-5:],
            "review_status": dict(review_status),
            "review_approved": review_status.get("approved", 0),
            "review_needs_review": review_status.get("needs_review", 0),
            "review_rejected": review_status.get("rejected", 0),
            "review_reasons": to_pairs(review_reasons),
        }


def build_html():
    return """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Yuki-Memory 多群聊实时看板</title>
  <style>
    :root{color-scheme:dark;--bg:#070b18;--card:rgba(255,255,255,.08);--line:rgba(255,255,255,.14);--text:#eef4ff;--muted:#aab7d4;--cyan:#65e4ff;--blue:#7aa7ff;--purple:#c084fc;--pink:#f0abfc;--green:#8bf5c2;--yellow:#fde68a;--red:#fca5a5}
    *{box-sizing:border-box} body{margin:0;min-height:100vh;font-family:\"Microsoft YaHei\",\"Segoe UI\",system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 12% 8%,rgba(101,228,255,.22),transparent 34%),radial-gradient(circle at 82% 16%,rgba(192,132,252,.2),transparent 32%),radial-gradient(circle at 50% 100%,rgba(139,245,194,.14),transparent 38%),var(--bg)}
    .page{width:min(1380px,calc(100vw - 40px));margin:0 auto;padding:32px 0 48px}.hero,.card{border:1px solid var(--line);background:var(--card);box-shadow:0 24px 80px rgba(0,0,0,.32);backdrop-filter:blur(18px)}.hero{border-radius:28px;padding:28px;position:relative;overflow:hidden}.hero:after{content:\"\";position:absolute;right:-90px;top:-120px;width:320px;height:320px;background:radial-gradient(circle,rgba(101,228,255,.36),transparent 68%)}
    h1{margin:0 0 10px;font-size:clamp(30px,4vw,50px);letter-spacing:-.04em}.sub{margin:0;color:var(--muted);line-height:1.8}.row{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.pill{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.07);color:var(--muted);font-size:13px}.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green)}
    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px;margin-top:18px}.card{border-radius:24px;padding:20px}.s3{grid-column:span 3}.s4{grid-column:span 4}.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s8{grid-column:span 8}.s12{grid-column:span 12}.label{color:var(--muted);font-size:13px;margin-bottom:10px}.value{font-size:34px;font-weight:850;line-height:1;letter-spacing:-.04em}.note{margin-top:10px;color:var(--muted);font-size:12px;line-height:1.6}.progress{height:12px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.1);margin-top:16px}.progress>i{display:block;height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,var(--cyan),var(--purple));box-shadow:0 0 22px rgba(101,228,255,.48);transition:width .6s ease}
    h2{margin:0 0 18px;font-size:18px}.bars{display:grid;gap:12px}.bar{display:grid;grid-template-columns:130px 1fr 60px;gap:12px;align-items:center;color:var(--muted);font-size:13px}.track{height:10px;overflow:hidden;border-radius:999px;background:rgba(255,255,255,.1)}.fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--blue),var(--cyan));transition:width .6s ease}.fill.purple{background:linear-gradient(90deg,var(--purple),var(--pink))}.fill.green{background:linear-gradient(90deg,var(--green),var(--cyan))}.fill.yellow{background:linear-gradient(90deg,var(--yellow),var(--pink))}
    .donut-area{display:grid;grid-template-columns:190px 1fr;gap:22px;align-items:center}.donut{width:180px;height:180px;border-radius:50%;background:conic-gradient(var(--cyan) 0 0);position:relative;box-shadow:inset 0 0 30px rgba(255,255,255,.06),0 0 38px rgba(101,228,255,.16)}.donut:after{content:attr(data-total);position:absolute;inset:34px;display:grid;place-items:center;border-radius:50%;background:#10162b;font-size:30px;font-weight:850}.legend{display:grid;gap:10px}.legend-row{display:flex;justify-content:space-between;gap:16px;color:var(--muted);font-size:13px}.legend-name{display:inline-flex;align-items:center;gap:8px}.swatch{width:10px;height:10px;border-radius:3px}
    table{width:100%;border-collapse:collapse}th,td{padding:11px 10px;border-bottom:1px solid rgba(255,255,255,.09);text-align:left;font-size:13px}th{color:var(--muted);font-weight:500}td:last-child,th:last-child{text-align:right}.status{display:inline-flex;padding:4px 9px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.07);color:var(--muted)}.status.done{color:#d5ffe9;border-color:rgba(139,245,194,.28);background:rgba(139,245,194,.1)}.status.active{color:#d8f7ff;border-color:rgba(101,228,255,.28);background:rgba(101,228,255,.1)}.status.error{color:#ffe2b5;border-color:rgba(253,230,138,.28);background:rgba(253,230,138,.1)}
    .warn{padding:14px 16px;border-radius:18px;background:rgba(253,230,138,.1);border:1px solid rgba(253,230,138,.24);color:#fff4c2;line-height:1.7;font-size:13px}.ok{background:rgba(139,245,194,.1);border-color:rgba(139,245,194,.24);color:#d5ffe9}code{color:#d8e8ff;background:rgba(255,255,255,.08);padding:2px 6px;border-radius:8px}
    @media(max-width:900px){.s3,.s4,.s5,.s6,.s7,.s8{grid-column:span 12}.donut-area{grid-template-columns:1fr}.bar{grid-template-columns:96px 1fr 48px}}
  </style>
</head>
<body>
  <main class=\"page\">
    <section class=\"hero\">
      <h1>Yuki-Memory 多群聊实时看板</h1>
      <p class=\"sub\">后端只读扫描所有 <code>mimo_*_candidates.jsonl</code> / <code>mimo_*_errors.jsonl</code>，前端每 <code id=\"interval\">3</code> 秒刷新一次。不会写入、截断或锁定后台转换文件。</p>
      <div class=\"row\"><span class=\"pill\"><span class=\"dot\"></span>实时监控中</span><span class=\"pill\">刷新时间：<span id=\"generatedAt\">-</span></span><span class=\"pill\">最新文件更新时间：<span id=\"mtime\">-</span></span><span class=\"pill\">候选总大小：<span id=\"fileSize\">-</span></span></div>
    </section>
    <section class=\"grid\">
      <div class=\"card s3\"><div class=\"label\">全量处理进度</div><div class=\"value\" id=\"processed\">-</div><div class=\"note\"><span id=\"progressText\">-</span></div><div class=\"progress\"><i id=\"progressBar\"></i></div></div>
      <div class=\"card s3\"><div class=\"label\">群聊完成数</div><div class=\"value\" id=\"chatProgress\">-</div><div class=\"note\">当前群聊：<span id=\"activeChat\">-</span></div></div>
      <div class=\"card s3\"><div class=\"label\">结构化候选</div><div class=\"value\" id=\"memories\">-</div><div class=\"note\">平均每条日记 <span id=\"avgPer\">-</span> 条候选</div></div>
      <div class=\"card s3\"><div class=\"label\">错误记录</div><div class=\"value\" id=\"errors\">-</div><div class=\"note\">来自所有 error JSONL</div></div>
      <div class=\"card s12\"><h2>群聊处理队列</h2><table><thead><tr><th>chat_id</th><th>状态</th><th>进度</th><th>候选行</th><th>错误</th><th>记忆候选</th><th>更新时间</th></tr></thead><tbody id=\"chatRows\"></tbody></table></div>
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
    function statusClass(status){
      if(status === '完成') return 'done';
      if(status === '进行中') return 'active';
      if(status === '暂停/异常') return 'error';
      return '';
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
      document.getElementById('chatProgress').textContent = `${num(data.completed_chats)} / ${num(data.chat_count)}`;
      document.getElementById('activeChat').textContent = data.active_chat?.chat_id || '-';
      document.getElementById('memories').textContent = num(data.memories);
      document.getElementById('avgPer').textContent = data.avg_memories_per_entry;
      document.getElementById('errors').textContent = num(data.error_lines);
      document.getElementById('lastId').textContent = data.last_source_diary_id || '-';
      document.getElementById('lastAt').textContent = data.last_extracted_at || '-';
      document.getElementById('chatRows').innerHTML = (data.chat_rows || []).map(row => `<tr><td><code>${esc(row.chat_id)}</code></td><td><span class=\"status ${statusClass(row.status)}\">${esc(row.status)}</span></td><td>${num(row.processed)} / ${num(row.target_total)} (${row.progress}%)</td><td>${num(row.candidate_lines)}</td><td>${num(row.error_lines)}</td><td>${num(row.memories)}</td><td>${esc(row.candidate_mtime || '-')}</td></tr>`).join('');
      renderDonut(data.by_type || [], data.memories || 0);
      renderBars('scopeBars', data.by_scope || []);
      renderBars('importanceBars', data.by_importance || [], 'purple');
      const low = (data.by_risk || []).find(x => x.name === 'low')?.count || 0;
      const medium = (data.by_risk || []).find(x => x.name === 'medium')?.count || 0;
      renderBars('qualityBars', [{name:'平均置信度',count:Math.round(data.avg_confidence * 100)}, {name:'low risk',count:low}, {name:'medium risk',count:medium}, {name:'平均重要性×20',count:Math.round(data.avg_importance * 20)}], 'green');
      document.getElementById('subjects').innerHTML = (data.top_subjects || []).map(x => `<tr><td>${esc(x.name)}</td><td>${num(x.count)}</td></tr>`).join('');
      document.getElementById('parseStatus').textContent = data.parse_errors?.length ? `候选/错误文件存在 ${data.parse_errors.length} 条解析异常，可能是读取到半写入行。刷新后通常会恢复。` : '所有 JSONL 当前可正常解析。';
      document.getElementById('errorStatus').textContent = data.error_lines ? `错误文件当前 ${data.error_lines} 条，结束后可单独重跑失败项。` : '错误文件暂无记录。';
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
    parser = argparse.ArgumentParser(description="Yuki-Memory 结构化候选多群聊实时只读看板")
    parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR, help="memory_exports 目录")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="候选文件前缀，默认 mimo")
    parser.add_argument("--stats-file", default=DEFAULT_EXPORT_STATS_FILE, help="diaries_stats_*.json 文件")
    parser.add_argument("--total", type=int, default=DEFAULT_TOTAL, help="目标日记总数，用于兜底计算进度")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    state = DashboardState(args.export_dir, args.prefix, args.stats_file, args.total)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"[Dashboard] 多群聊只读实时看板已启动: http://{args.host}:{args.port}/")
    print(f"[Dashboard] export_dir={Path(args.export_dir).resolve()}")
    print(f"[Dashboard] stats_file={Path(args.stats_file).resolve()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
