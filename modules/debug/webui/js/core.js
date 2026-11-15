const INITIAL_TAB = (() => {
  const p = window.location.pathname;
  if (p.startsWith('/phone')) return 'phone';
  if (p.startsWith('/analytics')) return 'analytics';
  if (p.startsWith('/autonomous')) return 'autonomous';
  return 'context';
})();

const stages = [
  'prepare_message_batch',
  'normalize_incoming_content',
  'prepare_chat_context',
  'retrieve_memories',
  'decide_reply_action',
  'generate_reply',
  'send_reply',
  'finalize_conversation'
];

const stageShortLabels = {
  prepare_message_batch: '1.读缓冲',
  normalize_incoming_content: '2.归一化',
  prepare_chat_context: '3.载上下文',
  retrieve_memories: '4.RAG回忆',
  decide_reply_action: '5.回复决策',
  generate_reply: '6.LLM生成',
  send_reply: '7.分段发送',
  finalize_conversation: '8.收尾保存'
};

let activeTab = INITIAL_TAB;
let selectedId = null;
let current = null;
let snapshotList = [];
let paused = false;
let sessFilter = 'all';
let msgRoleFilter = 'all';
let analyticsData = null;

// 手机监控状态
let selectedSessionId = null;
let selectedStepIndex = null;
let currentSession = null;
let followLatest = true;
let liveEnabled = true;
let showAnnotated = true;
let liveBusy = false;
let rawTreeCache = '';

function esc(s) {
  return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

function fmtMs(ms) {
  const n = Number(ms || 0);
  return n >= 1000 ? (n / 1000).toFixed(2) + 's (' + Math.round(n) + 'ms)' : Math.round(n) + 'ms';
}

function showToast(msg = '✨ 已复制到剪贴板') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
}

async function api(path) {
  const r = await fetch(path);
  return await r.json();
}

function switchTab(tab, pushUrl = true) {
  activeTab = tab;
  ['context', 'analytics', 'phone', 'autonomous'].forEach(k => {
    document.getElementById('tabBtn-' + k)?.classList.toggle('active', k === tab);
    document.getElementById('pane-' + k)?.classList.toggle('active', k === tab);
  });
  if (pushUrl && window.history && window.history.replaceState) {
    const targetPath = tab === 'phone' ? '/phone'
      : (tab === 'analytics' ? '/analytics'
      : (tab === 'autonomous' ? '/autonomous' : '/'));
    if (window.location.pathname !== targetPath) {
      window.history.replaceState({ tab }, '', targetPath);
    }
  }
  if (tab === 'analytics') refreshAnalytics();
  if (tab === 'phone') {
    refreshLiveImage(true);
    refreshPhoneData();
  }
  if (tab === 'autonomous') refreshAutonomous(false);
}

function openModal(src) {
  if (!src) return;
  document.getElementById('modalImg').src = src;
  document.getElementById('imgModal').style.display = 'flex';
}

function openHelpPoster() {
  openModal('/assets/yuki_help.png');
}

function copyText(id) {
  const el = document.getElementById(id);
  if (el) {
    navigator.clipboard.writeText(el.textContent || '');
    showToast('✨ 已复制文本');
  }
}

function copyField(field) {
  if (!current) return;
  navigator.clipboard.writeText(String(current[field] || ''));
  showToast('✨ 已复制内容');
}

function formatWithMemeBadges(text) {
  if (!text) return '<span class="muted">（无内容）</span>';
  const safe = esc(text);
  return safe.replace(/\[MEME:([^\]]+)\]/g, '<span class="meme-tag">🎀 表情包: $1</span>');
}

// ==================== 顶部状态条与头像渲染 ====================
let avatarLoadedQQ = '';
function renderTopBrainRibbon(status, yukiState) {
  const ys = yukiState || status?.yuki_state || {};
  const bio = ys.bioclock || {};
  const groups = ys.groups || [];

  if (ys.self_qq && ys.self_qq !== avatarLoadedQQ) {
    avatarLoadedQQ = ys.self_qq;
    const box = document.getElementById('yukiAvatarBox');
    const img = new Image();
    img.onload = () => { box.innerHTML = ''; box.appendChild(img); };
    img.src = `https://q1.qlogo.cn/g?b=qq&nk=${encodeURIComponent(ys.self_qq)}&s=640`;
  }

  document.getElementById('status').innerHTML = `
    <span class="status-pill"><i class="dot"></i>Online</span>
    <span class="status-pill">🕒 ${esc(status?.generated_at || '')}</span>
    <span class="status-pill">📸 快照 <b>${status?.snapshot_count || 0}</b></span>
    ${ys.llm_model ? `<span class="status-pill">🤖 模型 <b>${esc(ys.llm_model)}</b></span>` : ''}
    ${(ys.phone_focused_chats || []).length ? `<span class="status-pill"><i class="dot pink"></i>📱 手机聚焦中: <b>${esc(ys.phone_focused_chats.join(','))}</b></span>` : ''}
  `;

  document.getElementById('ribbonBioclock').innerHTML = `
    <span class="status-pill" onclick="switchTab('analytics')" style="cursor:pointer">
      <i class="dot pink"></i>
      <span>${esc(bio.phase_label || '🌸 日常态')}</span>
      <b>${bio.current_weight ?? 1.0}x</b>
    </span>
    ${Object.keys(ys.maid_tasks || {}).length ? `<span class="status-pill"><i class="dot warn"></i>🧹 小女仆执勤中 (${Object.keys(ys.maid_tasks).length})</span>` : ''}
  `;

  document.getElementById('ribbonGroups').innerHTML = groups.slice(0, 6).map(g => `
    <div class="group-mini" onclick="filterByChatId('${esc(g.chat_id)}')" title="点击筛选群 ${esc(g.chat_id)} | 精力 ${g.energy}/${g.max_energy} | 活跃度 ${g.activity} | 说话欲望 ${g.desire}%">
      <b>${g.sleeping ? '💤' : '⚡'} ${esc(g.chat_id)}</b>
      <div class="mini-bar"><div class="mini-bar-fill" style="width:${g.energy_pct}%"></div></div>
      <span style="color:var(--berry);font-weight:700">${g.energy}</span>
      <span class="muted">🔥${g.activity}</span>
      <span class="muted">💗${g.desire}%</span>
    </div>
  `).join('');
}

function filterByChatId(cid) {
  switchTab('context');
  const input = document.getElementById('sessSearch');
  input.value = cid;
  renderSessions();
}
