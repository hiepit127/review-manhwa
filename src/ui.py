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
#key-line .key-status {border-radius: 12px; padding: 10px 12px; font-size: 0.92rem; line-height: 1.45;}
#key-line .key-status.ok {background: #f2f8f4; border: 1px solid #b7d7c6; color: #145c3a;}
#key-line .key-status.miss {background: #fbf6ec; border: 1px solid #ead7b0; color: #6b4e16;}
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
  #sample-row {flex-direction: column !important;}
  #clone-layout {flex-direction: column !important;}
}
#sample-row {display: grid !important; grid-template-columns: minmax(0, 1fr) 52px minmax(0, 1fr) !important; gap: 12px !important; align-items: stretch !important;}
#sample-row > .dash-card {min-width: 0 !important;}
#sample-or {display: flex; align-items: center; justify-content: center; color: #a39a90; font-size: 0.95rem; height: 100%;}
.dash-card .upload-container, .dash-card .audio-container, .dash-card .wrap {background: #141210 !important; color: #f4efe8 !important; border-color: #3f3a36 !important;}
.dash-card span, .dash-card p {color: #f4efe8;}
#clone-screen .block, #clone-side .block {background: transparent !important; border: none !important; box-shadow: none !important;}
#clone-screen .form, #clone-side .form {background: #221f1c !important; border: 1px solid #3f3a36 !important; border-radius: 12px !important;}
#clone-screen label span, #clone-side label span {color: #d9cfc3 !important;}
.clone-link, .clone-link button {background: transparent !important; border: none !important; box-shadow: none !important; color: #176b45 !important; min-height: 32px !important; height: auto !important; width: fit-content !important; padding: 2px 0 !important; font-weight: 650 !important;}
#clone-screen {background: #161311; border: 1px solid #2c2824; border-radius: 20px; padding: 18px 18px 8px; margin-top: 4px;}
#clone-screen h2 {margin: 0 0 4px; color: #f4efe8; font-size: 1.35rem; letter-spacing: -0.02em;}
#clone-screen .lead {margin: 0 0 16px; color: #a39a90; font-size: 0.92rem; line-height: 1.45;}
#clone-screen .section-title {margin: 0 0 10px; color: #f4efe8; font-size: 1.05rem; font-weight: 650;}
#sample-row {align-items: stretch !important; gap: 12px !important;}
.dash-card {border: 1.5px dashed #5c564e !important; border-radius: 16px !important; background: #1c1916 !important; padding: 14px 14px 6px !important; min-height: 210px;}
.dash-card h3 {margin: 0; color: #f4efe8; font-size: 1rem; font-weight: 650;}
.dash-card p {margin: 4px 0 10px; color: #a39a90; font-size: 0.84rem; line-height: 1.4;}
@media (max-width: 860px) {
  #sample-row {grid-template-columns: 1fr !important;}
  #sample-or {min-height: 28px;}
}
.tips {background: #221e1a; border: 1px solid #3a342e; border-left: 3px solid #1f8a58; border-radius: 12px; padding: 12px 14px; margin: 4px 0 14px;}
.tips strong {display: block; color: #f4efe8; margin-bottom: 6px;}
.tips li {color: #c9c0b6; font-size: 0.88rem; line-height: 1.45; margin: 2px 0 2px 1.1em;}
#clone-screen label, #clone-screen .label-wrap span {color: #e7e0d6 !important;}
#clone-screen input, #clone-screen textarea, #clone-screen select {background: #221f1c !important; color: #f4efe8 !important; border-color: #3f3a36 !important;}
#clone-screen .count {display: block; text-align: right; color: #a39a90; font-size: 0.8rem; margin: -6px 2px 8px;}
#clone-screen .count.over {color: #e7b4b4;}
#create-row {align-items: center !important; margin-top: 4px;}
#create-row button {margin-left: auto;}
#clone-side {background: #1c1916; border: 1px solid #2c2824; border-radius: 16px; padding: 12px 12px 4px;}
#clone-side h3 {margin: 0 0 8px; color: #f4efe8; font-size: 1rem;}
.clone-link button {background: transparent !important; border: none !important; color: #3dbe86 !important; box-shadow: none !important; padding-left: 0 !important; justify-content: flex-start !important;}
#clone-screen .audio-container, #clone-screen .upload-container {background: transparent !important; border-color: #3f3a36 !important;}
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
    screen = _voice_screen()
    return (
        _storage_note(info),
        info["jobs"],
        info["voices"],
        info["output"],
        _root_value(info),
        _boot_status(info),
        _steps(None, "source"),
        _choices(),
        *screen,
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
    return (
        _storage_note(info),
        info["jobs"],
        info["voices"],
        info["output"],
        _root_value(info),
        status,
        _choices(),
        *_voice_screen(),
    )


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


def on_fetch(url, end_chapter, title, chapter, progress=gr.Progress()):
    from src.comicfetch import fetch_chapters

    log = StepLog()
    if not (url or "").strip():
        log("Chưa có link chương.")
        return [], [], _status("Hãy dán link chương truyện.", "err"), log.text(), gr.update(), gr.update()
    try:
        fetched = fetch_chapters(url, end_chapter, log, progress)
    except Exception as error:
        message = _fail(log, error)
        return [], [], _status(message, "err"), log.text(), gr.update(), gr.update()
    count = fetched["count"]
    next_title = title if (title or "").strip() else fetched["title"]
    next_chapter = chapter if (chapter or "").strip() else fetched["chapter"]
    return (
        fetched["pages"],
        fetched["pages"],
        _status(f"Đã lấy {count} trang. Bấm Tách panel để cắt và đọc chữ.", "ok"),
        log.text(),
        next_title,
        next_chapter,
    )


def on_prepare(
    files,
    pasted,
    fetched,
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
            as_list(files) + [path for path in (pasted or []) if path] + [path for path in (fetched or []) if path],
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
    model,
    temperature,
    use_vision,
    style,
    notes,
    progress=gr.Progress(),
):
    from src.keys import api_key_for, has_api_key, missing_message

    log = StepLog()
    if not has_api_key():
        message = missing_message()
        log(message)
        yield gr.update(), gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "script"), log.text()
        return
    if not job_id:
        log("Hãy tách panel trước.")
        yield gr.update(), gr.update(), _status("Hãy tách panel trước.", "err"), _steps(None, "script"), log.text()
        return
    api_key = api_key_for()
    yield gr.update(), gr.update(), _status("Đang viết kịch bản. Cứ để tab mở.", "wait"), _steps(_safe_job(job_id), "script"), log.text()
    try:
        job = write_script(
            job_id,
            scene_count,
            title=title,
            chapter=chapter,
            lore=lore,
            provider="xAI",
            api_key=api_key,
            base_url="",
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


def on_voices():
    log = StepLog()
    try:
        from src.tts import list_voices

        labels = list_voices(log)
        return (
            _voice_update(labels),
            _voice_update(labels),
            _voice_update(labels),
            _status(f"Có {len(labels)} giọng.", "ok"),
            log.text(),
        )
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text()


def _saved_update(selected: str | None = None):
    from src.voices import saved_choice_pairs, saved_names

    names = saved_names()
    value = selected if selected in names else (names[0] if names else None)
    return gr.update(choices=saved_choice_pairs(), value=value)


def _flow_voice(prefer: str | None = None):
    from src.tts import voice_choices

    return _voice_update(voice_choices(), prefer)


def _voice_screen(selected: str | None = None):
    """Danh sách giọng đã lưu, và các dropdown chọn giọng ở bước Giọng, Video, Đọc."""
    from src.voices import find_saved, saved_names, voice_meta

    names = saved_names()
    if selected not in names:
        selected = names[0] if names else None
    item = find_saved(selected) if selected else None
    preview = item["path"] if item and os.path.isfile(item["path"]) else None
    return (
        _saved_update(selected),
        preview,
        voice_meta(item),
        selected or "",
        _flow_voice(selected),
        _flow_voice(selected),
        _flow_voice(selected),
    )


def _count_html(text: str) -> str:
    from src.voices import PREVIEW_LIMIT

    count = len(text or "")
    kind = "over" if count > PREVIEW_LIMIT else ""
    return f'<span class="count {kind}">{count}/{PREVIEW_LIMIT}</span>'


def _sample_from(upload, recording) -> str | None:
    recorded = file_path(recording)
    if recorded and os.path.isfile(recorded):
        return recorded
    uploaded = file_path(upload)
    if uploaded and os.path.isfile(uploaded):
        return uploaded
    return None


def on_pick_saved(name):
    from src.voices import find_saved, voice_meta

    item = find_saved(name)
    if item is None:
        return None, "", ""
    preview = item["path"] if os.path.isfile(item["path"]) else None
    return preview, voice_meta(item), item["name"]


def on_create_voice(name, upload, recording, language, category, preview_text, consent):
    log = StepLog()
    blank = (gr.update(),) * 7
    try:
        from src.tts import create_cloned_voice

        made = create_cloned_voice(
            name,
            _sample_from(upload, recording),
            preview_text,
            bool(consent),
            language or "Việt Nam",
            category or "",
            log,
        )
        saved = made["name"]
        heard = made["preview"] or None
        if made["warning"]:
            note = f"Đã lưu giọng «{saved}» vào thư mục giọng. Chưa nghe thử được: {made['warning']}"
            kind = "wait"
        else:
            note = f"Đã tạo giọng «{saved}». Nghe thử bên dưới. Giọng này chọn được ở bước Giọng và màn Đọc."
            kind = "ok"
        return (
            *_voice_screen(saved),
            heard,
            None,
            None,
            "",
            False,
            _status(note, kind),
            log.text(),
        )
    except Exception as error:
        message = _fail(log, error)
        return (*blank, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text())


def on_rename_voice(selected, new_name):
    log = StepLog()
    try:
        from src.tts import rename_cloned_voice

        renamed = rename_cloned_voice(selected, new_name, log)
        return (
            _saved_update(renamed),
            renamed,
            _flow_voice(renamed),
            _flow_voice(renamed),
            _flow_voice(renamed),
            _status(f"Đã đổi tên thành «{renamed}».", "ok"),
            log.text(),
        )
    except Exception as error:
        message = _fail(log, error)
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text()


def on_delete_saved(selected):
    log = StepLog()
    try:
        from src.tts import delete_cloned_voice

        removed = delete_cloned_voice(selected, log)
        screen = _voice_screen()
        return (
            *screen,
            _status(f"Đã xóa giọng «{removed}».", "ok"),
            log.text(),
        )
    except Exception as error:
        message = _fail(log, error)
        return (
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            _status(message, "err"),
            log.text(),
        )


def on_generate_speech(voice, text, progress=gr.Progress()):
    log = StepLog()
    yield gr.update(), gr.update(), gr.update(), _status("Đang đọc. Lần đầu VieNeu sẽ tải model.", "wait"), log.text()
    try:
        from src.tts import generate_speech

        progress(0.2, desc="Đọc bằng giọng đã chọn")
        path = generate_speech(text, voice, log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), gr.update(), gr.update(), _status(message, "err"), log.text()
        return
    yield (
        path,
        path,
        path,
        _status(f"Đọc xong. File nằm tại {path}", "ok"),
        log.text(),
    )


def on_pick_voice(selected):
    return gr.update(value=selected)


def on_hear(selected, text, job_id, progress=gr.Progress()):
    log = StepLog()
    yield gr.update(), _status("Đang đọc thử giọng…", "wait"), _steps(_safe_job(job_id), "voice"), log.text()
    try:
        from src.tts import speak_line

        progress(0.2, desc="Đọc thử giọng")
        path = speak_line(text, selected, None, log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "voice"), log.text()
        return
    yield path, _status("Nghe thử xong. Nếu giọng ổn, sang bước Video.", "ok"), _steps(_safe_job(job_id), "video"), log.text()


def on_quick_hear(selected, progress=gr.Progress()):
    log = StepLog()
    yield gr.update(), _status("Đang nghe thử giọng đã chọn…", "wait"), log.text()
    try:
        from src.tts import speak_line

        progress(0.2, desc="Nghe thử giọng")
        path = speak_line("Xin chào. Đây là giọng đã lưu.", selected, None, log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), _status(message, "err"), log.text()
        return
    yield path, _status("Nghe thử xong.", "ok"), log.text()


def on_preview(job_id, table, voice, progress=gr.Progress()):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel và viết lời trước.")
        yield gr.update(), _status("Hãy tách panel và viết lời trước.", "err"), _steps(None, "video"), log.text()
        return
    yield gr.update(), _status("Đang đọc câu đầu của kịch bản…", "wait"), _steps(_safe_job(job_id), "video"), log.text()
    try:
        progress(0.1, desc="Đọc thử")
        path = preview_line(job_id, table, voice, None, log)
    except Exception as error:
        message = _fail(log, error)
        yield gr.update(), _status(message, "err"), _steps(_safe_job(job_id), "video"), log.text()
        return
    yield path, _status("Nghe thử câu đầu. Nếu ổn thì xuất video.", "ok"), _steps(_safe_job(job_id), "video"), log.text()


def on_render(
    job_id,
    table,
    voice,
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
            ref_audio=None,
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
    from src.keys import has_api_key, load_api_keys, status_html
    from src.tts import voice_choices
    from src.voices import saved_choice_pairs

    load_api_keys()
    info = describe()
    with gr.Blocks(title="Review Manhwa") as demo:
        gr.HTML(BRAND, elem_id="brand", padding=False)
        status = gr.HTML(_boot_status(info), elem_id="status-line", padding=False)
        steps = gr.HTML(_steps(None, "source"), elem_id="stepper", padding=False)
        with gr.Group(elem_classes="card"):
            storage_note = gr.HTML(_storage_note(info), padding=False)
            with gr.Row():
                cache_box = gr.Textbox(label="Thư mục cache", value=info["jobs"], interactive=False, buttons=["copy"])
                voices_box = gr.Textbox(label="Thư mục giọng", value=info["voices"], interactive=False, buttons=["copy"])
                output_box = gr.Textbox(label="Thư mục output", value=info["output"], interactive=False, buttons=["copy"])
            with gr.Accordion("Đổi thư mục gốc", open=False):
                root_box = gr.Textbox(
                    label="Thư mục gốc",
                    value=_root_value(info),
                    placeholder="Để trống để tự chọn. Ví dụ: /content/drive/MyDrive/ReviewManhwa",
                    info="Đường dẫn tuyệt đối, hoặc tên thư mục trong My Drive. Trên Colab, ô DRIVE_DIR mặc định là ReviewManhwa.",
                )
                apply_root = gr.Button("Dùng thư mục này", size="md")

        job_state = gr.State("")
        with gr.Tabs(elem_id="flow") as flow_tabs:
            with gr.Tab("1. Nguồn"):
                gr.Markdown(
                    "Đưa trang vào, rồi bấm **Tách panel**. Có thể lấy cả chương từ link, tải file, hoặc dán từng trang.",
                    elem_classes="hint",
                )
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Việc đã lưu**")
                    gr.Markdown("Mở lại panel và lời đã làm, kể cả sau khi tắt Colab nếu dữ liệu nằm trên Drive.", elem_classes="hint")
                    saved = gr.Dropdown(label="Chọn việc", choices=list_recent_jobs(), allow_custom_value=False)
                    with gr.Row():
                        reload_saved = gr.Button("Làm mới danh sách", size="md")
                        open_saved = gr.Button("Mở việc này", size="md")
                with gr.Group(elem_classes="card"):
                    gr.Markdown("**Lấy từ link chương**")
                    gr.Markdown(
                        "Dán link một chương. Có thể lấy thêm vài chương liền sau nếu link có dạng chuong-1.",
                        elem_classes="hint",
                    )
                    chapter_url = gr.Textbox(
                        label="Link chương truyện",
                        placeholder="https://www.zettruyen5.com/truyen-tranh/.../chuong-1",
                    )
                    end_chapter = gr.Number(
                        label="Đến chương (0 = chỉ link này)",
                        value=0,
                        precision=0,
                        minimum=0,
                        info="Chỉ khi link có chuong-N, chapter-N hoặc chap-N. Tối đa 15 chương.",
                    )
                    fetch_btn = gr.Button("Lấy truyện", variant="primary", elem_id="go-fetch")
                    fetched_state = gr.State([])
                    fetched_gallery = gr.Gallery(
                        label="Trang đã lấy",
                        columns=6,
                        height=220,
                        object_fit="contain",
                    )
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
                    "Bấm **Viết kịch bản** khi đã có API key. Không có key thì **Chia cảnh, tôi viết tay**, rồi sửa cột Lời review.",
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
                    key_line = gr.HTML(status_html("xAI"), elem_id="key-line", padding=False)
                    model = gr.Textbox(label="Model", value="grok-4.7", info="xAI dùng grok-4.7.")
                    with gr.Row():
                        temperature = gr.Slider(0, 1.2, value=0.6, step=0.05, label="Độ sáng tạo")
                        use_vision = gr.Checkbox(value=False, label="Gửi ảnh panel cho model")
                    notes = gr.Textbox(label="Ghi chú thêm cho lời thoại", lines=2, placeholder="Ví dụ: xưng hô ngắn, không spoil chương sau.")
                with gr.Row():
                    write = gr.Button(
                        "Viết kịch bản",
                        variant="primary",
                        interactive=has_api_key(),
                        elem_id="write-script",
                    )
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
                gr.Markdown(
                    "Chọn một giọng đã có. Muốn giọng mới, mở màn **Tạo giọng**.",
                    elem_classes="hint",
                )
                with gr.Group(elem_classes="card"):
                    with gr.Row():
                        voice_lab = gr.Dropdown(choices=voice_choices(), value="Hải Đăng", label="Giọng cho video", scale=4)
                        refresh_lab = gr.Button("Tải danh sách giọng", size="md", scale=0, min_width=180)
                    with gr.Row():
                        to_clone_voice = gr.Button("Tạo giọng mới", elem_classes=["clone-link"], scale=0, min_width=140)
                    trial_text = gr.Textbox(
                        label="Câu nghe thử",
                        value="Xin chào. Đây là giọng sẽ đọc phần review.",
                        lines=2,
                    )
                    hear = gr.Button("Nghe giọng này", variant="primary")
                    hear_audio = gr.Audio(label="Nghe thử giọng", type="filepath")

            with gr.Tab("4. Video"):
                gr.Markdown("Giọng đang chọn sẽ đọc cả kịch bản. Nghe một câu trước, rồi xuất video.", elem_classes="hint")
                with gr.Group(elem_classes="card"):
                    with gr.Row():
                        voice = gr.Dropdown(choices=voice_choices(), value="Hải Đăng", label="Giọng đã lưu", scale=4)
                        refresh = gr.Button("Tải danh sách giọng", size="md", scale=0, min_width=180)
                    with gr.Row():
                        to_clone_video = gr.Button("Tạo giọng mới", elem_classes=["clone-link"], scale=0, min_width=140)
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

            with gr.Tab("Đọc"):
                gr.Markdown(
                    "Chọn giọng đã có, nghe nhanh, rồi dán chữ để đọc. Tạo giọng mới ở màn **Tạo giọng**.",
                    elem_classes="hint",
                )
                with gr.Group(elem_classes="card"):
                    speak_voice = gr.Dropdown(label="Giọng đọc", choices=voice_choices(), value="Hải Đăng")
                    with gr.Row():
                        quick_hear = gr.Button("Nghe giọng này", size="md", scale=0, min_width=160)
                        to_clone_read = gr.Button("Tạo giọng mới", elem_classes=["clone-link"], scale=0, min_width=140)
                    quick_audio = gr.Audio(label="Nghe thử giọng", type="filepath")
                    speak_text = gr.Textbox(
                        label="Chữ cần đọc",
                        lines=5,
                        placeholder="Dán lời review hoặc một đoạn bất kỳ.",
                    )
                    generate = gr.Button("Đọc đoạn này", variant="primary")
                    speech_audio = gr.Audio(label="Nghe kết quả", type="filepath")
                    with gr.Row():
                        speech_file = gr.File(label="Tải file wav")
                        speech_path = gr.Textbox(label="Đã lưu tại", interactive=False, buttons=["copy"])

            with gr.Tab("Tạo giọng", id="clone"):
                from src.voices import CATEGORIES, LANGUAGES, PREVIEW_LIMIT, SAMPLE_HINT

                preview_default = "Xin chào. Đây là giọng sẽ đọc phần review."
                with gr.Row(elem_id="clone-layout"):
                    with gr.Column(elem_id="clone-screen", scale=3):
                        gr.HTML(
                            "<h2>Tạo giọng</h2><p class='lead'>Chỉ màn này dùng để clone. Giọng lưu vào cache/voices, rồi chọn ở bước Giọng và màn Đọc.</p>"
                            "<div class='section-title'>Thêm giọng mẫu của bạn</div>",
                            padding=False,
                        )
                        with gr.Row(elem_id="sample-row"):
                            with gr.Column(elem_classes="dash-card"):
                                gr.HTML(
                                    "<h3>Chọn hoặc kéo thả tệp vào đây</h3><p>WAV, MP3, M4A · tối đa 10 MB</p>",
                                    padding=False,
                                )
                                sample_file = gr.Audio(
                                    sources=["upload"],
                                    type="filepath",
                                    label="Tệp giọng mẫu",
                                    show_label=False,
                                )
                            gr.HTML("<div id='sample-or'>hoặc</div>", padding=False)
                            with gr.Column(elem_classes="dash-card"):
                                gr.HTML(
                                    f"<h3>Ghi âm trực tiếp</h3><p>Một người nói, {SAMPLE_HINT}. Bấm nút thu trên máy.</p>",
                                    padding=False,
                                )
                                sample_mic = gr.Audio(
                                    sources=["microphone"],
                                    type="filepath",
                                    label="Ghi âm",
                                    show_label=False,
                                )
                        gr.HTML(
                            "<div class='tips'><strong>Mẹo thu âm</strong><ul>"
                            "<li>Thu trong phòng yên, đóng cửa.</li>"
                            "<li>Tránh tiếng vọng, quạt, nhạc nền và nhiều người nói cùng lúc.</li>"
                            f"<li>Nên dài khoảng {SAMPLE_HINT}, nói rõ, một mạch.</li>"
                            "</ul></div>",
                            padding=False,
                        )
                        clone_name = gr.Textbox(label="Tên giọng", placeholder="Ví dụ: Giọng review")
                        with gr.Row():
                            clone_language = gr.Dropdown(label="Ngôn ngữ", choices=list(LANGUAGES), value="Việt Nam")
                            clone_category = gr.Dropdown(
                                label="Lĩnh vực",
                                choices=list(CATEGORIES),
                                value=None,
                                info="Không bắt buộc",
                            )
                        clone_preview = gr.Textbox(
                            label="Văn bản nghe thử",
                            lines=3,
                            value=preview_default,
                            max_length=PREVIEW_LIMIT,
                        )
                        preview_count = gr.HTML(_count_html(preview_default), padding=False)
                        with gr.Row(elem_id="create-row"):
                            clone_consent = gr.Checkbox(
                                label="Tôi có quyền sử dụng giọng này và đồng ý tạo bản đọc từ giọng đó.",
                                value=False,
                            )
                            create_voice = gr.Button("Tạo giọng", variant="primary", interactive=False, scale=0)
                        made_audio = gr.Audio(label="Nghe thử giọng vừa tạo", type="filepath")
                    with gr.Column(elem_id="clone-side", scale=2):
                        gr.HTML("<h3>Giọng đã lưu</h3>", padding=False)
                        gr.Markdown("Nghe mẫu, đổi tên hoặc xóa. File nằm trong thư mục giọng.", elem_classes="hint")
                        tts_saved = gr.Dropdown(label="Giọng đã clone", choices=saved_choice_pairs(), value=None)
                        saved_preview = gr.Audio(label="Đoạn mẫu", type="filepath")
                        saved_meta = gr.Textbox(label="Ngôn ngữ và lĩnh vực", interactive=False)
                        rename_box = gr.Textbox(label="Tên mới", placeholder="Đặt tên khác")
                        with gr.Row():
                            rename_voice = gr.Button("Đổi tên", size="md")
                            delete_saved = gr.Button("Xóa giọng này", size="md")

        with gr.Accordion("Nhật ký", open=False):
            log_box = gr.Textbox(label="Nhật ký", lines=14, elem_id="log", show_label=False)
        gr.HTML(CREDITS, elem_id="credits", padding=False)

        voice_screen = [tts_saved, saved_preview, saved_meta, rename_box, voice_lab, voice, speak_voice]

        def _open_clone():
            return gr.Tabs(selected="clone")

        demo.load(
            on_boot,
            None,
            [storage_note, cache_box, voices_box, output_box, root_box, status, steps, saved, *voice_screen],
        )
        apply_root.click(
            on_apply_root,
            [root_box],
            [storage_note, cache_box, voices_box, output_box, root_box, status, saved, *voice_screen],
        )
        to_clone_voice.click(_open_clone, None, flow_tabs)
        to_clone_video.click(_open_clone, None, flow_tabs)
        to_clone_read.click(_open_clone, None, flow_tabs)
        reload_saved.click(on_reload_saved, None, [saved, status])
        open_saved.click(
            on_open,
            [saved],
            [job_state, gallery, panel_table, script_table, script_file, video, srt_file, result_box, status, steps, log_box, title, chapter, lore],
        )
        add_page.click(on_add_page, [paste_image, pasted_state], [pasted_state, pasted_gallery, paste_image, status, log_box])
        drop_page.click(on_drop_page, [pasted_state], [pasted_state, pasted_gallery, status, log_box])
        clear_pasted.click(on_clear_pages, [pasted_state], [pasted_state, pasted_gallery, status, log_box])
        fetch_btn.click(
            on_fetch,
            [chapter_url, end_chapter, title, chapter],
            [fetched_state, fetched_gallery, status, log_box, title, chapter],
        )
        prepare.click(
            on_prepare,
            [files, pasted_state, fetched_state, title, chapter, lore, start_page, end_page, do_slice, rtl, do_ocr, langs, use_gpu, force_redo, job_state],
            [job_state, gallery, panel_table, script_table, script_file, video, srt_file, result_box, status, steps, log_box, saved],
        )
        write.click(
            on_script,
            [job_state, scene_count, title, chapter, lore, model, temperature, use_vision, style, notes],
            [script_table, script_file, status, steps, log_box],
        )
        manual.click(on_manual, [job_state, scene_count, title, chapter, lore], [script_table, status, steps, log_box])
        refresh_lab.click(on_voices, None, [voice_lab, voice, speak_voice, status, log_box])
        refresh.click(on_voices, None, [voice, voice_lab, speak_voice, status, log_box])
        voice_lab.change(on_pick_voice, voice_lab, voice)
        hear.click(on_hear, [voice_lab, trial_text, job_state], [hear_audio, status, steps, log_box])
        tts_saved.change(on_pick_saved, tts_saved, [saved_preview, saved_meta, rename_box])
        clone_preview.change(_count_html, clone_preview, preview_count)
        clone_consent.change(lambda ok: gr.Button(interactive=bool(ok)), clone_consent, create_voice)
        create_voice.click(
            on_create_voice,
            [clone_name, sample_file, sample_mic, clone_language, clone_category, clone_preview, clone_consent],
            [*voice_screen, made_audio, sample_file, sample_mic, clone_name, clone_consent, status, log_box],
        )
        rename_voice.click(
            on_rename_voice,
            [tts_saved, rename_box],
            [tts_saved, rename_box, voice_lab, voice, speak_voice, status, log_box],
        )
        delete_saved.click(
            on_delete_saved,
            [tts_saved],
            [*voice_screen, status, log_box],
        )
        quick_hear.click(on_quick_hear, [speak_voice], [quick_audio, status, log_box])
        generate.click(
            on_generate_speech,
            [speak_voice, speak_text],
            [speech_audio, speech_file, speech_path, status, log_box],
        )
        preview.click(on_preview, [job_state, script_table, voice], [preview_audio, status, steps, log_box])
        render.click(
            on_render,
            [job_state, script_table, voice, video_format, resolution, slideshow, ken_burns, burn_subtitles, bgm, bgm_volume],
            [video, srt_file, result_box, status, steps, log_box],
        )
    return demo
