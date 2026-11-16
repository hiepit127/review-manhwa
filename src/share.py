"""Link công khai khi chạy trên Colab.

Gradio ``share=True`` mở đường hầm frpc tới ``*.gradio.live``. Trên Colab đường
đó hay đứt: API ``api.gradio.app`` không trả relay, hoặc frpc không bắt tay được.
Khi đó Gradio chỉ còn nhãn ``https://localhost:...`` trong khung notebook. Máy
khác không mở được localhost của runtime.

Thứ tự: thử lại link Gradio vài lần, rồi Cloudflare quick tunnel (cùng kiểu
``cloudflared tunnel --url`` của tool audio), rồi URL proxy của Colab
(``google.colab.kernel.proxyPort``). In đúng một link.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

_CLOUDFLARE_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
_BINARY = Path("/tmp/review-manhwa-cloudflared")
_LOG = Path("/tmp/review-manhwa-cloudflared.log")
_PROCESS = None


def cloudflared_url_from_log(text: str) -> str:
    match = _CLOUDFLARE_RE.search(text or "")
    return match.group(0) if match else ""


def _in_colab() -> bool:
    return "COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ


def ensure_cloudflared() -> str:
    """Đường dẫn binary. Không tải trên máy local nếu chưa có sẵn."""
    found = shutil.which("cloudflared")
    if found:
        return found
    if _BINARY.is_file() and os.access(_BINARY, os.X_OK):
        return str(_BINARY)
    if not _in_colab():
        return ""
    try:
        import urllib.request

        with urllib.request.urlopen(_CLOUDFLARED_URL, timeout=60) as response:
            payload = response.read()
        _BINARY.write_bytes(payload)
        _BINARY.chmod(0o755)
    except Exception:
        return ""
    if _BINARY.is_file() and os.access(_BINARY, os.X_OK):
        return str(_BINARY)
    return ""


def cloudflared_url(port: int, *, binary: str | None = None, timeout: float = 25) -> str:
    """Quick tunnel. Chuỗi rỗng nếu không lấy được URL. Không in log."""
    global _PROCESS
    exe = binary or ensure_cloudflared()
    if not exe:
        return ""
    if _PROCESS is not None and _PROCESS.poll() is None:
        _PROCESS.terminate()
        try:
            _PROCESS.wait(timeout=3)
        except Exception:
            _PROCESS.kill()
    log = open(_LOG, "w", encoding="utf-8")
    try:
        _PROCESS = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{int(port)}"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    except OSError:
        log.close()
        return ""
    log.close()
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = cloudflared_url_from_log(_read_log())
        if found:
            return found
        if _PROCESS.poll() is not None:
            return cloudflared_url_from_log(_read_log())
        time.sleep(0.4)
    return cloudflared_url_from_log(_read_log())


def _read_log() -> str:
    try:
        return _LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def gradio_share_url(port: int) -> str:
    """Một lần hỏi relay Gradio. Lỗi thì ném ra, để vòng lặp thử lại."""
    import secrets

    from gradio.networking import setup_tunnel

    url = (setup_tunnel(
        local_host="127.0.0.1",
        local_port=int(port),
        share_token=secrets.token_urlsafe(32),
        share_server_address=None,
        share_server_tls_certificate=None,
    ) or "").strip()
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    if not url.startswith("https://"):
        return ""
    return url


def colab_proxy_url(port: int) -> str:
    """URL mà Colab cấp cho cổng kernel. Rỗng khi không chạy trong notebook."""
    try:
        from google.colab.output import eval_js
    except Exception:
        return ""
    try:
        value = eval_js(f"google.colab.kernel.proxyPort({int(port)})")
    except Exception:
        return ""
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    return ""


def choose_public_url(
    port: int,
    *,
    attempts: int = 3,
    pause: float = 2.0,
    sleeper=time.sleep,
    gradio_share=None,
    cloudflared=None,
    colab_proxy=None,
) -> dict:
    """Trả về ``{"url", "via"}``. ``via`` là gradio, cloudflared, colab hoặc none."""
    gradio_share = gradio_share or gradio_share_url
    cloudflared = cloudflared or cloudflared_url
    colab_proxy = colab_proxy or colab_proxy_url
    for attempt in range(max(attempts, 1)):
        try:
            url = gradio_share(port) or ""
        except Exception:
            url = ""
        if isinstance(url, str) and url.startswith("http"):
            return {"url": url, "via": "gradio"}
        if attempt + 1 < attempts:
            sleeper(pause)
    try:
        url = cloudflared(port) or ""
    except Exception:
        url = ""
    if isinstance(url, str) and url.startswith("http"):
        return {"url": url, "via": "cloudflared"}
    try:
        url = colab_proxy(port) or ""
    except Exception:
        url = ""
    if isinstance(url, str) and url.startswith("http"):
        return {"url": url, "via": "colab"}
    return {"url": "", "via": "none"}


def link_line(result: dict) -> str:
    """Một dòng, một URL. Không kèm giá trị API key."""
    url = (result or {}).get("url") or ""
    via = (result or {}).get("via") or "none"
    if via == "gradio" and url.startswith("http"):
        return f"Mở giao diện: {url}"
    if via in ("cloudflared", "colab") and url.startswith("http"):
        return f"Link Gradio không tạo được. Mở giao diện: {url}"
    return "Không tạo được link công khai. Dùng khung giao diện trong notebook."
