// ==UserScript==
// @name         Yuki Desktop Agent - Eye
// @namespace    yuki-agent
// @version      0.5
// @description  扫描页面交互元素，通过 HTTP 轮询与 Yuki 后端通信
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @inject-into  page
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const BACKEND = 'http://127.0.0.1:8766';
  const SCAN_INTERVAL = 3000;
  const POLL_INTERVAL = 1000;  // 每秒轮询一次指令
  const MAX_ELEMENTS = 80;

  let lastScanHash = '';
  let scanThrottle = null;
  let statusBadge = null;

  // ==================== 状态指示器 ====================

  function createStatusBadge() {
    if (statusBadge) return;
    const badge = document.createElement('div');
    badge.style.cssText = `
      position: fixed; top: 8px; right: 8px; z-index: 999999;
      padding: 4px 10px; border-radius: 12px;
      font: bold 11px/1.4 'Consolas','Monaco',monospace;
      color: #fff; background: #666;
      pointer-events: none; opacity: 0.7;
      transition: background 0.3s;
    `;
    badge.textContent = '● YUKI:OFFLINE';
    document.body.appendChild(badge);
    statusBadge = badge;
  }

  function setStatus(color, text) {
    createStatusBadge();
    const colors = { green: '#2d8', red: '#d44', gray: '#666', blue: '#48d' };
    statusBadge.style.background = colors[color] || '#666';
    statusBadge.textContent = '● ' + text;
  }

  // ==================== HTTP 通信 ====================

  function gmPost(path, data) {
    const url = BACKEND + path;
    const body = JSON.stringify(data);

    GM_xmlhttpRequest({
      method: 'POST',
      url: url,
      headers: { 'Content-Type': 'application/json' },
      data: body,
      onload: (res) => {
        console.log('[Yuki-Eye] POST', path, '→', res.status);
      },
      onerror: (err) => {
        console.warn('[Yuki-Eye] POST failed:', err.statusText || 'error');
        setStatus('red', 'YUKI:OFFLINE');
      },
    });
  }

  function gmGet(path, callback) {
    GM_xmlhttpRequest({
      method: 'GET',
      url: BACKEND + path,
      onload: (res) => {
        try {
          const data = JSON.parse(res.responseText);
          callback(data);
        } catch {}
      },
      onerror: () => {
        setStatus('red', 'YUKI:OFFLINE');
      },
    });
  }

  // ==================== 轮询指令 ====================

  function pollCommands() {
    gmGet('/poll', (data) => {
      if (data.type && data.type !== 'noop') {
        console.log('[Yuki-Eye] Poll ←', JSON.stringify(data).slice(0, 200));
        handleCommand(data);
      }
      setStatus('green', 'YUKI:ONLINE');
    });
  }

  // ==================== DOM 扫描 ====================

  function scanElements() {
    const selectors = [
      'a[href]', 'button', 'input', 'select', 'textarea',
      '[role="button"]', '[role="link"]', '[role="tab"]',
      '[role="menuitem"]', '[role="combobox"]', '[role="listbox"]',
      '[onclick]', '[tabindex]:not([tabindex="-1"])',
      '[data-testid]', '[data-cy]', '[data-qa]',
      'summary',
    ].join(', ');

    const candidates = document.querySelectorAll(selectors);
    const elements = [];
    const seen = new Set();

    for (const el of candidates) {
      if (!isVisible(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 4 || rect.height < 4) continue;

      const fp = `${el.tagName}|${(el.innerText||'').slice(0,40).trim()}|${Math.round(rect.x)}|${Math.round(rect.y)}`;
      if (seen.has(fp)) continue;
      seen.add(fp);

      const selector = generateSelector(el);
      if (!selector) continue;

      elements.push({
        id: elements.length,
        tag: el.tagName.toLowerCase(),
        type: el.type || null,
        text: cleanText(el).slice(0, 60),
        placeholder: el.placeholder || null,
        href: el.tagName === 'A' ? (el.href || '').slice(0, 120) : null,
        selector: selector,
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
        state: getElementState(el),
        // 新增：父元素上下文，帮助 LLM 理解匿名元素
        context: getElementContext(el),
      });

      if (elements.length >= MAX_ELEMENTS) break;
    }
    return elements;
  }

  function isVisible(el) {
    if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
      const st = getComputedStyle(el);
      if (st.position !== 'fixed' && st.position !== 'sticky') return false;
    }
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    if (parseFloat(st.opacity) < 0.05) return false;
    return true;
  }

  // 检查类名是否是合法的 CSS 选择器片段
  function isValidClassName(c) {
    // 只允许字母数字下划线连字符，不允许括号方括号等
    return /^[a-zA-Z_-][a-zA-Z0-9_-]*$/.test(c);
  }

  function generateSelector(el) {
    // 1) id
    if (el.id && /^[a-zA-Z][\w-]*$/.test(el.id)) {
      try {
        if (document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
          return '#' + CSS.escape(el.id);
        }
      } catch {}
    }
    // 2) data-testid
    for (const attr of ['data-testid', 'data-cy', 'data-qa']) {
      const val = el.getAttribute(attr);
      if (val) return `[${attr}="${val}"]`;
    }
    // 3) name in form
    if (el.name) {
      try {
        const scope = el.closest('form') || document;
        if (scope.querySelectorAll('[name="' + CSS.escape(el.name) + '"]').length === 1) {
          return el.tagName.toLowerCase() + '[name="' + CSS.escape(el.name) + '"]';
        }
      } catch {}
    }
    // 4) aria-label
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) {
      try {
        const sel = el.tagName.toLowerCase() + '[aria-label="' + CSS.escape(ariaLabel) + '"]';
        if (document.querySelectorAll(sel).length === 1) return sel;
      } catch {}
    }
    // 5) nth-child path（带 try-catch 兜底）
    const path = [];
    let cur = el;
    try {
      while (cur && cur !== document.body && cur !== document.documentElement) {
        let seg = cur.tagName.toLowerCase();
        if (cur.className && typeof cur.className === 'string') {
          const cls = cur.className.trim().split(/\s+/)
            .filter(c => isValidClassName(c) && c.length < 30)
            .slice(0, 2);
          if (cls.length) seg += '.' + cls.join('.');
        }
        const parent = cur.parentElement;
        if (parent) {
          const sibs = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
          if (sibs.length > 1) seg += ':nth-child(' + (sibs.indexOf(cur) + 1) + ')';
        }
        path.unshift(seg);
        const candidate = path.join(' > ');
        if (document.querySelectorAll(candidate).length === 1) break;
        cur = cur.parentElement;
      }
    } catch {}
    return path.join(' > ') || null;
  }

  function getElementState(el) {
    const s = [];
    if (el.disabled) s.push('disabled');
    if (el.readOnly) s.push('readonly');
    if (el === document.activeElement) s.push('focused');
    if (el.checked) s.push('checked');
    return s.length ? s : null;
  }

  /**
   * 获取元素的上下文信息：
   * - 父容器的文本（帮助理解匿名元素在什么区域）
   * - aria / title / alt 等无障碍属性
   * - 附近兄弟元素的文本
   */
  function getElementContext(el) {
    const parts = [];

    // 1) 无障碍属性（优先级最高）
    const ariaLabel = el.getAttribute('aria-label');
    const title = el.getAttribute('title');
    const alt = el.getAttribute('alt');
    if (ariaLabel) parts.push('aria-label="' + ariaLabel + '"');
    if (title) parts.push('title="' + title + '"');
    if (alt) parts.push('alt="' + alt + '"');

    // 2) 最近的有文本的父容器（往上找3层）
    let parent = el.parentElement;
    for (let i = 0; i < 3 && parent && parent !== document.body; i++) {
      const parentText = cleanText(parent);
      if (parentText && parentText.length > 2 && parentText.length < 200) {
        parts.push('in: "' + parentText.slice(0, 120) + '"');
        break;
      }
      parent = parent.parentElement;
    }

    // 3) 前一个兄弟的文本（常见模式：文字 + 按钮）
    const prev = el.previousElementSibling;
    if (prev) {
      const prevText = cleanText(prev);
      if (prevText && prevText.length < 80) {
        parts.push('before: "' + prevText + '"');
      }
    }

    return parts.length > 0 ? parts.join(' | ') : null;
  }

  function cleanText(el) {
    let t = el.innerText || el.value || el.textContent || '';
    t = t.replace(/[\n\r\t]+/g, ' ').replace(/\s+/g, ' ').trim();

    // 如果文本为空，尝试从 SVG 图标推断含义
    if (!t) {
      const svg = el.querySelector('svg') || (el.tagName === 'SVG' ? el : null);
      if (svg) {
        t = identifySvgIcon(svg);
      }
    }

    return t;
  }

  /**
   * 通过 SVG path 的几何特征识别常见图标
   */
  function identifySvgIcon(svg) {
    // 先检查无障碍属性
    const label = svg.getAttribute('aria-label') || svg.getAttribute('title') ||
                  svg.closest('[aria-label]')?.getAttribute('aria-label');
    if (label) return `[${label}]`;

    // 获取所有 path 的 d 属性
    const paths = svg.querySelectorAll('path');
    const allD = Array.from(paths).map(p => p.getAttribute('d') || '').join(' ');

    // 统计特征
    const pathCount = paths.length;
    const hasLine = /[ML]\s*\d/.test(allD);
    const dLen = allD.length;

    // 简单启发式识别
    // X/关闭：通常2条交叉线，path较短
    if (pathCount <= 3 && dLen < 200) {
      // 检查是否有两条近似交叉的线
      const coords = allD.match(/[\d.]+/g)?.map(Number) || [];
      if (coords.length >= 8) {
        // 取前两段的起点终点，看是否形成 X
        const x1 = coords[0], y1 = coords[1];
        const x2 = coords[2], y2 = coords[3];
        const x3 = coords[4], y3 = coords[5];
        const x4 = coords[6], y4 = coords[7];
        // X 形状：两线交叉
        if (Math.abs((x2-x1)*(y4-y3) - (y2-y1)*(x4-x3)) < 500) {
          return '[✕]';
        }
      }
    }

    // 搜索：放大镜通常是圆+线
    if (pathCount <= 3 && dLen < 300 && /a|A/.test(allD)) {
      return '[🔍]';
    }

    // 箭头：通常是三角形或 V 形
    if (pathCount <= 2 && dLen < 150) {
      const coords = allD.match(/[\d.]+/g)?.map(Number) || [];
      if (coords.length >= 6) {
        // 检查是否像箭头（开口三角形）
        const spread = Math.max(...coords.filter((_, i) => i % 2 === 0)) -
                       Math.min(...coords.filter((_, i) => i % 2 === 0));
        if (spread > 10 && spread < 50) return '[→]';
      }
    }

    // 菜单（三条横线）
    if (pathCount === 3 && dLen < 300) {
      return '[☰]';
    }

    // 无法识别
    return `[icon:${pathCount}p]`;
  }

  // ==================== 快照 ====================

  function buildSnapshot(trigger) {
    const elements = scanElements();
    const hash = JSON.stringify(elements.map(e => e.selector));
    if (trigger !== 'forced' && hash === lastScanHash) return null;
    lastScanHash = hash;

    return {
      type: 'page_state',
      trigger: trigger,
      url: location.href,
      title: document.title,
      timestamp: Date.now(),
      element_count: elements.length,
      elements: elements,
    };
  }

  // ==================== 动作执行 ====================

  function handleCommand(msg) {
    switch (msg.type) {
      case 'scan':
        triggerScan('manual');
        break;
      case 'action':
        executeAction(msg.action).then(ok => {
          if (ok) setTimeout(() => triggerScan('post_action'), 600);
        });
        break;
      case 'action_sequence':
        executeSequence(msg.actions);
        break;
    }
  }

  async function executeAction(action) {
    const el = resolveTarget(action.target);
    if (!el) {
      gmPost('/action_result', { ok: false, action: action.action, error: 'Element not found' });
      return false;
    }

    try {
      switch (action.action) {
        case 'click': {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          await sleep(250);
          el.focus();
          el.click();
          const rect = el.getBoundingClientRect();
          el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }));
          el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }));
          break;
        }
        case 'type':
          el.focus();
          el.value = '';
          for (const ch of action.text) {
            el.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true }));
            el.value += ch;
            el.dispatchEvent(new InputEvent('input', { data: ch, inputType: 'insertText', bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup', { key: ch, bubbles: true }));
            await sleep(20 + Math.random() * 40);
          }
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'clear':
          el.focus();
          el.value = '';
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'select':
          el.value = action.value;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'scroll':
          (action.target === 'window' ? window : el).scrollBy(0, action.amount || 300);
          break;
        case 'hover':
          el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
          el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
          break;
        case 'focus':
          el.focus();
          break;
        case 'navigate':
          if (action.url) location.href = action.url;
          break;
        case 'wait':
          await sleep(action.ms || 1000);
          break;
        default:
          gmPost('/action_result', { ok: false, action: action.action, error: 'Unknown' });
          return false;
      }

      setStatus('blue', 'YUKI:' + action.action.toUpperCase());
      gmPost('/action_result', { ok: true, action: action.action });
      return true;
    } catch (e) {
      gmPost('/action_result', { ok: false, action: action.action, error: e.message });
      return false;
    }
  }

  async function executeSequence(actions) {
    for (const action of actions) {
      const ok = await executeAction(action);
      if (!ok && action.critical !== false) break;
      await sleep(action.delay || 300);
    }
  }

  function resolveTarget(target) {
    if (typeof target === 'string') {
      try { return document.querySelector(target); } catch { return null; }
    }
    return null;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // ==================== 扫描触发 ====================

  function triggerScan(trigger) {
    const snapshot = buildSnapshot(trigger);
    if (snapshot) {
      gmPost('/scan', snapshot);
      setStatus('blue', 'YUKI:SCAN:' + snapshot.element_count + 'els');
    }
  }

  function throttledScan(trigger) {
    if (scanThrottle) return;
    scanThrottle = setTimeout(() => {
      scanThrottle = null;
      triggerScan(trigger || 'dom_change');
    }, 800);
  }

  // ==================== 初始化 ====================

  createStatusBadge();
  setStatus('gray', 'YUKI:CONNECTING');

  // 轮询指令
  setInterval(pollCommands, POLL_INTERVAL);

  // 定时扫描
  setInterval(() => triggerScan('timer'), SCAN_INTERVAL);

  // DOM 变化
  const observer = new MutationObserver((mutations) => {
    const has = mutations.some(m =>
      m.type === 'childList' ||
      (m.type === 'attributes' && ['class', 'style', 'disabled', 'hidden'].includes(m.attributeName))
    );
    if (has) throttledScan('mutation');
  });
  observer.observe(document.body, {
    childList: true, subtree: true,
    attributes: true, attributeFilter: ['class', 'style', 'disabled', 'hidden'],
  });

  // 首次扫描
  setTimeout(() => triggerScan('initial'), 1500);
  console.log('[Yuki-Eye] 🚀 Initialized on', location.hostname);
})();
