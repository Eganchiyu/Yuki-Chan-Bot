/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

export let canvas: HTMLCanvasElement | null = null;
export let gl: WebGLRenderingContext | null = null;
export let s_instance: LAppGlManager | null = null;
/**
 * Cubism SDKのサンプルで使用するWebGLを管理するクラス
 */
export class LAppGlManager {
  /**
   * クラスのインスタンス（シングルトン）を返す。
   * インスタンスが生成されていない場合は内部でインスタンスを生成する。
   *
   * @return クラスのインスタンス
   */
  public static getInstance(): LAppGlManager {
    if (s_instance == null) {
      s_instance = new LAppGlManager();
    }

    return s_instance;
  }

  /**
   * クラスのインスタンス（シングルトン）を解放する。
   */
  public static releaseInstance(): void {
    if (s_instance != null) {
      s_instance.release();
    }

    s_instance = null;
  }

  constructor() {
    // Use existing canvas instead of creating a new one
    canvas = document.getElementById('canvas') as HTMLCanvasElement;
    // canvas = document.createElement("canvas");

    if (!canvas) {
      console.warn("Canvas element not found during LAppGlManager initialization");
      return;
    }

     gl = canvas.getContext("webgl2", {
       alpha: true,
       premultipliedAlpha: false,
       preserveDrawingBuffer: true,
     });

     if (!gl) {
       // gl初期化失敗
       alert("Cannot initialize WebGL. This browser does not support.");
       gl = null;

       document.body.innerHTML =
         "This browser does not support the <code>&lt;canvas&gt;</code> element.";
     }
  }

  /**
   * 解放する。
   */
  public release(): void {}
}
