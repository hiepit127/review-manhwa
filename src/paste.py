"""Lưu từng trang người dùng dán từ clipboard, theo đúng thứ tự bấm thêm."""

from __future__ import annotations

import os
import uuid

import numpy as np

from src.images import save_png_from_file, write_png
from src.paths import jobs_dir
from src.textutil import file_path


def _batch_dir(pages: list[str]) -> str:
    if pages:
        return os.path.dirname(pages[0])
    folder = os.path.join(jobs_dir(), "_paste", uuid.uuid4().hex[:8])
    os.makedirs(folder, exist_ok=True)
    return folder


def _write_image(image, dest: str) -> None:
    path = file_path(image)
    if path and os.path.isfile(path):
        save_png_from_file(path, dest)
        return
    if hasattr(image, "save") and hasattr(image, "mode"):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        image.convert("RGB").save(dest, "PNG")
        return
    array = np.asarray(image)
    if array.ndim == 3 and array.shape[2] >= 3:
        import cv2

        bgr = cv2.cvtColor(array[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2BGR)
        write_png(bgr, dest)
        return
    raise RuntimeError("Không đọc được ảnh vừa dán.")


def add_pasted_page(image, pages: list[str] | None) -> list[str]:
    if image is None or image == "":
        raise RuntimeError("Hãy dán một trang vào ô ảnh trước.")
    stored = list(pages or [])
    folder = _batch_dir(stored)
    dest = os.path.join(folder, f"page_{len(stored) + 1:04d}.png")
    _write_image(image, dest)
    stored.append(dest)
    return stored


def drop_last_page(pages: list[str] | None) -> list[str]:
    stored = list(pages or [])
    if not stored:
        return []
    last = stored.pop()
    if os.path.isfile(last):
        os.remove(last)
    return stored


def clear_pages(pages: list[str] | None) -> list[str]:
    stored = list(pages or [])
    folder = os.path.dirname(stored[0]) if stored else ""
    for path in stored:
        if os.path.isfile(path):
            os.remove(path)
    if folder and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
    return []
