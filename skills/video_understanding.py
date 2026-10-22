# maid_deps: opencv-python pillow pyyaml requests
import argparse
import base64
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import requests
import yaml
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
MAX_VIDEO_SIZE_MB = 100
MAX_VIDEO_SECONDS = 120
MIN_FRAME_COUNT = 4
MAX_FRAME_COUNT = 4
MAX_PROMPT_CHARS = 800
MAX_IMAGE_BYTES = 2_500_000
REQUEST_TIMEOUT_SECONDS = 60
GRID_COLUMNS = 2
GRID_ROWS = 2
CELL_SIZE = (512, 288)
JPEG_QUALITIES = (82, 76, 70, 64, 58)


class VideoUnderstandingError(Exception):
    """视频理解 skill 的可预期错误。"""


def _load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise VideoUnderstandingError(f"配置文件不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    api = data.get("api") or {}
    model = data.get("model") or {}
    base_url = (api.get("image_process_url") or "").rstrip("/")
    api_key = api.get("image_process_api_key") or ""
    vision_model = model.get("vision") or ""

    if not base_url:
        raise VideoUnderstandingError("未配置 api.image_process_url")
    if not api_key:
        raise VideoUnderstandingError("未配置 api.image_process_api_key")
    if not vision_model:
        raise VideoUnderstandingError("未配置 model.vision")

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": vision_model,
    }


def _validate_video(video_path: Path) -> None:
    if not video_path.exists():
        raise VideoUnderstandingError(f"视频不存在: {video_path}")
    if not video_path.is_file():
        raise VideoUnderstandingError(f"路径不是文件: {video_path}")
    if video_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise VideoUnderstandingError(f"不支持的视频格式: {video_path.suffix}，允许: {allowed}")

    size_mb = video_path.stat().st_size / 1024 / 1024
    if size_mb > MAX_VIDEO_SIZE_MB:
        raise VideoUnderstandingError(
            f"视频过大: {size_mb:.1f}MB，限制 {MAX_VIDEO_SIZE_MB}MB"
        )


def _open_video(video_path: Path) -> Tuple[cv2.VideoCapture, Dict[str, Any]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise VideoUnderstandingError("无法打开视频，可能是编码不受支持或文件损坏")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    if frame_count <= 0 or fps <= 0:
        cap.release()
        raise VideoUnderstandingError("无法读取视频帧数或 FPS")

    duration = frame_count / fps
    if duration > MAX_VIDEO_SECONDS:
        cap.release()
        raise VideoUnderstandingError(
            f"视频过长: {duration:.1f}秒，限制 {MAX_VIDEO_SECONDS}秒"
        )

    info = {
        "duration_seconds": round(duration, 2),
        "fps": round(fps, 2),
        "frame_count": frame_count,
        "width": width,
        "height": height,
    }
    return cap, info


def _sample_frame_indices(frame_count: int, sample_count: int) -> List[int]:
    sample_count = max(MIN_FRAME_COUNT, min(sample_count, MAX_FRAME_COUNT))
    if frame_count <= sample_count:
        return list(range(frame_count))

    # 避开首尾黑屏高发区域，在 8% 到 92% 区间均匀采样。
    start = int(frame_count * 0.08)
    end = max(start + sample_count, int(frame_count * 0.92) - 1)
    step = (end - start) / max(sample_count - 1, 1)
    return [min(frame_count - 1, int(round(start + i * step))) for i in range(sample_count)]


def _frame_to_image(frame: Any) -> Image.Image:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _fit_to_cell(image: Image.Image, cell_size: Tuple[int, int]) -> Image.Image:
    cell_w, cell_h = cell_size
    fitted = Image.new("RGB", cell_size, (18, 18, 18))
    image.thumbnail(cell_size, Image.Resampling.LANCZOS)
    left = (cell_w - image.width) // 2
    top = (cell_h - image.height) // 2
    fitted.paste(image, (left, top))
    return fitted


def _draw_label(image: Image.Image, label: str) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    padding = 6
    bbox = draw.textbbox((0, 0), label, font=font)
    box_w = bbox[2] - bbox[0] + padding * 2
    box_h = bbox[3] - bbox[1] + padding * 2
    draw.rectangle((0, 0, box_w, box_h), fill=(0, 0, 0))
    draw.text((padding, padding), label, fill=(255, 255, 255), font=font)


def _build_grid(frames: List[Tuple[float, Image.Image]]) -> Image.Image:
    grid_w = CELL_SIZE[0] * GRID_COLUMNS
    grid_h = CELL_SIZE[1] * GRID_ROWS
    grid = Image.new("RGB", (grid_w, grid_h), (18, 18, 18))

    for idx, (timestamp, frame_image) in enumerate(frames[: MAX_FRAME_COUNT]):
        cell = _fit_to_cell(frame_image, CELL_SIZE)
        _draw_label(cell, f"#{idx + 1}  {timestamp:.1f}s")
        x = (idx % GRID_COLUMNS) * CELL_SIZE[0]
        y = (idx // GRID_COLUMNS) * CELL_SIZE[1]
        grid.paste(cell, (x, y))

    return grid


def _encode_jpeg_under_limit(image: Image.Image) -> str:
    last_data = b""
    for quality in JPEG_QUALITIES:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()
        last_data = data
        if len(data) <= MAX_IMAGE_BYTES:
            return base64.b64encode(data).decode("ascii")

    raise VideoUnderstandingError(
        f"采样图压缩后仍过大: {len(last_data)} bytes，限制 {MAX_IMAGE_BYTES} bytes"
    )


def _extract_video_grid(video_path: Path, sample_count: int) -> Tuple[Dict[str, Any], str]:
    cap, info = _open_video(video_path)
    frames: List[Tuple[float, Image.Image]] = []

    try:
        indices = _sample_frame_indices(info["frame_count"], sample_count)
        for frame_index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            timestamp = frame_index / max(info["fps"], 1)
            frames.append((timestamp, _frame_to_image(frame)))
    finally:
        cap.release()

    if len(frames) < MIN_FRAME_COUNT:
        raise VideoUnderstandingError(f"有效采样帧不足: {len(frames)}")

    grid = _build_grid(frames)
    image_b64 = _encode_jpeg_under_limit(grid)
    info["sampled_timestamps"] = [round(item[0], 2) for item in frames]
    info["sampled_frames"] = len(frames)
    return info, image_b64


def _build_prompt(video_info: Dict[str, Any], question: Optional[str]) -> str:
    user_question = (question or "请概括这个视频的主体信息、场景、人物/物体、动作和可能的事件。").strip()
    if len(user_question) > MAX_PROMPT_CHARS:
        user_question = user_question[:MAX_PROMPT_CHARS]

    info_text = json.dumps(video_info, ensure_ascii=False)
    return (
        "你会看到一个由视频均匀采样帧拼接成的四宫格。"
        "请基于可见画面回答，不要编造未出现的信息；如果信息不足请明确说明。\n"
        f"视频信息: {info_text}\n"
        f"用户问题: {user_question}"
    )


def _call_vision_model(config: Dict[str, Any], image_b64: str, prompt: str) -> str:
    url = f"{config['base_url']}/chat/completions"
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise VideoUnderstandingError(f"视觉模型请求失败: {e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:300].replace(config["api_key"], "***")
        raise VideoUnderstandingError(f"视觉模型返回错误 HTTP {resp.status_code}: {detail}")

    try:
        data = resp.json()
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise VideoUnderstandingError(f"视觉模型响应格式异常: {resp.text[:300]}") from e


def understand_video(
    video_path: str,
    question: Optional[str] = None,
    config_path: str = str(DEFAULT_CONFIG_PATH),
    sample_count: int = MAX_FRAME_COUNT,
) -> str:
    """采样视频帧并调用视觉模型理解视频内容。"""
    path = Path(video_path).expanduser().resolve()
    cfg_path = Path(config_path).expanduser().resolve()

    _validate_video(path)
    config = _load_config(cfg_path)
    video_info, image_b64 = _extract_video_grid(path, sample_count)
    prompt = _build_prompt(video_info, question)
    answer = _call_vision_model(config, image_b64, prompt)

    if not answer:
        raise VideoUnderstandingError("视觉模型返回空内容")

    return (
        "视频信息:\n"
        f"- 时长: {video_info['duration_seconds']}秒\n"
        f"- 分辨率: {video_info['width']}x{video_info['height']}\n"
        f"- FPS: {video_info['fps']}\n"
        f"- 采样时间点: {video_info['sampled_timestamps']}\n\n"
        f"视觉理解结果:\n"
        f"{answer}"
    )

def main() -> int:
    parser = argparse.ArgumentParser(description="视频理解 skill：采样视频帧并调用视觉模型回答问题")
    parser.add_argument("video_path", help="视频文件路径")
    parser.add_argument("question", nargs="?", default=None, help="可选问题，默认概括视频主体信息")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径")
    args = parser.parse_args()

    try:
        print(understand_video(args.video_path, question=args.question, config_path=args.config))
        return 0
    except VideoUnderstandingError as e:
        print(f"视频理解失败: {e}")
        return 2
    except Exception as e:
        print(f"视频理解失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
