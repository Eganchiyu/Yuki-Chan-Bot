// @ts-nocheck
/* eslint-disable no-underscore-dangle */
/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { LAppAdapter } from "./lappadapter";
import { LAppDelegate } from "./lappdelegate";
import * as LAppDefine from "./lappdefine";
import { LAppGlManager } from "./lappglmanager";
import { LAppLive2DManager } from "./lapplive2dmanager";

/**
 * Initialize the Live2D application
 */
export function initializeLive2D(): void {
  console.log(
    "Initializing Live2D with resourcePath:",
    LAppDefine.ResourcesPath
  );
  console.log("Model directories:", LAppDefine.ModelDir);

  // Clean up any existing instances first
  if (LAppDelegate.getInstance()) {
    // Release existing model resources
    LAppLive2DManager.releaseInstance();
  }

  if (
    !LAppGlManager.getInstance() ||
    !LAppDelegate.getInstance().initialize()
  ) {
    console.error("Failed to initialize Live2D");
    return;
  }

  LAppDelegate.getInstance().run();

  (window as any).getLive2DManager = () => LAppLive2DManager.getInstance();

  // Make sure LAppAdapter is available globally.
  // 注意：这里必须用打包期可见的静态 import。原来用 require()，Rollup 无法静态分析，
  // lappadapter 整块被 tree-shake 掉，浏览器里 require 又是 undefined，
  // 结果是表情/语音表情全部静默失效（控制台只留一句 "require is not defined"）。
  if (!(window as any).getLAppAdapter) {
    console.log('Setting up getLAppAdapter function');
    (window as any).getLAppAdapter = () => LAppAdapter.getInstance();
  }

  setupMousePassthrough();
}

/**
 * 鼠标穿透命中判定。
 *
 * Windows/macOS：setIgnoreMouseEvents(ignore, { forward: true }) 会继续把
 * mouse move 转发给页面，所以直接吃 window 的 pointermove 即可。
 *
 * Linux：forward 选项不生效（Electron 只在 Windows/macOS 实现），窗口一旦
 * 忽略鼠标就再也收不到 pointermove，会永久卡在穿透状态——表现为「模型点不动、
 * 拖不了」。这里改用主进程按帧推送的全局光标位置来判定是否落在模型上。
 */
let passthroughInstalled = false;

function setupMousePassthrough(): void {
  if (passthroughInstalled) return;

  const desktopApi = (window as any).pywebview?.api || (window as any).api;
  if (!desktopApi?.setIgnoreMouseEvent && !desktopApi?.set_ignore_mouse_event) return;

  passthroughInstalled = true;
  let lastIgnored: boolean | null = null;

  const setIgnoreMouseEvent = (ignored: boolean) => {
    // 轮询路径每帧都会调用，去重避免 IPC 刷屏
    if (ignored === lastIgnored) return;
    lastIgnored = ignored;
    if (desktopApi.setIgnoreMouseEvent) desktopApi.setIgnoreMouseEvent(ignored);
    else desktopApi.set_ignore_mouse_event(ignored);
  };

  let probed = false;
  let probeAttempts = 0;
  const updateMousePassthrough = (clientX: number, clientY: number) => {
    const model = LAppLive2DManager.getInstance().getModel(0);
    const view = LAppDelegate.getInstance().getView();
    const canvasElement = document.getElementById("canvas") as HTMLCanvasElement | null;
    const rect = canvasElement?.getBoundingClientRect();
    if (!model || !view || !rect) {
      setIgnoreMouseEvent(true);
      return;
    }

    const deviceX = (clientX - rect.left) * window.devicePixelRatio;
    const deviceY = (clientY - rect.top) * window.devicePixelRatio;

    let isHit = false;
    if (typeof model.isHitOnModelDevice === "function") {
      // 画布像素空间命中判定：用本帧 MVP 把 drawable 投到画布，和画面一致。
      isHit = model.isHitOnModelDevice(deviceX, deviceY);
    } else {
      // 老路径（需要模型自带 HitAreas）兜底
      const x = view.transformViewX(deviceX);
      const y = view.transformViewY(deviceY);
      isHit = Boolean(model.anyhitTest?.(x, y) || model.isHitOnModel?.(x, y));
    }

    // 模型是异步加载的，前若干帧还没有 MVP，等拿到包围盒再打一次
    if (desktopApi.debug && !probed && probeAttempts < 900) {
      probeAttempts++;
      const bounds = model.getModelScreenBounds?.();
      if (bounds) {
        probed = true;
        console.log('[passthrough-probe]', JSON.stringify({
          canvasSize: [canvasElement.width, canvasElement.height],
          rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
          dpr: window.devicePixelRatio,
          modelBounds: bounds,
          centerHit: model.isHitOnModelDevice?.(
            canvasElement.width / 2,
            canvasElement.height / 2
          ),
        }));
      }
    }
    setIgnoreMouseEvent(!isHit);
  };

  window.addEventListener(
    "pointermove",
    (e) => updateMousePassthrough(e.clientX, e.clientY),
    { passive: true }
  );

  if (typeof desktopApi.onCursorMoved === "function") {
    desktopApi.onCursorMoved((payload: any) => {
      if (!payload) return;
      const { x, y, windowX, windowY } = payload;
      if (typeof x !== "number" || typeof y !== "number") return;
      updateMousePassthrough(x - (windowX || 0), y - (windowY || 0));
    });
  }

  setIgnoreMouseEvent(true);
}

/**
 * Keep the original window.load handler for backwards compatibility
 * (for the standalone HTML file)
 */
/* // Comment out the window.load listener
window.addEventListener(
  "load",
  (): void => {
    initializeLive2D();
  },
  { passive: true }
);
*/

/**
 * 終了時の処理
 * 结束时的处理
 */
window.addEventListener(
  "beforeunload",
  (): void => LAppDelegate.releaseInstance(),
  { passive: true }
);

/**
 * Process when changing screen size.
 */
window.addEventListener(
  "resize",
  () => {
    if (LAppDefine.CanvasSize === "auto") {
      LAppDelegate.getInstance().onResize();
    }
  },
  { passive: true }
);

// Make the initialization function available globally
(window as any).initializeLive2D = initializeLive2D;
