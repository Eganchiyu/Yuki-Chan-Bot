// ==================== 全局控制与樱花粒子动效 ====================
function togglePause() {
  paused = !paused;
  const btn = document.getElementById('pauseBtn');
  btn.className = paused ? 'btn' : 'btn soft-active';
  btn.textContent = paused ? '⏸️ 自动同步: 已暂停' : '⚡ 自动同步: 开启';
}

function copySnapshot() {
  if (current) {
    navigator.clipboard.writeText(JSON.stringify(current, null, 2));
    showToast('✨ 已复制完整 Snapshot JSON');
  }
}

function downloadSnapshot() {
  if (!current) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], { type: 'application/json' }));
  a.download = (current.snapshot_id || 'snapshot') + '.json';
  a.click();
}

async function refreshEverything(manual = false) {
  await refreshAll();
  if (activeTab === 'analytics' || manual) await refreshAnalytics();
  if (activeTab === 'phone' || manual) await refreshPhoneData();
  if (activeTab === 'autonomous' || manual) await refreshAutonomous(false);
}

document.addEventListener('keydown', e => {
  if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
  if (activeTab === 'phone') {
    if (e.key === 'ArrowLeft') stepDelta(-1);
    if (e.key === 'ArrowRight') stepDelta(1);
  }
  if (e.key === 'Escape') document.getElementById('imgModal').style.display = 'none';
});

// 轻量级樱花星点粒子动画
let petalsEnabled = true;
function togglePetals() {
  petalsEnabled = !petalsEnabled;
  document.getElementById('sakuraCanvas').style.display = petalsEnabled ? 'block' : 'none';
  document.getElementById('petalBtn').className = petalsEnabled ? 'btn soft-active' : 'btn';
}

(function initSakuraCanvas() {
  const canvas = document.getElementById('sakuraCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;
  window.addEventListener('resize', () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });
  const petals = Array.from({ length: 22 }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    r: 3 + Math.random() * 4.5,
    vx: 0.25 + Math.random() * 0.55,
    vy: 0.45 + Math.random() * 0.75,
    angle: Math.random() * Math.PI * 2,
    spin: (Math.random() - 0.5) * 0.02,
    alpha: 0.22 + Math.random() * 0.35
  }));
  function draw() {
    if (petalsEnabled) {
      ctx.clearRect(0, 0, w, h);
      for (const p of petals) {
        p.x += p.vx;
        p.y += p.vy;
        p.angle += p.spin;
        if (p.y > h + 12) { p.y = -10; p.x = Math.random() * w; }
        if (p.x > w + 12) { p.x = -10; }
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.angle);
        ctx.fillStyle = `rgba(255, 117, 168, ${p.alpha})`;
        ctx.beginPath();
        ctx.ellipse(0, 0, p.r, p.r * 0.62, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();

// 启动初始化
switchTab(INITIAL_TAB, false);
refreshEverything(true);
setInterval(() => {
  if (paused) return;
  refreshAll();
  if (activeTab === 'analytics') refreshAnalytics();
  if (activeTab === 'phone') refreshPhoneData();
  if (activeTab === 'autonomous') refreshAutonomous(false);
}, 2000);
setInterval(() => {
  if (!paused && liveEnabled && activeTab === 'phone') refreshLiveImage(false);
}, 1200);
