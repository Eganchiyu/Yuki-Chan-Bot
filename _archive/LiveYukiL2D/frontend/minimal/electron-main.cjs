const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const { execFile } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');

const ROOT_DIR = path.resolve(__dirname, '..', '..');
const CONFIG_PATH = path.join(ROOT_DIR, 'config.json');
const EDIT_SHORTCUT = 'CommandOrControl+Alt+Y';
const IS_LINUX = process.platform === 'linux';
const IS_WAYLAND =
  IS_LINUX && process.env.XDG_SESSION_TYPE === 'wayland' && !process.env.DISPLAY;

let STATE_PATH = null;
const DEFAULT_CONFIG = {
  desktopPet: {
    width: 420,
    height: 640,
    x: null,
    y: null,
    transparent: true,
    frameless: true,
    alwaysOnTop: true,
    resizable: true,
    mousePassthrough: true,
  },
};

let mainWindow = null;
let editMode = false;

// LIVEYUKI_DEBUG=1 时把窗口几何、光标来源、穿透判定打到 stdout，
// 便于在 Linux 合成器上排查「点不中 / 拖不动 / 穿透失效」。
const DEBUG = process.env.LIVEYUKI_DEBUG === '1';
function debugLog(...args) {
  if (DEBUG) console.log('[LiveYukiL2D][debug]', ...args);
}

// ---------------------------------------------------------------------------
// Linux 适配：平台相关开关必须在 app ready 之前追加
// ---------------------------------------------------------------------------
function configureLinuxCommandLine() {
  if (!IS_LINUX) return;

  // 原生 Wayland 下 globalShortcut 需要走 xdg-desktop-portal 的 GlobalShortcuts，
  // 否则 Ctrl+Alt+Y 静默失效（Hyprland 提供 hyprland.portal）。
  if (!app.commandLine.hasSwitch('enable-features')) {
    app.commandLine.appendSwitch('enable-features', 'GlobalShortcutsPortal');
  }

  // 桌宠依赖「绝对窗口定位 + 全局光标 + 拖动」，原生 Wayland 客户端拿不到这些，
  // 因此没有显式指定时优先走 XWayland（Hyprland 等合成器都支持）。
  if (
    !app.commandLine.hasSwitch('ozone-platform') &&
    !app.commandLine.hasSwitch('ozone-platform-hint')
  ) {
    app.commandLine.appendSwitch('ozone-platform', process.env.DISPLAY ? 'x11' : 'wayland');
  }
}

configureLinuxCommandLine();

function readJsonFile(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function readState() {
  if (!STATE_PATH) return {};
  return readJsonFile(STATE_PATH) || {};
}

function readConfig() {
  const userConfig = readJsonFile(CONFIG_PATH) || {};
  const state = readState();
  return {
    ...DEFAULT_CONFIG,
    ...userConfig,
    desktopPet: {
      ...DEFAULT_CONFIG.desktopPet,
      ...(userConfig.desktopPet || {}),
      ...(state.desktopPet || {}),
    },
  };
}

function saveWindowBounds(window) {
  if (!window || window.isDestroyed() || !STATE_PATH) return;

  const bounds = window.getBounds();
  const state = readState();
  const nextState = {
    ...state,
    desktopPet: {
      ...(state.desktopPet || {}),
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
    },
  };

  try {
    fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
    fs.writeFileSync(STATE_PATH, `${JSON.stringify(nextState, null, 2)}\n`, 'utf8');
  } catch (err) {
    console.warn('[LiveYukiL2D] 保存窗口位置失败:', err);
  }
}

function sendEditMode(window) {
  if (!window || window.isDestroyed()) return;
  window.webContents.send('edit-mode-changed', editMode);
}

function applyEditMode(window, enabled) {
  if (!window || window.isDestroyed()) return;

  editMode = enabled;
  window.setResizable(enabled);
  // 注意：setIgnoreMouseEvents 的 forward 选项只在 Windows/macOS 生效。
  // Linux 上改为由主进程轮询全局光标并推给渲染进程做命中判定。
  window.setIgnoreMouseEvents(!enabled, { forward: true });

  if (!enabled) {
    saveWindowBounds(window);
  }

  sendEditMode(window);
}

function toggleEditMode() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  applyEditMode(mainWindow, !editMode);
}

// ---------------------------------------------------------------------------
// 全局光标：Linux 适配
// ---------------------------------------------------------------------------
const cursorState = {
  x: 0,
  y: 0,
  source: 'screen', // 'hyprland' | 'hyprctl' | 'screen'
  socketPath: null,
};

/**
 * Hyprland 的 IPC socket 路径。
 *
 * 为什么不用 Chromium 的 screen.getCursorScreenPoint()：在 Hyprland + XWayland 下
 * 它返回的是 X 服务器最后一次收到的指针位置，窗口一旦忽略鼠标事件就再也不更新，
 * 实测会永远停在启动那一刻的坐标——穿透判定会彻底失效。
 * 合成器自己才知道真实光标位置，所以优先走它的 IPC。
 */
function findHyprlandSocket() {
  const runtimeDir = process.env.XDG_RUNTIME_DIR;
  if (!runtimeDir) return null;
  const base = path.join(runtimeDir, 'hypr');
  const signature = process.env.HYPRLAND_INSTANCE_SIGNATURE;
  const candidates = [];
  if (signature) {
    candidates.push(path.join(base, signature, '.socket.sock'));
  } else {
    try {
      for (const entry of fs.readdirSync(base)) {
        candidates.push(path.join(base, entry, '.socket.sock'));
      }
    } catch {
      /* 目录不存在就当没有 */
    }
  }
  for (const candidate of candidates) {
    try {
      if (fs.statSync(candidate).isSocket()) return candidate;
    } catch {
      /* 继续找下一个 */
    }
  }
  return null;
}

function detectCursorSource() {
  if (!IS_LINUX) return { source: 'screen', socketPath: null };
  const socketPath = findHyprlandSocket();
  if (socketPath) return { source: 'hyprland', socketPath };
  if (findOnPath('hyprctl')) return { source: 'hyprctl', socketPath: null };
  return { source: 'screen', socketPath: null };
}

function parseCursorText(text) {
  // Hyprland IPC 返回 "x, y"
  const match = /(-?\d+)\s*,\s*(-?\d+)/.exec(text || '');
  if (!match) return null;
  return { x: parseInt(match[1], 10), y: parseInt(match[2], 10) };
}

function readCursorFromHyprlandSocket(socketPath) {
  return new Promise((resolve) => {
    let settled = false;
    let buffer = '';
    const finish = (value) => {
      if (settled) return;
      settled = true;
      try {
        socket.destroy();
      } catch {
        /* ignore */
      }
      resolve(value);
    };

    const socket = net.createConnection({ path: socketPath });
    socket.setTimeout(500, () => finish(null));
    socket.on('connect', () => socket.write('cursorpos'));
    socket.on('data', (chunk) => {
      buffer += chunk.toString('utf8');
      const parsed = parseCursorText(buffer);
      if (parsed) finish(parsed);
    });
    socket.on('end', () => finish(parseCursorText(buffer)));
    socket.on('error', () => finish(null));
  });
}

function findOnPath(binary) {
  const paths = (process.env.PATH || '').split(path.delimiter);
  return paths.some((dir) => {
    if (!dir) return false;
    try {
      fs.accessSync(path.join(dir, binary), fs.constants.X_OK);
      return true;
    } catch {
      return false;
    }
  });
}

function readCursorFromHyprctl() {
  return new Promise((resolve) => {
    execFile('hyprctl', ['-j', 'cursorpos'], { timeout: 1000 }, (err, stdout) => {
      if (err || !stdout) return resolve(null);
      try {
        const data = JSON.parse(stdout);
        if (typeof data.x === 'number' && typeof data.y === 'number') {
          return resolve({ x: Math.round(data.x), y: Math.round(data.y) });
        }
      } catch {
        /* 落到 screen 兜底 */
      }
      resolve(null);
    });
  });
}

async function readCursorPoint() {
  let point = null;
  if (cursorState.source === 'hyprland' && cursorState.socketPath) {
    point = await readCursorFromHyprlandSocket(cursorState.socketPath);
  } else if (cursorState.source === 'hyprctl') {
    point = await readCursorFromHyprctl();
  }
  if (!point) {
    try {
      const p = screen.getCursorScreenPoint();
      point = { x: Math.round(p.x), y: Math.round(p.y) };
    } catch {
      point = null;
    }
  }
  if (point) {
    cursorState.x = point.x;
    cursorState.y = point.y;
  }
  return point;
}

let cursorTimer = null;

function startCursorPolling(window) {
  if (cursorTimer) return;
  const interval = cursorState.source === 'hyprctl' ? 100 : 33;
  cursorTimer = setInterval(async () => {
    if (!window || window.isDestroyed()) return;
    const point = await readCursorPoint();
    if (!point || window.isDestroyed()) return;
    const bounds = window.getBounds();
    window.webContents.send('cursor-moved', {
      x: point.x,
      y: point.y,
      windowX: bounds.x,
      windowY: bounds.y,
    });
  }, interval);
}

function stopCursorPolling() {
  if (cursorTimer) {
    clearInterval(cursorTimer);
    cursorTimer = null;
  }
}

function registerEditShortcut() {
  try {
    const ok = globalShortcut.register(EDIT_SHORTCUT, toggleEditMode);
    if (!ok) {
      console.warn(
        '[LiveYukiL2D] 全局快捷键注册失败：' + EDIT_SHORTCUT +
          '。Linux/Wayland 下请确认 xdg-desktop-portal 可用，或改用窗口内单击模型进入编辑模式。'
      );
    }
  } catch (err) {
    console.warn('[LiveYukiL2D] 全局快捷键注册异常:', err);
  }
}

function createWindow() {
  const config = readConfig();
  const pet = config.desktopPet || DEFAULT_CONFIG.desktopPet;

  const window = new BrowserWindow({
    width: Number(pet.width || 420),
    height: Number(pet.height || 640),
    x: pet.x ?? undefined,
    y: pet.y ?? undefined,
    show: false,
    frame: pet.frameless === false,
    transparent: pet.transparent !== false,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: pet.alwaysOnTop !== false,
    resizable: false,
    skipTaskbar: true,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'electron-preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  mainWindow = window;

  if (pet.alwaysOnTop !== false) {
    // 'screen-saver' 这个层级只有 macOS 认，Linux/Windows 传了也无效。
    if (process.platform === 'darwin') {
      window.setAlwaysOnTop(true, 'screen-saver');
    } else {
      window.setAlwaysOnTop(true);
    }
  }
  window.setBackgroundColor('#00000000');

  window.once('ready-to-show', () => {
    window.show();
    applyEditMode(window, false);
    const detected = detectCursorSource();
    cursorState.source = detected.source;
    cursorState.socketPath = detected.socketPath;
    debugLog(
      'window bounds', window.getBounds(),
      'ozone', app.commandLine.getSwitchValue('ozone-platform'),
      'cursorSource', cursorState.source,
      'socket', cursorState.socketPath
    );
    startCursorPolling(window);
  });

  window.on('move', () => {
    if (editMode) saveWindowBounds(window);
  });

  window.on('resize', () => {
    if (editMode) saveWindowBounds(window);
  });

  window.on('close', () => saveWindowBounds(window));
  window.on('closed', () => {
    stopCursorPolling();
    if (mainWindow === window) mainWindow = null;
  });

  window.loadURL(process.env.LIVEYUKI_URL || 'http://127.0.0.1:18765');
  return window;
}

app.whenReady().then(() => {
  STATE_PATH = path.join(app.getPath('userData'), 'window-state.json');

  ipcMain.handle('get-cursor-position', async () => {
    const point = await readCursorPoint();
    return point || { x: cursorState.x, y: cursorState.y };
  });

  ipcMain.handle('get-window-position', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window) return { x: 0, y: 0 };
    const bounds = window.getBounds();
    return { x: bounds.x, y: bounds.y };
  });

  ipcMain.on('set-window-position', (event, x, y) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || !editMode) return;
    const bounds = window.getBounds();
    window.setBounds({ x: Number(x), y: Number(y), width: bounds.width, height: bounds.height });
  });

  ipcMain.handle('get-edit-mode', () => editMode);

  ipcMain.on('set-ignore-mouse-event', (event, ignored) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || editMode) return;
    debugLog('ignoreMouse ->', Boolean(ignored), 'cursor', cursorState.x, cursorState.y);
    window.setIgnoreMouseEvents(Boolean(ignored), { forward: true });
  });

  ipcMain.on('set-edit-mode', (event, enabled) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    applyEditMode(window, Boolean(enabled));
  });

  ipcMain.on('toggle-edit-mode', () => toggleEditMode());
  ipcMain.on('save-window-bounds', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    saveWindowBounds(window);
  });

  createWindow();
  registerEditShortcut();
});

app.on('will-quit', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    saveWindowBounds(mainWindow);
  }
  stopCursorPolling();
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  app.quit();
});
