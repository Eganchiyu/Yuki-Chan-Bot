import { updateModelConfig } from './WebSDK/src/lappdefine';
import { initializeLive2D } from './WebSDK/src/main';
import { LAppLive2DManager } from './WebSDK/src/lapplive2dmanager';
import { LAppDelegate } from './WebSDK/src/lappdelegate';
import * as LAppDefine from './WebSDK/src/lappdefine';
import { startMouseFollowLoop } from './mouse_tracker';

interface ModelInfo {
  name: string;
  url: string;
  kScale?: number;
  emotionMap?: Record<string, number | string>;
  defaultEmotion?: number | string;
  scrollToResize?: boolean;
  lookAtMouse?: boolean;
}

interface IncomingMessage {
  type: string;
  model_info?: ModelInfo;
  text?: string;
  expression?: number | string;
  audio?: string;
  actions?: { expressions?: Array<number | string> };
  display_text?: { text?: string; name?: string; avatar?: string };
  state?: string;
  message?: string;
}

type LiveYukiApi = {
  getCursorPosition?: () => Promise<CursorPosition>;
  getWindowPosition?: () => Promise<CursorPosition>;
  setWindowPosition?: (x: number, y: number) => void;
  getEditMode?: () => Promise<boolean>;
  setEditMode?: (enabled: boolean) => void;
  toggleEditMode?: () => void;
  saveWindowBounds?: () => void;
  onEditModeChanged?: (callback: (enabled: boolean) => void) => () => void;
};

const statusEl = document.getElementById('status')!;
const subtitleEl = document.getElementById('subtitle')!;
const chatForm = document.getElementById('chat') as HTMLFormElement;
const chatInput = document.getElementById('chat-input') as HTMLTextAreaElement;
const chatSend = document.getElementById('chat-send') as HTMLButtonElement;
const chatCancel = document.getElementById('chat-cancel') as HTMLButtonElement;
const chatClear = document.getElementById('chat-clear') as HTMLButtonElement;
const canvasEl = document.getElementById('canvas') as HTMLCanvasElement;
let isEditMode = false;
const DEFAULT_MODEL: ModelInfo = {
  name: 'Yuki',
  url: 'http://127.0.0.1:18765/models/Yuki/Yuki.model3.json',
  kScale: 1.0,
  emotionMap: { neutral: 0 },
  defaultEmotion: 0,
};

function setStatus(text: string) {
  statusEl.textContent = text;
  console.log('[LiveYuki]', text);
}

function parseModelUrl(url: string): { baseUrl: string; modelDir: string; modelFileName: string } {
  const urlObj = new URL(url, window.location.href);
  const pathname = urlObj.pathname;
  const lastSlashIndex = pathname.lastIndexOf('/');
  const fullFileName = pathname.substring(lastSlashIndex + 1);
  const modelFileName = fullFileName.replace('.model3.json', '');
  const secondLastSlashIndex = pathname.lastIndexOf('/', lastSlashIndex - 1);
  const modelDir = pathname.substring(secondLastSlashIndex + 1, lastSlashIndex);
  const baseUrl = `${urlObj.protocol}//${urlObj.host}${pathname.substring(0, secondLastSlashIndex + 1)}`;
  return { baseUrl, modelDir, modelFileName };
}

function loadModel(modelInfo: ModelInfo = DEFAULT_MODEL) {
  const { baseUrl, modelDir, modelFileName } = parseModelUrl(modelInfo.url);
  setStatus(`加载模型: ${modelInfo.name || modelDir}`);
  console.log('[LiveYuki] model config', { baseUrl, modelDir, modelFileName, modelInfo });

  updateModelConfig(
    baseUrl,
    modelDir,
    modelFileName,
    Number(modelInfo.kScale ?? 1.0),
    modelInfo.lookAtMouse ?? true,
    modelInfo.scrollToResize ?? true
  );

  // 释放旧模型并重新初始化。Open-LLM-VTuber 原代码也这么做。
  try {
    if ((window as any).LAppLive2DManager?.releaseInstance) {
      (window as any).LAppLive2DManager.releaseInstance();
    }
  } catch (err) {
    console.warn('[LiveYuki] release old model failed:', err);
  }

  initializeLive2D();
  setTimeout(() => {
    const model = LAppLive2DManager.getInstance().getModel(0);
    setStatus(model ? '模型加载请求已发送，看画布是否出现 Yuki' : '模型管理器已启动，等待模型资源加载');
  }, 800);
}

function getAdapter(): any {
  return (window as any).getLAppAdapter?.();
}

function getWebviewApi(): LiveYukiApi | null {
  return (window as any).pywebview?.api || (window as any).api || null;
}

function setExpression(expression: number | string) {
  const adapter = getAdapter();
  if (!adapter) {
    setStatus('adapter 未准备好，稍后再试');
    return;
  }
  try {
    if (typeof expression === 'number') {
      const name = adapter.getExpressionName(expression);
      if (name) adapter.setExpression(name);
      else setStatus(`模型没有 expression index=${expression}，Yuki 当前模型可能没有表情文件`);
    } else {
      adapter.setExpression(expression);
    }
  } catch (err) {
    console.warn('[LiveYuki] setExpression failed:', err);
    setStatus('设置表情失败，可能模型没有 expression 文件');
  }
}

function playTalkMotion() {
  const model = LAppLive2DManager.getInstance().getModel(0);
  if (!model) return;
  try {
    model.startRandomMotion('Talk', LAppDefine.PriorityNormal);
  } catch (err) {
    console.warn('[LiveYuki] Talk motion failed. This model probably has no motions.', err);
  }
}

function sayText(text: string, expression?: number | string) {
  subtitleEl.textContent = text;
  if (expression !== undefined) setExpression(expression);
  playTalkMotion();
}

function playAudioBase64(audioBase64: string, expression?: number | string, text?: string) {
  const model = LAppLive2DManager.getInstance().getModel(0) as any;
  if (!audioBase64) {
    if (text) sayText(text, expression);
    return;
  }

  if (expression !== undefined) setExpression(expression);
  if (text) subtitleEl.textContent = text;

  const audioDataUrl = `data:audio/wav;base64,${audioBase64}`;
  const audio = new Audio(audioDataUrl);
  audio.addEventListener('canplaythrough', () => {
    try {
      model?._wavFileHandler?.start(audioDataUrl);
    } catch (err) {
      console.warn('[LiveYuki] lip sync start failed:', err);
    }
    playTalkMotion();
    audio.play().catch((err) => console.warn('[LiveYuki] audio play failed:', err));
  });
  audio.addEventListener('ended', () => setStatus('音频播放结束'));
  audio.load();
}

function handleMessage(msg: IncomingMessage) {
  console.log('[LiveYuki] recv', msg);
  if (msg.type === 'set-model-and-conf' || msg.type === 'set-model') {
    if (msg.model_info) loadModel(msg.model_info);
    return;
  }

  if (msg.type === 'state') {
    const state = msg.state || 'idle';
    chatSend.disabled = state === 'thinking';
    chatCancel.disabled = state !== 'thinking';
    setStatus(state === 'thinking' ? 'Yuki 思考中...' : state === 'speaking' ? 'Yuki 正在说话' : `运行状态：${state}`);
    return;
  }

  if (msg.type === 'error') {
    chatSend.disabled = false;
    chatCancel.disabled = true;
    setStatus(msg.message || '处理失败');
    return;
  }

  if (msg.type === 'expression') {
    if (msg.expression !== undefined) setExpression(msg.expression);
    return;
  }

  if (msg.type === 'say') {
    sayText(msg.text || '', msg.expression);
    return;
  }

  if (msg.type === 'audio') {
    const expression = msg.actions?.expressions?.[0];
    const text = msg.display_text?.text || msg.text || '';
    playAudioBase64(msg.audio || '', expression, text);
  }
}

function connectWebSocket() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = window.location.hostname || '127.0.0.1';
  const wsUrl = `${wsProtocol}//${wsHost}:18765/ws`;
  const ws = new WebSocket(wsUrl);

  ws.addEventListener('open', () => setStatus(`WS 已连接: ${wsUrl}`));
  ws.addEventListener('close', () => {
    chatSend.disabled = false;
    chatCancel.disabled = true;
    setStatus('WS 已断开，2 秒后重连');
    setTimeout(connectWebSocket, 2000);
  });
  ws.addEventListener('error', () => setStatus('WS 连接错误，确认 Python 服务是否启动'));
  ws.addEventListener('message', (event) => {
    try {
      handleMessage(JSON.parse(event.data));
    } catch (err) {
      console.warn('[LiveYuki] bad ws message:', event.data, err);
    }
  });

  (window as any).LiveYukiWS = ws;
}

function sendChatMessage() {
  const text = chatInput.value.trim();
  const ws = (window as any).LiveYukiWS as WebSocket | undefined;
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) {
    setStatus('聊天连接尚未就绪');
    return;
  }
  ws.send(JSON.stringify({ type: 'user-input', text }));
  chatInput.value = '';
  chatSend.disabled = true;
  chatCancel.disabled = false;
}

chatForm.addEventListener('submit', (event) => {
  event.preventDefault();
  sendChatMessage();
});
chatInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendChatMessage();
  }
});
chatCancel.addEventListener('click', () => {
  const ws = (window as any).LiveYukiWS as WebSocket | undefined;
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'cancel' }));
});
chatClear.addEventListener('click', () => {
  const ws = (window as any).LiveYukiWS as WebSocket | undefined;
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'clear-history' }));
  subtitleEl.textContent = '';
});

function applyEditMode(enabled: boolean) {
  isEditMode = enabled;
  document.body.classList.toggle('edit-mode', enabled);
  setStatus(enabled ? '编辑模式：拖动模型区域移动窗口，滚轮缩放，拖拽边缘调整大小，按 Ctrl+Alt+Y 锁定' : '锁定模式：鼠标穿透已启用');
}

function setupEditWindowControls() {
  let dragging = false;
  let dragOffset = { x: 0, y: 0 };

  window.addEventListener('mousedown', async (event) => {
    if (!isEditMode || event.button !== 0) return;
    const edgeSize = 12;
    if (
      event.clientX <= edgeSize ||
      event.clientY <= edgeSize ||
      window.innerWidth - event.clientX <= edgeSize ||
      window.innerHeight - event.clientY <= edgeSize
    ) {
      return;
    }

    const api = getWebviewApi();
    if (!api?.setWindowPosition) return;

    const windowPos = await api.getWindowPosition?.() ?? { x: window.screenX, y: window.screenY };
    dragOffset = { x: event.screenX - windowPos.x, y: event.screenY - windowPos.y };
    dragging = true;
    event.preventDefault();
  });

  window.addEventListener('mousemove', (event) => {
    if (!dragging) return;
    getWebviewApi()?.setWindowPosition?.(event.screenX - dragOffset.x, event.screenY - dragOffset.y);
  });

  window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    getWebviewApi()?.saveWindowBounds?.();
  });

  window.addEventListener('wheel', (event) => {
    if (!isEditMode || !LAppDefine.ScrollToResize) return;
    event.preventDefault();
    const direction = event.deltaY > 0 ? -1 : 1;
    const nextScale = Math.max(0.3, Math.min(3.0, LAppDefine.CurrentKScale + direction * 0.05));
    LAppDefine.setCurrentKScale(nextScale);
    LAppDelegate.getInstance().getView()?.initialize();
  }, { passive: false });
}

async function setupEditMode() {
  const api = getWebviewApi();
  if (!api) return;

  const initial = await api.getEditMode?.();
  applyEditMode(Boolean(initial));
  api.onEditModeChanged?.(applyEditMode);

  window.addEventListener('beforeunload', () => api.saveWindowBounds?.());
}

function exposeDebug() {
  (window as any).LiveYuki = {
    loadModel,
    setExpression,
    sayText,
    playAudioBase64,
    toggleEditMode: () => getWebviewApi()?.toggleEditMode?.(),
    manager: () => LAppLive2DManager.getInstance(),
    model: () => LAppLive2DManager.getInstance().getModel(0),
    adapter: getAdapter,
  };
}

document.getElementById('btn-reload')?.addEventListener('click', () => loadModel(DEFAULT_MODEL));
document.getElementById('btn-smile')?.addEventListener('click', () => setExpression(0));
document.getElementById('btn-info')?.addEventListener('click', () => {
  console.log('LiveYuki debug:', (window as any).LiveYuki);
  console.log('model:', (window as any).LiveYuki.model());
  setStatus('调试对象已输出到 console: window.LiveYuki');
});

exposeDebug();
setupEditWindowControls();
setupEditMode();
connectWebSocket();
startMouseFollowLoop(canvasEl);
