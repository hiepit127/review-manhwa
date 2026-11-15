"""Giọng clone lưu trên đĩa, để lần mở sau vẫn có trong danh sách."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave

from src.textutil import slugify


def voices_dir() -> str:
    from src.storage import voices_dir as resolved

    return resolved()


def _index_path() -> str:
    return os.path.join(voices_dir(), "index.json")


def saved_voices() -> list[dict]:
    path = _index_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for item in payload.get("voices") or []:
        name = str(item.get("name") or "").strip()
        filename = os.path.basename(str(item.get("file") or ""))
        if not name or not filename:
            continue
        rows.append({"name": name, "file": filename, "path": os.path.join(voices_dir(), filename)})
    return rows


def saved_names() -> list[str]:
    return [item["name"] for item in saved_voices()]


def is_saved(name: str) -> bool:
    folded = (name or "").strip().casefold()
    return any(item["name"].casefold() == folded for item in saved_voices())


def _write_index(rows: list[dict]) -> None:
    payload = {"voices": [{"name": item["name"], "file": item["file"]} for item in rows]}
    path = _index_path()
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def _duration(path: str) -> float | None:
    try:
        with wave.open(path, "rb") as handle:
            rate = handle.getframerate()
            if rate:
                return handle.getnframes() / float(rate)
    except (wave.Error, OSError):
        pass
    try:
        import soundfile as sf

        info = sf.info(path)
        if info.samplerate:
            return float(info.duration)
    except Exception:
        return None
    return None


def _to_wav(src: str, dest: str) -> None:
    if os.path.splitext(src)[1].lower() == ".wav":
        shutil.copyfile(src, dest)
        return
    try:
        import soundfile as sf

        data, rate = sf.read(src)
        sf.write(dest, data, rate)
        return
    except Exception:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Không đọc được file mẫu. Hãy dùng file WAV.")
    result = subprocess.run(
        [ffmpeg, "-y", "-i", src, dest],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.isfile(dest):
        raise RuntimeError("Không đọc được file mẫu. Hãy dùng file WAV.")


def check_sample(name: str, src: str | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise RuntimeError("Hãy đặt tên cho giọng.")
    if len(cleaned) > 40:
        raise RuntimeError("Tên giọng tối đa 40 ký tự.")
    from src.tts import FALLBACK_VOICES

    reserved = {item.casefold() for item in FALLBACK_VOICES}
    reserved.add("giongreview")
    if cleaned.casefold() in reserved:
        raise RuntimeError("Tên này trùng một giọng có sẵn. Hãy đặt tên khác.")
    if not src or not os.path.isfile(src):
        raise RuntimeError("Hãy chọn file giọng mẫu 3–8 giây.")
    return cleaned


def store_sample(name: str, src: str) -> dict:
    """Ghi file mẫu vào thư mục giọng. Chưa gọi model."""
    cleaned = check_sample(name, src)
    folder = voices_dir()
    filename = (slugify(cleaned) or "giong") + ".wav"
    taken = {item["file"] for item in saved_voices() if item["name"].casefold() != cleaned.casefold()}
    if filename in taken:
        filename = f"{slugify(cleaned) or 'giong'}-{len(taken) + 1}.wav"
    dest = os.path.join(folder, filename)
    partial = dest + ".partial"
    _to_wav(src, partial)
    seconds = _duration(partial)
    if seconds is not None and seconds < 1:
        os.remove(partial)
        raise RuntimeError("File mẫu quá ngắn. Hãy dùng đoạn khoảng 3–8 giây.")
    os.replace(partial, dest)
    rows = [item for item in saved_voices() if item["name"].casefold() != cleaned.casefold()]
    rows.append({"name": cleaned, "file": filename})
    _write_index(rows)
    return {"name": cleaned, "file": filename, "path": dest, "seconds": seconds}


def forget_voice(name: str) -> str:
    folded = (name or "").strip().casefold()
    rows = saved_voices()
    match = next((item for item in rows if item["name"].casefold() == folded), None)
    if match is None:
        raise RuntimeError("Chỉ xóa được giọng đã lưu, không xóa giọng có sẵn.")
    if os.path.isfile(match["path"]):
        os.remove(match["path"])
    _write_index([item for item in rows if item["name"].casefold() != folded])
    return match["name"]
