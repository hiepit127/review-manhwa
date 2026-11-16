#!/usr/bin/env python3
"""Chuẩn bị Review Manhwa trên Google Colab, cùng kiểu với generate-ytb-audio.

Notebook gắn Drive bằng ``google.colab.drive.mount("/content/drive")``.
Script này tạo thư mục và gán biến môi trường để app ghi file thẳng lên ổ đó.
Drive tự đồng bộ. Không gọi API Google Drive, không đọc credential.

    python colab/setup_colab.py all --base /content/drive/MyDrive/ReviewManhwa
    python colab/setup_colab.py all --dry-run --base /tmp/review-manhwa

Secret không in ra. Token GitHub chỉ dùng trong notebook, dưới dạng header.
API key viết lời chỉ là XAI_API_KEY: Colab Secrets, rồi biến môi trường, rồi .env.
Giá trị không in ra.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_BASE = "/content/drive/MyDrive/ReviewManhwa"
DRY = False


def sh(cmd, check=True, quiet=False, **kw):
    """Chạy lệnh. Dry-run chỉ in ra, không chạy."""
    shown = cmd if isinstance(cmd, str) else " ".join(shlex.quote(str(c)) for c in cmd)
    print(f"$ {shown}", flush=True)
    if DRY:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    proc = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kw,
    )
    if proc.stdout and (not quiet or proc.returncode):
        print(proc.stdout[-6000:], end="" if proc.stdout.endswith("\n") else "\n")
    if check and proc.returncode:
        raise SystemExit(f"Lệnh lỗi (exit {proc.returncode}): {shown}")
    return proc


def _storage():
    from src import storage

    return storage


def _under(path: Path, root: Path) -> bool:
    path_s = os.path.abspath(path)
    root_s = os.path.abspath(root)
    return path_s == root_s or path_s.startswith(root_s + os.sep)


def _claims_colab_drive(path: Path) -> bool:
    text = path.as_posix()
    return text == "/content/drive" or text.startswith("/content/drive/")


def _mount_for(path: Path) -> Path | None:
    for candidate in _storage().DRIVE_MOUNTS:
        root = Path(candidate)
        if root.is_dir() and _under(path, root):
            return root
    return None


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _can_use(path: Path, dry: bool) -> bool:
    """Đường dẫn Colab mà chưa gắn ổ thì không tạo thư mục giả."""
    if _claims_colab_drive(path) and _mount_for(path) is None:
        return False
    if dry:
        return True
    return _writable(path)


def gpu_info():
    if not shutil.which("nvidia-smi"):
        return None
    proc = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip() or None


def check_gpu():
    found = gpu_info()
    if found:
        extra = "" if "T4" in found else "  (không phải T4 nhưng vẫn dùng được)"
        print(f"✅ GPU: {found}{extra}")
    else:
        print(
            "⚠️  Không thấy GPU. Vào Runtime → Change runtime type → T4 GPU rồi chạy lại từ đầu.\n"
            "   Vẫn chạy được trên CPU nhưng OCR và VieNeu sẽ chậm."
        )
    return found


def prepare(base=DEFAULT_BASE, hf_on_drive=True, dry_run=None, announce=True) -> dict:
    """Tạo thư mục bền và gán biến môi trường mà app đọc.

    ``base`` là thư mục gốc, mặc định ``MyDrive/ReviewManhwa``. Bên trong có
    ``cache/jobs``, ``cache/voices``, ``output`` và ``hf-cache``. Chưa gắn
    Drive, hoặc không ghi được, thì trỏ về ``cache/`` và ``output/`` cạnh mã nguồn.
    """
    dry = DRY if dry_run is None else dry_run
    requested = Path(base).expanduser()
    note = ""
    if _can_use(requested, dry):
        used = requested
        on_drive = _mount_for(requested) is not None
    else:
        used = Path(REPO)
        on_drive = False
        note = "Chưa gắn Google Drive hoặc không ghi được thư mục đã chọn. Đang lưu trên máy này."
        if announce:
            print("⚠️  " + note)

    layout = _storage().folders(str(used))
    if on_drive and not hf_on_drive and Path("/content").is_dir():
        hf = Path("/content/hf-cache")
    else:
        hf = Path(layout["hf"])
    dirs = [
        Path(layout["cache"]),
        Path(layout["jobs"]),
        Path(layout["voices"]),
        Path(layout["output"]),
        hf,
    ]
    for folder in dirs:
        if announce:
            print(f"📁 {folder}")
        if not dry:
            folder.mkdir(parents=True, exist_ok=True)

    env = {
        "RM_CACHE_DIR": layout["cache"],
        "RM_JOBS_DIR": layout["jobs"],
        "RM_VOICES_DIR": layout["voices"],
        "RM_OUTPUT_DIR": layout["output"],
        "HF_HOME": str(hf),
        "HF_HUB_DISABLE_SYMLINKS": "1",
        "HF_HUB_DISABLE_XET": "1",
    }
    os.environ.update(env)
    if on_drive or os.path.abspath(used) != os.path.abspath(REPO):
        os.environ["RM_DRIVE_ROOT"] = str(used)
        env["RM_DRIVE_ROOT"] = str(used)
    else:
        os.environ.pop("RM_DRIVE_ROOT", None)
        env["RM_DRIVE_ROOT"] = ""

    if on_drive:
        where = "Google Drive"
    elif os.path.abspath(used) == os.path.abspath(REPO):
        where = "máy local"
    else:
        where = "thư mục đã chọn"
    from src.keys import load_api_keys

    load_api_keys()
    if announce:
        print(f"✅ Dữ liệu ({where}): {used}")
    return {
        "base": str(used),
        "on_drive": on_drive,
        "note": note,
        "hf": str(hf),
        **env,
    }


def _torch_constraint() -> str | None:
    """Giữ torch CUDA sẵn có của Colab. Không để pip kéo bản torch khác."""
    try:
        keep = [f"torch=={metadata.version('torch')}"]
    except metadata.PackageNotFoundError:
        return None
    for name in ("torchvision", "numpy"):
        try:
            keep.append(f"{name}=={metadata.version(name)}")
        except metadata.PackageNotFoundError:
            pass
    constraint = "/tmp/review-manhwa-keep.txt"
    if not DRY:
        Path(constraint).write_text("\n".join(keep) + "\n", encoding="utf-8")
    return constraint


def install():
    if Path("/content").is_dir():
        if shutil.which("ffmpeg"):
            print("ffmpeg: có sẵn")
            sh("apt-get -qq install -y fonts-dejavu-core", quiet=True)
        else:
            sh("apt-get -qq update && apt-get -qq install -y ffmpeg fonts-dejavu-core", quiet=True)
    else:
        print("Bỏ qua apt: không phải Colab. Cần ffmpeg trong PATH khi xuất video.")
    cmd = [sys.executable, "-m", "pip", "install", "-q", "-r", str(REPO / "requirements-colab.txt")]
    constraint = _torch_constraint()
    if constraint:
        cmd.extend(["-c", constraint])
    sh(cmd, quiet=True)
    if not DRY:
        print("✅ Đã cài thư viện")


def doctor() -> str:
    from app import doctor as app_doctor

    text = app_doctor()
    print(text)
    return text


def close_ports():
    from src.ports import close_ports as stop

    stop()


def main(argv=None):
    global DRY
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["gpu", "prepare", "install", "doctor", "all"])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--no-hf-on-drive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    DRY = args.dry_run
    if args.step in ("gpu", "all"):
        check_gpu()
    if args.step in ("prepare", "doctor", "all"):
        prepare(args.base, hf_on_drive=not args.no_hf_on_drive)
    if args.step in ("install", "all"):
        install()
    if args.step in ("doctor", "all"):
        if DRY:
            print(f"$ {shlex.quote(sys.executable)} {shlex.quote(str(REPO / 'app.py'))} --doctor")
        else:
            doctor()
    if args.step == "all":
        print("Mở giao diện từ notebook, hoặc chạy: python app.py")


if __name__ == "__main__":
    main()
