"""Nhớ kết quả đã làm để lần sau khỏi cắt panel, OCR hoặc đọc lại cùng một câu."""

from __future__ import annotations

import hashlib
import json
import os

from src.jobs import job_abs, load_job
from src.paths import job_dir


def _index_path() -> str:
    from src.storage import jobs_dir

    return os.path.join(jobs_dir(), "_index.json")


def _load_index() -> dict:
    path = _index_path()
    if not os.path.isfile(path):
        return {"entries": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    return data


def _save_index(data: dict) -> None:
    path = _index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def fingerprint(paths: list[str], *, start_page, end_page, do_slice: bool, rtl: bool, do_ocr: bool, langs) -> str:
    hasher = hashlib.sha256()
    meta = {
        "start": int(start_page or 1),
        "end": int(end_page or 0),
        "slice": bool(do_slice),
        "rtl": bool(rtl),
        "ocr": bool(do_ocr),
        "langs": sorted(str(item) for item in (langs or [])),
    }
    hasher.update(json.dumps(meta, ensure_ascii=False, sort_keys=True).encode())
    for path in paths:
        hasher.update(b"\0")
        hasher.update(os.path.basename(path).encode())
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    return hasher.hexdigest()


def _panels_ready(job_id: str) -> bool:
    try:
        job = load_job(job_id)
    except (OSError, json.JSONDecodeError, FileNotFoundError):
        return False
    panels = job.get("panels") or []
    if not panels:
        return False
    for panel in panels:
        if not os.path.isfile(job_abs(job, panel.get("image") or "")):
            return False
    return os.path.isdir(job_dir(job_id))


def lookup_cached_job(key: str) -> str | None:
    entry = _load_index()["entries"].get(key) or {}
    job_id = str(entry.get("job_id") or "")
    if not job_id or not _panels_ready(job_id):
        return None
    return job_id


def remember_job(key: str, job_id: str) -> None:
    data = _load_index()
    data["entries"][key] = {"job_id": job_id}
    if len(data["entries"]) > 300:
        data["entries"] = dict(list(data["entries"].items())[-200:])
    _save_index(data)


def _audio_meta(path: str) -> str:
    return path + ".json"


def audio_can_reuse(path: str, narration: str, voice: str) -> bool:
    meta = _audio_meta(path)
    if not os.path.isfile(path) or not os.path.isfile(meta):
        return False
    try:
        with open(meta, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("narration") == narration and data.get("voice") == voice


def remember_audio(path: str, narration: str, voice: str) -> None:
    temporary = _audio_meta(path) + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"narration": narration, "voice": voice}, handle, ensure_ascii=False)
    os.replace(temporary, _audio_meta(path))
