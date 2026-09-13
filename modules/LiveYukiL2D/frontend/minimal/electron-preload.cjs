const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  platform: process.platform,
  debug: process.env.LIVEYUKI_DEBUG === '1',
  getCursorPosition: () => ipcRenderer.invoke('get-cursor-position'),
  getWindowPosition: () => ipcRenderer.invoke('get-window-position'),
  setWindowPosition: (x, y) => ipcRenderer.send('set-window-position', Math.round(x), Math.round(y)),
  getEditMode: () => ipcRenderer.invoke('get-edit-mode'),
  setEditMode: (enabled) => ipcRenderer.send('set-edit-mode', Boolean(enabled)),
  toggleEditMode: () => ipcRenderer.send('toggle-edit-mode'),
  saveWindowBounds: () => ipcRenderer.send('save-window-bounds'),
  onEditModeChanged: (callback) => {
    const listener = (_event, enabled) => callback(Boolean(enabled));
    ipcRenderer.on('edit-mode-changed', listener);
    return () => ipcRenderer.removeListener('edit-mode-changed', listener);
  },
  // Linux 上 setIgnoreMouseEvents 的 forward 不生效，窗口忽略鼠标时收不到
  // pointermove，改由主进程推送全局光标位置，渲染进程据此做穿透命中判定。
  onCursorMoved: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('cursor-moved', listener);
    return () => ipcRenderer.removeListener('cursor-moved', listener);
  },
  setIgnoreMouseEvent: (ignored) => ipcRenderer.send('set-ignore-mouse-event', Boolean(ignored)),
  set_ignore_mouse_event: (ignored) => ipcRenderer.send('set-ignore-mouse-event', Boolean(ignored)),
});
