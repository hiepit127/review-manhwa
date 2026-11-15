"""Đường dẫn gốc của project. Job nằm ngoài mã nguồn, có thể trỏ sang chỗ khác khi test."""

from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def jobs_dir() -> str:
    path = os.environ.get("RM_JOBS_DIR") or os.path.join(ROOT, "jobs")
    os.makedirs(path, exist_ok=True)
    return path


def job_dir(job_id: str) -> str:
    return os.path.join(jobs_dir(), job_id)
