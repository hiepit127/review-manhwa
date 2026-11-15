"""prepare() tạo cây thư mục và biến môi trường, cùng kiểu tool audio."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

_KEYS = (
    "RM_DRIVE_ROOT",
    "RM_CACHE_DIR",
    "RM_JOBS_DIR",
    "RM_VOICES_DIR",
    "RM_OUTPUT_DIR",
    "HF_HOME",
    "HF_HUB_DISABLE_SYMLINKS",
    "HF_HUB_DISABLE_XET",
)


def _load():
    path = os.path.join(os.path.dirname(__file__), "..", "colab", "setup_colab.py")
    spec = importlib.util.spec_from_file_location("setup_colab_under_test", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear(monkeypatch):
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


def test_prepare_creates_cache_voices_jobs_output_and_models(tmp_path, monkeypatch):
    setup = _load()
    _clear(monkeypatch)
    monkeypatch.setattr(setup, "REPO", tmp_path / "repo")
    base = tmp_path / "ReviewManhwa"
    info = setup.prepare(str(base))
    assert info["on_drive"] is False
    assert (base / "cache" / "jobs").is_dir()
    assert (base / "cache" / "voices").is_dir()
    assert (base / "output").is_dir()
    assert (base / "hf-cache").is_dir()
    assert os.environ["RM_DRIVE_ROOT"] == str(base)
    assert os.environ["RM_JOBS_DIR"] == str(base / "cache" / "jobs")
    assert os.environ["RM_VOICES_DIR"] == str(base / "cache" / "voices")
    assert os.environ["RM_OUTPUT_DIR"] == str(base / "output")
    assert os.environ["HF_HOME"] == str(base / "hf-cache")
    assert os.environ["HF_HUB_DISABLE_SYMLINKS"] == "1"
    assert os.environ["HF_HUB_DISABLE_XET"] == "1"

    from src.storage import describe

    described = describe()
    assert described["jobs"] == os.environ["RM_JOBS_DIR"]
    assert described["voices"] == os.environ["RM_VOICES_DIR"]
    assert described["output"] == os.environ["RM_OUTPUT_DIR"]


def test_prepare_on_a_mounted_drive(tmp_path, monkeypatch):
    setup = _load()
    _clear(monkeypatch)
    mount = tmp_path / "MyDrive"
    mount.mkdir()
    monkeypatch.setattr("src.storage.DRIVE_MOUNTS", (str(mount),))
    base = mount / "ReviewManhwa"
    info = setup.prepare(str(base))
    assert info["on_drive"] is True
    assert (base / "cache" / "voices").is_dir()
    assert (base / "output").is_dir()
    assert os.environ["RM_DRIVE_ROOT"] == str(base)


def test_missing_colab_drive_falls_back_without_creating_it(tmp_path, monkeypatch):
    setup = _load()
    _clear(monkeypatch)
    monkeypatch.setattr(setup, "REPO", tmp_path / "repo")
    target = "/content/drive/MyDrive/ReviewManhwa-khong-tao"
    info = setup.prepare(target)
    assert info["on_drive"] is False
    assert not os.path.exists(target)
    assert (tmp_path / "repo" / "cache" / "jobs").is_dir()
    assert (tmp_path / "repo" / "cache" / "voices").is_dir()
    assert (tmp_path / "repo" / "output").is_dir()
    assert "RM_DRIVE_ROOT" not in os.environ
    assert os.environ["RM_JOBS_DIR"] == str(tmp_path / "repo" / "cache" / "jobs")


def test_dry_run_prints_steps_and_writes_nothing(tmp_path):
    script = os.path.join(os.path.dirname(__file__), "..", "colab", "setup_colab.py")
    base = tmp_path / "cli"
    proc = subprocess.run(
        [sys.executable, script, "all", "--dry-run", "--base", str(base)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert not base.exists()
    assert str(base / "cache" / "jobs") in proc.stdout
    assert "pip" in proc.stdout
    assert "app.py" in proc.stdout
    assert "secret" not in proc.stdout.lower()
