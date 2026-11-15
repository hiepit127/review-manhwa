"""Giao diện Gradio. Mọi nút gọi pipeline và trả nhật ký về trang."""

from __future__ import annotations

import os

import gradio as gr

from src.jobs import PANEL_HEADERS, SCENE_HEADERS, job_abs, panels_to_table, scenes_to_table
from src.paste import add_pasted_page, clear_pages, drop_last_page
from src.pipeline import assign_scenes, prepare_job, preview_line, render_job, write_script
from src.textutil import StepLog, as_list, file_path
from src.tts import FALLBACK_VOICES

CSS = """
.gradio-container {max-width: 1080px !important; margin-left: auto !important; margin-right: auto !important;}
#log textarea {font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px;}
"""

GUIDE = """
1. Trên Colab chọn runtime **GPU**. Tải file, hoặc dán từng trang ảnh của chương bạn có quyền dùng.
2. Bấm **Tách panel**. Có thể tải file, hoặc dán từng trang: Ctrl+V vào ô ảnh rồi bấm **Thêm trang này**.
3. Dán API key xAI (console.x.ai), bấm **Viết kịch bản**. Sửa câu chữ ngay trên bảng.
4. Chọn giọng VieNeu-TTS v3 Turbo, bấm **Nghe thử**, rồi **Xuất video**.

Lần đầu VieNeu sẽ tải model. API key chỉ nằm trong phiên làm việc, không ghi vào file job.
"""


def _fail(log: StepLog, error: Exception):
    log(f"Lỗi: {error}")
    return log.text()


def _gallery(job) -> list[str]:
    paths = [job_abs(job, panel["image"]) for panel in job.get("panels") or []]
    return paths[:80]


def on_add_page(image, pages):
    log = StepLog()
    try:
        stored = add_pasted_page(image, list(pages or []))
        log(f"Đã thêm trang {len(stored)}. Dán trang tiếp theo rồi bấm Thêm trang này.")
        return stored, stored, None, log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), gr.update(), gr.update(), log.text()


def on_drop_page(pages):
    log = StepLog()
    stored = drop_last_page(list(pages or []))
    if stored:
        log(f"Đã xóa trang cuối. Còn {len(stored)} trang.")
    else:
        log("Không còn trang nào đã dán.")
    return stored, stored, log.text()


def on_clear_pages(pages):
    log = StepLog()
    clear_pages(list(pages or []))
    log("Đã xóa hết trang dán.")
    return [], [], log.text()


def on_prepare(files, pasted, title, chapter, lore, start_page, end_page, do_slice, rtl, do_ocr, langs, use_gpu, progress=gr.Progress()):
    log = StepLog()
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
            log=log,
            progress=progress,
        )
        return job["id"], _gallery(job), panels_to_table(job["panels"]), log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), gr.update(), gr.update(), log.text()


def on_script(job_id, scene_count, title, chapter, lore, provider, api_key, base_url, model, temperature, use_vision, style, notes, progress=gr.Progress()):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel trước.")
        return gr.update(), gr.update(), log.text()
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
        return scenes_to_table(job["scenes"]), os.path.join(job["dir"], "script.json"), log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), gr.update(), log.text()


def on_manual(job_id, scene_count, title, chapter, lore):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel trước.")
        return gr.update(), log.text()
    try:
        job = assign_scenes(job_id, scene_count, title, chapter, lore, log)
        log("Điền cột Lời review rồi xuất video, không cần gọi model.")
        return scenes_to_table(job["scenes"]), log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), log.text()


def on_voices():
    log = StepLog()
    try:
        from src.tts import list_voices

        labels = list_voices(log)
        value = "Hải Đăng" if "Hải Đăng" in labels else labels[0]
        return gr.update(choices=labels, value=value), log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), log.text()


def on_preview(job_id, table, voice, ref_audio, progress=gr.Progress()):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel và viết lời trước.")
        return gr.update(), log.text()
    try:
        progress(0.1, desc="Đọc thử")
        path = preview_line(job_id, table, voice, file_path(ref_audio), log)
        return path, log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), log.text()


def on_render(job_id, table, voice, ref_audio, video_format, resolution, slideshow, ken_burns, burn_subtitles, bgm, bgm_volume, progress=gr.Progress()):
    log = StepLog()
    if not job_id:
        log("Hãy tách panel và viết lời trước.")
        return gr.update(), gr.update(), log.text()
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
        log(f"Xong {os.path.basename(video)}")
        return video, srt, log.text()
    except Exception as error:
        _fail(log, error)
        return gr.update(), gr.update(), log.text()


def on_provider(provider):
    if provider == "xAI":
        return gr.update(visible=False), gr.update(value="grok-4.7")
    return gr.update(visible=True), gr.update(value="")


def build_demo():
    with gr.Blocks(title="Review Manhwa") as demo:
        gr.Markdown(
            """
# Review Manhwa
Dựng video review manhwa trên Google Colab: cắt panel, đọc chữ, viết lời tiếng Việt, VieNeu-TTS v3 Turbo, rồi ghép video.
Chỉ dùng với truyện bạn có quyền sử dụng. Tool không tải chương từ website.
"""
        )
        with gr.Accordion("Cách dùng", open=False):
            gr.Markdown(GUIDE)
        job_state = gr.State("")

        with gr.Tabs():
            with gr.Tab("1. Nguồn"):
                files = gr.File(
                    label="Ảnh, PDF hoặc ZIP",
                    file_count="multiple",
                    file_types=[".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf", ".zip"],
                )
                gr.Markdown("Hoặc dán từng trang: copy ảnh, bấm vào ô dưới, nhấn Ctrl+V hoặc Cmd+V, rồi **Thêm trang này**.")
                paste_image = gr.Image(
                    label="Dán một trang",
                    sources=["clipboard"],
                    type="filepath",
                    height=280,
                )
                with gr.Row():
                    add_page = gr.Button("Thêm trang này")
                    drop_page = gr.Button("Xóa trang cuối")
                    clear_pasted = gr.Button("Xóa hết trang đã dán")
                pasted_state = gr.State([])
                pasted_gallery = gr.Gallery(label="Trang đã dán", columns=6, height=240)
                with gr.Row():
                    title = gr.Textbox(label="Tên truyện")
                    chapter = gr.Textbox(label="Chương / phần", placeholder="Chương 1-10")
                lore = gr.Textbox(label="Nhân vật và bối cảnh", lines=4, placeholder="Nhân vật chính, mối quan hệ, bối cảnh. Model sẽ dùng phần này khi viết lời.")
                with gr.Row():
                    start_page = gr.Number(label="Từ trang", value=1, precision=0, minimum=1)
                    end_page = gr.Number(label="Đến trang (0 = hết)", value=0, precision=0, minimum=0)
                with gr.Row():
                    do_slice = gr.Checkbox(value=True, label="Tự cắt panel")
                    rtl = gr.Checkbox(value=False, label="Trong một hàng, đọc phải sang trái")
                    do_ocr = gr.Checkbox(value=True, label="Đọc chữ (OCR)")
                    use_gpu = gr.Checkbox(value=True, label="OCR dùng GPU nếu có")
                langs = gr.CheckboxGroup(
                    choices=["ko", "en", "vi"],
                    value=["ko", "en"],
                    label="Ngôn ngữ chữ trong tranh",
                )
                prepare = gr.Button("Tách panel", variant="primary")
                gallery = gr.Gallery(label="Panel", columns=5, height=420, preview=True)
                panel_table = gr.Dataframe(headers=PANEL_HEADERS, label="Chữ đọc được", interactive=False, wrap=True)

            with gr.Tab("2. Kịch bản"):
                scene_count = gr.Number(
                    label="Số cảnh",
                    value=24,
                    precision=0,
                    minimum=1,
                    maximum=200,
                    info="Mỗi cảnh là một đoạn lời. Nhập bằng số panel nếu muốn mỗi panel một cảnh.",
                )
                provider = gr.Radio(choices=["xAI", "OpenAI-compatible"], value="xAI", label="Nguồn viết lời")
                api_key = gr.Textbox(label="API key", type="password", info="xAI: https://console.x.ai")
                base_url = gr.Textbox(label="Base URL", visible=False)
                model = gr.Textbox(
                    label="Model",
                    value="grok-4.7",
                    info="xAI dùng grok-4.7. Đổi tên model nếu tài khoản của bạn dùng bản khác.",
                )
                with gr.Row():
                    temperature = gr.Slider(0, 1.2, value=0.6, step=0.05, label="Độ sáng tạo")
                    use_vision = gr.Checkbox(value=False, label="Gửi ảnh panel cho model")
                    style = gr.Dropdown(
                        choices=[("Review", "review"), ("Tóm tắt", "tomtat"), ("Hài nhẹ", "hai")],
                        value="review",
                        label="Giọng văn",
                    )
                notes = gr.Textbox(label="Ghi chú thêm cho lời thoại", lines=2)
                with gr.Row():
                    write = gr.Button("Viết kịch bản", variant="primary")
                    manual = gr.Button("Chia cảnh để viết tay")
                script_table = gr.Dataframe(
                    headers=SCENE_HEADERS,
                    label="Kịch bản — chỉ sửa cột Lời review",
                    interactive=True,
                    wrap=True,
                )
                script_file = gr.File(label="Tải script.json")

            with gr.Tab("3. Giọng và video"):
                with gr.Row():
                    voice = gr.Dropdown(choices=FALLBACK_VOICES, value="Hải Đăng", label="Giọng VieNeu-TTS v3 Turbo")
                    refresh = gr.Button("Tải danh sách giọng")
                ref_audio = gr.Audio(label="Hoặc file giọng mẫu 3–8 giây (không bắt buộc)", type="filepath")
                preview = gr.Button("Nghe thử")
                preview_audio = gr.Audio(label="Nghe thử", type="filepath")
                with gr.Row():
                    video_format = gr.Radio(choices=[("YouTube 16:9", "youtube"), ("Shorts 9:16", "shorts")], value="youtube", label="Khung hình")
                    resolution = gr.Radio(choices=["720p", "1080p"], value="720p", label="Độ phân giải")
                with gr.Row():
                    slideshow = gr.Checkbox(value=True, label="Lật vài panel trong mỗi cảnh")
                    ken_burns = gr.Checkbox(value=True, label="Ken Burns khi cảnh chỉ có một panel")
                    burn_subtitles = gr.Checkbox(value=True, label="Đốt phụ đề")
                bgm = gr.Audio(label="Nhạc nền (không bắt buộc)", type="filepath")
                bgm_volume = gr.Slider(0, 0.4, value=0.12, step=0.01, label="Âm lượng nhạc nền")
                render = gr.Button("Xuất video", variant="primary")
                video = gr.Video(label="Video")
                srt_file = gr.File(label="Phụ đề SRT")

        log_box = gr.Textbox(label="Nhật ký", lines=16, elem_id="log")
        gr.Markdown(
            "TTS dùng [VieNeu-TTS v3 Turbo](https://github.com/pnnbao97/VieNeu-TTS) (Apache-2.0, Phạm Nguyễn Ngọc Bảo). "
            "Các bước cắt panel, OCR, lời dẫn và ghép video tham khảo kiến trúc [ManhwaForge](https://github.com/allwin-antony/ManhwaForge)."
        )

        add_page.click(on_add_page, [paste_image, pasted_state], [pasted_state, pasted_gallery, paste_image, log_box])
        drop_page.click(on_drop_page, [pasted_state], [pasted_state, pasted_gallery, log_box])
        clear_pasted.click(on_clear_pages, [pasted_state], [pasted_state, pasted_gallery, log_box])
        prepare.click(
            on_prepare,
            [files, pasted_state, title, chapter, lore, start_page, end_page, do_slice, rtl, do_ocr, langs, use_gpu],
            [job_state, gallery, panel_table, log_box],
        )
        write.click(
            on_script,
            [job_state, scene_count, title, chapter, lore, provider, api_key, base_url, model, temperature, use_vision, style, notes],
            [script_table, script_file, log_box],
        )
        manual.click(
            on_manual,
            [job_state, scene_count, title, chapter, lore],
            [script_table, log_box],
        )
        provider.change(on_provider, provider, [base_url, model])
        refresh.click(on_voices, None, [voice, log_box])
        preview.click(on_preview, [job_state, script_table, voice, ref_audio], [preview_audio, log_box])
        render.click(
            on_render,
            [job_state, script_table, voice, ref_audio, video_format, resolution, slideshow, ken_burns, burn_subtitles, bgm, bgm_volume],
            [video, srt_file, log_box],
        )
    return demo
