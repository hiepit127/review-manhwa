"""Giọng clone lưu trên đĩa, để lần mở sau vẫn có trong danh sách."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave

from src.textutil import slugify

MAX_SAMPLE_BYTES = 10 * 1024 * 1024
PREVIEW_LIMIT = 180
LANGUAGES = ("Việt Nam", "English", "한국어", "中文", "日本語", "Français")
CATEGORIES = ("Truyện", "Review", "Podcast")
SAMPLE_HINT = "3–8 giây"


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
        rows.append(
            {
                "name": name,
                "file": filename,
                "path": os.path.join(voices_dir(), filename),
                "transcript": str(item.get("transcript") or "").strip(),
                "language": str(item.get("language") or "Việt Nam").strip() or "Việt Nam",
                "category": str(item.get("category") or "").strip(),
                "preview_text": str(item.get("preview_text") or "").strip(),
            }
        )
    return rows


def saved_names() -> list[str]:
    return [item["name"] for item in saved_voices()]


def _read_index() -> dict:
    path = _index_path()
    if not os.path.isfile(path):
        return {"voices": []}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"voices": []}
    if not isinstance(payload, dict):
        return {"voices": []}
    payload.setdefault("voices", [])
    return payload


def load_preset_names() -> list[str] | None:
    """Danh sách giọng có sẵn đã cache. None nếu chưa từng tải."""
    names = _read_index().get("presets")
    if not isinstance(names, list) or not names:
        return None
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    return cleaned or None


def save_preset_names(names: list[str]) -> None:
    """Ghi danh sách giọng có sẵn vào index.json, giữ nguyên giọng đã clone."""
    payload = _read_index()
    payload["presets"] = [str(name).strip() for name in names if str(name).strip()]
    path = _index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def is_saved(name: str) -> bool:
    folded = (name or "").strip().casefold()
    return any(item["name"].casefold() == folded for item in saved_voices())


def find_saved(name: str) -> dict | None:
    folded = (name or "").strip().casefold()
    if not folded:
        return None
    return next((item for item in saved_voices() if item["name"].casefold() == folded), None)


def saved_choice_pairs() -> list[tuple[str, str]]:
    pairs = []
    for item in saved_voices():
        seconds = _duration(item["path"])
        label = item["name"] if seconds is None else f"{item['name']} · {seconds:.1f} giây"
        pairs.append((label, item["name"]))
    return pairs


def _write_index(rows: list[dict]) -> None:
    payload = {
        "voices": [
            {
                "name": item["name"],
                "file": item["file"],
                "transcript": item.get("transcript") or "",
                "language": item.get("language") or "Việt Nam",
                "category": item.get("category") or "",
                "preview_text": item.get("preview_text") or "",
            }
            for item in rows
        ]
    }
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


def _ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _is_wav(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"


def _ffmpeg_to_wav(src: str, dest: str) -> str:
    """Trả về chuỗi rỗng khi ghi được WAV. Không thì trả dòng lỗi cuối."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return "chưa có ffmpeg trong PATH"
    result = subprocess.run(
        [ffmpeg, "-y", "-i", src, "-ac", "1", "-f", "wav", dest],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) >= 64 and _is_wav(dest):
        return ""
    lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    return lines[-1] if lines else "ffmpeg không ghi được WAV"


def _to_wav(src: str, dest: str) -> None:
    """Đưa WAV, MP3 hoặc M4A về file WAV. Không tin đuôi file: MP3 đôi khi bị đặt tên .wav."""
    if _is_wav(src):
        shutil.copyfile(src, dest)
        return
    note = _ffmpeg_to_wav(src, dest)
    if not note:
        return
    try:
        import soundfile as sf

        data, rate = sf.read(src)
        sf.write(dest, data, rate, format="WAV")
        if os.path.isfile(dest) and os.path.getsize(dest) >= 64:
            return
    except Exception as error:
        detail = str(error).strip().splitlines()
        if detail:
            note = f"{note}; {detail[-1]}"
    raise RuntimeError(f"Không đọc được file mẫu MP3/M4A. {note}")


def check_name(name: str) -> str:
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
    return cleaned


def check_sample(name: str, src: str | None) -> str:
    cleaned = check_name(name)
    if not src or not os.path.isfile(src):
        raise RuntimeError("Hãy tải file giọng mẫu hoặc ghi âm trực tiếp.")
    size = os.path.getsize(src)
    if size > MAX_SAMPLE_BYTES:
        raise RuntimeError("File lớn hơn 10 MB. Hãy dùng đoạn khoảng 3–8 giây.")
    if size < 64:
        raise RuntimeError("File mẫu trống. Hãy chọn đoạn giọng khác.")
    return cleaned


def prepare_clone(
    name: str,
    src: str | None,
    preview: str,
    consent: bool,
    language: str = "Việt Nam",
    category: str = "",
) -> dict:
    """Kiểm tra form tạo giọng trước khi ghi file. Ô xác nhận là bắt buộc."""
    if not consent:
        raise RuntimeError("Hãy tick ô xác nhận trước khi tạo giọng.")
    cleaned = check_sample(name, src)
    text = (preview or "").strip()
    if not text:
        raise RuntimeError("Hãy nhập văn bản nghe thử.")
    if len(text) > PREVIEW_LIMIT:
        raise RuntimeError(f"Văn bản nghe thử tối đa {PREVIEW_LIMIT} ký tự.")
    lang = language if language in LANGUAGES else "Việt Nam"
    field = category if category in CATEGORIES else ""
    return {
        "name": cleaned,
        "src": src,
        "preview": text,
        "language": lang,
        "category": field,
    }


def voice_meta(item: dict | None) -> str:
    if not item:
        return ""
    bits = [item.get("language") or "Việt Nam"]
    if item.get("category"):
        bits.append(item["category"])
    return " · ".join(bits)


def store_sample(
    name: str,
    src: str,
    transcript: str = "",
    language: str = "Việt Nam",
    category: str = "",
    preview_text: str = "",
) -> dict:
    """Ghi file mẫu vào thư mục giọng. Chưa gọi model."""
    cleaned = check_sample(name, src)
    folder = voices_dir()
    filename = (slugify(cleaned) or "giong") + ".wav"
    taken = {item["file"] for item in saved_voices() if item["name"].casefold() != cleaned.casefold()}
    if filename in taken:
        filename = f"{slugify(cleaned) or 'giong'}-{len(taken) + 1}.wav"
    dest = os.path.join(folder, filename)
    # Đuôi phải là .wav. soundfile và ffmpeg không ghi được ra file .partial.
    partial = dest + ".part.wav"
    try:
        _to_wav(src, partial)
        seconds = _duration(partial)
        if seconds is not None and seconds < 1:
            raise RuntimeError("File mẫu quá ngắn. Hãy dùng đoạn khoảng 3–8 giây.")
        os.replace(partial, dest)
    except Exception:
        if os.path.isfile(partial):
            os.remove(partial)
        raise
    rows = [item for item in saved_voices() if item["name"].casefold() != cleaned.casefold()]
    spoken = (transcript or "").strip()
    lang = language if language in LANGUAGES else "Việt Nam"
    field = category if category in CATEGORIES else ""
    rows.append(
        {
            "name": cleaned,
            "file": filename,
            "transcript": spoken,
            "language": lang,
            "category": field,
            "preview_text": (preview_text or "").strip(),
        }
    )
    _write_index(rows)
    return {
        "name": cleaned,
        "file": filename,
        "path": dest,
        "seconds": seconds,
        "transcript": spoken,
        "language": lang,
        "category": field,
        "preview_text": (preview_text or "").strip(),
    }


def rename_saved(old: str, new: str) -> str:
    cleaned = check_name(new)
    rows = saved_voices()
    match = next((item for item in rows if item["name"].casefold() == (old or "").strip().casefold()), None)
    if match is None:
        raise RuntimeError("Chỉ đổi tên được giọng đã lưu, không đổi giọng có sẵn.")
    taken = find_saved(cleaned)
    if taken and taken["name"].casefold() != match["name"].casefold():
        raise RuntimeError("Đã có một giọng lưu mang tên này.")
    match["name"] = cleaned
    _write_index(rows)
    return cleaned


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
