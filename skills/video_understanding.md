# video_understanding：视频理解与问答

## 功能

对本地视频做轻量理解：先读取视频长度、FPS、分辨率、帧数等信息，再在视频中均匀采样 4 帧，拼接为四宫格 JPEG，压缩后发送到配置中的视觉模型，用于概括视频主体信息或回答用户问题。

视觉模型配置来自 `configs/config.yaml`：

- `api.image_process_url`
- `api.image_process_api_key`
- `model.vision`

## 参数

- `video_path` (str): 视频文件路径（必填）
- `question` (str): 可选问题；不传时默认概括视频主体信息、场景、人物/物体、动作和可能事件
- `--config` (str): 可选配置文件路径，默认 `D:/Projects/YukiV6/configs/config.yaml`

## 保护与限制

- 仅允许 `.mp4`、`.mov`、`.mkv`、`.avi`、`.webm`、`.m4v`
- 单个视频最大 `200MB`
- 视频最长 `600` 秒
- 固定采样 `4` 帧并拼接四宫格，避免上传完整视频
- 采样图最大 `2.5MB`，会通过 JPEG 质量逐级压缩
- 用户问题最多保留 `800` 字符
- 视觉模型请求超时 `60` 秒
- 错误输出会脱敏 API Key
- 提示词要求模型只基于可见画面回答，信息不足时明确说明

## 返回

返回视频基础信息、采样时间点和视觉模型生成的概括或问答结果。

## 调用示例

为兼容 Windows 终端默认 GBK 编码，建议运行前设置 `PYTHONIOENCODING=utf-8`，避免中文路径、中文文件名或中文输出触发编码错误。

```bash
set PYTHONIOENCODING=utf-8 && python "D:/Projects/YukiV6/skills/video_understanding.py" "D:/Projects/YukiV6/workspace/姐姐大人的视频.mp4"
set PYTHONIOENCODING=utf-8 && python D:/Projects/YukiV6/skills/video_understanding.py C:/Users/eganc/Desktop/Demo.mp4 "概括主体信息" --config D:/Projects/YukiV6/configs/config.yaml
```

## 依赖

```text
opencv-python pillow pyyaml requests
```
