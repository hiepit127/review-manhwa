"""Giao diện Gradio. Mọi nút gọi pipeline và trả trạng thái về trang."""

from __future__ import annotations

import html
import os

import gradio as gr

from src.jobs import PANEL_HEADERS, SCENE_HEADERS, job_abs, list_recent_jobs, load_job, panels_to_table, scenes_to_table
from src.paste import add_pasted_page, clear_pages, drop_last_page
from src.pipeline import assign_scenes, prepare_job, preview_line, render_job, write_script
from src.storage import describe, set_root
from src.textutil import StepLog, as_list, file_path
from src.tts import FALLBACK_VOICES

BRAND = """
<div class="brand">
  <div class="mark" aria-hidden="true">3</div>
  <div>
    <h1>Review Manhwa</h1>
    <p>Làm lần lượt bốn bước: đưa trang truyện vào, viết lời, chọn giọng, xuất video. Chỉ dùng truyện bạn có quyền.</p>
  </div>
</div>
"""

CREDITS = """
<p>Giọng đọc dùng <a href="https://github.com/pnnbao97/VieNeu-TTS">VieNeu-TTS v3 Turbo</a> (Apache-2.0, Phạm Nguyễn Ngọc Bảo).
Cắt panel, OCR, lời dẫn và ghép video tham khảo kiến trúc <a href="https://github.com/allwin-antony/ManhwaForge">ManhwaForge</a>.</p>
"""


def _theme():
    theme = gr.themes.Soft(
        primary_hue="emerald",
        secondary_hue="stone",
        neutral_hue="stone",
        font=[gr.themes.GoogleFont("Be Vietnam Pro"), "Segoe UI", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("IBM Plex Mono"), "ui-monospace", "monospace"],
        radius_size=gr.themes.sizes.radius_lg,
    )
    known = set(theme.to_dict()["theme"])
    values = {
        "body_background_fill": "#f3efe6",
        "background_fill_primary": "#f3efe6",
        "background_fill_secondary": "#fffdf9",
        "block_background_fill": "#fffdf9",
        "block_border_color": "#e6dfd4",
        "block_label_text_color": "#1c1917",
        "block_title_text_color": "#1c1917",
        "body_text_color": "#1c1917",
        "body_text_color_subdued": "#6b625b",
        "border_color_primary": "#e6dfd4",
        "button_primary_background_fill": "#176b45",
        "button_primary_background_fill_hover": "#0f4d31",
        "button_primary_text_color": "#ffffff",
        "button_secondary_background_fill": "#fffdf9",
        "button_secondary_background_fill_hover": "#f3efe6",
        "button_secondary_text_color": "#1c1917",
        "button_secondary_border_color": "#e6dfd4",
        "input_background_fill": "#ffffff",
        "input_border_color": "#e4dcd0",
        "block_shadow": "none",
        "button_primary_shadow": "none",
        "button_primary_shadow_hover": "none",
        "button_secondary_shadow": "none",
        "shadow_drop": "none",
        "shadow_drop_lg": "none",
        "table_even_background_fill": "#fffdf9",
        "table_odd_background_fill": "#f7f4ee",
        "color_accent": "#176b45",
    }
    payload = {}
    for key, value in values.items():
        if key in known:
            payload[key] = value
        dark = key + "_dark"
        if dark in known:
            payload[dark] = value
    return theme.set(**payload)


THEME = _theme()

_UPLOAD_TEXT = {
    "click_to_upload": "Bấm để chọn file",
    "drop_audio": "Thả file âm thanh vào đây",
    "drop_csv": "Thả CSV vào đây",
    "drop_file": "Thả file vào đây",
    "drop_image": "Thả ảnh vào đây",
    "drop_video": "Thả video vào đây",
    "drop_gallery": "Thả ảnh vào đây",
    "paste_clipboard": "Dán từ clipboard",
}
_COMMON_TEXT = {
    "or": "hoặc",
    "empty": "Trống",
    "loading": "Đang tải",
    "error": "Lỗi",
    "download": "Tải xuống",
    "clear": "Xóa",
    "remove": "Xóa",
    "undo": "Hoàn tác",
    "edit": "Sửa",
    "share": "Chia sẻ",
    "submit": "Chạy",
}
I18N = gr.I18n(
    en={"upload_text": _UPLOAD_TEXT, "common": _COMMON_TEXT},
    vi={"upload_text": _UPLOAD_TEXT, "common": _COMMON_TEXT},
)

# Gradio nạp bản tiếng Anh sau bản dịch tùy chỉnh, nên ô kéo-thả vẫn hiện tiếng Anh
# trên trình duyệt en. Script này đổi đúng những câu đó sau khi trang vẽ.
HEAD = """
<script>
(() => {
  const phrases = new Map([
    ["Drop File Here", "Thả file vào đây"],
    ["Click to Upload", "Bấm để chọn file"],
    ["Paste from Clipboard", "Dán từ clipboard"],
    ["Drop Image Here", "Thả ảnh vào đây"],
    ["Drop Audio Here", "Thả file âm thanh vào đây"],
    ["Drop Video Here", "Thả video vào đây"],
    ["Drop Media Here", "Thả ảnh vào đây"],
    ["Drop CSV Here", "Thả CSV vào đây"],
    ["or", "hoặc"],
    ["- or -", "hoặc"],
    [" - or - ", "hoặc"],
    ["Loading...", "Đang tải..."],
    ["Empty", "Trống"]
  ]);
  const swap = (node) => {
    if (!node || node.nodeType !== 3) return;
    const raw = node.nodeValue;
    if (!raw) return;
    const trimmed = raw.trim();
    const next = phrases.get(trimmed);
    if (next && next !== trimmed) node.nodeValue = raw.replace(trimmed, next);
  };
  const walk = (node) => {
    if (!node) return;
    if (node.nodeType === 3) swap(node);
    else if (node.nodeType === 1 && node.childNodes) node.childNodes.forEach(walk);
  };
  const start = () => {
    walk(document.body);
    new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") swap(record.target);
        record.addedNodes.forEach(walk);
      }
    }).observe(document.body, {childList: true, subtree: true, characterData: true});
  };
  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
</script>
"""

CSS = """
.gradio-container {max-width: 1080px !important; margin: 0 auto !important; padding-top: 12px !important;}
footer {display: none !important;}
#brand .brand {display: flex; gap: 14px; align-items: center; padding: 6px 2px 2px;}
#brand .mark {width: 48px; height: 48px; border-radius: 16px; background: #176b45; display: grid; place-items: center; flex: none; color: #fff; font-weight: 700; font-size: 1.35rem; line-height: 1;}
#brand h1 {margin: 0; font-size: 1.65rem; letter-spacing: -0.03em; font-weight: 700; line-height: 1.15; color: #1c1917;}
#brand p {margin: 4px 0 0; color: #6b625b; font-size: 0.95rem; line-height: 1.45;}
#status-line {position: sticky; top: 8px; z-index: 30;}
#status-line .status {border-radius: 12px; padding: 12px 14px; border: 1px solid #e6dfd4; background: #fffdf9; font-size: 0.95rem; line-height: 1.45; box-shadow: 0 8px 18px rgba(28, 25, 23, 0.06);}
#status-line .status.ok {background: #f2f8f4; border-color: #b7d7c6;}
#status-line .status.wait {background: #fbf6ec; border-color: #ead7b0;}
#status-line .status.err {background: #fdf4f4; border-color: #e7b4b4; color: #8d2424;}
#stepper .steps {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 10px 0 14px;}
#stepper .step {background: #fffdf9; border: 1px solid #e6dfd4; border-radius: 12px; padding: 10px 12px; min-width: 0;}
#stepper .step b {display: block; font-size: 0.72rem; letter-spacing: 0.04em; color: #8a8178; font-weight: 650;}
#stepper .step strong {display: block; font-size: 0.98rem; margin-top: 2px; color: #1c1917;}
#stepper .step em {display: block; font-style: normal; color: #6b625b; font-size: 0.78rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
#stepper .step.done {background: #f2f8f4; border-color: #b7d7c6;}
#stepper .step.current {border-color: #176b45; box-shadow: inset 0 0 0 1px #176b45;}
.card {border: 1px solid #e6dfd4 !important; border-radius: 16px !important; background: #fffdf9 !important; padding: 12px 14px 4px !important; margin: 0 0 12px !important;}
.hint p, .hint span {color: #6b625b !important; font-size: 0.9rem !important;}
.store {display: flex; flex-direction: column; gap: 2px; margin: 2px 0 8px;}
.store strong {font-size: 0.95rem; color: #1c1917;}
.store span {color: #6b625b; font-size: 0.86rem; line-height: 1.4;}
#log textarea {font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px;}
#credits {color: #6b625b; font-size: 0.8rem; line-height: 1.45; margin-top: 8px;}
#credits a {color: #176b45;}
@media (max-width: 720px) {
  #stepper .steps {grid-template-columns: 1fr 1fr;}
  #brand h1 {font-size: 1.3rem;}
  #brand .brand {align-items: flex-start;}
  .gradio-container {padding-left: 8px !important; padding-right: 8px !important;}
}
"""


def _status(message: str, kind: str) -> str:
    return f'<div class="status {html.escape(kind)}">{html.escape(message)}</div>'


def _where(info: dict) -> str:
    if info.get("on_drive"):
        return "Google Drive"
    if info.get("custom"):
        return "Thư mục đã chọn"
    return "Máy local"


def _storage_note(info: dict) -> str:
    extra = info.get("note") or "Panel, chữ OCR, audio và giọng đã lưu nằm trong cache. Video và phụ đề nằm trong output."
    return f'<div class="store"><strong>{html.escape(_where(info))}</strong><span>{html.escape(extra)}</span></div>'


def _root_value(info: dict) -> str:
    if os.environ.get("RM_DRIVE_ROOT") or info.get("on_drive"):
        return info.get("base") or ""
    return ""


def _boot_status(info: dict) -> str:
    note = info.get("note") or ""
    if "Không ghi được" in note:
        return _status(note, "err")
    if info.get("on_drive"):
        return _status("Sẵn sàng. Cache và video nằm trên Google Drive, còn sau khi tắt phiên.", "ready")
    return _status("Sẵn sàng. Hãy tải trang truyện. Chưa gắn Drive nên dữ liệu đang lưu trên máy này.", "wait")


def _safe_job(job_id: str | None):
    if not job_id:
        return None
    try:
        return load_job(job_id)
    except (OSError, FileNotFoundError, ValueError):
        return None


def _video_ready(job) -> bool:
    if not job:
        return False
    for key in ("published_video",):
        path = job.get(key)
        if path and os.path.isfile(path):
            return True
    relative = job.get("video")
    return bool(relative and os.path.isfile(job_abs(job, relative)))


def _steps(job, current: str = "source") -> str:
    panels = list((job or {}).get("panels") or [])
    scenes = list((job or {}).get("scenes") or [])
    narrated = sum(1 for scene in scenes if (scene.get("narration") or "").strip())
    source_done = bool(panels)
    script_done = narrated > 0
    video_done = _video_ready(job)
    if source_done:
        source_detail = f"{len(panels)} panel"
    else:
        source_detail = "Tải trang truyện"
    if script_done:
        script_detail = f"Đã có lời {narrated}/{len(scenes)}"
    elif scenes:
        script_detail = f"Đã chia {len(scenes)} cảnh"
    else:
        script_detail = "Viết hoặc nhập lời"
    video_detail = "Đã xuất file" if video_done else "Ghép và tải về"
    items = [
        ("source", "01", "Nguồn", source_detail, source_done),
        ("script", "02", "Kịch bản", script_detail, script_done),
        ("voice", "03", "Giọng", "Chọn giọng đọc", False),
        ("video", "04", "Video", video_detail, video_done),
    ]
    parts = ['<div class="steps">']
    for key, number, title, detail, done in items:
        classes = "step"
        if done:
            classes += " done"
        if key == current:
            classes += " current"
        parts.append(
            f'<div class="{classes}"><b>BƯỚC {number}</b><strong>{title}</strong><em>{html.escape(detail)}</em></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _fail(log: StepLog, error: Exception) -> str:
    text = str(error).strip() or error.__class__.__name__
    log(f"Lỗi: {text}")
    return text


def _gallery(job) -> list[str]:
    return [job_abs(job, panel["image"]) for panel in job.get("panels") or [] if panel.get("image")][:80]


def _media(job, published_key: str, relative_key: str) -> str | None:
    if not job:
        return None
    published = job.get(published_key)
    if published and os.path.isfile(published):
        return published
    relative = job.get(relative_key)
    if relative:
        path = job_abs(job, relative)
        if os.path.isfile(path):
            return path
    return None


def _script_file(job) -> str | None:
    if not job:
        return None
    path = os.path.join(job["dir"], "script.json")
    return path if os.path.isfile(path) else None


def _result_text(job) -> str:
    lines = []
    video = _media(job, "published_video", "video")
    srt = _media(job, "published_srt", "srt")
    if video:
        lines.append(video)
    if srt:
        lines.append(srt)
    return "\n".join(lines)


def _choices(selected: str | None = None):
    choices = list_recent_jobs()
    ids = [value for _, value in choices]
    if selected in ids:
        return gr.update(choices=choices, value=selected)
    return gr.update(choices=choices, value=None)


def _voice_update(labels: list[str], selected: str | None = None):
    if not labels:
        labels = list(FALLBACK_VOICES)
    if selected and selected in labels:
        value = selected
    elif "Hải Đăng" in labels:
        value = "Hải Đăng"
    else:
        value = labels[0]
    return gr.update(choices=labels, value=value)


def on_boot():
    info = describe()
    return (
        _storage_note(info),
        info["jobs"],
        info["output"],
        _root_value(info),
        _boot_status(info),
        _steps(None, "source"),
        _choices(),
    )


def on_apply_root(path):
    log_note = ""
    try:
        info = set_root(path)
    except Exception as error:
        info = describe()
        log_note = str(error)
    note = info.get("note") or ""
    if log_note:
        status = _status(log_note, "err")
    elif "Không ghi được" in note:
        status = _status(note, "err")
    elif info.get("on_drive"):
        status = _status("Đã chuyển nơi lưu sang Google Drive.", "ok")
    elif note:
        status = _status(note, "wait")
    else:
        status = _status(f"Đang lưu vào {_where(info).lower()}.", "ok")
    return _storage_note(info), info["jobs"], info["output"], _root_value(info), status, _choices()


def on_reload_saved():
    choices = list_recent_jobs()
    if choices:
        return _choices(), _status(f"Có {len(choices)} việc trong cache.", "ok")
    return _choices(), _status("Cache chưa có việc nào. Hãy tách panel trước.", "wait")


def on_open(selected):
    log = StepLog()
    hold = (
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
    )
    if not selected:
        log("Chưa chọn việc.")
        return (*hold[:8], _status("Hãy chọn một việc trong danh sách.", "err"), gr.update(), log.text(), *hold[:3])
    try:
        job = load_job(selected)
    except Exception as error:
        message = _fail(log, error)
        return (*hold[:8], _status(message, "err"), gr.update(), log.text(), gr.update(), gr.update(), gr.update())
    title = job.get("title") or "Chưa đặt tên"
    log(f"Đã mở {job['id']}.")
    return (
        job["id"],
        _gallery(job),
        panels_to_table(job.get("panels") or []),
        scenes_to_table(job.get("scenes") or []),
        _script_file(job),
        _media(job, "published_video", "video"),
        _media(job, "published_srt", "srt"),
        _result_text(job),
        _status(f"Đã mở «{title}». Panel ở bước Nguồn, lời ở bước Kịch bản.", "ok"),
        _steps(job, "source"),
        log.text(),
        job.get("title") or "",
        job.get("chapter") or "",
        job.get("lore") or "",
    )


def on_add_page(image, pages):
    log = StepLog()
    try:
        stored = add_pasted_page(image, list(pages or []))
        log(f"Đã thêm trang {len(stored)}.")
        return stored, stored, None, _status(f"Đã có {len(stored)} trang dán. Thêm tiếp hoặc bấm Tách panel.", "ok"), log.text()
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text()


def on_drop_page(pages):
    log = StepLog()
    stored = drop_last_page(list(pages or []))
    if stored:
        message = f"Đã xóa trang cuối. Còn {len(stored)} trang."
        kind = "ok"
    else:
        message = "Không còn trang nào đã dán."
        kind = "wait"
    log(message)
    return stored, stored, _status(message, kind), log.text()


def on_clear_pages(pages):
    log = StepLog()
    clear_pages(list(pages or []))
    log("Đã xóa hết trang dán.")
    return [], [], _status("Đã xóa hết trang dán.", "ok"), log.text()


def _hold_prepare(job_id, message, kind, log):
    return (
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        _status(message, kind),
        _steps(_safe_job(job_id), "source"),
        log.text(),
        gr.update(),
    )


def on_prepare(
    files,
    pasted,
    title,
    chapter,
    lore,
    start_page,
    end_page,
    do_slice,
    rtl,
    do_ocr,
    langs,
    use_gpu,
    force_redo,
    job_id,
    progress=gr.Progress(),
):
    log = StepLog()
    yield _hold_prepare(job_id, "Đang tách panel và đọc chữ. Cứ để tab mở.", "wait", log)
    try:
        job = prepare_job(
            as_list(files) + [path for path in (pasted or []) if path],
            title=title,
            chapter=chapter,
            lore=lore,
            start_page=start_page,
            end_page=end_page,
            do_slice=do_slice,
            rtl=rtl,
            do_ocr=do_ocr,
            langs=langs,
            use_gpu=use_gpu,
            use_cache=not bool(force_redo),
            log=log,
            progress=progress,
        )
    except Exception as error:
        message = _fail(log, error)
        yield _hold_prepare(job_id, message, "err", log)
        return
    count = len(job.get("panels") or [])
    if "Dùng lại cache" in log.text():
        message, kind = f"Dùng lại {count} panel đã lưu, không làm lại. Có thể sang bước Kịch bản.", "ok"
    else:
        message, kind = f"Đã tách {count} panel. Sang bước Kịch bản để viết lời.", "ok"
    yield (
        job["id"],
        _gallery(job),
        panels_to_table(job.get("panels") or []),
        scenes_to_table(job.get("scenes") or []),
        _script_file(job),
        _media(job, "published_video", "video"),
        _media(job, "published_srt", "srt"),
        _result_text(job),
        _status(message, kind),
        _steps(job, "script"),
        log.text(),
        _choices(job["id"]),
    )


def on_script(
    job_id,
    scene_count,
    title,
    chapter,
    lore,
    provider,
    api_key,
    base_url,
    model,
    temperature,
    use_vision,
    style,
    notes,
    progress=gr.Progress(),
):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel trước.")
        yield gr.update(), gr.update(), _status("Hãy tách panel trước.", "err"), _steps(None, "script"), log.text()
        return
    yield gr.update(), gr.update(), _status("Đang viết kịch bản. Cứ để tab mở.", "wait"), _steps(_safe_job(job_id), "script"), log.text()
    try:
        job = write_script(
            job_id,
            scene_count,
            title=title,
            chapter=chapter,
            lore=lore,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            use_vision=use_vision,
            style_key=style,
            notes=notes,
            log=log,
            progress=progress,
        )
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "script"), log.text()
        return
    filled = sum(1 for scene in job.get("scenes") or [] if (scene.get("narration") or "").strip())
    total = len(job.get("scenes") or [])
    yield (
        scenes_to_table(job.get("scenes") or []),
        _script_file(job),
        _status(f"Đã có lời cho {filled}/{total} cảnh. Sửa cột Lời review nếu cần.", "ok"),
        _steps(job, "voice"),
        log.text(),
    )


def on_manual(job_id, scene_count, title, chapter, lore):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel trước.")
        return gr.update(), _status("Hãy tách panel trước.", "err"), _steps(None, "script"), log.text()
    try:
        job = assign_scenes(job_id, scene_count, title, chapter, lore, log)
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "script"), log.text()
    log("Điền cột Lời review rồi xuất video, không cần gọi model.")
    count = len(job.get("scenes") or [])
    return (
        scenes_to_table(job.get("scenes") or []),
        _status(f"Đã chia {count} cảnh. Điền cột Lời review, không cần API.", "ok"),
        _steps(job, "script"),
        log.text(),
    )


def on_provider(provider):
    if provider == "xAI":
        return gr.update(visible=False), gr.update(value="grok-4.7")
    return gr.update(visible=True), gr.update(value="")


def on_voices():
    log = StepLog()
    try:
        from src.tts import list_voices

        labels = list_voices(log)
        update = _voice_update(labels)
        return update, update, _status(f"Có {len(labels)} giọng.", "ok"), log.text()
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), _status(message, "err"), log.text()


def on_save_voice(name, audio):
    log = StepLog()
    try:
        from src.tts import list_voices, save_cloned_voice

        saved = save_cloned_voice(name, file_path(audio), log)
        update = _voice_update(list_voices(log), saved)
        return update, update, gr.update(value=None), _status(f"Đã lưu giọng «{saved}».", "ok"), log.text()
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text()


def on_delete_voice(selected):
    log = StepLog()
    try:
        from src.tts import delete_cloned_voice, voice_choices

        delete_cloned_voice(selected, log)
        update = _voice_update(voice_choices())
        return update, update, _status("Đã xóa giọng đã lưu.", "ok"), log.text()
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), _status(message, "err"), log.text()


def on_pick_voice(selected):
    return gr.update(value=selected)


def on_hear(selected, text, audio, job_id, progress=gr.Progress()):
    log = StepLog()
    yield gr.update(), _status("Đang đọc thử giọng…", "wait"), _steps(_safe_job(job_id), "voice"), log.text()
    try:
        from src.tts import speak_line

        progress(0.2, desc="Đọc thử giọng")
        path = speak_line(text, selected, file_path(audio), log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "voice"), log.text()
        return
    yield path, _status("Nghe thử xong. Nếu giọng ổn, sang bước Video.", "ok"), _steps(_safe_job(job_id), "video"), log.text()


def on_preview(job_id, table, voice, ref_audio, progress=gr.Progress()):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel và viết lời trước.")
        yield gr.update(), _status("Hãy tách panel và viết lời trước.", "err"), _steps(None, "video"), log.text()
        return
    yield gr.update(), _status("Đang đọc câu đầu của kịch bản…", "wait"), _steps(_safe_job(job_id), "video"), log.text()
    try:
        progress(0.1, desc="Đọc thử")
        path = preview_line(job_id, table, voice, file_path(ref_audio), log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "video"), log.text()
        return
    yield path, _status("Nghe thử câu đầu. Nếu ổn thì xuất video.", "ok"), _steps(_safe_job(job_id), "video"), log.text()


def on_render(
    job_id,
    table,
    voice,
    ref_audio,
    video_format,
    resolution,
    slideshow,
    ken_burns,
    burn_subtitles,
    bgm,
    bgm_volume,
    progress=gr.Progress(),
):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel và viết lời trước.")
        yield gr.update(), gr.update(), gr.update(), _status("Hãy tách panel và viết lời trước.", "err"), _steps(None, "video"), log.text()
        return
    yield (
        gr.update(),
        gr.update(),
        gr.update(),
        _status("Đang đọc lời và ghép video. Cứ để tab mở.", "wait"),
        _steps(_safe_job(job_id), "video"),
        log.text(),
    )
    try:
        video, srt = render_job(
            job_id,
            table,
            voice=voice,
            ref_audio=file_path(ref_audio),
            video_format=video_format,
            resolution=resolution,
            slideshow=slideshow,
            ken_burns=ken_burns,
            burn_subtitles=burn_subtitles,
            bgm_path=file_path(bgm),
            bgm_volume=bgm_volume,
            log=log,
            progress=progress,
        )
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), gr.update(), gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "video"), log.text()
        return
    log(f"Xong {os.path.basename(video)}")
    yield (
        video,
        srt,
        "\n".join(path for path in (video, srt) if path),
        _status(f"Xong. Video đã lưu tại {video}", "ok"),
        _steps(_safe_job(job_id), "video"),
        log.text(),
    )


def build_demo():
    info = describe()
    with gr.Blocks(title="Review Manhwa") as demo:
        gr.HTML(BRAND, elem_id="brand", padding=False)
        status = gr.HTML(_boot_status(info), elem_id="status-line", padding=False)
        steps = gr.HTML(_steps(None, "source"), elem_id="stepper", padding=False)
        with gr.Group(elem_classes="card"):
            storage_note = gr.HTML(_storage_note(info), padding=False)
            with gr.Row():
                cache_box = gr.Textbox(label="Thư mục cache", value=info["jobs"], interactive=False, buttons=["copy"])
                output_box = gr.Textbox(label="Thư mục output", value=info["output"], interactive=False, buttons=["copy"])
            with gr.Accordion("Đổi thư mục gốc", open=False):
                root_box = gr.Textbox(
                    label="Thư mục gốc",
                    value=_root_value(info),
                    placeholder="Để trống để tự chọn. Ví dụ: /content/drive/MyDrive/ReviewManhwa",
                    info="Đường dẫn tuyệt đối, hoặc tên thư mục trong My Drive. Trên Colab mặc định là ReviewManhwa.",
                )
                apply_root = gr.Button("Dùng thư mục này", size="md")

        job_state = gr.State("")
        with gr.Tabs(elem_id="flow"):
            with gr.Tab("1. Nguồn"):
                gr.Markdown("Đưa trang vào, rồi bấm **Tách panel**. Ảnh, PDF, ZIP hoặc dán từng trang đều được.", elem_classes="hint")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Việc đã lưu**")
                    gr.Markdown("Mở lại panel và lời đã làm, kể cả sau khi tắt Colab nếu dữ liệu nằm trên Drive.", elem_classes="hint")
                    saved = gr.Dropdown(label="Chọn việc", choices=list_recent_jobs(), allow_custom_value=False)
                    with gr.Row():
                        reload_saved = gr.Button("Làm mới danh sách", size="md")
                        open_saved = gr.Button("Mở việc này", size="md")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Tải file**")
                    files = gr.File(
                        label="Ảnh, PDF hoặc ZIP",
                        file_count="multiple",
                        file_types=[".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf", ".zip"],
                    )
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Hoặc dán từng trang**")
                    gr.Markdown("Copy ảnh, bấm vào ô dưới, nhấn Ctrl+V hoặc Cmd+V, rồi **Thêm trang này**.", elem_classes="hint")
                    paste_image = gr.Image(
                        label="Dán một trang",
                        sources=["clipboard", "upload"],
                        type="filepath",
                        height=240,
                        placeholder="Dán ảnh trang truyện vào đây",
                    )
                    with gr.Row():
                        add_page = gr.Button("Thêm trang này", variant="primary", size="md")
                        drop_page = gr.Button("Xóa trang cuối", size="md")
                        clear_pasted = gr.Button("Xóa hết trang đã dán", size="md")
                    pasted_state = gr.State([])
                    pasted_gallery = gr.Gallery(label="Trang đã dán", columns=6, height=180, object_fit="contain")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Thông tin cho lời review**")
                    with gr.Row():
                        title = gr.Textbox(label="Tên truyện", placeholder="Ví dụ: Sống sót trong trò chơi")
                        chapter = gr.Textbox(label="Chương / phần", placeholder="Chương 1-10")
                    lore = gr.Textbox(
                        label="Nhân vật và bối cảnh",
                        lines=4,
                        placeholder="Nhân vật chính, mối quan hệ, bối cảnh. Model dùng phần này khi viết lời.",
                    )
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Cách tách**")
                    with gr.Row():
                        start_page = gr.Number(label="Từ trang", value=1, precision=0, minimum=1)
                        end_page = gr.Number(label="Đến trang (0 = hết)", value=0, precision=0, minimum=0)
                    with gr.Row():
                        do_slice = gr.Checkbox(value=True, label="Tự cắt panel")
                        rtl = gr.Checkbox(value=False, label="Trong một hàng, đọc phải sang trái")
                        do_ocr = gr.Checkbox(value=True, label="Đọc chữ (OCR)")
                        use_gpu = gr.Checkbox(value=True, label="OCR dùng GPU nếu có")
                    langs = gr.CheckboxGroup(
                        choices=[("Tiếng Hàn", "ko"), ("Tiếng Anh", "en"), ("Tiếng Việt", "vi")],
                        value=["ko", "en"],
                        label="Ngôn ngữ chữ trong tranh",
                    )
                    force_redo = gr.Checkbox(
                        value=False,
                        label="Làm lại, không dùng cache",
                        info="Bật khi muốn cắt và OCR lại dù file không đổi.",
                    )
                prepare = gr.Button("Tách panel", variant="primary", elem_id="go-prepare")
                gr.Markdown("Lần đầu OCR có thể mất vài phút. Thanh tiến trình hiện phía trên.", elem_classes="hint")
                gallery = gr.Gallery(label="Panel đã tách", columns=5, height=420, preview=True, object_fit="contain")
                panel_table = gr.Dataframe(
                    headers=PANEL_HEADERS,
                    label="Chữ đọc được",
                    interactive=False,
                    wrap=True,
                    max_height=360,
                )

            with gr.Tab("2. Kịch bản"):
                gr.Markdown(
                    "Có API thì bấm **Viết kịch bản**. Không có API thì **Chia cảnh, tôi viết tay**, rồi sửa cột Lời review.",
                    elem_classes="hint",
                )
                with gr.Group(elem_classes="card"):
                    with gr.Row():
                        scene_count = gr.Number(
                            label="Số cảnh",
                            value=24,
                            precision=0,
                            minimum=1,
                            maximum=200,
                            info="Mỗi cảnh là một đoạn lời. Nhập bằng số panel nếu muốn mỗi panel một cảnh.",
                        )
                        style = gr.Dropdown(
                            choices=[("Review", "review"), ("Tóm tắt", "tomtat"), ("Hài nhẹ", "hai")],
                            value="review",
                            label="Giọng văn",
                        )
                    provider = gr.Radio(choices=["xAI", "OpenAI-compatible"], value="xAI", label="Nguồn viết lời")
                    api_key = gr.Textbox(
                        label="API key",
                        type="password",
                        info="Chỉ nằm trong phiên này, không ghi vào file. xAI: console.x.ai",
                    )
                    with gr.Row():
                        model = gr.Textbox(label="Model", value="grok-4.7", info="xAI dùng grok-4.7.")
                        base_url = gr.Textbox(label="Base URL", visible=False)
                    with gr.Row():
                        temperature = gr.Slider(0, 1.2, value=0.6, step=0.05, label="Độ sáng tạo")
                        use_vision = gr.Checkbox(value=False, label="Gửi ảnh panel cho model")
                    notes = gr.Textbox(label="Ghi chú thêm cho lời thoại", lines=2, placeholder="Ví dụ: xưng hô ngắn, không spoil chương sau.")
                with gr.Row():
                    write = gr.Button("Viết kịch bản", variant="primary")
                    manual = gr.Button("Chia cảnh, tôi viết tay", size="md")
                script_table = gr.Dataframe(
                    headers=SCENE_HEADERS,
                    label="Kịch bản — sửa cột Lời review",
                    interactive=True,
                    wrap=True,
                    datatype="str",
                    static_columns=[0, 1, 2],
                    column_widths=["70px", "100px", "32%", "40%"],
                    max_height=480,
                    show_search="search",
                )
                script_file = gr.File(label="Tải script.json")

            with gr.Tab("3. Giọng"):
                gr.Markdown("Chọn giọng có sẵn, hoặc lưu giọng của bạn từ file mẫu 3–8 giây.", elem_classes="hint")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Giọng có sẵn**")
                    with gr.Row():
                        voice_lab = gr.Dropdown(choices=FALLBACK_VOICES, value="Hải Đăng", label="Giọng")
                        refresh_lab = gr.Button("Tải danh sách giọng", size="md")
                    trial_text = gr.Textbox(
                        label="Câu nghe thử",
                        value="Xin chào. Đây là giọng sẽ đọc phần review.",
                        lines=2,
                    )
                    hear = gr.Button("Nghe giọng này", variant="primary")
                    hear_audio = gr.Audio(label="Nghe thử giọng", type="filepath")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Giọng của bạn**")
                    gr.Markdown("File mẫu được lưu trong cache nên lần mở sau vẫn còn trong danh sách.", elem_classes="hint")
                    sample = gr.Audio(label="File giọng mẫu 3–8 giây", type="filepath")
                    clone_name = gr.Textbox(label="Tên giọng mới", placeholder="Ví dụ: Giọng review")
                    with gr.Row():
                        save_voice = gr.Button("Lưu giọng vào danh sách", variant="primary", size="md")
                        delete_voice = gr.Button("Xóa giọng đã lưu", size="md")

            with gr.Tab("4. Video"):
                gr.Markdown("Giọng đang chọn sẽ đọc cả kịch bản. Nghe một câu trước, rồi xuất video.", elem_classes="hint")
                with gr.Group(elem_classes="card"):
                    with gr.Row():
                        voice = gr.Dropdown(choices=FALLBACK_VOICES, value="Hải Đăng", label="Giọng VieNeu-TTS v3 Turbo")
                        refresh = gr.Button("Tải danh sách giọng", size="md")
                    ref_audio = gr.Audio(
                        label="Hoặc file giọng mẫu 3–8 giây, nếu chưa lưu vào danh sách",
                        type="filepath",
                    )
                    preview = gr.Button("Nghe thử câu kịch bản", size="md")
                    preview_audio = gr.Audio(label="Nghe thử câu kịch bản", type="filepath")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Khung hình**")
                    with gr.Row():
                        video_format = gr.Radio(
                            choices=[("YouTube 16:9", "youtube"), ("Shorts 9:16", "shorts")],
                            value="youtube",
                            label="Khung hình",
                        )
                        resolution = gr.Radio(choices=["720p", "1080p"], value="720p", label="Độ phân giải")
                    with gr.Row():
                        slideshow = gr.Checkbox(value=True, label="Lật vài panel trong mỗi cảnh")
                        ken_burns = gr.Checkbox(value=True, label="Ken Burns khi cảnh chỉ có một panel")
                        burn_subtitles = gr.Checkbox(value=True, label="Đốt phụ đề")
                    bgm = gr.Audio(label="Nhạc nền (không bắt buộc)", type="filepath")
                    bgm_volume = gr.Slider(0, 0.4, value=0.12, step=0.01, label="Âm lượng nhạc nền")
                render = gr.Button("Xuất video", variant="primary", elem_id="go-render")
                gr.Markdown("Đọc lời và ghép video có thể mất khá lâu. File xong hiện bên dưới và được chép vào thư mục output.", elem_classes="hint")
                video = gr.Video(label="Video", height=420)
                with gr.Row():
                    srt_file = gr.File(label="Phụ đề SRT")
                    result_box = gr.Textbox(label="File đã lưu", lines=2, interactive=False, buttons=["copy"])

        with gr.Accordion("Nhật ký", open=False):
            log_box = gr.Textbox(label="Nhật ký", lines=14, elem_id="log", show_label=False)
        gr.HTML(CREDITS, elem_id="credits", padding=False)

        demo.load(on_boot, None, [storage_note, cache_box, output_box, root_box, status, steps, saved])
        apply_root.click(on_apply_root, [root_box], [storage_note, cache_box, output_box, root_box, status, saved])
        reload_saved.click(on_reload_saved, None, [saved, status])
        open_saved.click(
            on_open,
            [saved],
            [job_state, gallery, panel_table, script_table, script_file, video, srt_file, result_box, status, steps, log_box, title, chapter, lore],
        )
        add_page.click(on_add_page, [paste_image, pasted_state], [pasted_state, pasted_gallery, paste_image, status, log_box])
        drop_page.click(on_drop_page, [pasted_state], [pasted_state, pasted_gallery, status, log_box])
        clear_pasted.click(on_clear_pages, [pasted_state], [pasted_state, pasted_gallery, status, log_box])
        prepare.click(
            on_prepare,
            [files, pasted_state, title, chapter, lore, start_page, end_page, do_slice, rtl, do_ocr, langs, use_gpu, force_redo, job_state],
            [job_state, gallery, panel_table, script_table, script_file, video, srt_file, result_box, status, steps, log_box, saved],
        )
        write.click(
            on_script,
            [job_state, scene_count, title, chapter, lore, provider, api_key, base_url, model, temperature, use_vision, style, notes],
            [script_table, script_file, status, steps, log_box],
        )
        manual.click(on_manual, [job_state, scene_count, title, chapter, lore], [script_table, status, steps, log_box])
        provider.change(on_provider, provider, [base_url, model])
        refresh_lab.click(on_voices, None, [voice_lab, voice, status, log_box])
        refresh.click(on_voices, None, [voice, voice_lab, status, log_box])
        voice_lab.change(on_pick_voice, voice_lab, voice)
        save_voice.click(on_save_voice, [clone_name, sample], [voice_lab, voice, sample, status, log_box])
        delete_voice.click(on_delete_voice, voice_lab, [voice_lab, voice, status, log_box])
        hear.click(on_hear, [voice_lab, trial_text, sample, job_state], [hear_audio, status, steps, log_box])
        preview.click(on_preview, [job_state, script_table, voice, ref_audio], [preview_audio, status, steps, log_box])
        render.click(
            on_render,
            [job_state, script_table, voice, ref_audio, video_format, resolution, slideshow, ken_burns, burn_subtitles, bgm, bgm_volume],
            [video, srt_file, result_box, status, steps, log_box],
        )
    return demo
