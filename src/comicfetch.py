"""Lấy ảnh một chương truyện từ link, rồi đưa vào pipeline như file tải lên.

Site cụ thể (zettruyen, nettruyen, truyenqq, blogtruyen) đọc ảnh trong khung
chương. Trang khác dùng cách lấy ảnh lớn. HTML kiểm bằng fixture, không cần mạng.
"""

from __future__ import annotations

import io
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from src.jobs import new_job_id
from src.paths import job_dir

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_LAZY = ("data-original", "data-src", "data-lazy-src", "data-lazy", "data-url", "data-image")
_CHAPTER_MARKERS = (
    "reading-detail",
    "page-chapter",
    "chapter_content",
    "chapter-content",
    "chapter-c",
    "box_doc",
    "reading-content",
    "comicpage",
    "content",
    "chapter-images-container",
    "chapter-img",
)
_SKIP = (
    "logo",
    "banner",
    "ads",
    "advert",
    "icon",
    "avatar",
    "loading",
    "spacer",
    "pixel",
    "blank.gif",
    "favicon",
    "emoji",
)
_CHAPTER_IN_URL = re.compile(r"(chuong|chapter|chap)-(\d+)", re.IGNORECASE)
_IMG_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp|avif)(?:\?[^\s\"'<>]*)?", re.IGNORECASE)
_MAX_CHAPTERS = 15
_WORKERS = 6


_VOID = {"img", "meta", "br", "hr", "input", "link", "source", "base"}


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images: list[dict] = []
        self._class: list[str] = []
        self._id: list[str] = []
        self.title = ""
        self.h1 = ""
        self.og_title = ""
        self._capture = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or "") for key, value in attrs}
        if tag == "img":
            self.images.append(
                {
                    "attrs": attr,
                    "context": " ".join(self._class + self._id).lower(),
                }
            )
        if tag == "meta" and attr.get("property", "").lower() == "og:title":
            self.og_title = attr.get("content", "").strip()
        if tag in ("title", "h1") and not self._capture:
            self._capture = tag
            self._buf = []
        if tag not in _VOID:
            self._class.append(attr.get("class", ""))
            self._id.append(attr.get("id", ""))

    def handle_endtag(self, tag):
        if tag not in _VOID and self._class:
            self._class.pop()
            self._id.pop()
        if self._capture == tag:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title" and not self.title:
                self.title = text
            elif tag == "h1" and not self.h1:
                self.h1 = text
            self._capture = ""

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)


def _usable(url: str) -> bool:
    text = (url or "").strip()
    if not text or text.startswith("data:"):
        return False
    low = text.lower()
    return not any(word in low for word in _SKIP)


def _srcset(value: str) -> str:
    best = ""
    best_width = -1
    for part in (value or "").split(","):
        bits = part.strip().split()
        if not bits or not _usable(bits[0]):
            continue
        width = 0
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                width = int(bits[1][:-1])
            except ValueError:
                width = 0
        if width >= best_width:
            best = bits[0]
            best_width = width
    return best


def _img_url(attrs: dict) -> str:
    for key in _LAZY:
        value = (attrs.get(key) or "").strip()
        if _usable(value):
            return value
    packed = _srcset(attrs.get("srcset") or attrs.get("data-srcset") or "")
    if packed:
        return packed
    src = (attrs.get("src") or "").strip()
    return src if _usable(src) else ""


def _size_attr(attrs: dict, name: str) -> int:
    raw = (attrs.get(name) or "").strip().rstrip("px")
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _too_small(attrs: dict) -> bool:
    width = _size_attr(attrs, "width")
    height = _size_attr(attrs, "height")
    if width and height and height < 140:
        return True
    if width and height and width < 400 and height < 500:
        return True
    if width and not height and width < 200:
        return True
    return False


def _in_chapter(context: str) -> bool:
    return any(marker in context for marker in _CHAPTER_MARKERS)


def _absolute(page_url: str, src: str) -> str:
    return urljoin(page_url, src.strip())


def _dedupe(urls: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _chapter_image(url: str) -> bool:
    """Bỏ thumbnail CDN, icon và ảnh lặp trong onerror."""
    low = url.lower().split("?", 1)[0].split("#", 1)[0]
    if "/thumb/" in low or "cdn1.zetimage.com" in low:
        return False
    if low.endswith((".ico", ".svg")):
        return False
    if any(part in low for part in ("/favicon", "/sprite", "/icons/", "/icon.", "logo.")):
        return False
    return True


def _page_number(url: str) -> int | None:
    """Số trang trên CDN zetimage. 10.jpg đứng sau 2.jpg, không phải sau 1.jpg."""
    if "zetimage.com" not in url.lower() or "/thumb/" in url.lower():
        return None
    match = re.search(r"/(\d+)\.(?:jpe?g|png|webp|avif)$", url.lower().split("?", 1)[0])
    return int(match.group(1)) if match else None


def _reading_order(urls: list[str]) -> list[str]:
    numbers = [_page_number(url) for url in urls]
    if not urls or any(number is None for number in numbers):
        return urls
    return [url for _, url in sorted(zip(numbers, urls), key=lambda item: item[0])]


def extract_page(html: str, page_url: str) -> dict:
    """Đọc HTML chương. Trả về url ảnh theo thứ tự đọc, tên truyện và chương."""
    parser = _PageParser()
    parser.feed(html or "")
    parser.close()
    chapter_urls = []
    other_urls = []
    for image in parser.images:
        src = _img_url(image["attrs"])
        if not src or _too_small(image["attrs"]):
            continue
        absolute = _absolute(page_url, src)
        if _in_chapter(image["context"]):
            chapter_urls.append(absolute)
        else:
            other_urls.append(absolute)
    urls = _dedupe(chapter_urls or other_urls)
    if not urls:
        urls = _dedupe(_absolute(page_url, item) for item in _IMG_IN_TEXT.findall(html or "") if _usable(item))
    urls = _reading_order([url for url in urls if _chapter_image(url)])
    title = parser.og_title or parser.h1 or parser.title
    title = re.sub(r"\s*[-|–]\s*(Đọc|ZetTruyen|NetTruyen|TruyenQQ|BlogTruyen).*$", "", title, flags=re.IGNORECASE).strip()
    chapter = ""
    match = _CHAPTER_IN_URL.search(page_url or "")
    if match:
        chapter = f"Chương {int(match.group(2))}"
    return {"urls": urls, "title": title, "chapter": chapter}


def chapter_urls(url: str, end_chapter) -> list[str]:
    """Một link, hoặc chương trong link tới ``end_chapter`` nếu URL có dạng chuong-N."""
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("Link phải bắt đầu bằng http hoặc https.")
    try:
        end = int(end_chapter or 0)
    except (TypeError, ValueError):
        end = 0
    match = _CHAPTER_IN_URL.search(text)
    if end <= 0 or match is None:
        return [text]
    start = int(match.group(2))
    if end < start:
        raise RuntimeError("Đến chương phải lớn hơn hoặc bằng chương trong link.")
    if end - start + 1 > _MAX_CHAPTERS:
        raise RuntimeError(f"Chỉ lấy tối đa {_MAX_CHAPTERS} chương một lần.")
    urls = []
    for number in range(start, end + 1):
        urls.append(text[: match.start(2)] + str(number) + text[match.end(2) :])
    return urls


def blocked_message(status: int, body: str) -> str:
    code = ""
    match = re.search(r"(?:error code:\s*|Error\s+)(\d{4})", body or "", re.IGNORECASE)
    if not match:
        match = re.search(r"\b(1005|1006|1015|1020)\b", body or "")
    if match:
        code = match.group(1)
    detail = f" (mã {code})" if code else ""
    if status in (401, 403, 429, 503) and (
        "cloudflare" in (body or "").lower() or "just a moment" in (body or "").lower() or code
    ):
        return (
            f"Không lấy được truyện: trang chặn bằng Cloudflare{detail}. "
            "Máy Colab thường bị chặn theo nhà mạng, và trang vẽ bằng JavaScript thì không đọc được ảnh. "
            "Hãy mở chương trên máy, lưu ảnh hoặc ZIP, rồi dùng ô Tải file."
        )
    return ""


def _request(url: str, referer: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": referer or url,
            "Accept": "text/html,image/avif,image/webp,image/*,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        payload = error.read() if error.fp else b""
        return error.code, payload


def _cloudscraper(url: str, timeout: float) -> tuple[int, bytes] | None:
    try:
        import cloudscraper
    except Exception:
        return None
    try:
        scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        response = scraper.get(url, timeout=timeout)
    except Exception:
        return None
    return response.status_code, response.content or b""


def fetch_html(url: str, *, timeout: float = 30) -> str:
    status, payload = _request(url, url, timeout)
    text = payload.decode("utf-8", "replace")
    message = blocked_message(status, text)
    if message:
        alt = _cloudscraper(url, timeout)
        if alt:
            alt_text = alt[1].decode("utf-8", "replace")
            if not blocked_message(alt[0], alt_text) and alt[0] < 400:
                return alt_text
        raise RuntimeError(message)
    if status >= 400:
        raise RuntimeError(f"Không tải được trang (mã {status}).")
    if not text.strip():
        raise RuntimeError("Trang trả về rỗng.")
    return text


def _png_bytes(data: bytes) -> bytes | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if height < 140 or (width < 400 and height < 500):
                return None
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception as error:
        raise RuntimeError("Không đọc được ảnh (webp/avif hoặc file hỏng).") from error


def _download_bytes(url: str, referer: str, timeout: float) -> bytes:
    last = "Không tải được ảnh."
    for attempt in range(3):
        try:
            status, payload = _request(url, referer, timeout)
        except Exception as error:
            last = error.__class__.__name__
            payload = b""
            status = 0
        if status == 200 and payload:
            return payload
        if status in (403, 401):
            last = f"mã {status}"
        time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"Không tải được ảnh ({last}).")


def _download_ordered(urls: list[str], referer: str, timeout: float, log, progress) -> list[bytes | None]:
    total = max(len(urls), 1)
    results: list[bytes | None] = [None] * len(urls)
    done = 0

    def one(index: int, url: str):
        try:
            return index, _download_bytes(url, referer, timeout)
        except Exception as error:
            log(f"Bỏ qua ảnh {index + 1}: {error}")
            return index, None

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = [pool.submit(one, index, url) for index, url in enumerate(urls)]
        for future in as_completed(futures):
            index, payload = future.result()
            results[index] = payload
            done += 1
            if progress:
                progress(done / total, desc=f"Tải trang {done}/{len(urls)}")
    return results


def download_pages(urls: list[str], folder: str, referer: str, log, progress=None, timeout: float = 30) -> list[str]:
    """Tải song song, lọc quảng cáo, ghi PNG theo thứ tự đọc."""
    os.makedirs(folder, exist_ok=True)
    if len(urls) > 400:
        raise RuntimeError("Quá nhiều ảnh trên trang. Có thể đã lấy nhầm cả website, không phải một chương.")
    payloads = _download_ordered(urls, referer, timeout, log, progress)
    saved = []
    for payload in payloads:
        if not payload:
            continue
        try:
            png = _png_bytes(payload)
        except RuntimeError as error:
            log(str(error))
            continue
        if not png:
            continue
        path = os.path.join(folder, f"page_{len(saved) + 1:04d}.png")
        with open(path, "wb") as handle:
            handle.write(png)
        saved.append(path)
    return saved


def fetch_chapters(url: str, end_chapter, log, progress=None) -> dict:
    """Tải chương vào ``cache/jobs/<job>/source``. Trả về đường dẫn PNG và tên truyện."""
    pages = chapter_urls(url, end_chapter)
    job_id = new_job_id()
    folder = os.path.join(job_dir(job_id), "source")
    saved: list[str] = []
    title = ""
    chapter = ""
    for index, page in enumerate(pages):
        log(f"Đọc trang chương {index + 1}/{len(pages)}")
        html = fetch_html(page)
        extracted = extract_page(html, page)
        if not extracted["urls"]:
            raise RuntimeError(
                "Không thấy ảnh chương trong trang. Site có thể vẽ bằng JavaScript. "
                "Hãy lưu ảnh hoặc ZIP rồi dùng ô Tải file."
            )
        title = title or extracted["title"]
        chapter = extracted["chapter"] or chapter
        log(f"Thấy {len(extracted['urls'])} ảnh.")

        def chapter_progress(fraction, desc=None):
            if not progress:
                return
            overall = (index + float(fraction)) / len(pages)
            progress(overall, desc=desc)

        saved.extend(download_pages(extracted["urls"], folder, page, log, chapter_progress))
    if not saved:
        raise RuntimeError("Không còn ảnh trang sau khi bỏ logo và quảng cáo.")
    if len(pages) > 1:
        match_start = _CHAPTER_IN_URL.search(pages[0])
        match_end = _CHAPTER_IN_URL.search(pages[-1])
        if match_start and match_end:
            chapter = f"Chương {int(match_start.group(2))}-{int(match_end.group(2))}"
    log(f"Đã lưu {len(saved)} trang vào {folder}")
    return {"job_id": job_id, "dir": folder, "pages": saved, "title": title, "chapter": chapter, "count": len(saved)}
