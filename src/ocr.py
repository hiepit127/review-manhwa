"""Đọc chữ trong panel bằng EasyOCR. Model được giải phóng trước khi tải VieNeu."""

from __future__ import annotations

import gc
import os

from src.images import imread


def _cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def read_images(paths: list[str], langs: list[str], use_gpu: bool, log, progress) -> list[str]:
    import cv2
    import easyocr

    languages = [lang for lang in (langs or []) if lang]
    if "en" not in languages:
        languages.append("en")
    gpu = bool(use_gpu and _cuda())
    log(f"OCR {languages}, GPU={gpu}. Lần đầu sẽ tải model nhận dạng.")
    try:
        reader = easyocr.Reader(languages, gpu=gpu, verbose=False)
    except Exception as error:
        if not gpu:
            raise
        log(f"OCR trên GPU lỗi ({error}). Chuyển sang CPU.")
        reader = easyocr.Reader(languages, gpu=False, verbose=False)

    texts = []
    total = max(len(paths), 1)
    try:
        for index, path in enumerate(paths):
            progress((index) / total, desc=f"OCR {index + 1}/{len(paths)}")
            try:
                image = imread(path)
                height, width = image.shape[:2]
                if width > 1280:
                    scale = 1280 / float(width)
                    image = cv2.resize(
                        image,
                        (1280, max(1, int(height * scale))),
                        interpolation=cv2.INTER_AREA,
                    )
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                lines = reader.readtext(rgb, detail=0, paragraph=True)
                if isinstance(lines, str):
                    text = lines
                else:
                    text = "\n".join(str(line) for line in lines)
                texts.append(text.strip())
            except Exception as error:
                log(f"OCR lỗi {os.path.basename(path)}: {error}")
                texts.append("")
    finally:
        del reader
        gc.collect()
        _empty_cache()
    progress(1, desc="OCR xong")
    filled = sum(1 for text in texts if text)
    log(f"Đọc được chữ ở {filled}/{len(texts)} panel")
    return texts
