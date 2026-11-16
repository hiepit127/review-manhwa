"""Nhiều link, tách panel, cache giọng, và prompt mẫu cách kể."""

from __future__ import annotations

import io
import os

import cv2
import numpy as np
from PIL import Image

from src.comicfetch import fetch_many
from src.panelboard import move_panel, remove_panel, restore_panel, split_existing
from src.script import _user_prompt, read_style_sample
from src.voices import load_preset_names, save_preset_names, saved_names


def _png(width, height, color) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_fetch_many_keeps_line_order(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    pages = {
        "https://reader.example/chuong-1": "<div class='chapter-images-container'><img src='https://img.example/a.jpg'></div>",
        "https://reader.example/chuong-2": "<div class='chapter-images-container'><img src='https://img.example/b.jpg'></div>",
    }
    blobs = {
        "https://img.example/a.jpg": _png(800, 1000, (10, 10, 10)),
        "https://img.example/b.jpg": _png(800, 1100, (200, 200, 200)),
    }
    monkeypatch.setattr("src.comicfetch.fetch_html", lambda url: pages[url])
    monkeypatch.setattr("src.comicfetch._download_bytes", lambda url, referer, timeout: blobs[url])
    result = fetch_many("https://reader.example/chuong-1\n\nhttps://reader.example/chuong-2\n", 0, lambda _message: None)
    assert result["count"] == 2
    assert result["chapter"] == "Chương 1-2"
    means = []
    for path in result["pages"]:
        image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        means.append(float(image.mean()))
    assert means[0] < 40
    assert means[1] > 150


def test_split_remove_move_and_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    from src.jobs import save_job

    page = tmp_path / "page.png"
    image = np.full((700, 600, 3), 255, np.uint8)
    blocks = [
        (20, 20, 270, 300, (30, 30, 30)),
        (330, 20, 580, 300, (180, 180, 180)),
        (20, 360, 580, 680, (90, 90, 90)),
    ]
    for x0, y0, x1, y1, color in blocks:
        image[y0:y1, x0:x1] = color
        cv2.rectangle(image, (x0 + 8, y0 + 8), (x0 + 180, y0 + 36), (0, 0, 0), -1)
    cv2.imwrite(str(page), image)
    job_id = "job-panels"
    folder = tmp_path / "jobs" / job_id / "source"
    folder.mkdir(parents=True)
    target = folder / "page_0001.png"
    cv2.imwrite(str(target), image)
    save_job({"id": job_id, "title": "T", "chapter": "1", "lore": "", "pages": ["source/page_0001.png"], "panels": [], "scenes": []})
    job = split_existing(job_id, False, lambda _message: None)
    assert len(job["panels"]) == 3
    moved = move_panel(job_id, 1, 1)
    assert moved["panels"][1]["index"] == 1
    removed = remove_panel(job_id, 1)
    assert len(removed["panels"]) == 2
    assert len(removed["removed"]) == 1
    restored = restore_panel(job_id)
    assert len(restored["panels"]) == 3
    assert restored["removed"] == []


def test_voice_preset_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    assert load_preset_names() is None
    save_preset_names(["Hải Đăng", "Mai Anh"])
    assert load_preset_names() == ["Hải Đăng", "Mai Anh"]
    assert saved_names() == []
    from src.tts import voice_choices

    labels = voice_choices()
    assert labels[0] == "Hải Đăng"
    assert "Mai Anh" in labels


def test_style_reference_is_in_the_prompt_as_style_not_plot(tmp_path):
    sample = tmp_path / "mau.srt"
    sample.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nNgày ấy có một thuyền trưởng tên Là Đốm.\n",
        encoding="utf-8",
    )
    text = read_style_sample(str(sample))
    assert "thuyền trưởng tên Là Đốm" in text
    assert "-->" not in text
    prompt = _user_prompt(
        [{"id": 1, "ocr": "Xin chào"}],
        {"title": "Truyện A", "chapter": "1", "lore": "", "style_text": "kể chậm", "style_reference": text},
        "",
    )
    assert "Không chép nội dung" in prompt
    assert "thuyền trưởng tên Là Đốm" in prompt
    assert "Truyện A" in prompt
