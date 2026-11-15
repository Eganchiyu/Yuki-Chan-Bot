// ==================== TAB 1: CONTEXT STUDIO 逻辑 ====================
async function refreshAll() {
  try {
    const [status, list] = await Promise.all([
      api('/api/status'),
      api('/api/snapshots?limit=100')
    ]);
    snapshotList = Array.isArray(list) ? list : [];
    document.getElementById('navSnapCount').textContent = status.snapshot_count || snapshotList.length;
    renderTopBrainRibbon(status, status.yuki_state);
    renderSessions();

    if (!selectedId && status.latest_snapshot_id) {
      selectedId = status.latest_snapshot_id;
    }

    if (selectedId) {
      const freshData = await api('/api/snapshots/' + encodeURIComponent(selectedId));
      if (freshData && freshData.snapshot_id) {
        if (!current || current.snapshot_id !== freshData.snapshot_id || current.updated_at !== freshData.updated_at) {
          current = freshData;
          renderSnapshot();
        }
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function setSessFilter(f, btn) {
  sessFilter = f;
  btn.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c === btn));
  renderSessions();
}

function decisionBadge(x) {
  if (x.errors && x.errors.length) return '<span class="badge err">⚠️ 异常</span>';
  if (x.skip_reply) return '<span class="badge skip">⏭️ Skip安静</span>';
  if (x.should_reply === false) return '<span class="badge dived">🫧 潜水</span>';
  if (x.should_reply === true) return '<span class="badge replied">💬 已回复</span>';
  return '<span class="badge cyan">⚡ 处理中</span>';
}

function renderSessions() {
  const q = (document.getElementById('sessSearch')?.value || '').trim().toLowerCase();
  const filtered = snapshotList.filter(x => {
    if (sessFilter === 'replied' && (x.should_reply !== true || x.skip_reply)) return false;
    if (sessFilter === 'dived' && (x.should_reply !== false && !x.skip_reply)) return false;
    if (sessFilter === 'tools' && !(x.tools_used && x.tools_used.length)) return false;
    if (sessFilter === 'group' && x.mode !== 'group') return false;
    if (sessFilter === 'private' && x.mode === 'group') return false;
    if (q) {
      const hay = `${x.chat_id || ''} ${x.combined_text_preview || ''} ${x.answer_text_preview || ''} ${(x.senders || []).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  document.getElementById('filteredSnapCount').textContent = `${filtered.length} 条`;
  const el = document.getElementById('sessions');
  if (!filtered.length) {
    el.innerHTML = '<div class="empty">🌸 没有匹配的会话快照</div>';
    return;
  }

  el.innerHTML = filtered.map(x => {
    const modeIcon = x.mode === 'group' ? '👥' : '💌';
    const timeShort = String(x.updated_at || x.created_at || '').split(' ').pop();
    const latStr = x.latency_total != null ? `${Number(x.latency_total).toFixed(2)}s` : '-';
    const toolsTag = (x.tools_used && x.tools_used.length) ? `<span>🔧 ${x.tools_used.length}</span>` : '';
    return `
      <div class="sess-card ${x.snapshot_id === selectedId ? 'active' : ''}" onclick="selectSnapshot('${esc(x.snapshot_id)}')">
        <div class="sess-head">
          <span class="sess-chat">${modeIcon} ${esc(x.chat_id || '-')}</span>
          ${decisionBadge(x)}
        </div>
        <div class="sess-in">${esc(x.combined_text_preview || '（空消息）')}</div>
        ${x.answer_text_preview ? `<div class="sess-out">🎀 ${esc(x.answer_text_preview)}</div>` : ''}
        <div class="sess-meta">
          <span>⏱️ ${latStr}</span>
          <span>🪙 ${x.estimated_tokens || 0}</span>
          ${x.rag_count ? `<span>📚 RAG ${x.rag_count}</span>` : ''}
          ${toolsTag}
          <span style="margin-left:auto">${esc(timeShort)}</span>
        </div>
      </div>
    `;
  }).join('');
}

async function selectSnapshot(id) {
  selectedId = id;
  current = null;
  renderSessions();
  await refreshAll();
}

function renderSnapshot() {
  if (!current) return;
  document.getElementById('snapshotJson').textContent = JSON.stringify(current, null, 2);

  // 1) 顶部速览卡
  const modeLabel = current.mode === 'group' ? '👥 群聊' : (current.mode === 'master_private' ? '👑 主人私聊' : '💌 私聊');
  const senders = (current.senders || []).length ? ` · 来自: ${current.senders.join(', ')}` : '';
  document.getElementById('turnHeroTitle').innerHTML = `
    🎀 会话 <b>${esc(current.chat_id || '-')}</b> (${modeLabel})
    <span class="muted" style="font-weight:500;font-size:12px">${esc(current.updated_at || '')}${esc(senders)}</span>
  `;
  document.getElementById('turnSenderLabel').innerHTML = `
    📥 收到消息 ${current.native_image_count ? `<span class="badge cyan">🖼️ 附图 ${current.native_image_count}</span>` : ''}
  `;
  document.getElementById('turnIncomingBox').innerHTML = current.combined_text
    ? esc(current.combined_text)
    : '<span class="muted">（本轮无输入文本）</span>';

  const latTotal = current.latency?.total != null ? `${Number(current.latency.total).toFixed(2)}s` : '-';
  document.getElementById('turnDecisionBridge').innerHTML = `
    ${decisionBadge(current)}
    <span class="badge pink">⏱️ 总耗时 ${latTotal}</span>
    ${current.energy != null ? `<span class="muted" style="font-size:11px">⚡精力 ${current.energy} · 🔥${current.activity ?? 0}</span>` : ''}
    ${current.rag_interest != null ? `<span class="muted" style="font-size:11px">🧠语义分 ${(current.rag_interest * 100).toFixed(0)}%</span>` : ''}
  `;

  if (current.skip_reply) {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">⏭️ 模型调用了 skip 工具，本轮主动保持安静喵～</span>';
  } else if (current.should_reply === false) {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">🫧 群聊潜水判定未触发回复，Yuki 静静观察中～</span>';
  } else if (current.answer_text) {
    document.getElementById('turnAnswerBox').innerHTML = formatWithMemeBadges(current.answer_text);
  } else {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">（尚未生成或无可见文本）</span>';
  }

  // 2) 工具调用链追踪
  const trace = current.tool_trace || [];
  const traceWrap = document.getElementById('toolTraceWrap');
  if (trace.length > 1 || (trace.length === 1 && (trace[0].calls || []).length)) {
    traceWrap.style.display = 'block';
    traceWrap.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b style="font-size:13px;color:#b45309">🔧 本轮 LLM 思考与工具调用链 (共 ${trace.length} 轮)</b>
        <span class="badge skip">调用工具: ${esc((current.tools_used || []).join(', ') || '无')}</span>
      </div>
      ${trace.map(r => `
        <div class="tool-round-item">
          <div style="display:flex;justify-content:space-between;font-weight:700;margin-bottom:3px">
            <span>Round #${r.round}</span>
            <span class="muted">LLM ${r.llm_ms || 0}ms ${r.exec_ms ? `· 工具执行 ${r.exec_ms}ms` : ''}</span>
          </div>
          ${r.thought ? `<div style="color:var(--text-sec);margin-bottom:4px">💭 ${esc(r.thought)}</div>` : ''}
          ${(r.calls || []).map(c => `<div style="font-family:monospace;color:var(--berry)">⚡ <b>${esc(c.name)}</b>(${esc(c.args)})</div>`).join('')}
        </div>
      `).join('')}
    `;
  } else {
    traceWrap.style.display = 'none';
  }

  renderTimeline();
  renderMessagesList();
  renderTokenBreakdown();
  renderMemories();
}

function setMsgRoleFilter(role, btn) {
  msgRoleFilter = role;
  btn.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c === btn));
  renderMessagesList();
}

function toggleAllMessages(openState) {
  document.querySelectorAll('#messages details.msg-card').forEach(d => { d.open = openState; });
}

function renderMessagesList() {
  const messages = (current && current.built_messages) || [];
  const q = (document.getElementById('msgSearchInput')?.value || '').trim().toLowerCase();
  const container = document.getElementById('messages');

  if (!messages.length) {
    container.className = 'messages-stream empty';
    container.innerHTML = '🌸 暂无完整 messages（如群聊潜水轮次在进入 LLM 前已结束）';
    return;
  }

  const total = messages.length;
  const filtered = messages.map((m, idx) => ({ m, idx })).filter(({ m }) => {
    const role = m.role || 'unknown';
    if (msgRoleFilter !== 'all' && role !== msgRoleFilter) return false;
    if (q) {
      const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
      if (!c.toLowerCase().includes(q) && !(m.name || '').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  container.className = filtered.length ? 'messages-stream' : 'messages-stream empty';
  if (!filtered.length) {
    container.innerHTML = '没有匹配的上下文消息';
    return;
  }

  container.innerHTML = filtered.map(({ m, idx }) => {
    const role = String(m.role || 'unknown');
    const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);
    const tok = Math.max(1, Math.floor(c.length / 2));
    // 默认折叠超长 system prompt，展开最后 6 条对话消息
    const shouldOpen = q ? true : (role !== 'system' && idx >= Math.max(0, total - 6));
    const snippet = c.replace(/\s+/g, ' ').slice(0, 95);
    const toolLabel = m.name ? `<span class="badge skip">${esc(m.name)}</span>` : '';
    return `
      <details class="msg-card role-${esc(role)}" ${shouldOpen ? 'open' : ''}>
        <summary>
          <div class="msg-sum-left">
            <span class="role-pill ${esc(role)}">${esc(role)}</span>
            ${toolLabel}
            <span class="muted">#${idx + 1} · ${c.length} 字 · ≈${tok} tok</span>
            <span class="msg-snippet">${esc(snippet)}</span>
          </div>
          <button class="btn btn-sm" onclick="event.stopPropagation();navigator.clipboard.writeText(${JSON.stringify(c).replace(/"/g, '&quot;')});showToast('✨ 已复制该条消息')">复制</button>
        </summary>
        <div class="msg-content">${esc(c)}</div>
      </details>
    `;
  }).join('');
}

function renderTokenBreakdown() {
  const te = (current && current.token_estimate) || {};
  const total = te.estimated_tokens || 0;
  const byRole = te.by_role || {};
  document.getElementById('totalTokenBadge').textContent = `${total.toLocaleString()} tok`;

  const roles = [
    { key: 'system', label: '🌸 System', color: '#9b5de5' },
    { key: 'user', label: '💧 User', color: '#00b4d8' },
    { key: 'assistant', label: '🍓 Yuki', color: '#ff4785' },
    { key: 'tool', label: '🍯 Tool', color: '#f59e0b' }
  ];

  const rowsHtml = roles.map(r => {
    const val = byRole[r.key] || 0;
    const pct = total > 0 ? Math.round((val / total) * 100) : 0;
    return `
      <div class="token-role-row">
        <span style="font-weight:700;color:var(--text-sec)">${r.label}</span>
        <div class="progress-track">
          <div class="progress-fill" style="width:${pct}%;background:${r.color}"></div>
        </div>
        <span style="text-align:right;font-weight:700">${val} <span class="muted">(${pct}%)</span></span>
      </div>
    `;
  }).join('');

  document.getElementById('tokenBreakdownBox').innerHTML = rowsHtml;
}

function renderMemories() {
  const diaries = (current && current.relevant_diaries) || [];
  document.getElementById('ragCountBadge').textContent = `${diaries.length} 条`;
  const box = document.getElementById('memories');
  if (!diaries.length) {
    box.innerHTML = '<div class="empty" style="padding:18px">本轮无召回日记</div>';
    return;
  }
  box.innerHTML = diaries.map((d, i) => {
    if (typeof d === 'string') {
      return `<div class="diary-card">${esc(d)}</div>`;
    }
    const score = d.relevance ?? d.score;
    const scoreBadge = score != null ? `<span class="badge pink">相关度 ${(Number(score) * 100).toFixed(1)}%</span>` : '';
    const ts = (d.metadata && d.metadata.timestamp) || d.timestamp || '';
    const content = d.content || d.document || JSON.stringify(d, null, 2);
    return `
      <div class="diary-card">
        <div class="diary-head">
          <span><b>#${i + 1}</b> ${esc(ts)}</span>
          ${scoreBadge}
        </div>
        <div>${esc(content)}</div>
      </div>
    `;
  }).join('');
}

function renderTimeline() {
  const latency = (current && current.latency) || {};
  const curStage = (current && current.stage) || '';
  const errors = (current && current.errors) || [];
  const errStages = new Set(errors.map(e => e.stage));

  document.getElementById('timeline').innerHTML = stages.map(s => {
    const val = latency[s];
    const hasDone = val != null;
    const isErr = errStages.has(s);
    const isActive = curStage === s && !hasDone;
    const cls = isErr ? 'error' : (hasDone ? 'done' : (isActive ? 'active' : ''));
    const timeText = val != null ? (val >= 1 ? `${Number(val).toFixed(2)}s` : `${Math.round(val * 1000)}ms`) : (isActive ? '运行中...' : '—');
    return `
      <div class="stage-node ${cls}" title="${esc(s)}">
        <div class="st-name">${esc(stageShortLabels[s] || s)}</div>
        <div class="st-time">${timeText}</div>
      </div>
    `;
  }).join('');
}
