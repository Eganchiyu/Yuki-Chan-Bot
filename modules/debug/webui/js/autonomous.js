// ==================== TAB 4: AUTONOMOUS SANDBOX 逻辑 ====================
// 数据源：GET /api/autonomous（状态快照）、/api/autonomous/runs（逐轮清单）、
//         /api/autonomous/runs/<run_id>（单次完整事件流）。

let autoSnapshot = null;
let autoRuns = [];
let autoSelectedRun = null;
let autoEvents = [];
let autoOutcomeFilter = 'all';
let autoKindFilter = 'all';
let autoLive = true;

const AUTO_GAUGE_R = 40;
const AUTO_GAUGE_C = 2 * Math.PI * AUTO_GAUGE_R;

const AUTO_OUTCOME_LABELS = {
  start_work: ['🛠️ 进入工坊', 'finished'],
  memo_only: ['📝 只留随想', 'replied'],
  stalled: ['⏸️ 被系统收尾', 'time'],
  do_nothing: ['🌫️ 什么都不做', 'dived'],
  abandon: ['🪶 本尊放弃', 'dived'],
  mode_busy: ['🚧 模式被占用', 'err'],
  error: ['⚠️ 异常', 'err'],
  exception: ['💥 异常', 'err']
};

const AUTO_KIND_GROUPS = {
  debate: ['debate_start', 'debate_step', 'debate_finish'],
  vote: ['vote'],
  reflection: ['reflection'],
  workshop: ['workshop_start', 'workshop_step', 'workshop_finish'],
  lifecycle: ['gate', 'phase', 'run_start', 'run_finish']
};

const AUTO_COMMANDS = [
  { cmd: '/深思', desc: '在本群手动跑一次自主轮；休眠群 / 未开启 / 已被占用会直接拒绝并说明原因。' },
  { cmd: '/自主轮 开', desc: '运行时开启本群自主轮（写 group_overrides，能越过总开关，重启后仍生效）。' },
  { cmd: '/自主轮 关', desc: '运行时关闭本群自主轮（同样持久化，重启后仍生效）。' },
  { cmd: '/工坊状态', desc: '当前模式与墙钟、暂停中的会话 + 512 字日志头、今日配额、上次结束时间与异常。' },
  { cmd: '/强制放行', desc: '逃生阀：请求当前模式尽快收尾，立刻把群还给群聊。' }
];

function autoPct(value, max) {
  const m = Number(max || 0);
  if (!m) return 0;
  return Math.max(0, Math.min(1, Number(value || 0) / m));
}

function autoFmtElapsed(sec) {
  const s = Math.max(0, Math.round(Number(sec || 0)));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  if (mm >= 60) {
    const hh = Math.floor(mm / 60);
    return `${hh}:${String(mm % 60).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
  }
  return `${mm}:${String(ss).padStart(2, '0')}`;
}

function autoFmtMinutes(min) {
  const m = Math.max(0, Math.round(Number(min || 0)));
  if (m >= 60) return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`;
  return `${m}m`;
}

function autoGauge({ pct, center, label, sub, color }) {
  const p = Math.max(0, Math.min(1, Number(pct || 0)));
  const offset = AUTO_GAUGE_C * (1 - p);
  return `
    <div class="auto-gauge">
      <div class="auto-gauge-dial">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle class="g-track" cx="50" cy="50" r="${AUTO_GAUGE_R}"></circle>
          <circle class="g-val" cx="50" cy="50" r="${AUTO_GAUGE_R}" stroke="${color}"
            stroke-dasharray="${AUTO_GAUGE_C.toFixed(2)}"
            stroke-dashoffset="${offset.toFixed(2)}"></circle>
        </svg>
        <div class="auto-gauge-value">${esc(center)}</div>
      </div>
      <div class="auto-gauge-label">${esc(label)}</div>
      <div class="auto-gauge-sub">${esc(sub || '')}</div>
    </div>`;
}

function autoInQuietHours(hours) {
  const list = Array.isArray(hours) ? hours : [];
  if (list.length !== 2) return false;
  const start = Number(list[0]);
  const end = Number(list[1]);
  if (start === end) return false;
  const hour = new Date().getHours();
  return start < end ? (hour >= start && hour < end) : (hour >= start || hour < end);
}

function autoIsLive() {
  return !!(autoSnapshot && autoSnapshot.run && autoSnapshot.run.run_id);
}

// ---------------------------------------------------------------- 主刷新
async function refreshAutonomous(manual = false) {
  try {
    const [snap, runs] = await Promise.all([
      api('/api/autonomous?limit=20'),
      api('/api/autonomous/runs?limit=60')
    ]);
    if (!snap || snap.ok === false) throw new Error((snap && snap.error) || 'snapshot_unavailable');
    autoSnapshot = snap;
    autoRuns = Array.isArray(runs && runs.runs) ? runs.runs : [];

    renderAutoToolbar();
    renderAutoRun();
    renderAutoGauges();
    renderAutoFreeze();
    renderAutoGate();
    renderAutoMemories();
    renderAutoCommands();
    renderAutoRunList();

    const badge = document.getElementById('navAutoState');
    if (badge) badge.textContent = autoIsLive() ? (autoSnapshot.run.mode === 'workshop' ? '工坊中' : '交锋中') : '待机';

    const activeRunId = autoIsLive() ? autoSnapshot.run.run_id : '';
    if (activeRunId && (autoLive || !autoSelectedRun)) {
      await loadTranscript(activeRunId, false);
    } else if (!autoSelectedRun && autoRuns.length) {
      await loadTranscript(autoRuns[0].run_id, false);
    } else if (autoSelectedRun) {
      renderAutoReplay();
    }
    if (manual) showToast('✨ 自主轮快照已刷新');
  } catch (err) {
    const pills = document.getElementById('autoToolbarPills');
    if (pills) pills.innerHTML = `<span class="status-pill"><i class="dot err"></i>读取失败：${esc(err.message || err)}</span>`;
  }
}

// ---------------------------------------------------------------- 顶部状态条
function renderAutoToolbar() {
  const s = autoSnapshot || {};
  const gate = s.gate || {};
  const quota = s.quota || {};
  const run = s.run;
  const quiet = autoInQuietHours(gate.quiet_hours);
  const pills = [
    `<span class="status-pill"><i class="dot ${s.enabled ? '' : 'warn'}"></i>总开关 <b>${s.enabled ? 'ON' : 'OFF'}</b></span>`,
    `<span class="status-pill"><i class="dot ${s.auto_trigger ? '' : 'warn'}"></i>冷场自动 <b>${s.auto_trigger ? 'ON' : 'OFF'}</b></span>`,
    `<span class="status-pill">今日自动 <b>${quota.auto_runs_today ?? 0}/${quota.daily_max_runs ?? 0}</b></span>`,
    `<span class="status-pill">白名单 <b>${(gate.enabled_groups || []).length}</b> 群</span>`,
    quiet ? `<span class="status-pill"><i class="dot warn"></i>深夜静默 ${esc((gate.quiet_hours || []).join('→'))} 点</span>`
          : `<span class="status-pill">静默门槛 <b>${gate.min_group_idle_minutes ?? '-'}min</b></span>`,
    run ? `<span class="status-pill"><i class="dot pink"></i>运行中 <b>${esc(run.run_id)}</b></span>`
        : `<span class="status-pill">上次结束 <b>${esc(quota.last_run_at || '从未')}</b></span>`,
    `<span class="status-pill">快照 <b>${esc(s.now || '')}</b></span>`
  ];
  const box = document.getElementById('autoToolbarPills');
  if (box) box.innerHTML = pills.join('');
}

// ---------------------------------------------------------------- 当前运行态
function renderAutoRun() {
  const s = autoSnapshot || {};
  const run = s.run;
  const limits = s.limits || {};
  const body = document.getElementById('autoRunBody');
  const badge = document.getElementById('autoRunBadge');
  if (!body) return;

  if (!run) {
    if (badge) { badge.className = 'badge dived'; badge.textContent = '待机'; }
    const quota = s.quota || {};
    const gate = s.gate || {};
    body.innerHTML = `
      <div class="auto-run-head">
        <div class="auto-mode-orb idle">🌙</div>
        <div class="auto-run-meta">
          <div class="auto-run-title">群聊模式待机 · 她正在正常接话</div>
          <div class="auto-run-sub">
            <span>今日自动 <b>${quota.auto_runs_today ?? 0}/${quota.daily_max_runs ?? 0}</b></span>
            <span>冷却 <b>${gate.cooldown_minutes ?? '-'}min</b></span>
            <span>上次结束 <b>${esc(quota.last_run_at || '从未')}</b></span>
          </div>
        </div>
        <div class="auto-clock"><b>--:--</b><span>墙钟空闲</span></div>
      </div>
      <div class="auto-phase-track">
        ${autoPhaseNode(1, 'debate', 'Phase 1 双念头交锋', `A/B 交替 ≤${limits.debate_max_rounds ?? 32} 轮，需双向投票收敛`, 'todo')}
        ${autoPhaseNode(2, 'reflection', 'Phase 2 本尊复盘', '三向：abandon / memo_only / start_work', 'todo')}
        ${autoPhaseNode(3, 'workshop', 'Phase 3 自主工坊', `≤${limits.workshop_max_tool_calls ?? 60} 次工具，产出日志与 artifacts`, 'todo')}
      </div>`;
    return;
  }

  if (badge) { badge.className = 'badge running'; badge.textContent = run.mode === 'workshop' ? '工坊中' : '交锋中'; }
  const progress = run.progress || {};
  const phase = progress.phase || run.mode || 'debate';
  const stateOf = (name) => {
    const order = ['debate', 'reflection', 'workshop'];
    const current = order.indexOf(phase);
    const idx = order.indexOf(name);
    if (current < 0) return name === 'debate' ? 'active' : 'todo';
    if (idx < current) return 'done';
    if (idx === current) return 'active';
    return 'todo';
  };
  const debateNote = progress.debate_steps
    ? `已交锋 ${progress.debate_steps}/${limits.debate_max_rounds ?? 32} 步 · 投票 ${progress.votes || 0} 次`
    : `A/B 交替 ≤${limits.debate_max_rounds ?? 32} 轮`;
  const workNote = progress.workshop_steps
    ? `已走 ${progress.workshop_steps} 步 · 工具 ${progress.tool_calls || 0}/${limits.workshop_max_tool_calls ?? 60}`
    : `≤${limits.workshop_max_tool_calls ?? 60} 次工具预算`;
  const wallPct = autoPct(run.elapsed, limits.max_wall_seconds);
  const orb = run.mode === 'workshop' ? '🛠️' : (run.mode === 'reflection' ? '🪞' : '⚔️');

  body.innerHTML = `
    <div class="auto-run-head">
      <div class="auto-mode-orb live">${orb}</div>
      <div class="auto-run-meta">
        <div class="auto-run-title">
          ${esc(run.phase || run.mode)}
          <span class="badge pink">唯一体性占用中</span>
        </div>
        <div class="auto-run-sub">
          <span>群 <b>${esc(run.name || run.chat_id)}</b></span>
          <code>${esc(run.run_id || '')}</code>
          ${run.session_id ? `<code>${esc(run.session_id)}</code>` : ''}
          <span>开始 <b>${esc(run.started_at || '')}</b></span>
        </div>
      </div>
      <div class="auto-clock">
        <b>${autoFmtElapsed(run.elapsed)}</b>
        <span>墙钟 / 上限 ${autoFmtElapsed(limits.max_wall_seconds)} · ${Math.round(wallPct * 100)}%</span>
      </div>
    </div>
    <div class="auto-phase-track">
      ${autoPhaseNode(1, 'debate', 'Phase 1 双念头交锋', debateNote, stateOf('debate'))}
      ${autoPhaseNode(2, 'reflection', 'Phase 2 本尊复盘', '单工具环 conclude_reflection，最多 3 次', stateOf('reflection'))}
      ${autoPhaseNode(3, 'workshop', 'Phase 3 自主工坊', workNote, stateOf('workshop'))}
    </div>`;
}

function autoPhaseNode(idx, name, title, note, state) {
  return `
    <div class="auto-phase-node" data-state="${esc(state)}" data-phase="${esc(name)}">
      <div class="ph-idx">PHASE ${idx}</div>
      <div class="ph-name">${esc(title)}</div>
      <div class="ph-note">${esc(note)}</div>
    </div>`;
}

// ---------------------------------------------------------------- 仪表
function renderAutoGauges() {
  const s = autoSnapshot || {};
  const limits = s.limits || {};
  const gate = s.gate || {};
  const quota = s.quota || {};
  const run = s.run;
  const now = Date.now() / 1000;

  const quotaMax = Number(quota.daily_max_runs || 0);
  const quotaUsed = Number(quota.auto_runs_today || 0);

  const cdSeconds = Math.max(1, Number(gate.cooldown_minutes || 0) * 60);
  const sinceLast = quota.last_run_at_ts ? Math.max(0, now - Number(quota.last_run_at_ts)) : cdSeconds;
  const cdLeft = Math.max(0, cdSeconds - sinceLast);

  const wallElapsed = run ? Number(run.elapsed || 0) : 0;
  const wallMax = Number(limits.max_wall_seconds || 900);

  const html = [
    autoGauge({
      pct: quotaMax ? quotaUsed / quotaMax : 0,
      center: `${quotaUsed}/${quotaMax || 0}`,
      label: '今日自动配额',
      sub: quotaUsed >= quotaMax && quotaMax ? '已用尽，等明天' : `还剩 ${Math.max(0, quotaMax - quotaUsed)} 次`,
      color: '#ff4785'
    }),
    autoGauge({
      pct: cdSeconds ? cdLeft / cdSeconds : 0,
      center: cdLeft > 0 ? autoFmtMinutes(cdLeft / 60) : '就绪',
      label: '自动触发冷却',
      sub: cdLeft > 0 ? `上限 ${gate.cooldown_minutes}m` : '冷却已完成',
      color: '#9b5de5'
    }),
    autoGauge({
      pct: run ? autoPct(wallElapsed, wallMax) : 0,
      center: run ? autoFmtElapsed(wallElapsed) : '--:--',
      label: '本次墙钟',
      sub: run ? `上限 ${autoFmtElapsed(wallMax)}` : '没有运行中的自主轮',
      color: '#00b4d8'
    }),
    autoGauge({
      pct: run && run.progress ? autoPct(run.progress.workshop_steps, limits.workshop_max_tool_calls) : 0,
      center: `${(run && run.progress && run.progress.tool_calls) || 0}`,
      label: '工坊工具调用',
      sub: `预算 ${limits.workshop_max_tool_calls ?? '-'} 次`,
      color: '#10b981'
    })
  ].join('');
  const box = document.getElementById('autoGaugeGrid');
  if (box) box.innerHTML = html;
}

// ---------------------------------------------------------------- 唯一体性
function renderAutoFreeze() {
  const s = autoSnapshot || {};
  const freeze = s.freeze || {};
  const frozen = Array.isArray(s.frozen) ? s.frozen : [];
  const pending = Array.isArray(freeze.pending_catchups) ? freeze.pending_catchups : [];
  const banner = document.getElementById('autoFreezeBanner');
  const badge = document.getElementById('autoFreezeBadge');
  const box = document.getElementById('autoFrozenBox');
  const busy = !freeze.idle || frozen.length > 0;

  if (banner) {
    banner.className = 'auto-freeze-banner' + (busy ? ' busy' : '');
    banner.innerHTML = busy
      ? `<span>⏳</span><span>全局唯一体性被占用：${frozen.length} 个群处于冻结，真人消息只入缓冲区，结束后逐个补台。</span>`
      : `<span>✅</span><span>当前没有群被冻结，所有群都在 chat 模式正常接话。</span>`;
  }
  if (badge) {
    badge.className = 'badge ' + (busy ? 'running' : 'finished');
    badge.textContent = busy ? `${frozen.length} 群冻结` : '空闲';
  }
  if (!box) return;
  const rows = [];
  for (const f of frozen) {
    rows.push(`
      <div class="auto-frozen-row">
        <div>
          <div class="fr-name">🧊 ${esc(f.name || f.chat_id)}</div>
          <div class="fr-sub">${esc(f.chat_id)} · 冻结于 ${esc(f.since || '')}</div>
        </div>
        <span class="mini-tag amber">待补 ${f.messages || 0} 条</span>
      </div>`);
  }
  for (const p of pending) {
    rows.push(`
      <div class="auto-frozen-row" style="border-color:rgba(255,71,133,.3)">
        <div>
          <div class="fr-name">💌 ${esc(p.name || p.chat_id)}</div>
          <div class="fr-sub">${esc(p.chat_id)} · 已结束但还没补台</div>
        </div>
        <span class="mini-tag">排队补台</span>
      </div>`);
  }
  const run = s.run;
  if (run) {
    rows.unshift(`
      <div class="auto-frozen-row" style="background:var(--grad-soft);border-color:var(--line-strong)">
        <div>
          <div class="fr-name">🔒 ${esc(run.name || run.chat_id)}</div>
          <div class="fr-sub">独占中 · ${esc(run.phase || run.mode)} · ${esc(run.run_id || '')}</div>
        </div>
        <span class="mini-tag">占用</span>
      </div>`);
  }
  box.innerHTML = rows.length ? rows.join('') : '<div class="auto-empty">没有冻结群，也没有排队中的补台</div>';
}

// ---------------------------------------------------------------- 准入看板
function renderAutoGate() {
  const s = autoSnapshot || {};
  const rows = Array.isArray(s.groups) ? s.groups : [];
  const box = document.getElementById('autoGateGrid');
  if (!box) return;
  if (!rows.length) {
    box.innerHTML = '<div class="auto-empty">没有可展示的群：配置白名单为空，也没有运行时覆盖</div>';
    return;
  }
  box.innerHTML = rows.map(g => {
    const tags = [];
    if (g.running) tags.push('<span class="mini-tag">🚀 正在跑</span>');
    tags.push(`<span class="mini-tag ${g.enabled ? 'mint' : 'muted'}">${g.enabled ? '✅ 已开启' : '🚫 未开启'}</span>`);
    if (g.override === 'on') tags.push('<span class="mini-tag purple">/自主轮 开 覆盖</span>');
    if (g.override === 'off') tags.push('<span class="mini-tag amber">/自主轮 关 覆盖</span>');
    if (g.in_config) tags.push('<span class="mini-tag cyan">配置白名单</span>');
    if (!g.in_target) tags.push('<span class="mini-tag amber">非目标群</span>');
    return `
      <div class="auto-gate-row ${g.enabled ? 'on' : ''} ${g.running ? 'running' : ''}">
        <div class="gr-main">
          <div class="gr-name">${esc(g.name || g.chat_id)}<span class="muted" style="font-size:11px">${esc(g.chat_id)}</span></div>
          <div class="gr-reason">${esc(g.reason || '')}</div>
          <div class="gr-tags">${tags.join('')}</div>
        </div>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------- 五层记忆（L2–L5）
function renderAutoMemories() {
  const s = autoSnapshot || {};
  const diaries = Array.isArray(s.work_diaries) ? s.work_diaries : [];
  const sessions = Array.isArray(s.sessions) ? s.sessions : [];
  const daily = s.daily_work_memory || {};
  const notebook = s.notebook || {};
  const tuning = s.tuning || {};

  const diaryBox = document.getElementById('autoDiaryList');
  const diaryCount = document.getElementById('autoDiaryCount');
  if (diaryCount) diaryCount.textContent = `${diaries.length} 条`;
  if (diaryBox) {
    diaryBox.innerHTML = diaries.length ? diaries.map(d => `
      <div class="auto-diary-item">
        <div class="di-top">
          <span>${esc(d.ts || '')}</span>
          ${d.kind ? `<span class="mini-tag cyan">${esc(d.kind)}</span>` : ''}
        </div>
        <div class="di-title">${esc(d.title || '(无标题)')}</div>
        <div class="di-body">${esc(d.content || '')}</div>
      </div>`).join('') : '<div class="auto-empty">还没有工作日记：工坊跑完才会写 L2</div>';
  }

  const sessBox = document.getElementById('autoSessList');
  const sessCount = document.getElementById('autoSessCount');
  if (sessCount) sessCount.textContent = `${sessions.length} 个`;
  if (sessBox) {
    sessBox.innerHTML = sessions.length ? sessions.map(x => {
      const statusCls = x.status === 'completed' ? 'finished' : (x.status === 'active' ? 'running' : 'time');
      const arts = Array.isArray(x.artifacts) ? x.artifacts : [];
      return `
        <div class="auto-sess-item">
          <div class="si-top">
            <span>${esc(x.session_id || '')}</span>
            <span class="badge ${statusCls}">${esc(x.status || '?')}</span>
            ${x.kind ? `<span class="mini-tag purple">${esc(x.kind)}</span>` : ''}
            <span>${esc(x.updated_at || '')}</span>
          </div>
          <div class="si-title">${esc(x.title || '(未命名会话)')}</div>
          <div class="si-log">${esc(x.work_log || '（暂无工作日志）')}</div>
          ${arts.length ? `<div class="si-artifacts">${arts.map(a => `<span class="auto-artifact" title="${esc(a)}">${esc(a)}</span>`).join('')}</div>` : ''}
        </div>`;
    }).join('') : '<div class="auto-empty">还没有工作会话：start_work 之后才会建 L3</div>';
  }

  const dailyBox = document.getElementById('autoDailyMemory');
  const dailyMeta = document.getElementById('autoDailyMeta');
  if (dailyMeta) {
    dailyMeta.textContent = daily.date
      ? `${daily.date} · ${daily.entries || 0} 条 · TTL ${tuning.daily_memory_ttl_hours ?? '-'}h`
      : '今天还没有';
  }
  if (dailyBox) {
    dailyBox.innerHTML = daily.text
      ? `<div class="auto-memory-text">${esc(daily.text)}</div>
         <div class="muted" style="font-size:11px;margin-top:7px">
           更新 ${esc(daily.updated_at || '-')}${daily.archived_at ? ` · 已归档 ${esc(daily.archived_at)}` : ''}
         </div>`
      : '<div class="auto-empty">今日工作记忆为空：只有 memo_only / start_work 才会写入</div>';
  }

  const nb = document.getElementById('autoNotebook');
  if (nb) {
    nb.innerHTML = `
      <div class="auto-notebook-zone">
        <div class="nz-head"><span>📅 daily 区</span><span>${(notebook.daily || '').length}/350</span></div>
        <div class="nz-body">${esc(notebook.daily || '（空）')}</div>
      </div>
      <div class="auto-notebook-zone">
        <div class="nz-head"><span>🗺️ plans 区</span><span>${(notebook.plans || '').length}/160</span></div>
        <div class="nz-body">${esc(notebook.plans || '（空）')}</div>
      </div>`;
  }
}

// ---------------------------------------------------------------- 指令与流程
function renderAutoCommands() {
  const box = document.getElementById('autoCmdGrid');
  if (box) {
    box.innerHTML = AUTO_COMMANDS.map(c => `
      <button class="auto-cmd" onclick="copyAutoCommand('${esc(c.cmd)}')">
        <code>${esc(c.cmd)}</code>
        <p>${esc(c.desc)}</p>
      </button>`).join('');
  }
  const flow = document.getElementById('autoFlow');
  if (flow) {
    const s = autoSnapshot || {};
    const phase = (s.run && s.run.progress && s.run.progress.phase) || '';
    const cls = (name) => name === phase ? ' active' : '';
    flow.innerHTML = `
      <span class="auto-flow-node chat">chat</span>
      <span class="auto-flow-arrow">→</span>
      <span class="auto-flow-node debate${cls('debate')}">debate 交锋</span>
      <span class="auto-flow-arrow">→</span>
      <span class="auto-flow-node reflection${cls('reflection')}">reflection 复盘</span>
      <span class="auto-flow-arrow">→</span>
      <span class="auto-flow-node workshop${cls('workshop')}">workshop 工坊</span>
      <span class="auto-flow-arrow">→</span>
      <span class="auto-flow-node chat">回群</span>
      <div class="auto-flow-note">
        出口：<b>do_nothing / abandon / 中断</b> 走零痕迹退场（不写 chat_history 与 L1–L5）；
        <b>memo_only</b> 只落备忘录与今日记忆；<b>start_work</b> 进工坊，结束后高涨 25 分钟并可能破冰。
      </div>`;
  }
}

function copyAutoCommand(cmd) {
  navigator.clipboard.writeText(cmd);
  showToast(`✨ 已复制指令 ${cmd}`);
}

// ---------------------------------------------------------------- 逐轮清单
function autoOutcomeBucket(outcome) {
  if (['start_work', 'memo_only'].includes(outcome)) return 'completed';
  if (outcome === 'stalled') return 'stalled';
  if (['do_nothing', 'abandon'].includes(outcome)) return 'quiet';
  if (['error', 'exception', 'mode_busy'].includes(outcome)) return 'error';
  return 'other';
}

function setAutoOutcome(value, el) {
  autoOutcomeFilter = value;
  document.querySelectorAll('#pane-autonomous .filter-chips [data-outcome]').forEach(b => b.classList.toggle('active', b === el));
  renderAutoRunList();
}

function renderAutoRunList() {
  const box = document.getElementById('autoRunList');
  const countLabel = document.getElementById('autoRunCount');
  if (!box) return;
  const keyword = (document.getElementById('autoRunSearch')?.value || '').trim().toLowerCase();
  const rows = autoRuns.filter(r => {
    if (autoOutcomeFilter !== 'all' && autoOutcomeBucket(r.outcome) !== autoOutcomeFilter) return false;
    if (!keyword) return true;
    return [r.run_id, r.name, r.chat_id, r.outcome].join(' ').toLowerCase().includes(keyword);
  });
  if (countLabel) countLabel.textContent = `${rows.length}/${autoRuns.length} 次`;
  if (!rows.length) {
    box.innerHTML = autoRuns.length
      ? '<div class="auto-empty">没有匹配的运行记录</div>'
      : '<div class="auto-empty">还没有逐轮记录：本群用 /深思 跑一次后就会出现</div>';
    return;
  }
  box.innerHTML = rows.map(r => {
    const [label, cls] = AUTO_OUTCOME_LABELS[r.outcome] || [`· ${r.outcome || '未收尾'}`, ''];
    const active = r.run_id === autoSelectedRun ? ' active' : '';
    return `
      <div class="auto-run-item${active}" onclick="selectAutoRun('${esc(r.run_id)}')">
        <div class="ri-top">
          <span class="ri-name">${esc(r.name || r.chat_id || '未知群')}</span>
          <span class="badge ${cls}">${esc(label)}</span>
        </div>
        <div class="ri-id">${esc(r.run_id)}</div>
        <div class="ri-stats">
          <span>⚔️ ${r.debate_steps || 0} 步</span>
          <span>🗳️ ${r.votes || 0} 票</span>
          <span>🛠️ ${r.workshop_steps || 0} 步</span>
          <span>🔧 ${r.tool_calls || 0} 次</span>
          <span>${esc(r.updated_at || '')}</span>
        </div>
      </div>`;
  }).join('');
}

async function selectAutoRun(runId) {
  await loadTranscript(runId, false);
}

async function replaySelectedRun() {
  if (!autoSelectedRun) { showToast('还没有选中运行'); return; }
  await loadTranscript(autoSelectedRun, true);
}

function setAutoKind(value, el) {
  autoKindFilter = value;
  document.querySelectorAll('#autoKindChips .chip').forEach(b => b.classList.toggle('active', b === el));
  renderAutoReplay();
}

// ---------------------------------------------------------------- 事件回放
async function loadTranscript(runId, manual = false) {
  if (!runId) return;
  try {
    const data = await api('/api/autonomous/runs/' + encodeURIComponent(runId));
    if (!data || data.ok === false) throw new Error((data && data.error) || 'run_not_found');
    autoSelectedRun = data.run_id;
    autoEvents = Array.isArray(data.events) ? data.events : [];
    renderAutoRunList();
    renderAutoReplay();
    autoScrollReplayToEnd();
    if (manual) showToast(`✨ 已重放 ${data.run_id}`);
  } catch (err) {
    const stream = document.getElementById('autoReplayStream');
    if (stream) stream.innerHTML = `<div class="auto-empty">读取逐轮记录失败：${esc(err.message || err)}</div>`;
  }
}

function autoScrollReplayToEnd() {
  const stream = document.getElementById('autoReplayStream');
  if (!stream) return;
  const live = autoIsLive() && autoSelectedRun === (autoSnapshot.run || {}).run_id;
  stream.scrollTop = live ? stream.scrollHeight : 0;
}

function renderAutoReplay() {
  const stream = document.getElementById('autoReplayStream');
  const title = document.getElementById('autoReplayTitle');
  const meta = document.getElementById('autoReplayMeta');
  if (!stream) return;
  const summary = autoRuns.find(r => r.run_id === autoSelectedRun);
  if (title) title.textContent = summary ? `📜 ${summary.name || summary.chat_id} · ${autoSelectedRun}` : '📜 逐轮回放';
  if (meta) {
    if (summary) {
      const [label] = AUTO_OUTCOME_LABELS[summary.outcome] || [`· ${summary.outcome || '未收尾'}`];
      meta.className = 'badge pink';
      meta.textContent = `${label} · ${summary.events || autoEvents.length} 个事件`;
    } else {
      meta.className = 'badge';
      meta.textContent = '未选择';
    }
  }

  const allowed = autoKindFilter === 'all' ? null : (AUTO_KIND_GROUPS[autoKindFilter] || []);
  const events = allowed ? autoEvents.filter(ev => allowed.includes(ev.kind)) : autoEvents;
  if (!events.length) {
    stream.innerHTML = '<div class="auto-empty">这个筛选下没有事件</div>';
    return;
  }
  stream.innerHTML = events.map(autoEventCard).join('');
}

function autoEventHead(ev, kindLabel) {
  return `<div class="auto-ev-head">
      <span class="auto-ev-kind">${esc(kindLabel)}</span>
      <span>${esc(ev.ts || '')}</span>
    </div>`;
}

function autoToolRows(calls, tools) {
  const rows = [];
  const callList = Array.isArray(calls) ? calls : [];
  const resultList = Array.isArray(tools) ? tools : [];
  const count = Math.max(callList.length, resultList.length);
  for (let i = 0; i < count; i += 1) {
    const call = callList[i] || {};
    const result = resultList[i] || {};
    const name = call.name || result.name || 'tool';
    const ok = resultList.length ? (result.success ? '✅' : '⚠️') : '🔧';
    const args = call.args ? esc(call.args) : '';
    const content = result.content ? esc(result.content) : '';
    rows.push(`
      <div class="auto-tool-row">
        <div class="tr-head"><span>${ok} ${esc(name)}</span>${result.name && call.name && result.name !== call.name ? `<span class="muted">→ ${esc(result.name)}</span>` : ''}</div>
        ${content ? `<div class="tr-body">${content}</div>` : ''}
        ${args ? `<details><summary>参数</summary><div class="tr-body">${args}</div></details>` : ''}
      </div>`);
  }
  return rows.length ? `<div class="auto-ev-tools">${rows.join('')}</div>` : '';
}

function autoEventCard(ev) {
  const kind = ev.kind || '';
  let label = kind;
  let body = '';

  if (kind === 'gate') {
    label = '准入判定';
    body = `触发方式 <b>${esc(ev.trigger || '')}</b> · 群 <b>${esc(ev.chat_label || ev.chat_id || '')}</b><br/>判定：${esc(ev.reason || '')}`;
  } else if (kind === 'run_start') {
    label = '开跑';
    body = `模式 <b>${esc(ev.mode || '')}</b> · run_id <b>${esc(ev.run_id || '')}</b>`;
  } else if (kind === 'debate_start') {
    label = '交锋开始';
    const seeds = Array.isArray(ev.seeds) ? ev.seeds.join(' / ') : '';
    body = `上限 <b>${ev.rounds_limit ?? '-'}</b> 轮${seeds ? ` · 日记契机：${esc(seeds)}` : ''}`;
  } else if (kind === 'debate_step') {
    label = `交锋 · 念头 ${ev.role || '?'}`;
    body = esc(ev.content || '（空）');
    if (ev.narration) body += `<div class="auto-ev-narration">🫧 压力旁白：${esc(ev.narration)}</div>`;
    body += autoToolRows(ev.calls, ev.tools);
  } else if (kind === 'vote') {
    label = '投票';
    body = `<div class="auto-vote-line">
        <span class="vflag ${ev.agree ? '' : 'no'}">${ev.agree ? '✅ agree_to_end' : '✋ 继续'}</span>
        <span>verdict <b>${esc(ev.verdict || '')}</b></span>
        ${ev.role ? `<span class="mini-tag purple">念头 ${esc(ev.role)}</span>` : ''}
        ${ev.step ? `<span class="muted">第 ${ev.step} 步</span>` : ''}
      </div>${ev.note ? `<div class="auto-ev-body">${esc(ev.note)}</div>` : ''}`;
  } else if (kind === 'debate_finish') {
    label = '交锋收尾';
    body = `stopped <b>${esc(ev.stopped || '-')}</b> · verdict <b>${esc(ev.verdict || '-')}</b> · rounds <b>${ev.rounds ?? '-'}</b>${ev.note ? `<br/>${esc(ev.note)}` : ''}`;
  } else if (kind === 'phase') {
    label = '阶段切换';
    body = `进入 <b>${esc(ev.phase || '')}</b>${ev.verdict ? ` · 交锋结论 ${esc(ev.verdict)}` : ''}${ev.title ? ` · 目标「${esc(ev.title)}」` : ''}${ev.rounds ? ` · 共 ${ev.rounds} 轮` : ''}`;
  } else if (kind === 'reflection') {
    label = '本尊复盘';
    const action = ev.action || '';
    const actionCls = action === 'start_work' ? 'mint' : (action === 'memo_only' ? 'cyan' : 'muted');
    const parts = [`<span class="mini-tag ${actionCls}">${esc(action || '?')}</span>`];
    if (ev.title) parts.push(`<b>${esc(ev.title)}</b>`);
    body = `<div class="auto-ev-body" style="margin-top:0">${parts.join(' ')}</div>`;
    if (ev.memo) body += `<div class="auto-ev-body">📝 备忘录：${esc(ev.memo)}</div>`;
    if (ev.work_diary_entry) body += `<div class="auto-ev-body">📔 工作日记：${esc(ev.work_diary_entry)}</div>`;
    if (ev.notebook_pointer) body += `<div class="auto-ev-body">🗺️ 小本本计划：${esc(ev.notebook_pointer)}</div>`;
  } else if (kind === 'workshop_start') {
    label = '工坊开张';
    body = `会话 <b>${esc(ev.session_id || '')}</b> · 目标「${esc(ev.goal || '')}」${ev.resume_hint ? `<div class="auto-ev-body">↩️ 接续上次：${esc(ev.resume_hint)}</div>` : ''}`;
  } else if (kind === 'workshop_step') {
    label = `工坊 · 第 ${ev.step ?? '?'} 步`;
    body = esc(ev.content || '（空）');
    if (ev.tool_calls_count) body += `<div class="muted" style="font-size:11px">累计工具 ${ev.tool_calls_count} 次</div>`;
    body += autoToolRows(ev.calls, ev.tools);
  } else if (kind === 'workshop_finish') {
    label = '工坊收尾';
    body = `状态 <b>${esc(ev.status || '')}</b> · ${ev.steps ?? 0} 步 · 工具 ${ev.tool_calls ?? 0} 次`;
    if (ev.work_log) body += `<div class="auto-ev-body">🗒️ 工作日志：${esc(ev.work_log)}</div>`;
    if (Array.isArray(ev.artifacts) && ev.artifacts.length) {
      body += `<div class="auto-ev-tools">${ev.artifacts.map(a => `<span class="auto-artifact">${esc(a)}</span>`).join(' ')}</div>`;
    }
  } else if (kind === 'run_finish') {
    const [labelText, cls] = AUTO_OUTCOME_LABELS[ev.outcome] || [`· ${ev.outcome || '未收尾'}`, ''];
    label = '收尾';
    body = `<span class="badge ${cls}">${esc(labelText)}</span> outcome <b>${esc(ev.outcome || '')}</b>`;
    if (ev.session_id) body += ` · 会话 <b>${esc(ev.session_id)}</b>`;
    if (ev.high_spirits) body += ' · <span class="mini-tag">💗 回群高涨</span>';
    if (ev.summary) body += `<div class="auto-ev-body">${esc(ev.summary)}</div>`;
    if (ev.work_log) body += `<div class="auto-ev-body">🗒️ ${esc(ev.work_log)}</div>`;
  } else {
    const rest = Object.entries(ev)
      .filter(([k]) => !['ts', 'run_id', 'chat_id', 'kind'].includes(k))
      .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
      .join(' · ');
    body = esc(rest || '（无附加字段）');
  }

  const roleAttr = kind === 'debate_step' ? ` data-role="${esc(ev.role || '')}"` : '';
  return `
    <div class="auto-ev" data-kind="${esc(kind)}"${roleAttr}>
      ${autoEventHead(ev, label)}
      <div class="auto-ev-body">${body}</div>
    </div>`;
}

// ---------------------------------------------------------------- 实时开关
function toggleAutoLive() {
  autoLive = !autoLive;
  const btn = document.getElementById('autoLiveBtn');
  if (btn) {
    btn.className = autoLive ? 'btn soft-active' : 'btn';
    btn.textContent = autoLive ? '🛰️ 实时跟随: 开启' : '⏸️ 实时跟随: 关闭';
  }
  if (autoLive) refreshAutonomous(false);
}
