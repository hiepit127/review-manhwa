"""Chuỗi, thời gian phụ đề, và nhật ký bước chạy."""

from __future__ import annotations

import json
import re
import time
import unicodedata


def natural_key(path: str):
    name = path.replace("\\", "/").split("/")[-1].lower()
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def slugify(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:50]


def apply_range(items: list, start_page, end_page) -> list:
    count = len(items)
    if count == 0:
        return []
    start = int(start_page or 1)
    end = int(end_page or 0)
    if start < 1:
        start = 1
    if end < 1 or end > count:
        end = count
    if start > count or start > end:
        return []
    return items[start - 1 : end]


def clean_spoken(text: str) -> str:
    text = (text or "").replace("\n", " ")
    text = re.sub(r"[*_#>`]", "", text)
    text = re.sub(r"^(cảnh|scene)\s*\d+\s*[:\-–]\s*", "", text, flags=re.I)
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.!?…])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def split_for_tts(text: str, limit: int = 420) -> list[str]:
    text = clean_spoken(text)
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buffer = ""
    for sentence in split_sentences(text):
        if buffer and len(buffer) + 1 + len(sentence) > limit:
            chunks.append(buffer)
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        chunks.append(buffer)
    flattened: list[str] = []
    for chunk in chunks:
        while len(chunk) > limit:
            flattened.append(chunk[:limit].strip())
            chunk = chunk[limit:].strip()
        if chunk:
            flattened.append(chunk)
    return flattened


def sample_even(items: list, limit: int) -> list:
    if limit <= 0 or not items:
        return []
    if len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[len(items) // 2]]
    last = len(items) - 1
    chosen = []
    seen = set()
    for index in range(limit):
        position = round(index * last / (limit - 1))
        if position not in seen:
            seen.add(position)
            chosen.append(items[position])
    return chosen


def format_srt_time(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def sentence_cues(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    parts = split_sentences(text)
    if not parts:
        return []
    span = max(end - start, 0.2)
    weights = [max(len(part), 1) for part in parts]
    total = float(sum(weights))
    cues = []
    cursor = start
    for part, weight in zip(parts, weights):
        duration = span * weight / total
        cues.append((cursor, cursor + duration, part))
        cursor += duration
    last_start, _, last_text = cues[-1]
    cues[-1] = (last_start, end, last_text)
    return cues


def write_srt(cues: list[tuple[float, float, str]], path: str) -> None:
    blocks = []
    for index, (start, end, text) in enumerate(cues, start=1):
        blocks.append(str(index))
        blocks.append(f"{format_srt_time(start)} --> {format_srt_time(max(end, start + 0.05))}")
        blocks.append(text.strip())
        blocks.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(blocks))


def parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model không trả về JSON object.")
    return data


def narrations_from_payload(data: dict, expected_ids: list[int]) -> list[str]:
    items = data.get("scenes") or data.get("canh") or data.get("segments") or []
    by_id: dict[int, str] = {}
    ordered: list[str] = []
    if isinstance(items, dict):
        items = [items]
    for item in items:
        if isinstance(item, str):
            ordered.append(clean_spoken(item))
            continue
        if not isinstance(item, dict):
            continue
        text = ""
        for key in ("narration", "loi", "text", "script", "content"):
            if item.get(key):
                text = clean_spoken(str(item[key]))
                break
        scene_id = item.get("id")
        try:
            by_id[int(scene_id)] = text
        except (TypeError, ValueError):
            ordered.append(text)
    result = []
    cursor = 0
    for scene_id in expected_ids:
        if by_id.get(scene_id):
            result.append(by_id[scene_id])
        elif cursor < len(ordered):
            result.append(ordered[cursor])
            cursor += 1
        else:
            result.append("")
    return result


def public_error(error: Exception, secret: str = "") -> str:
    message = f"{type(error).__name__}: {error}"
    if secret:
        message = message.replace(secret, "***")
    from src.keys import redact

    return redact(message)


def file_path(item) -> str | None:
    if item is None:
        return None
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("path") or item.get("name")
    for attr in ("path", "name"):
        value = getattr(item, attr, None)
        if isinstance(value, str):
            return value
    return str(item)


def as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


class StepLog:
    def __init__(self):
        self.lines: list[str] = []
        self.started = time.perf_counter()

    def __call__(self, message: str) -> None:
        from src.keys import redact

        line = f"[{time.perf_counter() - self.started:6.1f}s] {redact(str(message))}"
        print(line, flush=True)
        self.lines.append(line)

    def text(self) -> str:
        return "\n".join(self.lines)
