"""Viết lời review tiếng Việt từ hội thoại OCR hoặc từ ảnh panel."""

from __future__ import annotations

import base64
import io
import os
import time

from src.keys import missing_message
from src.paths import ROOT
from src.textutil import clean_spoken, narrations_from_payload, parse_json_object

_CONFIG = None


def load_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        import yaml

        path = os.path.join(ROOT, "configs", "review_vi.yaml")
        with open(path, encoding="utf-8") as handle:
            _CONFIG = yaml.safe_load(handle)
    return _CONFIG


def _system_prompt(config: dict) -> str:
    rules = "\n".join(f"- {rule}" for rule in config.get("rules", []))
    return config["system"].strip() + "\n" + rules


def _jpeg(path: str, max_width: int = 720) -> bytes:
    from PIL import Image

    with Image.open(path) as handle:
        image = handle.convert("RGB")
        if image.width > max_width:
            height = max(1, int(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)
        if image.height > 1280:
            width = max(1, int(image.width * 1280 / image.height))
            image = image.resize((width, 1280), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=80)
        return buffer.getvalue()


def _scene_block(scene: dict) -> str:
    ocr = (scene.get("ocr") or "").strip()
    if len(ocr) > 1500:
        ocr = ocr[:1500] + "…"
    if not ocr:
        ocr = "(không đọc được chữ)"
    return f"Cảnh {scene['id']}\nHội thoại đọc được:\n{ocr}"


def _user_prompt(scenes: list[dict], meta: dict, tail: str) -> str:
    lines = [
        f"Truyện: {meta.get('title') or 'không rõ'}",
        f"Phần: {meta.get('chapter') or 'không rõ'}",
        "Bối cảnh và nhân vật:",
        meta.get("lore") or "(không có)",
        "",
        "Phong cách:",
        meta.get("style_text") or "",
    ]
    if meta.get("notes"):
        lines.extend(["", "Ghi chú của người review:", meta["notes"]])
    if tail:
        lines.extend(["", f"Đoạn liền trước, nối mạch và đừng lặp lại: {tail}"])
    lines.extend(
        [
            "",
            "Viết lời cho từng cảnh. Trả về JSON đúng dạng "
            '{"scenes":[{"id":1,"narration":"..."}]} '
            "và đủ mọi id bên dưới.",
            "",
        ]
    )
    lines.extend(_scene_block(scene) + "\n" for scene in scenes)
    return "\n".join(lines)


XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = "grok-4.7"


def _openai_compatible(api_key: str, base_url: str, model: str, system: str, prompt: str, scenes: list[dict], use_vision: bool, temperature: float) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=300)
    if use_vision:
        content = [{"type": "text", "text": prompt}]
        for scene in scenes:
            content.append({"type": "text", "text": f"Ảnh của cảnh {scene['id']}:"})
            for image in (scene.get("abs_images") or [])[:3]:
                encoded = base64.b64encode(_jpeg(image)).decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
    else:
        content = prompt
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]
    variants = [
        {"temperature": temperature, "response_format": {"type": "json_object"}},
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last = None
    for extra in variants:
        try:
            response = client.chat.completions.create(model=model, messages=messages, **extra)
        except Exception as error:
            last = error
            continue
        text = response.choices[0].message.content or ""
        if text.strip():
            return text
        last = RuntimeError("API không trả về nội dung.")
    raise last


def _call(**kwargs) -> str:
    last = None
    for attempt in range(3):
        try:
            return _openai_compatible(**kwargs)
        except Exception as error:
            last = error
            if attempt == 2:
                break
            time.sleep(1.5 * (attempt + 1))
    raise last


def generate_narrations(
    scenes: list[dict],
    *,
    title: str,
    chapter: str,
    lore: str,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
    use_vision: bool,
    temperature: float,
    style_key: str,
    notes: str,
    log,
    progress,
) -> list[str]:
    if not (api_key or "").strip():
        raise RuntimeError(missing_message(provider))
    if not model.strip():
        raise RuntimeError("Điền tên model.")
    del provider, base_url
    base_url = XAI_BASE_URL

    config = load_config()
    style_text = (config.get("styles") or {}).get(style_key) or (config.get("styles") or {}).get("review", "")
    system = _system_prompt(config)
    narrations = [""] * len(scenes)
    chunk_size = 3 if use_vision else 6
    tail = ""
    total = max(len(scenes), 1)
    for start in range(0, len(scenes), chunk_size):
        chunk = scenes[start : start + chunk_size]
        progress(start / total, desc=f"Viết cảnh {chunk[0]['id']}-{chunk[-1]['id']}")
        prompt = _user_prompt(
            chunk,
            {
                "title": title,
                "chapter": chapter,
                "lore": lore,
                "style_text": style_text,
                "notes": notes,
            },
            tail,
        )
        log(f"Gọi xAI cho cảnh {chunk[0]['id']}-{chunk[-1]['id']}")
        raw = _call(
            api_key=api_key.strip(),
            base_url=(base_url or "").strip(),
            model=model.strip(),
            system=system,
            prompt=prompt,
            scenes=chunk,
            use_vision=use_vision,
            temperature=float(temperature),
        )
        parsed = narrations_from_payload(parse_json_object(raw), [scene["id"] for scene in chunk])
        for offset, text in enumerate(parsed):
            narrations[start + offset] = clean_spoken(text)
        spoken = [text for text in parsed if text]
        if spoken:
            tail = spoken[-1][-240:]
        missing = [scene["id"] for scene, text in zip(chunk, parsed) if not text]
        if missing:
            log(f"Chưa có lời cho cảnh {missing}. Có thể viết tay ở cột Lời review.")
    progress(1, desc="Xong kịch bản")
    return narrations
