from __future__ import annotations

import json
import os

import cv2
import numpy as np

from src.cache import audio_can_reuse, remember_audio
from src.pipeline import prepare_job
from src.storage import (
    DEFAULT_NAME,
    describe,
    find_drive_mount,
    publish_outputs,
    resolve_layout,
    set_root,
)
from src.textutil import StepLog


def _isolate(monkeypatch, root):
    monkeypatch.setattr("src.storage.ROOT", str(root))
    monkeypatch.delenv("RM_DRIVE_ROOT", raising=False)
    monkeypatch.delenv("RM_CACHE_DIR", raising=False)
    monkeypatch.delenv("RM_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("RM_JOBS_DIR", raising=False)
    monkeypatch.delenv("RM_VOICES_DIR", raising=False)


def _page(path, color):
    image = np.full((180, 140, 3), color, np.uint8)
    cv2.rectangle(image, (12, 12), (120, 40), (0, 0, 0), -1)
    cv2.imwrite(str(path), image)


def test_missing_drive_uses_local_cache_and_output(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: None)
    info = resolve_layout()
    assert info["on_drive"] is False
    assert info["cache"] == str(tmp_path / "cache")
    assert info["output"] == str(tmp_path / "output")
    assert "Chưa gắn Google Drive" in info["note"]


def test_drive_mount_uses_review_manhwa_folders(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path / "repo")
    mount = tmp_path / "MyDrive"
    mount.mkdir()
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: str(mount))
    info = describe()
    assert info["on_drive"] is True
    assert info["cache"] == str(mount / DEFAULT_NAME / "cache")
    assert info["jobs"] == str(mount / DEFAULT_NAME / "cache" / "jobs")
    assert info["voices"] == str(mount / DEFAULT_NAME / "cache" / "voices")
    assert info["output"] == str(mount / DEFAULT_NAME / "output")
    assert os.path.isdir(info["jobs"])
    assert os.path.isdir(info["output"])


def test_relative_root_and_absolute_root(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path / "repo")
    mount = tmp_path / "MyDrive"
    mount.mkdir()
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: str(mount))
    monkeypatch.setenv("RM_DRIVE_ROOT", "KenhReview")
    info = resolve_layout()
    assert info["cache"] == str(mount / "KenhReview" / "cache")
    custom = tmp_path / "CustomRoot"
    set_root(str(custom))
    info = resolve_layout()
    assert info["custom"] is True
    assert info["cache"] == str(custom / "cache")
    assert os.path.isdir(info["output"])


def test_unwritable_drive_falls_back(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path / "repo")
    mount = tmp_path / "MyDrive"
    mount.mkdir()
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: str(mount))
    real = __import__("src.storage", fromlist=["_writable"])._writable

    def blocked(path):
        if "MyDrive" in path or "ReviewManhwa" in path:
            return False
        return real(path)

    monkeypatch.setattr("src.storage._writable", blocked)
    info = resolve_layout()
    assert info["on_drive"] is False
    assert info["cache"] == str(tmp_path / "repo" / "cache")
    assert "Không ghi được" in info["note"]


def test_drive_path_without_mount_does_not_invent_a_drive(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: None)
    target = "/content/drive/MyDrive/ReviewManhwa-khong-tao"
    monkeypatch.setenv("RM_DRIVE_ROOT", target)
    info = resolve_layout()
    assert info["on_drive"] is False
    assert info["cache"] == str(tmp_path / "cache")
    assert not os.path.exists(target)


def test_jobs_dir_override_wins(tmp_path, monkeypatch):
    from src.storage import jobs_dir

    mount = tmp_path / "MyDrive"
    mount.mkdir()
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: str(mount))
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    assert jobs_dir() == str(tmp_path / "jobs")


def test_find_drive_mount_uses_configured_candidates(tmp_path, monkeypatch):
    missing = tmp_path / "nope"
    present = tmp_path / "MyDrive"
    present.mkdir()
    monkeypatch.setattr("src.storage.DRIVE_MOUNTS", (str(missing),))
    assert find_drive_mount() is None
    monkeypatch.setattr("src.storage.DRIVE_MOUNTS", (str(present),))
    assert find_drive_mount() == str(present)


def test_prepare_reuses_cache_and_can_force_redo(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    page = tmp_path / "page.png"
    _page(page, (30, 140, 200))
    kwargs = dict(
        title="Sống sót",
        chapter="1",
        lore="",
        start_page=1,
        end_page=0,
        do_slice=False,
        rtl=False,
        do_ocr=False,
        langs=["ko"],
        use_gpu=False,
    )
    first = prepare_job([str(page)], log=StepLog(), **kwargs)
    second_log = StepLog()
    second = prepare_job([str(page)], log=second_log, **kwargs)
    assert second["id"] == first["id"]
    assert "Dùng lại cache" in second_log.text()
    assert second["title"] == "Sống sót"
    third = prepare_job([str(page)], log=StepLog(), use_cache=False, **kwargs)
    assert third["id"] != first["id"]


def test_publish_outputs_and_audio_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: None)
    video = tmp_path / "in.mp4"
    srt = tmp_path / "in.srt"
    video.write_bytes(b"video-a")
    srt.write_text("1\n", encoding="utf-8")
    out_video, out_srt = publish_outputs(str(video), str(srt), "job-a", "review.mp4")
    assert os.path.dirname(out_video) == str(tmp_path / "out")
    assert open(out_video, "rb").read() == b"video-a"
    assert open(out_srt, encoding="utf-8").read() == "1\n"
    other = tmp_path / "other.mp4"
    other.write_bytes(b"video-b")
    bumped, _ = publish_outputs(str(other), str(srt), "job-b", "review.mp4")
    assert os.path.basename(bumped).startswith("review-job-b")
    again, _ = publish_outputs(str(other), str(srt), "job-a", "review.mp4")
    assert os.path.basename(again) == "review.mp4"
    assert open(again, "rb").read() == b"video-b"
    meta = json.loads(open(again + ".json", encoding="utf-8").read())
    assert meta["job_id"] == "job-a"

    wav = tmp_path / "line.wav"
    wav.write_bytes(b"RIFFxxxx")
    assert not audio_can_reuse(str(wav), "Xin chào.", "Hải Đăng")
    remember_audio(str(wav), "Xin chào.", "Hải Đăng")
    assert audio_can_reuse(str(wav), "Xin chào.", "Hải Đăng")
    assert not audio_can_reuse(str(wav), "Câu khác.", "Hải Đăng")


def test_parent_path_is_rejected(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: str(tmp_path / "MyDrive"))
    (tmp_path / "MyDrive").mkdir()
    monkeypatch.setenv("RM_DRIVE_ROOT", "../thoat")
    info = resolve_layout()
    assert info["on_drive"] is True
    assert info["cache"] == str(tmp_path / "MyDrive" / DEFAULT_NAME / "cache")
    assert "không hợp lệ" in info["note"]


def test_notebook_mounts_drive():
    text = open(os.path.join(os.path.dirname(__file__), "..", "notebooks", "Review_Manhwa.ipynb"), encoding="utf-8").read()
    assert "drive.mount" in text
    assert "ReviewManhwa" in text
    assert "RM_DRIVE_ROOT" in text
