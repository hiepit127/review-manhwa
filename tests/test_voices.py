from __future__ import annotations

import os
import shutil
import subprocess
import wave

import pytest

from app import choose_port
from src.tts import save_cloned_voice
from src.voices import check_sample, forget_voice, is_saved, saved_names, store_sample


def _wav(path: str, seconds: float = 2.0) -> str:
    rate = 8000
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def test_saved_voice_stays_in_the_list(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "mau.wav"))
    record = store_sample("Giọng review", src)
    assert record["name"] == "Giọng review"
    assert os.path.isfile(record["path"])
    assert saved_names() == ["Giọng review"]
    assert is_saved("giọng review")
    again = store_sample("Giọng review", src)
    assert saved_names() == ["Giọng review"]
    assert again["path"] == record["path"]


def test_clone_form_requires_consent_and_keeps_metadata(tmp_path, monkeypatch):
    from src.voices import prepare_clone

    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "mau.wav"), seconds=3)
    with pytest.raises(RuntimeError, match="xác nhận"):
        prepare_clone("Giọng review", src, "Xin chào.", False)
    with pytest.raises(RuntimeError, match="180"):
        prepare_clone("Giọng review", src, "à" * 181, True)
    form = prepare_clone("Giọng review", src, "Xin chào các bạn.", True, "Việt Nam", "Review")
    record = store_sample(
        form["name"],
        form["src"],
        language=form["language"],
        category=form["category"],
        preview_text=form["preview"],
    )
    assert record["language"] == "Việt Nam"
    assert record["category"] == "Review"
    assert record["preview_text"] == "Xin chào các bạn."
    huge = tmp_path / "lon.wav"
    huge.write_bytes(b"RIFFxxxx" + b"0" * (10 * 1024 * 1024))
    with pytest.raises(RuntimeError, match="10 MB"):
        store_sample("Giọng to", str(huge))


def test_create_voice_saves_even_when_preview_cannot_play(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setenv("RM_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: None)

    def boom(log=None):
        raise RuntimeError("chưa có VieNeu")

    monkeypatch.setattr("src.tts.get_engine", boom)
    from src.tts import create_cloned_voice

    src = _wav(str(tmp_path / "mau.wav"), seconds=3)
    made = create_cloned_voice("Giọng review", src, "Xin chào.", True, "Việt Nam", "Podcast", log=lambda message: None)
    assert made["name"] == "Giọng review"
    assert made["warning"]
    assert os.path.isfile(made["sample"])
    assert is_saved("Giọng review")
    assert made["preview"] == ""


def test_sample_needs_a_name_and_a_file(tmp_path):
    with pytest.raises(RuntimeError, match="đặt tên"):
        check_sample("  ", str(tmp_path / "missing.wav"))
    with pytest.raises(RuntimeError, match="giọng có sẵn"):
        check_sample("Hải Đăng", str(tmp_path / "missing.wav"))
    with pytest.raises(RuntimeError, match="file giọng mẫu"):
        check_sample("Giọng mới", None)


def _mp3(path: str, seconds: float = 3.0) -> str:
    if not shutil.which("ffmpeg"):
        pytest.skip("cần ffmpeg")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-q:a",
            "7",
            path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return path


def test_mp3_sample_is_stored_as_wav(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _mp3(str(tmp_path / "mau.mp3"))
    record = store_sample("Giọng mp3", src, language="Việt Nam", category="Review")
    assert record["path"].endswith(".wav")
    assert record["file"].endswith(".wav")
    with wave.open(record["path"], "rb") as handle:
        heard = handle.getnframes() / float(handle.getframerate())
    assert 2.5 < heard < 3.5
    assert is_saved("Giọng mp3")


def test_mp3_renamed_as_wav_is_still_decoded(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    made = _mp3(str(tmp_path / "that.mp3"))
    src = tmp_path / "doi-ten.wav"
    shutil.copyfile(made, src)
    record = store_sample("Giọng doi ten", str(src))
    with wave.open(record["path"], "rb") as handle:
        heard = handle.getnframes() / float(handle.getframerate())
    assert 2.5 < heard < 3.5


def test_mp3_still_converts_when_soundfile_cannot_read_it(tmp_path, monkeypatch):
    import soundfile

    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _mp3(str(tmp_path / "mau.mp3"), seconds=3)

    def unreadable(*_args, **_kwargs):
        raise RuntimeError("libsndfile không đọc MP3")

    monkeypatch.setattr(soundfile, "read", unreadable)
    record = store_sample("Giọng ffmpeg", src)
    with wave.open(record["path"], "rb") as handle:
        heard = handle.getnframes() / float(handle.getframerate())
    assert 2.5 < heard < 3.5


def test_short_sample_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "ngan.wav"), seconds=0.2)
    with pytest.raises(RuntimeError, match="quá ngắn"):
        store_sample("Giọng ngắn", src)
    assert saved_names() == []


def test_transcript_is_kept_and_voice_can_be_renamed(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "mau.wav"))
    record = store_sample("Giọng review", src, transcript="Xin chào các bạn.")
    assert record["transcript"] == "Xin chào các bạn."
    from src.voices import find_saved, rename_saved

    assert find_saved("Giọng review")["transcript"] == "Xin chào các bạn."
    assert rename_saved("Giọng review", "Giọng kênh") == "Giọng kênh"
    renamed = find_saved("Giọng kênh")
    assert renamed["transcript"] == "Xin chào các bạn."
    assert os.path.isfile(renamed["path"])
    assert saved_names() == ["Giọng kênh"]
    with pytest.raises(RuntimeError, match="giọng có sẵn"):
        rename_saved("Giọng kênh", "Hải Đăng")


def test_speech_file_lands_in_output(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setenv("RM_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("src.storage.find_drive_mount", lambda: None)
    src = _wav(str(tmp_path / "mau.wav"), seconds=3)
    store_sample("Giọng review", src)
    monkeypatch.setattr("src.tts.open_voice", lambda *args, **kwargs: "Giọng review")

    def fake_synth(text, voice, dest, log=None):
        with open(dest, "wb") as handle:
            handle.write(b"RIFFdemo")
        return dest

    monkeypatch.setattr("src.tts.synthesize_to_file", fake_synth)
    from src.tts import generate_speech

    path = generate_speech("Xin chào. Đây là đoạn đọc thử.", "Giọng review", log=lambda message: None)
    assert os.path.dirname(path) == str(tmp_path / "out")
    assert open(path, "rb").read() == b"RIFFdemo"


def test_only_saved_voices_can_be_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "mau.wav"))
    store_sample("Giọng review", src)
    assert forget_voice("Giọng review") == "Giọng review"
    assert saved_names() == []
    assert not os.path.exists(os.path.join(tmp_path, "voices", "giong-review.wav"))
    with pytest.raises(RuntimeError, match="giọng đã lưu"):
        forget_voice("Hải Đăng")


def test_busy_port_lets_gradio_pick_the_next_one():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        busy = sock.getsockname()[1]
        assert choose_port(busy) is None
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = sock.getsockname()[1]
    assert choose_port(free) == free


def test_clone_enrolls_the_saved_name(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setattr("src.tts._ENROLLED", set())
    enrolled = []

    class Engine:
        def add_voice(self, name, path, denoise=True):
            enrolled.append((name, os.path.isfile(path), denoise))

        def list_preset_voices(self):
            return []

    monkeypatch.setattr("src.tts.get_engine", lambda log=None: Engine())
    src = _wav(str(tmp_path / "mau.wav"))
    assert save_cloned_voice("Giọng review", src, log=lambda message: None) == "Giọng review"
    assert enrolled[-1][0] == "Giọng review"
    assert enrolled[-1][1] is True
    assert is_saved("Giọng review")
