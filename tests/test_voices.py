from __future__ import annotations

import os
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


def test_sample_needs_a_name_and_a_file(tmp_path):
    with pytest.raises(RuntimeError, match="đặt tên"):
        check_sample("  ", str(tmp_path / "missing.wav"))
    with pytest.raises(RuntimeError, match="giọng có sẵn"):
        check_sample("Hải Đăng", str(tmp_path / "missing.wav"))
    with pytest.raises(RuntimeError, match="file giọng mẫu"):
        check_sample("Giọng mới", None)


def test_short_sample_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    src = _wav(str(tmp_path / "ngan.wav"), seconds=0.2)
    with pytest.raises(RuntimeError, match="quá ngắn"):
        store_sample("Giọng ngắn", src)
    assert saved_names() == []


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
