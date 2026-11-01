# Open-LLM-VTuber Live2D 可复用代码

这里存放从 `D:\Projects\Open-LLM-VTuber` 抽出来的 Live2D 渲染/通信相关代码。

目标不是直接运行原项目，而是把可复用部分留作桌宠项目的素材库。

## 目录

```text
frontend/vendor/open-llm-vtuber-live2d/
  WebSDK/src/                 # Cubism SDK 示例封装，真正的 Live2D 渲染层
  hooks/canvas/               # React hooks：模型加载、缩放、表情
  hooks/utils/use-audio-task.ts# 音频播放 + 唇同步 + 表情触发
  context/                    # modelInfo 状态管理
  components/canvas/          # Live2D canvas 组件
  services/                   # 原项目 WebSocket handler，偏重，仅作参考
  public/libs/                # live2d.min.js / live2dcubismcore.min.js
  examples/model_dict.example.json
```

## 最值得复用的文件

1. `WebSDK/src/`

这是 Live2D/Cubism 的渲染封装。

主要入口：

- `main.ts`：初始化入口，导出 `initializeLive2D`
- `lappdefine.ts`：模型路径配置，尤其是 `updateModelConfig()`
- `lappdelegate.ts`：WebGL 初始化和 requestAnimationFrame 渲染主循环
- `lapplive2dmanager.ts`：模型实例管理，加载 `.model3.json`
- `lappmodel.ts`：表情、motion、lip sync 等模型行为
- `lappadapter.ts`：对外适配层，提供 getModel/setExpression 等方法

2. `hooks/canvas/use-live2d-model.ts`

负责：

- 解析模型 URL
- 调用 `updateModelConfig()`
- release 旧模型并重新 `initializeLive2D()`
- 鼠标拖拽模型
- 点击触发 tap motion
- 暴露 `window.Live2DDebug`

3. `hooks/canvas/use-live2d-expression.ts`

负责：

- 按 expression 名称设置表情
- 按 expression 索引设置表情
- idle 时恢复默认表情

4. `hooks/canvas/use-live2d-resize.ts`

负责：

- canvas 自适应窗口
- 滚轮缩放
- DPR 适配

5. `hooks/utils/use-audio-task.ts`

负责：

- 播放后端发来的 base64 wav
- 调用 Live2D lip sync：`model._wavFileHandler.start(audioDataUrl)`
- 播放时设置表情：`setExpression(expressions[0], adapter)`
- 播放时触发 `Talk` motion

## 最小接入思路

如果你要新做一个桌宠，不建议直接照搬原前端全套 Context。建议这样拆：

```text
React/Electron/Tauri 前端
  ├─ 一个 canvas: <canvas id="canvas" />
  ├─ 拷贝 WebSDK/src
  ├─ 拷贝 use-live2d-model/use-live2d-expression/use-live2d-resize
  ├─ 自己维护一个 modelInfo state
  └─ 后端/主进程只发 modelInfo、audio、expression
```

## modelInfo 格式

前端需要收到类似这样的对象：

```json
{
  "name": "mao_pro",
  "url": "http://127.0.0.1:8000/live2d-models/mao_pro/runtime/mao_pro.model3.json",
  "kScale": 1.0,
  "initialXshift": 0,
  "initialYshift": 0,
  "idleMotionGroupName": "Idle",
  "defaultEmotion": 0,
  "emotionMap": {
    "neutral": 0,
    "joy": 3,
    "sadness": 1,
    "anger": 2
  },
  "tapMotions": {
    "HitAreaHead": { "": 1 },
    "HitAreaBody": { "": 1 }
  },
  "pointerInteractive": true,
  "scrollToResize": true
}
```

注意：

- 原项目后端发的是相对路径 `/live2d-models/...`，前端再拼 `baseUrl`。
- 如果你自己做项目，可以直接发完整 URL，省掉拼接逻辑。

## 前端通信协议

### 1. 切换/加载模型

```json
{
  "type": "set-model-and-conf",
  "model_info": { ...modelInfo },
  "conf_name": "default",
  "conf_uid": "default"
}
```

前端处理逻辑在：

```text
services/websocket-handler.tsx
```

但这个文件依赖很多原项目 Context。建议只参考里面这段逻辑：

```ts
case 'set-model-and-conf':
  setModelInfo(message.model_info)
  break
```

### 2. 播放音频 + 表情

```json
{
  "type": "audio",
  "audio": "base64 wav...",
  "volumes": [],
  "slice_length": 0,
  "display_text": {
    "text": "你好呀",
    "name": "Yuki",
    "avatar": ""
  },
  "actions": {
    "expressions": [3]
  }
}
```

前端处理逻辑核心在：

```text
hooks/utils/use-audio-task.ts
```

关键代码：

```ts
setExpression(expressions[0], lappAdapter)
model.startRandomMotion("Talk", LAppDefine.PriorityNormal)
model._wavFileHandler.start(audioDataUrl)
```

### 3. 控制状态

```json
{"type": "control", "text": "conversation-chain-start"}
{"type": "control", "text": "conversation-chain-end"}
```

桌宠项目里可选，不一定需要。

## Python 侧消息构造

我放了一个极简 helper：

```text
liveyuki_l2d/protocol.py
```

示例：

```python
from liveyuki_l2d.protocol import set_model_message, audio_message

model_msg = set_model_message({
    "name": "mao_pro",
    "url": "http://127.0.0.1:8000/live2d-models/mao_pro/runtime/mao_pro.model3.json",
    "kScale": 1.0,
    "initialXshift": 0,
    "initialYshift": 0,
    "emotionMap": {"neutral": 0, "joy": 3},
})

say_msg = audio_message(
    audio_wav_path="cache/hello.wav",
    text="你好呀",
    expression=3,
    speaker_name="Yuki",
)
```

## 依赖注意

原代码是 React + TypeScript + Electron 环境，不能直接被 Python 项目 import。

如果你新建前端，至少需要：

```bash
npm install react react-dom
```

Cubism SDK 相关 alias 需要配置：

```ts
// vite/tsconfig alias，大意如下
'@framework': './frontend/vendor/open-llm-vtuber-live2d/WebSDK/Framework/src'
'@cubismsdksamples/main': './frontend/vendor/open-llm-vtuber-live2d/WebSDK/src/main.ts'
```

但当前只复制了 `WebSDK/src`，还没有复制完整 `Framework/` 和 `Core/`。
如果后续要真的跑起来，需要再从原项目复制：

```text
D:\Projects\Open-LLM-VTuber\frontend\src\renderer\WebSDK\Core
D:\Projects\Open-LLM-VTuber\frontend\src\renderer\WebSDK\Framework
```

我这次没有默认复制它们，因为体积和授权文件较多；等确定要做前端工程时再搬更干净。

## 推荐改造方式

不要直接用原项目 `websocket-handler.tsx`，它耦合了聊天历史、VAD、背景、群聊、浏览器工具等。

建议自己写一个小 handler：

```ts
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)

  if (msg.type === 'set-model-and-conf') {
    setModelInfo(msg.model_info)
  }

  if (msg.type === 'audio') {
    addAudioTask({
      audioBase64: msg.audio || '',
      volumes: msg.volumes || [],
      sliceLength: msg.slice_length || 0,
      displayText: msg.display_text || null,
      expressions: msg.actions?.expressions || null,
    })
  }
}
```

## 一句话结论

这次复制的代码不是成品应用，而是 Live2D 桌宠渲染材料包。

最先研究这三个就够了：

1. `WebSDK/src/lappdefine.ts`
2. `hooks/canvas/use-live2d-model.ts`
3. `hooks/utils/use-audio-task.ts`
