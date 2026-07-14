const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');

const ROOT_DIR = path.resolve(__dirname, '..', '..');
const CONFIG_PATH = path.join(ROOT_DIR, 'config.json');
const EDIT_SHORTCUT = 'CommandOrControl+Alt+Y';
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
    window.setAlwaysOnTop(true, 'screen-saver');
  }
  window.setBackgroundColor('#00000000');

  window.once('ready-to-show', () => {
    window.show();
    applyEditMode(window, false);
  });

  window.on('move', () => {
    if (editMode) saveWindowBounds(window);
  });

  window.on('resize', () => {
    if (editMode) saveWindowBounds(window);
  });

  window.on('close', () => saveWindowBounds(window));
  window.loadURL(process.env.LIVEYUKI_URL || 'http://127.0.0.1:18765');
  return window;
}

app.whenReady().then(() => {
  STATE_PATH = path.join(app.getPath('userData'), 'window-state.json');

  ipcMain.handle('get-cursor-position', () => {
    const point = screen.getCursorScreenPoint();
    return { x: point.x, y: point.y };
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
  globalShortcut.register(EDIT_SHORTCUT, toggleEditMode);
});

app.on('will-quit', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    saveWindowBounds(mainWindow);
  }
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  app.quit();
});
