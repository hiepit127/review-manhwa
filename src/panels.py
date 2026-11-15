"""Cắt trang manhwa dọc thành từng panel bằng khoảng trắng giữa các khung."""

from __future__ import annotations

import os

import cv2
import numpy as np

from src.images import imread, limit_width, write_png


def is_blank(image) -> bool:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if float(gray.std()) < 5:
        return True
    edges = cv2.Canny(gray, 80, 160)
    return float((edges > 0).mean()) < 0.003 and float(gray.std()) < 20


def _smooth(values: np.ndarray) -> np.ndarray:
    if values.size < 5:
        return values
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float64)
    kernel /= kernel.sum()
    return np.convolve(values, kernel, mode="same")


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    if mask.size == 0:
        return []
    padded = np.pad(mask.astype(np.int8), (1, 1))
    diff = np.diff(padded)
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends) if end - start >= min_len]


def _gutter_mask(mean: np.ndarray, std: np.ndarray, border: float) -> np.ndarray:
    flat = std < 6.0
    like_gutter = (mean >= 245) | (mean <= 12) | (np.abs(mean - border) <= 8)
    return flat & like_gutter


def _content_segments(gutter: np.ndarray, min_gutter: int, min_content: int) -> list[tuple[int, int]]:
    length = int(gutter.shape[0])
    gaps = _runs(gutter, min_gutter)
    if not gaps:
        return [(0, length)]
    segments = []
    cursor = 0
    for start, end in gaps:
        if start - cursor >= min_content:
            segments.append((cursor, start))
        cursor = end
    if length - cursor >= min_content:
        segments.append((cursor, length))
    return segments or [(0, length)]


def _profile(gray: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    return _smooth(gray.mean(axis=axis)), _smooth(gray.std(axis=axis))


def find_panels(image) -> list[tuple[int, int, int, int]]:
    """Trả về hộp (x0, y0, x1, y1) từ trên xuống dưới, trái sang phải."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    border = float(np.median(np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])))
    row_mean, row_std = _profile(gray, axis=1)
    min_gutter = min(28, max(8, height // 250))
    rows = _content_segments(_gutter_mask(row_mean, row_std, border), min_gutter, 70)
    if len(rows) == 1 and height > width * 2.2:
        rows = _content_segments(_gutter_mask(row_mean, row_std, border), 6, 70)

    boxes: list[tuple[int, int, int, int]] = []
    min_col = max(48, int(width * 0.12))
    min_col_gutter = min(28, max(8, width // 250))
    for y0, y1 in rows:
        band = gray[y0:y1]
        col_mean, col_std = _profile(band, axis=0)
        columns = _content_segments(_gutter_mask(col_mean, col_std, border), min_col_gutter, min_col)
        if len(columns) <= 1:
            boxes.append((0, y0, width, y1))
            continue
        for x0, x1 in columns:
            boxes.append((x0, y0, x1, y1))

    if len(boxes) > 40:
        return [(0, 0, width, height)]
    if len(boxes) == 1:
        x0, y0, x1, y1 = boxes[0]
        if (x1 - x0) * (y1 - y0) > 0.92 * width * height:
            return [(0, 0, width, height)]
    return boxes


def order_boxes(boxes: list[tuple[int, int, int, int]], rtl: bool) -> list[tuple[int, int, int, int]]:
    rows: list[list[tuple[int, int, int, int]]] = []
    for box in sorted(boxes, key=lambda item: (item[1], item[0])):
        if not rows or abs(box[1] - rows[-1][0][1]) > 40:
            rows.append([box])
        else:
            rows[-1].append(box)
    ordered = []
    for row in rows:
        row.sort(key=lambda item: item[0], reverse=rtl)
        ordered.extend(row)
    return ordered


def slice_pages(page_paths: list[str], panels_dir: str, enabled: bool, rtl: bool, log) -> list[str]:
    os.makedirs(panels_dir, exist_ok=True)
    saved = []
    counter = 1
    for page_path in page_paths:
        image = imread(page_path)
        if image is None:
            log(f"Không đọc được ảnh {os.path.basename(page_path)}")
            continue
        if is_blank(image):
            log(f"Bỏ trang trống {os.path.basename(page_path)}")
            continue
        height, width = image.shape[:2]
        if not enabled:
            crops = [image]
        else:
            boxes = order_boxes(find_panels(image), rtl=rtl)
            if len(boxes) > 40:
                log(f"{os.path.basename(page_path)} bị cắt vụn ({len(boxes)} mảnh), giữ cả trang")
                boxes = [(0, 0, width, height)]
            crops = []
            for x0, y0, x1, y1 in boxes:
                x0 = max(0, x0 - 4)
                y0 = max(0, y0 - 4)
                x1 = min(width, x1 + 4)
                y1 = min(height, y1 + 4)
                crop = image[y0:y1, x0:x1]
                if crop.size == 0 or min(crop.shape[:2]) < 64:
                    continue
                crops.append(crop)
            if len(crops) <= 1:
                crops = [image]
            else:
                log(f"{os.path.basename(page_path)} → {len(crops)} panel")
        for crop in crops:
            out = os.path.join(panels_dir, f"panel_{counter:04d}.png")
            write_png(limit_width(crop, 1400), out)
            saved.append(out)
            counter += 1
    return saved
