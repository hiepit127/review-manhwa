"""Sửa danh sách panel của một job đã tách, rồi ghi lại manifest trên Drive."""

from __future__ import annotations

import os
import shutil

from src.jobs import job_abs, load_job, save_job
from src.panels import slice_pages


def _reindex(panels: list[dict]) -> None:
    for index, panel in enumerate(panels):
        panel["index"] = index


def split_existing(job_id: str, rtl: bool, log) -> dict:
    """Cắt các trang đã lưu trong job thành panel. Chưa đọc chữ."""
    job = load_job(job_id)
    pages = [job_abs(job, relative) for relative in (job.get("pages") or [])]
    pages = [path for path in pages if os.path.isfile(path)]
    if not pages:
        raise RuntimeError("Chưa có trang. Hãy lấy truyện hoặc tải ảnh trước.")
    panel_paths = slice_pages(pages, os.path.join(job["dir"], "panels"), True, bool(rtl), log)
    if not panel_paths:
        raise RuntimeError("Không còn panel sau khi bỏ trang trống.")
    job["panels"] = [
        {"index": index, "image": os.path.relpath(path, job["dir"]), "ocr": ""}
        for index, path in enumerate(panel_paths)
    ]
    job["scenes"] = []
    job["removed"] = []
    save_job(job)
    log(f"Đã tách {len(job['panels'])} panel. Có thể xóa, thêm hoặc đổi thứ tự.")
    return job


def remove_panel(job_id: str, number: int) -> dict:
    job = load_job(job_id)
    panels = list(job.get("panels") or [])
    index = int(number) - 1
    if index < 0 or index >= len(panels):
        raise RuntimeError(f"Không có panel số {int(number)}.")
    removed = panels.pop(index)
    job.setdefault("removed", []).append({"image": removed.get("image") or "", "ocr": removed.get("ocr") or ""})
    _reindex(panels)
    job["panels"] = panels
    job["scenes"] = []
    save_job(job)
    return job


def restore_panel(job_id: str) -> dict:
    job = load_job(job_id)
    removed = list(job.get("removed") or [])
    if not removed:
        raise RuntimeError("Không còn panel đã xóa để thêm lại.")
    item = removed.pop()
    if not item.get("image") or not os.path.isfile(job_abs(job, item["image"])):
        job["removed"] = removed
        save_job(job)
        raise RuntimeError("File panel đã xóa không còn trên đĩa.")
    panels = list(job.get("panels") or [])
    panels.append({"index": len(panels), "image": item["image"], "ocr": item.get("ocr") or ""})
    _reindex(panels)
    job["panels"] = panels
    job["removed"] = removed
    job["scenes"] = []
    save_job(job)
    return job


def move_panel(job_id: str, number: int, delta: int) -> dict:
    job = load_job(job_id)
    panels = list(job.get("panels") or [])
    index = int(number) - 1
    target = index + int(delta)
    if index < 0 or index >= len(panels) or target < 0 or target >= len(panels):
        raise RuntimeError("Không đổi được thứ tự panel này.")
    panels[index], panels[target] = panels[target], panels[index]
    _reindex(panels)
    job["panels"] = panels
    job["scenes"] = []
    save_job(job)
    return job


def add_panel_files(job_id: str, paths: list[str]) -> dict:
    job = load_job(job_id)
    panels = list(job.get("panels") or [])
    added = 0
    dest_dir = os.path.join(job["dir"], "panels")
    os.makedirs(dest_dir, exist_ok=True)
    for source in paths:
        if not source or not os.path.isfile(source):
            continue
        name = f"extra_{len(panels) + 1:04d}{os.path.splitext(source)[1].lower() or '.png'}"
        dest = os.path.join(dest_dir, name)
        shutil.copyfile(source, dest)
        panels.append({"index": len(panels), "image": os.path.relpath(dest, job["dir"]), "ocr": ""})
        added += 1
    if not added:
        raise RuntimeError("Chưa chọn ảnh để thêm.")
    _reindex(panels)
    job["panels"] = panels
    job["scenes"] = []
    save_job(job)
    return job
