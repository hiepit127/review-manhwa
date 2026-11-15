"""Nơi lưu cache và video xuất ra.

Cùng cách với tool Audio Full Truyện: Colab gắn Google Drive thành ổ
(`/content/drive/MyDrive`), rồi `colab/setup_colab.py` tạo thư mục và gán
biến môi trường. App chỉ đọc những biến đó và ghi file bằng đường dẫn thường.
Drive tự đồng bộ. Không dùng API Google Drive và không chứa credential.

Mặc định trên Drive là `MyDrive/ReviewManhwa/`:

- `cache/jobs` — panel, chữ OCR, audio, việc đang làm
- `cache/voices` — giọng đã clone
- `output` — video, phụ đề, wav đọc thử
- `hf-cache` — trọng số VieNeu

Máy local đọc `.env` (không commit) nếu có. Chưa gắn Drive, hoặc thư mục
không ghi được, thì dùng `cache/` và `output/` cạnh mã nguồn.
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
HF_DIR_NAME = "hf-cache"
_DOTENV_LOADED = False
# Chỉ đường dẫn. API key không nằm ở đây; src/keys.py đọc Colab Secrets, môi trường và .env.
_DOTENV_KEYS = {
    "RM_DRIVE_ROOT",
    "RM_CACHE_DIR",
    "RM_OUTPUT_DIR",
    "RM_JOBS_DIR",
    "RM_VOICES_DIR",
    "HF_HOME",
    "HF_HUB_DISABLE_SYMLINKS",
    "HF_HUB_DISABLE_XET",
}


def find_drive_mount() -> str | None:
    for path in DRIVE_MOUNTS:
        if os.path.isdir(path):
            return path
    return None


def folders(base: str) -> dict[str, str]:
    """Thư mục cache, việc, giọng, output và model dưới một gốc."""
    cache = os.path.join(base, "cache")
    return {
        "base": base,
        "cache": cache,
        "jobs": os.path.join(cache, "jobs"),
        "voices": os.path.join(cache, "voices"),
        "output": os.path.join(base, "output"),
        "hf": os.path.join(base, HF_DIR_NAME),
    }


def _load_dotenv() -> None:
    """Đọc `.env` một lần. Biến đã có trong môi trường được giữ nguyên."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in _DOTENV_KEYS:
            continue
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


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


def _mounted_drive_path(path: str) -> str:
    """Giữ đường dẫn trên Drive đã gắn. Đường dẫn /content/drive khi chưa gắn thì bỏ."""
    path = (path or "").strip()
    if not path or not _drive_path(path):
        return path
    mount = find_drive_mount()
    if mount and _under(path, mount):
        return path
    return ""


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
    _load_dotenv()
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

    picked = folders(base if (on_drive or custom) else ROOT)
    cache = picked["cache"]
    output = picked["output"]

    cache_override = _mounted_drive_path(os.environ.get("RM_CACHE_DIR") or "")
    output_override = _mounted_drive_path(os.environ.get("RM_OUTPUT_DIR") or "")
    if cache_override:
        cache = cache_override
    if output_override:
        output = output_override

    if not (_writable(cache) and _writable(output)):
        note = "Không ghi được vào thư mục đã chọn. Đang lưu trên máy này."
        on_drive = False
        custom = False
        base = ROOT
        local = folders(ROOT)
        cache = local["cache"]
        output = local["output"]
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
    override = _mounted_drive_path(os.environ.get("RM_JOBS_DIR") or "")
    path = override or os.path.join(resolve_layout()["cache"], "jobs")
    os.makedirs(path, exist_ok=True)
    return path


def voices_dir() -> str:
    override = _mounted_drive_path(os.environ.get("RM_VOICES_DIR") or "")
    path = override or os.path.join(resolve_layout()["cache"], "voices")
    os.makedirs(path, exist_ok=True)
    return path


def output_dir() -> str:
    path = _mounted_drive_path(resolve_layout()["output"]) or folders(ROOT)["output"]
    os.makedirs(path, exist_ok=True)
    return path


def _on_colab() -> bool:
    return "COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ


def prepare_runtime() -> dict:
    """Tạo thư mục dữ liệu. Trên Drive hoặc Colab, giữ model trong hf-cache.

    Drive FUSE không chạy symlink của Hugging Face, nên tắt symlink và Xet,
    cùng cách với tool audio.
    """
    info = resolve_layout()
    os.makedirs(jobs_dir(), exist_ok=True)
    os.makedirs(voices_dir(), exist_ok=True)
    os.makedirs(info["output"], exist_ok=True)
    on_colab = _on_colab()
    if info["on_drive"] or on_colab:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    if not os.environ.get("HF_HOME"):
        if info["on_drive"]:
            os.environ["HF_HOME"] = folders(info["base"])["hf"]
        elif on_colab:
            os.environ["HF_HOME"] = "/content/hf-cache" if os.path.isdir("/content") else folders(ROOT)["hf"]
    hf = os.environ.get("HF_HOME") or ""
    if hf and (info["on_drive"] or on_colab):
        try:
            os.makedirs(hf, exist_ok=True)
        except OSError:
            pass
    return describe()


def describe() -> dict:
    info = resolve_layout()
    info["jobs"] = jobs_dir()
    info["voices"] = voices_dir()
    info["output"] = output_dir()
    info["hf"] = os.environ.get("HF_HOME") or ""
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
    if info.get("hf"):
        lines.append(f"Model: {info['hf']}")
    if info["note"]:
        lines.append(info["note"])
    return "\n".join(lines)


def set_root(path: str) -> dict:
    """Đổi thư mục gốc. Để trống thì tự chọn Drive hoặc máy local.

    Xóa các biến thư mục mà `prepare()` đã gán, để thư mục mới có hiệu lực
    trong cùng phiên.
    """
    cleaned = (path or "").strip()
    previous = os.path.abspath(resolve_layout()["base"])
    if cleaned:
        os.environ["RM_DRIVE_ROOT"] = cleaned
    else:
        os.environ.pop("RM_DRIVE_ROOT", None)
    for key in ("RM_CACHE_DIR", "RM_OUTPUT_DIR", "RM_JOBS_DIR", "RM_VOICES_DIR"):
        os.environ.pop(key, None)
    hf = os.environ.get("HF_HOME") or ""
    if hf and _under(hf, previous):
        os.environ.pop("HF_HOME", None)
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
