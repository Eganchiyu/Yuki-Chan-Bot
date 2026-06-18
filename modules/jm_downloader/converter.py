"""文件转换工具 — webp→jpg / PDF 生成 / ZIP 加密打包

无 AstrBot 依赖。
"""
import io
import os
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger("jm_cli.converter")

# ── 常量 ──────────────────────────────────────────────────
PDF_MAX_LONG_EDGE = 2000   # PDF 预处理：长边超过此值等比缩放
JPEG_QUALITY = 100         # JPEG 质量


# ── webp → jpg ────────────────────────────────────────────
def webp_to_jpg_bytes(webp_path: Path, quality: int = JPEG_QUALITY) -> bytes | None:
    """webp 转 JPEG 字节流，失败返回 None"""
    try:
        img = Image.open(str(webp_path))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception as exc:
        logger.warning(f"webp→jpg 失败: {webp_path}: {exc}")
        return None


def convert_to_jpg(src: Path, dst: Path, quality: int = JPEG_QUALITY) -> bool:
    """任意图片转 JPG 文件，成功返回 True"""
    try:
        img = Image.open(str(src))
        if img.mode in ("RGBA", "P", "LA", "RGB"):
            if img.mode != "RGB":
                img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(str(dst), format="JPEG", quality=quality)
        return True
    except Exception as exc:
        logger.warning(f"图片转换失败: {src}: {exc}")
        return False


# ── PDF 生成 ──────────────────────────────────────────────
def _resize_for_pdf(img_path: Path) -> tuple[io.BytesIO, int, int]:
    """预处理图片：长边>2000则缩放，输出 JPEG BytesIO"""
    img = Image.open(str(img_path))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    w, h = img.size
    long_edge = max(w, h)
    if long_edge > PDF_MAX_LONG_EDGE:
        scale = PDF_MAX_LONG_EDGE / long_edge
        w = int(w * scale)
        h = int(h * scale)
        img = img.resize((w, h), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    buf.seek(0)
    return buf, w, h


def images_to_pdf(image_paths: list[Path], pdf_path: str | Path) -> bool:
    """图片列表 → PDF 文件，返回是否成功"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    valid = [p for p in image_paths if p.exists()]
    if not valid:
        logger.warning("images_to_pdf: 无有效图片")
        return False

    try:
        first_buf, first_w, first_h = _resize_for_pdf(valid[0])
        c = canvas.Canvas(str(pdf_path), pagesize=(first_w, first_h))

        reader = ImageReader(first_buf)
        c.drawImage(reader, 0, 0, width=first_w, height=first_h)
        c.showPage()

        for i, img_path in enumerate(valid[1:], start=1):
            try:
                buf, w, h = _resize_for_pdf(img_path)
                c.setPageSize((w, h))
                reader = ImageReader(buf)
                c.drawImage(reader, 0, 0, width=w, height=h)
                if i < len(valid) - 1:
                    c.showPage()
            except Exception as exc:
                logger.warning(f"跳过损坏图片 {img_path}: {exc}")
                continue

        c.save()
        size_mb = os.path.getsize(str(pdf_path)) / 1024 / 1024
        logger.info(f"✅ PDF 生成: {pdf_path} ({len(valid)}页, {size_mb:.1f}MB)")
        return True

    except Exception as exc:
        logger.error(f"❌ PDF 生成失败: {exc}")
        return False


# ── ZIP 加密打包 ──────────────────────────────────────────
def images_to_zip(
    image_paths: list[Path],
    zip_path: str | Path,
    password: str = "",
) -> bool:
    """图片列表 → ZIP（webp自动转jpg，可选加密），返回是否成功"""
    import shutil
    import zipfile

    valid = [p for p in image_paths if p.exists()]
    if not valid:
        logger.warning("images_to_zip: 无有效图片")
        return False

    try:
        temp_dir = Path(zip_path).parent / "_zip_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        converted: list[str] = []

        for i, img_path in enumerate(valid):
            jpg_name = f"{i+1:04d}.jpg"
            jpg_file = temp_dir / jpg_name

            suffix = img_path.suffix.lower()
            if suffix == ".webp":
                jpg_bytes = webp_to_jpg_bytes(img_path)
                if jpg_bytes is None:
                    jpg_file.write_bytes(img_path.read_bytes())
                else:
                    jpg_file.write_bytes(jpg_bytes)
            else:
                if not convert_to_jpg(img_path, jpg_file):
                    jpg_file.write_bytes(img_path.read_bytes())

            converted.append(str(jpg_file))

        # 无密码时用标准 zipfile（兼容性好），有密码时用 pyminizip
        if password:
            import pyminizip
            pyminizip.compress_multiple(converted, [], str(zip_path), password, 5)
        else:
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for fpath in converted:
                    zf.write(fpath, os.path.basename(fpath))

        # 清理临时文件
        try:
            shutil.rmtree(str(temp_dir))
        except Exception:
            pass

        size_mb = os.path.getsize(str(zip_path)) / 1024 / 1024
        logger.info(f"✅ ZIP 生成: {zip_path} ({len(converted)}文件, {size_mb:.1f}MB, {'加密' if password else '无加密'})")
        return True

    except Exception as exc:
        logger.error(f"❌ ZIP 生成失败: {exc}")
        return False
