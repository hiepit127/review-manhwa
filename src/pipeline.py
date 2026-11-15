"""Nối các bước: nhận file, cắt panel, OCR, kịch bản, giọng đọc, video."""

from __future__ import annotations

import os

from src.ingest import collect_pages
from src.jobs import apply_narrations, job_abs, load_job, new_job_id, save_job, table_rows
from src.panels import slice_pages
from src.paths import job_dir
from src.scenes import group_panels
from src.textutil import file_path, public_error, slugify


def _noop(_fraction, desc=None):
    return None


def _meta(job: dict, title: str, chapter: str, lore: str) -> None:
    job["title"] = (title or "").strip()
    job["chapter"] = (chapter or "").strip()
    job["lore"] = (lore or "").strip()


def output_filename(job: dict) -> str:
    parts = [slugify(job.get("title") or ""), slugify(job.get("chapter") or "")]
    base = "-".join(part for part in parts if part) or "review"
    return base + ".mp4"


def prepare_job(
    files,
    *,
    title: str,
    chapter: str,
    lore: str,
    start_page,
    end_page,
    do_slice: bool,
    rtl: bool,
    do_ocr: bool,
    langs,
    use_gpu: bool,
    log,
    progress=None,
) -> dict:
    progress = progress or _noop
    paths = []
    for item in files or []:
        path = file_path(item)
        if path and os.path.isfile(path):
            paths.append(path)
    if not paths:
        raise RuntimeError("Hãy tải ảnh, PDF, ZIP, hoặc dán từng trang rồi bấm Tách panel.")

    job_id = new_job_id()
    folder = job_dir(job_id)
    os.makedirs(folder, exist_ok=True)
    log(f"Job {job_id}")
    progress(0.05, desc="Đọc file")
    pages = collect_pages(paths, folder, start_page, end_page, log)
    if not pages:
        raise RuntimeError("Không có trang nào trong khoảng đã chọn.")
    log(f"{len(pages)} trang")
    progress(0.25, desc="Cắt panel")
    panel_paths = slice_pages(pages, os.path.join(folder, "panels"), bool(do_slice), bool(rtl), log)
    if not panel_paths:
        raise RuntimeError("Không còn panel sau khi bỏ trang trống.")

    ocr_texts = [""] * len(panel_paths)
    if do_ocr:
        from src.ocr import read_images

        def ocr_progress(fraction, desc=None):
            progress(0.35 + 0.6 * float(fraction), desc=desc)

        ocr_texts = read_images(panel_paths, list(langs or []), bool(use_gpu), log, ocr_progress)
    else:
        log("Bỏ qua OCR.")

    panels = []
    for index, (path, text) in enumerate(zip(panel_paths, ocr_texts)):
        panels.append({"index": index, "image": os.path.relpath(path, folder), "ocr": text})
    job = {
        "id": job_id,
        "title": (title or "").strip(),
        "chapter": (chapter or "").strip(),
        "lore": (lore or "").strip(),
        "panels": panels,
        "scenes": [],
    }
    save_job(job)
    job["dir"] = folder
    log(f"Xong {len(panels)} panel.")
    progress(1, desc="Xong panel")
    return job


def assign_scenes(job_id: str, scene_count, title: str, chapter: str, lore: str, log) -> dict:
    job = load_job(job_id)
    _meta(job, title, chapter, lore)
    scenes = group_panels(job.get("panels") or [], int(scene_count or 1))
    job["scenes"] = scenes
    save_job(job)
    log(f"{len(job['panels'])} panel được chia thành {len(scenes)} cảnh.")
    return job


def write_script(
    job_id: str,
    scene_count,
    *,
    title: str,
    chapter: str,
    lore: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    use_vision: bool,
    style_key: str,
    notes: str,
    log,
    progress=None,
) -> dict:
    progress = progress or _noop
    job = assign_scenes(job_id, scene_count, title, chapter, lore, log)
    if not job["scenes"]:
        raise RuntimeError("Chưa có panel để viết lời.")
    if not use_vision and not any((scene.get("ocr") or "").strip() for scene in job["scenes"]):
        raise RuntimeError("Chưa có chữ OCR. Bật 'Gửi ảnh cho model' hoặc chạy lại OCR.")
    from src.script import generate_narrations

    for scene in job["scenes"]:
        scene["abs_images"] = [job_abs(job, relative) for relative in scene["images"]]
    try:
        narrations = generate_narrations(
            job["scenes"],
            title=job["title"],
            chapter=job["chapter"],
            lore=job["lore"],
            provider=provider,
            api_key=api_key or "",
            model=model or "",
            base_url=base_url or "",
            use_vision=bool(use_vision),
            temperature=float(temperature if temperature is not None else 0.6),
            style_key=style_key or "review",
            notes=notes or "",
            log=log,
            progress=progress,
        )
    except Exception as error:
        raise RuntimeError(public_error(error, api_key or "")) from error
    finally:
        for scene in job["scenes"]:
            scene.pop("abs_images", None)
    for scene, text in zip(job["scenes"], narrations):
        scene["narration"] = text
    filled = sum(1 for scene in job["scenes"] if scene.get("narration"))
    save_job(job)
    _write_script_file(job)
    log(f"Đã có lời cho {filled}/{len(job['scenes'])} cảnh. Sửa trực tiếp ở cột Lời review nếu cần.")
    return job


def sync_narrations(job_id: str, table) -> dict:
    job = load_job(job_id)
    if job.get("scenes"):
        apply_narrations(job["scenes"], table_rows(table))
        save_job(job)
        _write_script_file(job)
    return job


def _write_script_file(job: dict) -> str:
    import json

    path = os.path.join(job["dir"], "script.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "title": job.get("title"),
                "chapter": job.get("chapter"),
                "scenes": [
                    {"id": scene["id"], "panels": scene["panel_indexes"], "narration": scene.get("narration") or ""}
                    for scene in job.get("scenes") or []
                ],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
    return path


def preview_line(job_id: str, table, voice: str, ref_audio: str | None, log) -> str:
    job = sync_narrations(job_id, table)
    text = ""
    for scene in job.get("scenes") or []:
        if (scene.get("narration") or "").strip():
            text = scene["narration"].strip()
            break
    if not text:
        raise RuntimeError("Chưa có lời review để nghe thử.")
    from src.tts import open_voice, synthesize_to_file

    chosen = open_voice(voice, ref_audio if ref_audio else None, log)
    dest = os.path.join(job["dir"], "preview.wav")
    synthesize_to_file(text, chosen, dest, log)
    log("Nghe thử câu đầu. Nếu ổn thì xuất video.")
    return dest


def render_job(
    job_id: str,
    table,
    *,
    voice: str,
    ref_audio: str | None,
    video_format: str,
    resolution: str,
    slideshow: bool,
    ken_burns: bool,
    burn_subtitles: bool,
    bgm_path: str | None,
    bgm_volume: float,
    log,
    progress=None,
) -> tuple[str, str]:
    progress = progress or _noop
    job = sync_narrations(job_id, table)
    scenes = [scene for scene in job.get("scenes") or [] if (scene.get("narration") or "").strip()]
    if not scenes:
        raise RuntimeError("Chưa có lời review. Hãy viết kịch bản hoặc điền cột Lời review.")
    from src.tts import open_voice, synthesize_to_file
    from src.video import render_video

    progress(0.02, desc="Mở VieNeu-TTS")
    chosen = open_voice(voice, ref_audio if ref_audio else None, log)
    audio_dir = os.path.join(job["dir"], "audio")
    os.makedirs(audio_dir, exist_ok=True)
    payloads = []
    total = len(scenes)
    for index, scene in enumerate(scenes):
        progress(0.05 + 0.4 * index / total, desc=f"Đọc cảnh {scene['id']}")
        dest = os.path.join(audio_dir, f"scene_{int(scene['id']):03d}.wav")
        log(f"TTS cảnh {scene['id']}")
        synthesize_to_file(scene["narration"], chosen, dest, None)
        payloads.append(
            {
                "images": [job_abs(job, relative) for relative in scene["images"]],
                "audio": dest,
                "narration": scene["narration"],
            }
        )
    output = os.path.join(job["dir"], output_filename(job))
    video, srt = render_video(
        payloads,
        output,
        video_format=video_format or "youtube",
        resolution=resolution or "720p",
        slideshow=bool(slideshow),
        ken_burns=bool(ken_burns),
        burn_subtitles=bool(burn_subtitles),
        bgm_path=bgm_path if bgm_path else None,
        bgm_volume=float(bgm_volume if bgm_volume is not None else 0.12),
        log=log,
        progress=progress,
    )
    job["video"] = os.path.relpath(video, job["dir"])
    job["srt"] = os.path.relpath(srt, job["dir"])
    save_job(job)
    return video, srt
