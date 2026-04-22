import asyncio
import cv2
import numpy as np
from mss import mss
import time
from utils.logger import get_logger

try:
    from rapidocr_onnxruntime import RapidOCR
    # Initialize OCR engine once (lazy-load or load at startup)
    ocr_engine = RapidOCR()
except ImportError:
    ocr_engine = None

logger = get_logger("retina_prefrontal")

# 全局队列，用于前额叶将处理后的图像推送到注意力循环
# 队列存放元组：(timestamp, resized_image)
image_queue = asyncio.Queue(maxsize=3)


def capture_and_resize_sync():
    """
    同步函数：使用 mss 截取屏幕，保持彩色并缩放到足以看清文字的分辨率。
    """
    try:
        with mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = np.array(sct_img)

            # 1. 🌟 保留颜色：去掉转灰度图的操作，改为转为标准的 RGB
            # 颜色对于识别报错（红色）、代码高亮和 UI 元素非常重要
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

            # 2. 🌟 提高分辨率：不要缩放到 640x480
            # 建议保持 1280 宽度（720p 级别），这是看清代码文字的底线
            h, w = img_rgb.shape[:2]
            target_width = 1280
            target_height = int(h * (target_width / w))

            img_resized = cv2.resize(img_rgb, (target_width, target_height), interpolation=cv2.INTER_AREA)

            return img_resized
    except Exception as e:
        logger.error(f"[Prefrontal] Failed to capture screen: {e}")
        return None

def compute_mse_sync(img1, img2):
    """
    同步函数：计算两张图像的均方误差 (MSE)。
    MSE 越大，差异越大。
    """
    if img1 is None or img2 is None:
        return 0.0
    err = np.sum((img1.astype("float") - img2.astype("float")) ** 2)
    err /= float(img1.shape[0] * img1.shape[1])
    return err

def extract_ocr_sync(image: np.ndarray) -> str:
    """
    同步函数：调用 RapidOCR 提取图片中的文字。
    """
    if ocr_engine is None:
        return "mock_ocr_text_placeholder"
    try:
        # RapidOCR requires BGR or RGB array, since we resized grey, let's convert back if needed,
        # but RapidOCR should handle numpy arrays directly (usually reads better from BGR/RGB).
        # We'll just pass the image. If it's single channel we might need to convert it.
        if len(image.shape) == 2:
            img_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            img_bgr = image

        result, _ = ocr_engine(img_bgr)
        if result:
            # result is a list of tuples: [[points], text, score]
            texts = [item[1] for item in result]
            return "\n".join(texts)
        return ""
    except Exception as e:
        logger.error(f"[Prefrontal] OCR extract failed: {e}")
        return ""

async def ocr_extract(image: np.ndarray) -> str:
    """
    异步函数：将 OCR 提取放入线程池防止阻塞
    """
    return await asyncio.to_thread(extract_ocr_sync, image)

async def local_prefrontal_loop(interval: float = 60.0, mse_threshold: float = 2000.0, ocr_check_interval: float = 60.0):
    logger.info("[Prefrontal] Local Prefrontal Cortex loop started.")

    prev_image = None
    last_ocr_time = time.time()
    last_ocr_text = ""

    # --- 🌟 新增：静止状态追踪变量 ---
    static_count = 0
    current_static_threshold = 20  # 初始阈值：连续 20 次不动触发
    MAX_STATIC_THRESHOLD = 320     # 阈值上限，防止无限翻倍
    # ----------------------------------

    while True:
        try:
            curr_image = await asyncio.to_thread(capture_and_resize_sync)

            if curr_image is not None:
                trigger_attention = False
                is_static_trigger = False  # 新增：标记本次是否为“太久没动”触发

                # 1. 快速感知：画面变化检测
                if prev_image is not None:
                    mse = await asyncio.to_thread(compute_mse_sync, prev_image, curr_image)
                    if mse > mse_threshold:
                        logger.debug(f"[Prefrontal] MSE threshold exceeded: {mse:.2f}")
                        trigger_attention = True

                # 2. 定期感知：OCR 变化检测
                current_time = time.time()
                if (current_time - last_ocr_time) >= ocr_check_interval:
                    current_text = await ocr_extract(curr_image)
                    if current_text != last_ocr_text:
                        logger.debug(f"[Prefrontal] OCR change detected.")
                        trigger_attention = True
                    last_ocr_text = current_text
                    last_ocr_time = current_time

                # --- 🌟 新增：时间梯度拉长逻辑 ---
                if trigger_attention:
                    # 画面有真实变化，清空静止计数，将阈值恢复到敏感状态（20）
                    static_count = 0
                    current_static_threshold = 20
                else:
                    # 画面毫无变化，开始累加无聊情绪
                    static_count += 1
                    if static_count >= current_static_threshold:
                        logger.info(f"[Prefrontal] 画面已连续静止 {static_count} 次，触发无聊警报！")
                        trigger_attention = True
                        is_static_trigger = True
                        
                        # 触发后清零计数，并把下一次的阈值翻倍 (时间梯度拉长)
                        static_count = 0
                        current_static_threshold = min(current_static_threshold * 2, MAX_STATIC_THRESHOLD)
                # ----------------------------------

                if trigger_attention:
                    if image_queue.full():
                        try:
                            image_queue.get_nowait()
                            image_queue.task_done()
                        except asyncio.QueueEmpty:
                            pass
                    # 🌟 修改：将 is_static_trigger 标志一起打包送给下游大脑
                    await image_queue.put((current_time, curr_image, is_static_trigger))

                prev_image = curr_image

        except Exception as e:
            logger.error(f"[Prefrontal] Loop exception: {e}")

        import modules.retina_perception.attention as attention_module
        current_interval = attention_module.dynamic_sleep_interval
        await asyncio.sleep(current_interval)