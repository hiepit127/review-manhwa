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
    return _ENGINE


def list_voices(log=None) -> list[str]:
    engine = get_engine(log)
    try:
        voices = engine.list_preset_voices()
    except Exception as error:
        if log:
            log(f"Không lấy được danh sách giọng ({error}). Dùng danh sách có sẵn.")
        return list(FALLBACK_VOICES)
    labels = []
    for item in voices or []:
        if isinstance(item, (list, tuple)) and item:
            labels.append(str(item[0]))
        else:
            labels.append(str(item))
    return labels or list(FALLBACK_VOICES)


def _resolve_voice(engine, name: str) -> str:
    labels = []
    try:
        for item in engine.list_preset_voices() or []:
            label = str(item[0] if isinstance(item, (list, tuple)) and item else item)
            labels.append(label)
            if label.casefold() == name.casefold():
                return label
    except Exception:
        labels = []
    if name in labels or not labels:
        return name
    raise RuntimeError("Không có giọng này. Các giọng đang có: " + ", ".join(labels))


def open_voice(voice: str, ref_audio: str | None, log=None) -> str:
    """Mở model một lần và trả về tên giọng sẽ dùng cho cả chương."""
    engine = get_engine(log)
    if ref_audio:
        name = "GiongReview"
        try:
            engine.add_voice(name, ref_audio)
        except Exception:
            engine.add_voice(name, ref_audio, denoise=False)
        if log:
            log("Đã lấy giọng từ file mẫu cho phiên này.")
        return name
    return _resolve_voice(engine, voice)


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
