// @ts-nocheck
/* eslint-disable no-underscore-dangle */
/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

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

  // Make sure LAppAdapter is available globally
  if (!(window as any).getLAppAdapter) {
    console.log('Setting up getLAppAdapter function');
    const { LAppAdapter } = require('./lappadapter');
    (window as any).getLAppAdapter = () => LAppAdapter.getInstance();
  }

  const desktopApi = (window as any).pywebview?.api || (window as any).api;
  if (desktopApi?.setIgnoreMouseEvent || desktopApi?.set_ignore_mouse_event) {
    const setIgnoreMouseEvent = (ignored: boolean) => {
      if (desktopApi.setIgnoreMouseEvent) desktopApi.setIgnoreMouseEvent(ignored);
      else desktopApi.set_ignore_mouse_event(ignored);
    };

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
      const x = view.transformViewX(deviceX);
      const y = view.transformViewY(deviceY);
      const isHit = Boolean(model.anyhitTest?.(x, y) || model.isHitOnModel?.(x, y));
      setIgnoreMouseEvent(!isHit);
    };

    window.addEventListener("pointermove", (e) => updateMousePassthrough(e.clientX, e.clientY), { passive: true });
    setIgnoreMouseEvent(true);
  }
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
