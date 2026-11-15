"""Nơi lưu cache và video xuất ra.

Trên Colab, Google Drive gắn ở /content/drive/MyDrive. Dữ liệu vào
MyDrive/ReviewManhwa/cache và MyDrive/ReviewManhwa/output, cùng kiểu với
AudioFullTruyen/data của tool audio. Không gắn được Drive, hoặc thư mục
không ghi được, thì dùng cache/ và output/ cạnh mã nguồn.
"""

from __future__ import annotations

import json
import os
import shutil

from src.paths import ROOT

DRIVE_MOUNTS = (
    "/content/drive/MyDrive",
    "/content/drive/My Drive",
)
DEFAULT_NAME = "ReviewManhwa"


def find_drive_mount() -> str | None:
    for path in DRIVE_MOUNTS:
        if os.path.isdir(path):
            return path
    return None


def _under(path: str, root: str) -> bool:
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


def _drive_path(path: str) -> bool:
    normal = os.path.abspath(path).replace("\\", "/")
    return normal == "/content/drive" or normal.startswith("/content/drive/")


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _clean_request(raw: str) -> tuple[str, str]:
    requested = (raw or "").strip().rstrip("/\\")
    if not requested or os.path.isabs(requested):
        return requested, ""
    parts = requested.replace("\\", "/").split("/")
    if ".." in parts:
        return "", "Đường dẫn không hợp lệ. Đang dùng thư mục mặc định."
    return requested, ""


def resolve_layout() -> dict:
    """Quyết định thư mục gốc, cache và output. Không ghi secret."""
    requested, request_note = _clean_request(os.environ.get("RM_DRIVE_ROOT") or "")
    mount = find_drive_mount()
    note = request_note
    on_drive = False
    base = ROOT
    custom = False

    if requested and os.path.isabs(requested):
        if _drive_path(requested) and not (mount and _under(requested, mount)):
            note = note or "Chưa gắn Google Drive. Đang lưu trên máy này."
            base = ROOT
        else:
            base = requested
            custom = True
            on_drive = bool(mount and _under(requested, mount))
    elif requested and mount:
        base = os.path.join(mount, requested)
        custom = True
        on_drive = True
    elif requested and not mount:
        note = note or "Chưa gắn Google Drive. Đang lưu trên máy này."
        base = ROOT
    elif mount:
        base = os.path.join(mount, DEFAULT_NAME)
        on_drive = True
    else:
        note = note or "Chưa gắn Google Drive. Đang lưu trên máy này."
        base = ROOT

    if on_drive or custom:
        cache = os.path.join(base, "cache")
        output = os.path.join(base, "output")
    else:
        cache = os.path.join(ROOT, "cache")
        output = os.path.join(ROOT, "output")

    cache_override = (os.environ.get("RM_CACHE_DIR") or "").strip()
    output_override = (os.environ.get("RM_OUTPUT_DIR") or "").strip()
    if cache_override:
        cache = cache_override
    if output_override:
        output = output_override

    if not (_writable(cache) and _writable(output)):
        note = "Không ghi được vào thư mục đã chọn. Đang lưu trên máy này."
        on_drive = False
        custom = False
        base = ROOT
        cache = os.path.join(ROOT, "cache")
        output = os.path.join(ROOT, "output")
        if not (_writable(cache) and _writable(output)):
            raise RuntimeError("Không tạo được thư mục cache và output trên máy.")

    return {
        "base": base,
        "cache": cache,
        "output": output,
        "on_drive": on_drive,
        "custom": custom,
        "mount": mount or "",
        "note": note,
        "requested": requested,
    }


def jobs_dir() -> str:
    override = (os.environ.get("RM_JOBS_DIR") or "").strip()
    path = override or os.path.join(resolve_layout()["cache"], "jobs")
    os.makedirs(path, exist_ok=True)
    return path


def voices_dir() -> str:
    override = (os.environ.get("RM_VOICES_DIR") or "").strip()
    path = override or os.path.join(resolve_layout()["cache"], "voices")
    os.makedirs(path, exist_ok=True)
    return path


def output_dir() -> str:
    path = resolve_layout()["output"]
    os.makedirs(path, exist_ok=True)
    return path


def prepare_runtime() -> dict:
    """Tạo thư mục và, khi có Drive hoặc Colab, giữ model Hugging Face trong cache."""
    info = resolve_layout()
    os.makedirs(jobs_dir(), exist_ok=True)
    os.makedirs(voices_dir(), exist_ok=True)
    os.makedirs(info["output"], exist_ok=True)
    on_colab = "COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ
    if info["on_drive"] or on_colab:
        os.environ.setdefault("HF_HOME", os.path.join(info["cache"], "huggingface"))
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    return describe()


def describe() -> dict:
    info = resolve_layout()
    info["jobs"] = jobs_dir()
    info["voices"] = voices_dir()
    info["output"] = output_dir()
    return info


def summary_lines() -> str:
    info = describe()
    if info["on_drive"]:
        where = "Google Drive"
    elif info.get("custom"):
        where = "thư mục đã chọn"
    else:
        where = "máy local"
    lines = [
        f"Nơi lưu: {where}",
        f"Cache: {info['jobs']}",
        f"Giọng: {info['voices']}",
        f"Output: {info['output']}",
    ]
    if info["note"]:
        lines.append(info["note"])
    return "\n".join(lines)


def set_root(path: str) -> dict:
    """Đổi thư mục gốc. Để trống thì tự chọn Drive hoặc máy local."""
    cleaned = (path or "").strip()
    if cleaned:
        os.environ["RM_DRIVE_ROOT"] = cleaned
    else:
        os.environ.pop("RM_DRIVE_ROOT", None)
    os.environ.pop("RM_CACHE_DIR", None)
    os.environ.pop("RM_OUTPUT_DIR", None)
    return prepare_runtime()


def allowed_paths() -> list[str]:
    info = describe()
    ordered = [info["cache"], info["jobs"], info["voices"], info["output"], ROOT]
    extra = (os.environ.get("RM_JOBS_DIR") or "").strip()
    if extra:
        ordered.append(extra)
    unique = []
    seen = set()
    for path in ordered:
        absolute = os.path.abspath(path)
        if absolute in seen or not os.path.isdir(absolute):
            continue
        seen.add(absolute)
        unique.append(absolute)
    return unique


def _owner_of(meta_path: str) -> str:
    if not os.path.isfile(meta_path):
        return ""
    try:
        with open(meta_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("job_id") or "")


def publish_outputs(video: str, srt: str, job_id: str, filename: str) -> tuple[str, str]:
    """Chép video và phụ đề sang thư mục output, giữ bản trong cache của job."""
    folder = output_dir()
    dest_video = os.path.join(folder, filename)
    meta_path = dest_video + ".json"
    if os.path.exists(dest_video):
        owner = _owner_of(meta_path)
        if owner and owner != job_id:
            stem, ext = os.path.splitext(filename)
            dest_video = os.path.join(folder, f"{stem}-{job_id}{ext}")
            meta_path = dest_video + ".json"
    if os.path.abspath(video) != os.path.abspath(dest_video):
        shutil.copy2(video, dest_video)
    dest_srt = os.path.splitext(dest_video)[0] + ".srt"
    if srt and os.path.isfile(srt) and os.path.abspath(srt) != os.path.abspath(dest_srt):
        shutil.copy2(srt, dest_srt)
    temporary = meta_path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(
            {"job_id": job_id, "video": os.path.basename(dest_video), "srt": os.path.basename(dest_srt)},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(temporary, meta_path)
    return dest_video, dest_srt
