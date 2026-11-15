// ==================== TAB 3: PHONE MONITOR 逻辑 ====================
function toggleFollow() {
  followLatest = !followLatest;
  const btn = document.getElementById('followBtn');
  btn.className = followLatest ? 'btn soft-active' : 'btn';
  btn.textContent = followLatest ? '🎯 自动跟随最新步' : '📌 已锁定当前步';
  if (followLatest) refreshPhoneData();
}

function toggleLive() {
  liveEnabled = !liveEnabled;
  const btn = document.getElementById('liveBtn');
  btn.className = liveEnabled ? 'btn soft-active' : 'btn';
  btn.textContent = liveEnabled ? '🟢 实时画面流: 开启' : '⏸️ 实时画面流: 暂停';
}

function toggleStepImgMode() {
  showAnnotated = !showAnnotated;
  document.getElementById('viewModeBtn').textContent = showAnnotated ? '切换: 红框标注图' : '切换: 无框原图';
  renderSelectedStep();
}

function refreshLiveImage(force = false) {
  if (activeTab !== 'phone' && !force) return;
  if (liveBusy && !force) return;
  liveBusy = true;
  const img = document.getElementById('liveImg');
  const t0 = performance.now();
  const url = '/api/phone/live.jpg?t=' + Date.now() + (force ? '&force=1' : '');
  const loader = new Image();
  loader.onload = () => {
    img.src = url;
    const cost = Math.round(performance.now() - t0);
    document.getElementById('liveMeta').textContent = '实时帧 ' + cost + 'ms';
    liveBusy = false;
  };
  loader.onerror = () => {
    document.getElementById('liveMeta').textContent = '设备未就绪或抓屏失败';
    liveBusy = false;
  };
  loader.src = url;
}

async function refreshPhoneData() {
  try {
    const [status, sessions] = await Promise.all([
      api('/api/phone/status'),
      api('/api/phone/sessions?limit=60')
    ]);
    document.getElementById('navPhoneCount').textContent = status.session_count || sessions.length || 0;
    const activeChats = Object.keys(status.active_chats || {});
    document.getElementById('statusPills').innerHTML = `
      <span class="status-pill"><i class="dot ${status.live_error ? 'warn' : ''}"></i>${status.live_error ? 'ADB: ' + esc(status.live_error) : 'ADB 实时在线'}</span>
      <span class="status-pill">聚焦中会话: <b>${activeChats.length ? esc(activeChats.join(',')) : '无'}</b></span>
      <span class="status-pill">历史轨迹数: <b>${status.session_count || 0}</b></span>
      <span class="status-pill">刷新: ${esc(status.generated_at || '')}</span>
    `;
    document.getElementById('sessCount').textContent = `${sessions.length} 条`;

    if ((followLatest && status.latest_session_id) || (!selectedSessionId && sessions.length)) {
      selectedSessionId = (followLatest && status.latest_session_id) ? status.latest_session_id : sessions[0].session_id;
    }

    renderSessionList(sessions);

    if (selectedSessionId) {
      const detail = await api('/api/phone/sessions/' + encodeURIComponent(selectedSessionId));
      if (detail && detail.session_id) {
        currentSession = detail;
        const steps = currentSession.steps || [];
        if (followLatest || !selectedStepIndex || selectedStepIndex > steps.length) {
          selectedStepIndex = steps.length ? steps[steps.length - 1].step_index : null;
        }
        renderStepList();
        renderSelectedStep();
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function renderSessionList(sessions) {
  const el = document.getElementById('sessionList');
  if (!sessions.length) {
    el.innerHTML = '<div class="empty">暂无手机操作轨迹</div>';
    return;
  }
  el.innerHTML = sessions.map(s => `
    <div class="item ${s.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${esc(s.session_id)}')">
      <div class="item-head">
        <b>${esc(s.goal || '手机操作')}</b>
        <span class="badge ${s.status === 'running' ? 'running' : 'finished'}">${esc(s.status)}</span>
      </div>
      <div class="sub">chat: ${esc(s.chat_id)} · ${s.step_count || 0} 步 · 总耗时 ${fmtMs(s.total_elapsed_ms)}</div>
      <div class="sub">${esc(s.updated_at || s.created_at || '')}</div>
    </div>
  `).join('');
}

async function selectSession(sid) {
  selectedSessionId = sid;
  selectedStepIndex = null;
  followLatest = false;
  document.getElementById('followBtn').className = 'btn';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  await refreshPhoneData();
}

function selectStep(idx) {
  selectedStepIndex = idx;
  followLatest = false;
  document.getElementById('followBtn').className = 'btn';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  renderStepList();
  renderSelectedStep();
}

function stepDelta(delta) {
  if (!currentSession || !(currentSession.steps || []).length) return;
  const total = currentSession.steps.length;
  const cur = selectedStepIndex || total;
  const next = Math.max(1, Math.min(total, cur + delta));
  selectStep(next);
}

function renderStepList() {
  const el = document.getElementById('stepList');
  const steps = (currentSession && currentSession.steps) || [];
  if (!steps.length) {
    el.innerHTML = '<div class="empty">该会话暂无步骤记录</div>';
    return;
  }
  el.innerHTML = steps.map(st => `
    <div class="item ${st.step_index === selectedStepIndex ? 'active' : ''}" onclick="selectStep(${st.step_index})">
      <div class="item-head">
        <b>#${st.step_index} ${esc(st.step_display || st.action)}</b>
        <span class="badge ${st.success ? 'time' : 'err'}">${fmtMs(st.elapsed_ms)}</span>
      </div>
      <div class="sub">${esc(st.note || '')}</div>
      <div class="sub">${esc(st.package || '未知包名')} · 节点 ${st.node_count || 0} · ${esc(st.timestamp || '')}</div>
    </div>
  `).join('');
}

function renderSelectedStep() {
  if (!currentSession) return;
  const steps = currentSession.steps || [];
  const step = steps.find(s => s.step_index === selectedStepIndex) || steps[steps.length - 1];

  const incomingList = (currentSession.incoming_messages || []).map(m => `[${m.time}] ${m.text}`).join('\n---\n');
  const stepIncoming = step ? (step.user_incoming_text || '') : '';
  document.getElementById('userIncomingText').textContent =
    incomingList || stepIncoming || currentSession.last_incoming_text || '暂无';

  if (!step) {
    document.getElementById('yukiReplyText').textContent = currentSession.last_final_reply || '暂无';
    rawTreeCache = '暂无步骤';
    renderTreeText();
    return;
  }

  document.getElementById('stepScreenTitle').textContent =
    `👁️ 第 #${step.step_index} 步 Yuki 视角 (${step.action})`;
  document.getElementById('stepElapsedBadge').textContent = fmtMs(step.elapsed_ms);

  const imgUrl = showAnnotated ? (step.yuki_image_url || step.raw_image_url) : (step.raw_image_url || step.yuki_image_url);
  const yukiImg = document.getElementById('yukiImg');
  if (imgUrl) {
    yukiImg.src = imgUrl;
  } else {
    yukiImg.removeAttribute('src');
  }

  const tb = step.timing_breakdown || {};
  const parts = [
    { key: 'dump_before_ms', label: '动作前Dump', color: '#9b5de5' },
    { key: 'exec_ms', label: 'ADB执行', color: '#ff4785' },
    { key: 'wait_ms', label: '等待稳定', color: '#f59e0b' },
    { key: 'dump_after_ms', label: '动作后Dump', color: '#00b4d8' },
    { key: 'screenshot_ms', label: '截图+标注', color: '#10b981' }
  ];
  const chips = [`<span class="timing-chip"><b>总用时</b>: ${fmtMs(step.elapsed_ms)}</span>`];
  const totalParts = parts.reduce((acc, p) => acc + (Number(tb[p.key]) || 0), 0) || 1;
  const segHtml = parts.map(p => {
    const v = tb[p.key];
    if (v == null) return '';
    chips.push(`<span class="timing-chip"><b style="color:${p.color}">●</b> ${p.label}: ${v}ms</span>`);
    const pct = Math.max(2, Math.round((Number(v) / totalParts) * 100));
    return `<div style="width:${pct}%;background:${p.color}" title="${p.label}: ${v}ms"></div>`;
  }).join('');

  document.getElementById('stepTimingSegBar').innerHTML = segHtml;
  document.getElementById('stepTimingBar').innerHTML = chips.join('');

  const replyParts = [];
  if (step.yuki_replied_text) {
    replyParts.push(`【第 #${step.step_index} 步模型思考 & 调用原文】\n${step.yuki_replied_text}`);
  }
  if (step.yuki_final_reply || currentSession.last_final_reply) {
    replyParts.push(`【本轮最终回复原文】\n${step.yuki_final_reply || currentSession.last_final_reply}`);
  }
  if (currentSession.summary) {
    replyParts.push(`【聚焦退出总结】\n${currentSession.summary}`);
  }
  document.getElementById('yukiReplyText').textContent = replyParts.join('\n\n====================\n\n') || '（本步无附加文本）';

  rawTreeCache = step.yuki_received_text || '暂无';
  renderTreeText();
}

function renderTreeText() {
  const q = (document.getElementById('treeSearchInput')?.value || '').trim().toLowerCase();
  const el = document.getElementById('toolResultText');
  if (!q) {
    el.textContent = rawTreeCache;
    return;
  }
  const lines = String(rawTreeCache).split('\n');
  const matched = lines.filter(l => l.toLowerCase().includes(q));
  el.textContent = matched.length ? matched.join('\n') : `（未找到包含 "${q}" 的控件节点）`;
}
