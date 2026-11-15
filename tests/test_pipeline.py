from __future__ import annotations

import json
import os
import zipfile

import cv2
import numpy as np
import pytest

from src.ingest import collect_pages
from src.panels import is_blank, slice_pages
from src.paste import add_pasted_page, clear_pages, drop_last_page
from src.pipeline import assign_scenes, prepare_job
from src.scenes import group_panels
from src.textutil import (
    StepLog,
    apply_range,
    format_srt_time,
    narrations_from_payload,
    natural_key,
    parse_json_object,
    sample_even,
    slugify,
    split_for_tts,
)


def test_natural_sort_and_range():
    names = ["page_10.png", "page_2.png", "page_1.png"]
    assert sorted(names, key=natural_key) == ["page_1.png", "page_2.png", "page_10.png"]
    assert apply_range(names, 2, 3) == ["page_2.png", "page_1.png"]
    assert apply_range(["a"], 1, 0) == ["a"]
    assert apply_range(["a", "b"], 3, 0) == []


def test_slug_srt_and_script_parse():
    assert slugify("Sống Sót Ở Đêm") == "song-sot-o-dem"
    assert format_srt_time(1.25) == "00:00:01,250"
    assert format_srt_time(3661.009) == "01:01:01,009"
    payload = parse_json_object('```json\n{"scenes":[{"id":2,"narration":"Câu hai."},{"id":1,"narration":"Câu một."}]}\n```')
    assert narrations_from_payload(payload, [1, 2]) == ["Câu một.", "Câu hai."]
    assert split_for_tts("Ngắn.") == ["Ngắn."]
    assert sample_even(["a", "b", "c", "d", "e"], 3) == ["a", "c", "e"]


def test_group_panels_spreads_remainder():
    panels = [{"index": index, "image": f"{index}.png", "ocr": "lời"} for index in range(5)]
    scenes = group_panels(panels, 2)
    assert [len(scene["panel_indexes"]) for scene in scenes] == [3, 2]
    assert scenes[0]["id"] == 1
    assert "lời" in scenes[1]["ocr"]


def _write_color(path, color, width=120, height=160):
    image = np.full((height, width, 3), color, np.uint8)
    cv2.rectangle(image, (8, 8), (width - 8, 36), (0, 0, 0), -1)
    cv2.imwrite(path, image)


def _page_with_three_panels(path):
    image = np.full((700, 600, 3), 255, np.uint8)
    blocks = [
        (20, 20, 270, 300, (30, 30, 30)),
        (330, 20, 580, 300, (180, 180, 180)),
        (20, 360, 580, 680, (90, 90, 90)),
    ]
    for x0, y0, x1, y1, color in blocks:
        image[y0:y1, x0:x1] = color
        cv2.rectangle(image, (x0 + 8, y0 + 8), (x0 + 180, y0 + 36), (0, 0, 0), -1)
    cv2.imwrite(path, image)


def _center(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    height, width = image.shape
    sample = image[height // 2 - 4 : height // 2 + 4, width // 2 - 4 : width // 2 + 4]
    return float(sample.mean())


def test_slice_orders_panels_and_skips_blank(tmp_path):
    page = tmp_path / "page.png"
    blank = tmp_path / "blank.png"
    _page_with_three_panels(page)
    cv2.imwrite(str(blank), np.full((180, 180, 3), 255, np.uint8))
    assert is_blank(cv2.imread(str(blank)))
    saved = slice_pages([str(blank), str(page)], str(tmp_path / "panels"), True, False, StepLog())
    assert len(saved) == 3
    means = [_center(path) for path in saved]
    assert means[0] < 50
    assert means[1] > 150
    assert 70 < means[2] < 120
    rtl = slice_pages([str(page)], str(tmp_path / "rtl"), True, True, StepLog())
    rtl_means = [_center(path) for path in rtl]
    assert rtl_means[0] > 150
    assert rtl_means[1] < 50


def test_prepare_sorts_images_and_blocks_zip_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    source = tmp_path / "src"
    source.mkdir()
    _write_color(source / "page_10.png", (30, 30, 30))
    _write_color(source / "page_2.png", (120, 120, 120))
    _write_color(source / "page_1.png", (220, 220, 220))
    archive = tmp_path / "chap.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(zipfile.ZipInfo("../evil.png"), b"nope")
        handle.write(source / "page_1.png", "chap/page_1.png")
        handle.write(source / "page_2.png", "chap/page_2.png")
        handle.write(source / "page_10.png", "chap/page_10.png")
    job = prepare_job(
        [str(archive)],
        title="Sống Sót",
        chapter="1",
        lore="",
        start_page=1,
        end_page=0,
        do_slice=False,
        rtl=False,
        do_ocr=False,
        langs=["en"],
        use_gpu=False,
        log=StepLog(),
    )
    assert not (tmp_path / "evil.png").exists()
    assert not os.path.exists(os.path.join(job["dir"], "evil.png"))
    assert len(job["panels"]) == 3
    centers = [_center(os.path.join(job["dir"], panel["image"])) for panel in job["panels"]]
    assert centers[0] > 180
    assert 80 < centers[1] < 160
    assert centers[2] < 50
    job = assign_scenes(job["id"], 2, "Sống Sót", "1", "rừng", StepLog())
    assert len(job["scenes"]) == 2
    assert job["lore"] == "rừng"


def test_collect_page_range(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    for name, color in (("b.png", (0, 0, 10)), ("a.png", (0, 0, 240))):
        _write_color(folder / name, color)
    pages = collect_pages([str(folder / "b.png"), str(folder / "a.png")], str(tmp_path / "job"), 2, 2, StepLog())
    assert len(pages) == 1
    assert _center(pages[0]) < 40


def test_pasted_pages_keep_order(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    dark = tmp_path / "dark.png"
    light = tmp_path / "light.png"
    _write_color(dark, (20, 20, 20))
    _write_color(light, (210, 210, 210))
    pages = add_pasted_page(str(dark), [])
    pages = add_pasted_page(str(light), pages)
    assert [os.path.basename(path) for path in pages] == ["page_0001.png", "page_0002.png"]
    assert _center(pages[0]) < 50
    assert _center(pages[1]) > 170
    pages = drop_last_page(pages)
    assert len(pages) == 1
    assert not os.path.exists(os.path.join(os.path.dirname(pages[0]), "page_0002.png"))
    pages = add_pasted_page(str(light), pages)
    assert os.path.basename(pages[1]) == "page_0002.png"
    with pytest.raises(RuntimeError):
        add_pasted_page(None, pages)
    assert clear_pages(pages) == []


def test_pdf_page_range(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    for _ in range(3):
        document.new_page(width=400, height=500)
    path = tmp_path / "chap.pdf"
    document.save(path)
    document.close()
    pages = collect_pages([str(path)], str(tmp_path / "job"), 2, 3, StepLog())
    assert len(pages) == 2
    assert all(page.endswith(".png") for page in pages)


def test_load_prompt():
    pytest.importorskip("yaml")
    from src.script import load_config

    config = load_config()
    assert "review" in config["styles"]
    assert "tiếng Việt" in "\n".join(config["rules"])


def test_render_video(tmp_path):
    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("cần ffmpeg")
    import soundfile as sf

    from src.video import render_video

    images = []
    for index, color in enumerate(((20, 40, 200), (40, 180, 40), (180, 80, 20))):
        path = tmp_path / f"panel_{index}.png"
        _write_color(path, color, 640, 900)
        images.append(str(path))
    rate = 48000
    tone = 0.1 * np.sin(2 * np.pi * 220 * np.linspace(0, 1.0, rate, endpoint=False))
    audio_a = tmp_path / "a.wav"
    audio_b = tmp_path / "b.wav"
    bgm = tmp_path / "bgm.wav"
    sf.write(audio_a, tone, rate)
    sf.write(audio_b, tone[: int(rate * 0.8)], rate)
    sf.write(bgm, 0.05 * tone, rate)
    log = StepLog()
    video, srt = render_video(
        [
            {"images": [images[0]], "audio": str(audio_a), "narration": "Hắn bước vào rừng."},
            {"images": [images[1], images[2]], "audio": str(audio_b), "narration": "Rồi cánh cửa đóng lại."},
        ],
        str(tmp_path / "review.mp4"),
        video_format="youtube",
        resolution="720p",
        slideshow=True,
        ken_burns=True,
        burn_subtitles=True,
        bgm_path=str(bgm),
        bgm_volume=0.1,
        log=log,
    )
    assert os.path.getsize(video) > 1000
    text = open(srt, encoding="utf-8").read()
    assert "Hắn bước vào rừng." in text
    probe = __import__("shutil").which("ffprobe")
    if probe:
        import subprocess

        raw = subprocess.check_output(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
            text=True,
        )
        assert float(raw.strip()) > 1.0
    assert json.dumps(log.text(), ensure_ascii=False)
