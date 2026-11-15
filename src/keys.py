"""API key cho bước viết kịch bản.

Thứ tự: Colab Secrets (``google.colab.userdata.get``) → biến môi trường → file
``.env``. Giá trị được đưa vào ``os.environ`` để app dùng, và không được in,
ghi log, hay đưa lên giao diện. Giao diện chỉ biết nguồn: colab, env, dotenv
hoặc missing.
"""

from __future__ import annotations

import os

from src.paths import ROOT

PROVIDERS = {
    "xAI": "XAI_API_KEY",
    "OpenAI-compatible": "OPENAI_API_KEY",
}

_SOURCE_LABELS = {
    "colab": "Colab",
    "env": "biến môi trường",
    "dotenv": "file .env",
    "missing": "chưa có",
}


def _source_var(secret: str) -> str:
    return f"RM_API_KEY_FROM_{secret}"


def _dotenv_file() -> str:
    return os.path.join(ROOT, ".env")


def _from_colab(name: str) -> str:
    """Đọc một secret. Lỗi hoặc không có thì chuỗi rỗng, không in giá trị."""
    try:
        from google.colab import userdata
    except Exception:
        return ""
    getter = getattr(userdata, "get", None)
    if not callable(getter):
        return ""
    try:
        value = getter(name)
    except Exception:
        return ""
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_dotenv(path: str) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return found
    allowed = set(PROVIDERS.values())
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if key not in allowed:
            continue
        found[key] = value.strip().strip('"').strip("'")
    return found


def _remember(secret: str, value: str, source: str) -> str:
    if value:
        os.environ[secret] = value
    else:
        os.environ.pop(secret, None)
    os.environ[_source_var(secret)] = source
    return source


def _resolve(secret: str) -> str:
    """Nạp một key vào môi trường. Trả về nguồn, không trả về giá trị."""
    colab = _from_colab(secret)
    if colab:
        return _remember(secret, colab, "colab")
    env = (os.environ.get(secret) or "").strip()
    if env:
        previous = os.environ.get(_source_var(secret), "")
        source = previous if previous in ("env", "dotenv") else "env"
        return _remember(secret, env, source)
    file_value = (_parse_dotenv(_dotenv_file()).get(secret) or "").strip()
    if file_value:
        return _remember(secret, file_value, "dotenv")
    return _remember(secret, "", "missing")


def load_api_keys() -> dict[str, str]:
    """Nạp mọi key đang hỗ trợ. Kết quả là tên secret → nguồn."""
    return {secret: _resolve(secret) for secret in PROVIDERS.values()}


def source_of(provider: str) -> str:
    secret = PROVIDERS.get(provider)
    if not secret:
        return "missing"
    return _resolve(secret)


def api_key_for(provider: str) -> str:
    """Giá trị dùng để gọi API. Người gọi không được in hoặc ghi log chuỗi này."""
    secret = PROVIDERS.get(provider)
    if not secret:
        return ""
    if _resolve(secret) == "missing":
        return ""
    return (os.environ.get(secret) or "").strip()


def has_api_key(provider: str) -> bool:
    return source_of(provider) != "missing"


def missing_message(provider: str) -> str:
    secret = PROVIDERS.get(provider) or "XAI_API_KEY"
    return (
        f"Chưa có API key. Bấm biểu tượng khóa ở thanh bên trái, thêm secret {secret}, "
        "bật Notebook access, rồi khởi động lại runtime. "
        f"Máy local thì đặt biến {secret} hoặc ghi vào file .env."
    )


def found_message(source: str) -> str:
    if source == "colab":
        return "Đã có API key từ Colab Secrets."
    if source == "dotenv":
        return "Đã có API key từ file .env."
    return "Đã có API key từ biến môi trường."


def status_message(provider: str) -> tuple[str, str]:
    source = source_of(provider)
    if source == "missing":
        return missing_message(provider), "miss"
    return found_message(source), "ok"


def status_html(provider: str) -> str:
    import html

    text, kind = status_message(provider)
    return f'<div class="key-status {html.escape(kind)}">{html.escape(text)}</div>'


def summary_line() -> str:
    """Một dòng trạng thái cho notebook và --doctor. Không có giá trị key."""
    sources = load_api_keys()
    parts = [f"{name} ({_SOURCE_LABELS.get(source, 'chưa có')})" for name, source in sources.items()]
    return "API key: " + ", ".join(parts)


def redact(text: str) -> str:
    """Xóa giá trị key khỏi một chuỗi trước khi in hoặc hiện lên giao diện."""
    if not text:
        return text
    cleaned = text
    for secret in PROVIDERS.values():
        value = os.environ.get(secret) or ""
        if len(value) >= 8 and value in cleaned:
            cleaned = cleaned.replace(value, "***")
    return cleaned
