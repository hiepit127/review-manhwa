"""Đọc và ghi ảnh. OpenCV không mở được webp thì dùng Pillow."""

from __future__ import annotations

import os

import cv2
import numpy as np


def imread(path: str):
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is not None:
        return image
    from PIL import Image

    with Image.open(path) as handle:
        rgb = np.array(handle.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def write_png(image, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not cv2.imwrite(path, image):
        raise RuntimeError(f"Không ghi được ảnh {path}")


def save_png_from_file(src: str, dest: str) -> None:
    from PIL import Image

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with Image.open(src) as handle:
        handle.convert("RGB").save(dest, "PNG")


def limit_width(image, max_width: int = 1400):
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / float(width)
    target = (max_width, max(1, int(round(height * scale))))
    return cv2.resize(image, target, interpolation=cv2.INTER_AREA)
