const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
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
  setIgnoreMouseEvent: (ignored) => ipcRenderer.send('set-ignore-mouse-event', Boolean(ignored)),
  set_ignore_mouse_event: (ignored) => ipcRenderer.send('set-ignore-mouse-event', Boolean(ignored)),
});
