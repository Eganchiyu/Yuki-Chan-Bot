import { LAppDelegate } from './WebSDK/src/lappdelegate';
import { LAppLive2DManager } from './WebSDK/src/lapplive2dmanager';
import * as LAppDefine from './WebSDK/src/lappdefine';

type CursorPosition = { x: number; y: number };

type CanvasGeometry = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type LiveYukiApi = {
  getCursorPosition?: () => Promise<CursorPosition>;
  getWindowPosition?: () => Promise<CursorPosition>;
};

function getWebviewApi(): LiveYukiApi | null {
  return (window as any).pywebview?.api || (window as any).api || null;
}

async function getCursorPosition(): Promise<CursorPosition | null> {
  const api = getWebviewApi();
  if (api?.getCursorPosition) return await api.getCursorPosition();

  try {
    const response = await fetch('/api/cursor', { cache: 'no-store' });
    if (response.ok) return await response.json();
  } catch {
  }

  return null;
}

async function getWindowPosition(): Promise<CursorPosition> {
  const api = getWebviewApi();
  if (api?.getWindowPosition) return await api.getWindowPosition();
  return { x: window.screenX, y: window.screenY };
}

export function startMouseFollowLoop(canvasEl: HTMLCanvasElement): void {
  let geometry: CanvasGeometry | null = null;
  let windowPosition: CursorPosition = { x: window.screenX, y: window.screenY };
  let latestCursor: CursorPosition | null = null;
  let latestViewPoint: { x: number; y: number } | null = null;
  let pendingWindowRequest = false;
  let pendingCursorRequest = false;
  let lastWindowPositionAt = 0;
  let lastFrameAt = performance.now();

  const updateGeometry = () => {
    const rect = canvasEl.getBoundingClientRect();
    geometry = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  };

  const refreshWindowPosition = async () => {
    if (pendingWindowRequest || performance.now() - lastWindowPositionAt < 80) return;
    pendingWindowRequest = true;
    try {
      windowPosition = await getWindowPosition();
      lastWindowPositionAt = performance.now();
    } finally {
      pendingWindowRequest = false;
    }
  };

  const refreshCursor = async () => {
    if (pendingCursorRequest) return;
    pendingCursorRequest = true;
    try {
      const cursor = await getCursorPosition();
      if (cursor) latestCursor = cursor;
    } finally {
      pendingCursorRequest = false;
    }
  };

  const consumeCursor = () => {
    const manager = LAppLive2DManager.getInstance();
    const model = manager.getModel(0);
    const view = LAppDelegate.getInstance().getView();
    if (!LAppDefine.LookAtMouse || !model || !view || !geometry || !latestCursor) return;
    if (geometry.width <= 0 || geometry.height <= 0) return;

    const pointX = latestCursor.x - windowPosition.x - geometry.left;
    const pointY = latestCursor.y - windowPosition.y - geometry.top;
    const centerX = geometry.width * 0.5;
    const centerY = geometry.height * 0.25;
    const relativeX = Math.max(-1.5, Math.min(1.5, (pointX - centerX) / (geometry.width * 0.5)));
    const relativeY = Math.max(-1.5, Math.min(1.5, (pointY - centerY) / (geometry.height * 0.5)));
    const targetX = (centerX + relativeX * centerX) * window.devicePixelRatio;
    const targetY = (centerY + relativeY * geometry.height * 0.5) * window.devicePixelRatio;
    const nextPoint = { x: view.transformViewX(targetX), y: view.transformViewY(targetY) };
    const elapsed = Math.min(0.1, Math.max(0.001, (performance.now() - lastFrameAt) / 1000));
    const alpha = 1 - Math.exp(-elapsed * 18);
    latestViewPoint = latestViewPoint
      ? {
          x: latestViewPoint.x + (nextPoint.x - latestViewPoint.x) * alpha,
          y: latestViewPoint.y + (nextPoint.y - latestViewPoint.y) * alpha,
        }
      : nextPoint;
    manager.onDrag(latestViewPoint.x, latestViewPoint.y);
  };

  const frame = (timestamp: number) => {
    lastFrameAt = timestamp;
    consumeCursor();
    window.requestAnimationFrame(frame);
  };

  updateGeometry();
  window.addEventListener('resize', updateGeometry, { passive: true });
  window.addEventListener('scroll', updateGeometry, { passive: true });
  window.addEventListener('mousemove', (event) => {
    latestCursor = { x: event.screenX, y: event.screenY };
  }, { passive: true });
  window.setInterval(() => {
    void refreshWindowPosition();
    if (!getWebviewApi()?.getCursorPosition) void refreshCursor();
  }, 50);
  void refreshWindowPosition();
  void refreshCursor();
  window.requestAnimationFrame(frame);
}
