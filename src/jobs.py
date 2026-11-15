"""Lưu trạng thái một lần dựng video. API key không được ghi vào manifest."""

from __future__ import annotations

import json
import os
import time
import uuid

from src.paths import job_dir, jobs_dir
from src.textutil import cell_text

PANEL_HEADERS = ["Panel", "Hội thoại OCR"]
SCENE_HEADERS = ["Cảnh", "Panel", "Hội thoại OCR", "Lời review"]


def new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def save_job(job: dict) -> None:
    folder = job_dir(job["id"])
    os.makedirs(folder, exist_ok=True)
    payload = {key: value for key, value in job.items() if key != "dir"}
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_job(job_id: str) -> dict:
    path = os.path.join(jobs_dir(), job_id, "manifest.json")
    if not os.path.isfile(path):
        raise FileNotFoundError("Hãy tách panel trước. Chưa có job để tiếp tục.")
    with open(path, encoding="utf-8") as handle:
        job = json.load(handle)
    job["dir"] = job_dir(job_id)
    return job


def job_abs(job: dict, relative: str) -> str:
    if os.path.isabs(relative):
        return relative
    return os.path.join(job["dir"], relative)


def panels_to_table(panels: list[dict]) -> list[list]:
    rows = []
    for panel in panels:
        ocr = panel.get("ocr") or ""
        if len(ocr) > 300:
            ocr = ocr[:300] + "…"
        rows.append([panel["index"] + 1, ocr])
    return rows


def scenes_to_table(scenes: list[dict]) -> list[list]:
    rows = []
    for scene in scenes:
        indexes = scene.get("panel_indexes") or []
        if not indexes:
            label = ""
        elif len(indexes) == 1:
            label = str(indexes[0] + 1)
        else:
            label = f"{indexes[0] + 1}-{indexes[-1] + 1}"
        ocr = scene.get("ocr") or ""
        if len(ocr) > 500:
            ocr = ocr[:500] + "…"
        rows.append([scene["id"], label, ocr, scene.get("narration") or ""])
    return rows


def table_rows(table) -> list[list[str]]:
    if table is None:
        return []
    if hasattr(table, "fillna"):
        data = table.fillna("").values.tolist()
    else:
        data = list(table)
    rows = []
    for row in data:
        if isinstance(row, dict):
            values = [row.get(header, "") for header in SCENE_HEADERS]
        else:
            values = list(row)
        text = [cell_text(value) for value in values]
        if text == SCENE_HEADERS or text == PANEL_HEADERS:
            continue
        rows.append(text)
    return rows


def apply_narrations(scenes: list[dict], rows: list[list[str]]) -> None:
    for index, scene in enumerate(scenes):
        if index < len(rows) and len(rows[index]) >= 4:
            scene["narration"] = rows[index][3].strip()
