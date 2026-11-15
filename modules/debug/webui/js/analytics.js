// ==================== TAB 2: ANALYTICS & BRAIN 图表渲染 ====================
async function refreshAnalytics() {
  try {
    analyticsData = await api('/api/analytics');
    if (!analyticsData || !analyticsData.ok) return;
    const dec = analyticsData.decisions || {};
    document.getElementById('navReplyRate').textContent = `${dec.reply_rate ?? 0}%`;

    renderAnalyticsKpis(analyticsData);
    renderBioclockChart(analyticsData.yuki_state?.bioclock);
    renderGroupGauges(analyticsData.yuki_state?.groups || []);
    renderStageWaterfall(analyticsData.latency);
    renderTokenTrendChart(analyticsData.tokens?.recent_series || []);
    renderDecisionAndTools(analyticsData);
  } catch (e) {
    console.error(e);
  }
}

function renderAnalyticsKpis(data) {
  const dec = data.decisions || {};
  const lat = data.latency || {};
  const tok = data.tokens || {};
  const rag = data.rag || {};
  const tools = data.tools || {};
  const phone = data.phone || {};

  document.getElementById('analyticsKpiGrid').innerHTML = `
    <div class="glass kpi-card">
      <div class="kpi-label"><span>💬 累计会话 &amp; 回复率</span><span class="badge pink">${dec.total || 0} 轮</span></div>
      <div class="kpi-val">${dec.reply_rate ?? 0}%</div>
      <div class="kpi-sub">已回 ${dec.replied || 0} · 潜水 ${dec.dived || 0} · Skip ${dec.skipped || 0}</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>⚡ 平均响应耗时</span><span class="badge cyan">P95 ${fmtMs(lat.p95_total_ms)}</span></div>
      <div class="kpi-val">${fmtMs(lat.avg_total_ms)}</div>
      <div class="kpi-sub">端到端管线平均总耗时</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>🪙 平均单轮 Token</span><span class="badge skip">Max ${tok.max_tokens || 0}</span></div>
      <div class="kpi-val">${(tok.avg_tokens || 0).toLocaleString()}</div>
      <div class="kpi-sub">累计估算 ${(tok.total_tokens || 0).toLocaleString()} tok</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>📚 RAG 记忆命中率</span><span class="badge replied">平均 ${rag.avg_recall_count || 0} 条</span></div>
      <div class="kpi-val">${rag.hit_rate ?? 0}%</div>
      <div class="kpi-sub">平均语义兴趣度 ${((rag.avg_interest || 0) * 100).toFixed(1)}%</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>🔧 工具链调用统计</span><span class="badge dived">${tools.total_llm_rounds || 0} LLM轮</span></div>
      <div class="kpi-val">${tools.total_tool_calls || 0}</div>
      <div class="kpi-sub">共 ${tools.turns_with_tools || 0} 轮触发工具调用</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>📱 手机自动化轨迹</span><span class="badge replied">成功率 ${phone.success_rate ?? 100}%</span></div>
      <div class="kpi-val">${phone.total_steps || 0} 步</div>
      <div class="kpi-sub">${phone.session_count || 0} 个会话 · 均步 ${fmtMs(phone.avg_step_ms)}</div>
    </div>
  `;
}

function renderBioclockChart(bio) {
  if (!bio || !bio.curve || !bio.curve.length) return;
  document.getElementById('bioclockPhaseBadge').textContent = `${bio.phase_label || ''} · 当前 ${bio.current_weight}x (${bio.now_hour}h)`;

  const W = 680, H = 220, padL = 38, padR = 18, padT = 18, padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const minW = 0.15, maxW = 1.55;

  const xOf = h => padL + (h / 24.0) * plotW;
  const yOf = w => padT + plotH - ((w - minW) / (maxW - minW)) * plotH;

  const pts = bio.curve.map(p => `${xOf(p.hour).toFixed(1)},${yOf(p.weight).toFixed(1)}`).join(' ');
  const areaPts = `${xOf(0).toFixed(1)},${(padT + plotH).toFixed(1)} ${pts} ${xOf(24).toFixed(1)},${(padT + plotH).toFixed(1)}`;
  const curX = xOf(bio.now_hour || 0);
  const curY = yOf(bio.current_weight || 1.0);

  const hours = [0, 4, 8, 12, 16, 20, 24];
  document.getElementById('bioclockChartBox').innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="220">
      <defs>
        <linearGradient id="bioGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ff4785" stop-opacity="0.45"/>
          <stop offset="65%" stop-color="#ff85b3" stop-opacity="0.16"/>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      ${[0.3, 0.6, 0.9, 1.2, 1.5].map(v => `
        <line x1="${padL}" y1="${yOf(v)}" x2="${W - padR}" y2="${yOf(v)}" stroke="rgba(255,110,168,0.18)" stroke-dasharray="3,3"/>
        <text x="${padL - 6}" y="${yOf(v) + 4}" text-anchor="end" font-size="10" fill="#a47690">${v}x</text>
      `).join('')}
      ${hours.map(h => `
        <text x="${xOf(h)}" y="${H - 6}" text-anchor="middle" font-size="10.5" fill="#6e445c">${String(h).padStart(2, '0')}:00</text>
      `).join('')}
      <polygon points="${areaPts}" fill="url(#bioGrad)"/>
      <polyline points="${pts}" fill="none" stroke="#ff4785" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="${curX}" y1="${padT}" x2="${curX}" y2="${padT + plotH}" stroke="#9b5de5" stroke-width="1.5" stroke-dasharray="4,3"/>
      <circle cx="${curX}" cy="${curY}" r="6" fill="#ff4785" stroke="#fff" stroke-width="2.5"/>
      <text x="${Math.min(W - 65, Math.max(45, curX))}" y="${Math.max(24, curY - 10)}" text-anchor="middle" font-size="11" font-weight="800" fill="#d61f69">当前 ${bio.current_weight}x</text>
    </svg>
  `;
}

function renderGroupGauges(groups) {
  const el = document.getElementById('groupGaugeGrid');
  if (!groups.length) {
    el.innerHTML = '<div class="empty">暂无群组实时状态</div>';
    return;
  }
  el.innerHTML = groups.map(g => `
    <div class="group-gauge-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <b style="font-size:13.5px">👥 ${esc(g.chat_id)}</b>
        <span class="badge ${g.sleeping ? 'dived' : 'replied'}">${g.sleeping ? '💤 午睡休眠' : '⚡ 元气在线'}</span>
      </div>
      <div style="font-size:11.5px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between"><span>🔋 精力值 (Energy)</span><b>${g.energy} / ${g.max_energy}</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.energy_pct}%;background:var(--grad-primary)"></div></div>
      </div>
      <div style="font-size:11.5px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between"><span>🔥 群聊活跃度 (Activity)</span><b>${g.activity} / 10</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.activity_pct}%;background:#f59e0b"></div></div>
      </div>
      <div style="font-size:11.5px">
        <div style="display:flex;justify-content:space-between"><span>💗 说话/破冰欲望 (Desire)</span><b>${g.desire}%</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.desire}%;background:#9b5de5"></div></div>
      </div>
    </div>
  `).join('');
}

function renderStageWaterfall(lat) {
  const stList = (lat && lat.stages) || [];
  document.getElementById('stageTotalAvgLabel').textContent = `平均总耗时 ${fmtMs(lat?.avg_total_ms)}`;
  const maxAvg = Math.max(1, ...stList.map(s => s.avg_ms || 0));
  document.getElementById('stageWaterfallBox').innerHTML = stList.map(s => {
    const w = Math.max(3, Math.round(((s.avg_ms || 0) / maxAvg) * 100));
    return `
      <div class="waterfall-row">
        <span style="font-weight:700;color:var(--text-sec);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.label)}</span>
        <div class="progress-track" style="height:10px">
          <div class="progress-fill" style="width:${w}%;background:var(--grad-primary)"></div>
        </div>
        <span style="text-align:right;font-weight:700;color:var(--berry)">${fmtMs(s.avg_ms)}</span>
      </div>
    `;
  }).join('');
}

function renderTokenTrendChart(series) {
  const box = document.getElementById('tokenTrendChartBox');
  if (!series.length) {
    box.innerHTML = '<div class="empty">暂无足够快照生成趋势图</div>';
    return;
  }
  const W = 540, H = 220, padL = 42, padR = 12, padT = 16, padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const maxTok = Math.max(100, ...series.map(s => s.total_tokens || 0));
  const barW = Math.max(8, Math.min(22, (plotW / series.length) - 4));

  const bars = series.map((s, i) => {
    const x = padL + (i + 0.5) * (plotW / series.length) - barW / 2;
    const sysH = ((s.system || 0) / maxTok) * plotH;
    const usrH = ((s.user || 0) / maxTok) * plotH;
    const astH = ((s.assistant || 0) / maxTok) * plotH;
    const tolH = ((s.tool || 0) / maxTok) * plotH;
    let curY = padT + plotH;
    const segs = [
      { h: sysH, c: '#9b5de5' },
      { h: usrH, c: '#00b4d8' },
      { h: astH, c: '#ff4785' },
      { h: tolH, c: '#f59e0b' }
    ].map(seg => {
      curY -= seg.h;
      return `<rect x="${x.toFixed(1)}" y="${curY.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(0, seg.h).toFixed(1)}" fill="${seg.c}" rx="2"/>`;
    }).join('');
    return `
      <g style="cursor:pointer" onclick="switchTab('context');selectSnapshot('${esc(s.snapshot_id)}')">
        <title>会话 ${esc(s.chat_id)} (${esc(s.time)}) | 总 Token: ${s.total_tokens} | 耗时: ${s.latency_ms}ms</title>
        ${segs}
      </g>
    `;
  }).join('');

  box.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="220">
      <line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="rgba(255,110,168,0.3)"/>
      <text x="${padL - 5}" y="${padT + 8}" text-anchor="end" font-size="10" fill="#a47690">${maxTok}</text>
      <text x="${padL - 5}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="#a47690">0</text>
      ${bars}
    </svg>
    <div style="display:flex;justify-content:center;gap:14px;font-size:11.5px;color:var(--text-sec)">
      <span><b style="color:#9b5de5">■</b> System</span>
      <span><b style="color:#00b4d8">■</b> User</span>
      <span><b style="color:#ff4785">■</b> Yuki</span>
      <span><b style="color:#f59e0b">■</b> Tool</span>
    </div>
  `;
}

function renderDecisionAndTools(data) {
  const tools = data.tools || {};
  const ranking = tools.ranking || [];
  const chats = data.chats || [];
  document.getElementById('toolTotalCallsLabel').textContent = `${tools.total_tool_calls || 0} 次工具调用`;

  const toolHtml = ranking.length
    ? ranking.slice(0, 5).map(t => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:9px;background:rgba(255,255,255,0.8);border:1px solid var(--line);font-size:12px;margin-bottom:5px">
          <b>🔧 ${esc(t.name)}</b>
          <span class="badge pink">${t.count} 次</span>
        </div>
      `).join('')
    : '<div class="muted" style="font-size:12px;margin-bottom:8px">暂无工具调用记录</div>';

  const chatHtml = chats.length
    ? chats.slice(0, 4).map(c => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:9px;background:rgba(255,255,255,0.8);border:1px solid var(--line);font-size:12px;margin-bottom:5px;cursor:pointer" onclick="filterByChatId('${esc(c.chat_id)}')">
          <span><b>${c.mode === 'group' ? '👥' : '💌'} ${esc(c.chat_id)}</b> (${c.turns}轮)</span>
          <span class="muted">回复率 ${c.reply_rate}% · ${fmtMs(c.avg_latency_ms)}</span>
        </div>
      `).join('')
    : '';

  document.getElementById('decisionAndToolsBox').innerHTML = `
    <div style="margin-bottom:10px">
      <div style="font-size:12px;font-weight:700;color:var(--text-sec);margin-bottom:6px">🛠️ 热门工具排行榜</div>
      ${toolHtml}
    </div>
    <div>
      <div style="font-size:12px;font-weight:700;color:var(--text-sec);margin-bottom:6px">🔥 活跃会话 Top</div>
      ${chatHtml}
    </div>
  `;
}
