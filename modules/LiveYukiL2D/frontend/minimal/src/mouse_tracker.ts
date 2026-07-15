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

async function fetchCursorPosition(): Promise<CursorPosition | null> {
  const api = getWebviewApi();
  if (api?.getCursorPosition) return await api.getCursorPosition();

  try {
    const response = await fetch('/api/cursor', { cache: 'no-store' });
    if (response.ok) return await response.json();
  } catch {
    // 忽略网络错误，避免控制台刷屏
  }
  return null;
}

async function fetchWindowPosition(): Promise<CursorPosition> {
  const api = getWebviewApi();
  if (api?.getWindowPosition) return await api.getWindowPosition();
  return { x: window.screenX, y: window.screenY };
}

export function startMouseFollowLoop(canvasEl: HTMLCanvasElement): void {
  let geometry: CanvasGeometry | null = null;
  let windowPosition: CursorPosition = { x: window.screenX, y: window.screenY };
  let latestCursor: CursorPosition = { x: window.screenX + canvasEl.width / 2, y: window.screenY + canvasEl.height / 2 };
  
  let currentViewPoint: CursorPosition = { x: 0, y: 0 };
  let lastFrameAt = performance.now();

  // 更新 Canvas 尺寸和相对屏幕的坐标
  const updateGeometry = () => {
    const rect = canvasEl.getBoundingClientRect();
    geometry = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  };

  // 1. 独立且高效的异步数据轮询 (替代 setInterval，避免请求堆叠和资源浪费)
  const pollSystemData = async () => {
    while (true) {
      const start = performance.now();
      
      const [winPos, curPos] = await Promise.all([
        fetchWindowPosition(),
        // 仅在原生 API 不可用时，才通过网络轮询，降低网络开销
        !getWebviewApi()?.getCursorPosition ? fetchCursorPosition() : Promise.resolve(null)
      ]);

      if (winPos) windowPosition = winPos;
      if (curPos) latestCursor = curPos;

      const elapsed = performance.now() - start;
      // 动态调整休眠时间，目标刷新率约 30-40Hz，比 50ms (20Hz) 更跟手，且网络拥堵时不卡死
      const delay = Math.max(16, 33 - elapsed);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  };

  // 2. 消费坐标并执行平滑渲染
  const consumeCursor = () => {
    const manager = LAppLive2DManager.getInstance();
    const model = manager.getModel(0);
    const view = LAppDelegate.getInstance().getView();
    
    if (!LAppDefine.LookAtMouse || !model || !view || !geometry) return;
    if (geometry.width <= 0 || geometry.height <= 0) return;

    // --- 核心数学计算开始 ---

    // 屏幕物理分辨率，用于边缘衰减的基准 (防备拿不到取 1920/1080 兜底)
    const screenW = window.screen.width || 1920;
    const screenH = window.screen.height || 1080;

    // A. 设定头部锚点：画布宽度的中心 50%，高度的 25% (偏上四分之一处)
    const centerX = geometry.width * 0.5;
    const centerY = geometry.height * 0.25;

    // 计算头部在整个屏幕中的绝对全局坐标
    const headGlobalX = windowPosition.x + geometry.left + centerX;
    const headGlobalY = windowPosition.y + geometry.top + centerY;

    // B. 计算鼠标距离头部的实际距离
    const deltaX = latestCursor.x - headGlobalX;
    const deltaY = latestCursor.y - headGlobalY;

    // C. 归一化并应用边缘衰减效应 (使用 Math.tanh)
    // tanh 函数曲线可以提供最丝滑的边缘衰减：越靠近中心呈线性，越靠近边缘变化率越小，最终无限逼近边界 1 和 -1
    const intensity = 2.0; // 敏感度参数，数值越大，小幅度移动反应越强
    const smoothFactorX = Math.tanh((deltaX / (screenW * 0.5)) * intensity);
    const smoothFactorY = Math.tanh((deltaY / (screenH * 0.5)) * intensity);

    // 将平滑后的系数映射回 Canvas 空间
    const targetX = (centerX + smoothFactorX * centerX) * window.devicePixelRatio;
    const targetY = (centerY + smoothFactorY * (geometry.height * 0.5)) * window.devicePixelRatio;

    // 转换为 Live2D 的 View 坐标系
    const nextPoint = { 
      x: view.transformViewX(targetX), 
      y: view.transformViewY(targetY) 
    };

    // --- 缓动与阻尼系统 ---
    
    // 结合 deltaTime 计算 LERP 系数，保证不同刷新率下丝滑程度一致
    const now = performance.now();
    const dt = Math.min(0.1, Math.max(0.001, (now - lastFrameAt) / 1000));
    lastFrameAt = now;

    // stiffness 阻尼系数 (原为 18)。改为 12 能让动作更加柔和不生硬
    const stiffness = 12; 
    const alpha = 1 - Math.exp(-dt * stiffness);

    currentViewPoint.x += (nextPoint.x - currentViewPoint.x) * alpha;
    currentViewPoint.y += (nextPoint.y - currentViewPoint.y) * alpha;

    // 应用最终坐标
    manager.onDrag(currentViewPoint.x, currentViewPoint.y);
  };

  const frame = () => {
    consumeCursor();
    window.requestAnimationFrame(frame);
  };

  // 初始化和事件绑定
  updateGeometry();
  window.addEventListener('resize', updateGeometry, { passive: true });
  window.addEventListener('scroll', updateGeometry, { passive: true });
  
  // 浏览器内的高频鼠标移动，直接捕获，避免过度依赖轮询
  window.addEventListener('mousemove', (event) => {
    latestCursor = { x: event.screenX, y: event.screenY };
  }, { passive: true });

  // 启动两个互不阻塞的系统：数据拉取系统 和 渲染系统
  pollSystemData();
  window.requestAnimationFrame(frame);
}