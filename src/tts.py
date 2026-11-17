"""Đọc lời review bằng VieNeu-TTS v3 Turbo. Model mở một lần cho cả phiên."""

from __future__ import annotations

import os

import numpy as np

from src.textutil import split_for_tts

SAMPLE_RATE = 48000
FALLBACK_VOICES = [
    "Hải Đăng",
    "Mai Anh",
    "Phạm Tuyên",
    "Trúc Ly",
    "Thiện Minh",
    "Thùy Dung",
    "Thiền Tâm Đức",
    "Ngọc Huyền",
    "Quang Sơn",
    "Ngọc Trân",
    "Adam bựa",
    "Minh Đức",
    "Xuân Vĩnh",
    "Thanh Bình",
    "Ngọc Linh",
    "Đoan Trang",
    "Quỳnh Anh",
    "Quốc Tuấn",
    "Adam",
    "Thái Sơn",
    "Thục Đoan",
    "Minh Triết",
    "Mỹ Duyên",
    "Đức Trí",
    "Kim Thanh",
]

_ENGINE = None
_ENROLLED: set[str] = set()
DEFAULT_LINE = "Xin chào. Đây là giọng sẽ đọc phần review."


def _empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def get_engine(log=None):
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    if log:
        log("Đang mở VieNeu-TTS v3 Turbo. Lần đầu sẽ tải model từ Hugging Face.")
    try:
        from vieneu import Vieneu
    except ImportError as error:
        raise RuntimeError(
            "Chưa cài vieneu. Trên Colab: pip install vieneu \"transformers==4.57.6\" safetensors"
        ) from error
    try:
        import torch

        if torch.cuda.is_available():
            if log:
                log(f"VieNeu dùng GPU {torch.cuda.get_device_name(0)}")
        elif log:
            log("VieNeu dùng CPU (ONNX). Bật GPU của Colab nếu muốn nhanh hơn.")
    except Exception:
        if log:
            log("VieNeu dùng CPU (ONNX).")
    _ENGINE = Vieneu()
    register_saved(_ENGINE, log)
    return _ENGINE


def _voice_id(item) -> str:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return str(item[1])
    if isinstance(item, (list, tuple)) and item:
        return str(item[0])
    return str(item)


def _enroll(engine, name: str, path: str, transcript: str = "") -> None:
    """Đưa một file mẫu vào model. VieNeu v3 Turbo không cần lời của đoạn mẫu."""
    spoken = (transcript or "").strip()
    attempts = []
    if spoken:
        attempts.append({"denoise": True, "ref_text": spoken})
        attempts.append({"ref_text": spoken})
    attempts.append({"denoise": True})
    attempts.append({})
    last = None
    for kwargs in attempts:
        try:
            engine.add_voice(name, path, **kwargs)
            return
        except TypeError as error:
            last = error
    if last is not None:
        engine.add_voice(name, path)


def register_saved(engine, log=None) -> None:
    """Đưa các giọng đã lưu vào model của phiên này, mỗi giọng một lần."""
    from src.voices import saved_voices

    for item in saved_voices():
        name = item["name"]
        if name in _ENROLLED:
            continue
        if not os.path.isfile(item["path"]):
            continue
        try:
            _enroll(engine, name, item["path"], item.get("transcript") or "")
        except Exception as error:
            if log:
                log(f"Không mở được giọng đã lưu {name}: {error}")
            continue
        _ENROLLED.add(name)


def list_voices(log=None, refresh: bool = False) -> list[str]:
    """Danh sách giọng. Lần sau đọc cache trên Drive, trừ khi bấm làm mới."""
    from src.voices import load_preset_names, save_preset_names, saved_names

    cached = None if refresh else load_preset_names()
    if cached:
        if log:
            log(f"Dùng danh sách giọng đã cache ({len(cached)} giọng).")
        labels = list(cached)
    else:
        engine = get_engine(log)
        try:
            voices = engine.list_preset_voices()
        except Exception as error:
            if log:
                log(f"Không lấy được danh sách giọng ({error}). Dùng danh sách có sẵn.")
            voices = []
        labels = []
        for item in voices or []:
            label = _voice_id(item)
            if label not in labels:
                labels.append(label)
        if not labels:
            labels = list(FALLBACK_VOICES)
        save_preset_names(labels)
        if log:
            log(f"Đã ghi {len(labels)} giọng vào cache.")
    for name in saved_names():
        if name not in labels:
            labels.append(name)
    return labels


def voice_choices() -> list[str]:
    """Danh sách hiện trên UI. Có cache thì không mở model."""
    from src.voices import load_preset_names, saved_names

    labels = list(load_preset_names() or FALLBACK_VOICES)
    for name in saved_names():
        if name not in labels:
            labels.append(name)
    return labels


def _resolve_voice(engine, name: str) -> str:
    labels = []
    try:
        for item in engine.list_preset_voices() or []:
            label = _voice_id(item)
            shown = str(item[0]) if isinstance(item, (list, tuple)) and item else label
            labels.append(label)
            if name.casefold() in (label.casefold(), shown.casefold()):
                return label
    except Exception:
        labels = []
    resolver = getattr(engine, "resolve_voice_name", None)
    if resolver:
        try:
            found = resolver(name)
        except Exception:
            found = None
        if found:
            return found
    if name in labels or not labels:
        return name
    raise RuntimeError("Không có giọng này. Các giọng đang có: " + ", ".join(labels))


def open_voice(voice: str, ref_audio: str | None, log=None) -> str:
    """Mở model một lần và trả về tên giọng sẽ dùng cho cả chương."""
    from src.voices import is_saved

    engine = get_engine(log)
    if is_saved(voice):
        register_saved(engine, log)
        if log:
            log(f"Dùng giọng đã lưu {voice}.")
        return _resolve_voice(engine, voice)
    if ref_audio:
        name = "GiongReview"
        try:
            engine.add_voice(name, ref_audio)
        except Exception:
            engine.add_voice(name, ref_audio, denoise=False)
        _ENROLLED.add(name)
        if log:
            log("Đã lấy giọng từ file mẫu cho phiên này.")
        return name
    return _resolve_voice(engine, voice)


def save_cloned_voice(name: str, ref_audio: str | None, transcript: str = "", log=None) -> str:
    """Clone một file mẫu 3–8 giây và ghi giọng vào danh sách."""
    from src.voices import check_sample, saved_voices, store_sample

    cleaned = check_sample(name, ref_audio)
    spoken = (transcript or "").strip()
    if log:
        log(f"Đang clone giọng {cleaned}.")
        if spoken:
            log("Có lời của đoạn mẫu. Gửi kèm nếu bản VieNeu nhận.")
        else:
            log("VieNeu v3 Turbo clone từ đoạn mẫu, không cần lời của đoạn đó.")
    engine = get_engine(log)
    register_saved(engine, log)
    existing = {item.casefold() for item in _preset_names(engine)}
    if cleaned.casefold() in existing and not any(item["name"].casefold() == cleaned.casefold() for item in saved_voices()):
        raise RuntimeError("Tên này trùng một giọng có sẵn. Hãy đặt tên khác.")
    record = store_sample(cleaned, ref_audio, spoken)
    try:
        _enroll(engine, record["name"], record["path"], spoken)
    except Exception:
        from src.voices import forget_voice

        forget_voice(record["name"])
        raise
    _ENROLLED.add(record["name"])
    seconds = record.get("seconds")
    if log:
        if seconds and seconds > 8:
            log("File dài hơn 8 giây. VieNeu dùng khoảng 8 giây đầu.")
        log(f"Đã lưu giọng {record['name']} vào danh sách.")
    return record["name"]


def create_cloned_voice(
    name: str,
    ref_audio: str | None,
    preview_text: str,
    consent: bool,
    language: str = "Việt Nam",
    category: str = "",
    log=None,
) -> dict:
    """Lưu giọng vào cache/voices, rồi đọc câu nghe thử nếu VieNeu mở được."""
    from src.voices import prepare_clone, store_sample

    form = prepare_clone(name, ref_audio, preview_text, consent, language, category)
    if log:
        log(f"Đang tạo giọng {form['name']}.")
    record = store_sample(
        form["name"],
        form["src"],
        language=form["language"],
        category=form["category"],
        preview_text=form["preview"],
    )
    preview_path = ""
    warning = ""
    try:
        engine = get_engine(log)
        register_saved(engine, log)
        _enroll(engine, record["name"], record["path"], "")
        _ENROLLED.add(record["name"])
        preview_path = speech_output_path(record["name"])
        synthesize_to_file(form["preview"], record["name"], preview_path, log)
        if log:
            log(f"Đã lưu giọng {record['name']} và đọc câu nghe thử.")
    except Exception as error:
        warning = str(error).strip() or error.__class__.__name__
        if log:
            log(f"Đã lưu giọng {record['name']}. Chưa nghe thử được: {warning}")
    return {
        "name": record["name"],
        "sample": record["path"],
        "preview": preview_path,
        "warning": warning,
        "language": record["language"],
        "category": record["category"],
    }


def rename_cloned_voice(old: str, new: str, log=None) -> str:
    from src.voices import find_saved, rename_saved

    renamed = rename_saved(old, new)
    _ENROLLED.discard((old or "").strip())
    item = find_saved(renamed)
    if _ENGINE is not None and item and os.path.isfile(item["path"]):
        remover = getattr(_ENGINE, "remove_voice", None)
        if remover:
            try:
                remover((old or "").strip())
            except Exception:
                pass
        try:
            _enroll(_ENGINE, renamed, item["path"], item.get("transcript") or "")
            _ENROLLED.add(renamed)
        except Exception as error:
            if log:
                log(f"Đã đổi tên trên đĩa. Phiên này chưa nhận lại giọng: {error}")
    if log:
        log(f"Đã đổi tên thành {renamed}.")
    return renamed


def speech_output_path(voice: str) -> str:
    """File đọc thử nằm trong thư mục output, cạnh video."""
    import time
    import uuid

    from src.storage import output_dir
    from src.textutil import slugify

    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    slug = slugify(voice or "") or "giong"
    return os.path.join(output_dir(), f"{slug}-{stamp}.wav")


def generate_speech(text: str, voice: str, log=None) -> str:
    """Đọc một đoạn bằng giọng đã lưu hoặc giọng có sẵn, ghi file vào output."""
    from src.voices import is_saved

    spoken = (text or "").strip()
    if not spoken:
        raise RuntimeError("Hãy nhập hoặc dán câu cần đọc.")
    if len(spoken) > 2000:
        spoken = spoken[:2000].strip()
        if log:
            log("Đoạn đọc được cắt còn 2000 ký tự.")
    chosen_name = (voice or "").strip()
    if not chosen_name:
        raise RuntimeError("Hãy chọn một giọng.")
    if not is_saved(chosen_name) and chosen_name not in FALLBACK_VOICES:
        raise RuntimeError("Hãy chọn một giọng đã lưu hoặc một giọng có sẵn.")
    chosen = open_voice(chosen_name, None, log)
    dest = speech_output_path(chosen_name)
    synthesize_to_file(spoken, chosen, dest, log)
    if log:
        log(f"Đã lưu file đọc: {dest}")
    return dest


def delete_cloned_voice(name: str, log=None) -> str:
    from src.voices import forget_voice

    removed = forget_voice(name)
    _ENROLLED.discard(removed)
    if _ENGINE is not None:
        remover = getattr(_ENGINE, "remove_voice", None)
        if remover:
            try:
                remover(removed)
            except Exception:
                pass
    if log:
        log(f"Đã xóa giọng {removed}.")
    return removed


def _preset_names(engine) -> list[str]:
    try:
        return [_voice_id(item) for item in engine.list_preset_voices() or []]
    except Exception:
        return []


def speak_line(text: str, voice: str, ref_audio: str | None, log=None) -> str:
    """Đọc một câu để nghe giọng, không cần kịch bản."""
    from src.paths import jobs_dir

    spoken = (text or "").strip() or DEFAULT_LINE
    if len(spoken) > 500:
        spoken = spoken[:500].strip()
        if log:
            log("Câu nghe thử được cắt còn 500 ký tự.")
    chosen = open_voice(voice, ref_audio if ref_audio else None, log)
    dest = os.path.join(jobs_dir(), "_voice_preview", "preview.wav")
    synthesize_to_file(spoken, chosen, dest, log)
    if log:
        log("Nghe thử xong.")
    return dest


def _infer(engine, text: str, voice: str):
    try:
        return engine.infer(text, voice=voice)
    except RuntimeError as error:
        if "out of memory" not in str(error).lower():
            raise
        _empty_cache()
        return engine.infer(text, voice=voice)


def _to_mono(audio) -> np.ndarray:
    array = np.squeeze(np.asarray(audio, dtype=np.float32))
    array = np.ascontiguousarray(array.reshape(-1))
    peak = float(np.max(np.abs(array))) if array.size else 0.0
    if peak > 1:
        array = array / peak
    return array


def synthesize_to_file(text: str, voice: str, dest: str, log=None) -> str:
    pieces = split_for_tts(text)
    if not pieces:
        raise RuntimeError("Không có câu nào để đọc.")
    engine = get_engine(log)
    chosen = voice
    gap = np.zeros(int(SAMPLE_RATE * 0.1), dtype=np.float32)
    parts = []
    for index, piece in enumerate(pieces):
        parts.append(_to_mono(_infer(engine, piece, chosen)))
        if index != len(pieces) - 1:
            parts.append(gap)
    audio = np.concatenate(parts) if parts else np.zeros(SAMPLE_RATE // 5, dtype=np.float32)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    import soundfile as sf

    sf.write(dest, audio, SAMPLE_RATE, subtype="PCM_16")
    return dest
