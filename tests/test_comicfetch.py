"""Đọc HTML chương và tải ảnh. Không gọi mạng."""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from src.comicfetch import (
    blocked_message,
    chapter_urls,
    download_pages,
    extract_page,
    fetch_chapters,
    fetch_html,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PAGE = "https://www.zettruyen5.com/truyen-tranh/canh-sat-thien-tai-chuyen-sinh/chuong-1"


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


def _image(width: int, height: int, fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (20, 40, 60)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_real_zettruyen_chapter_is_109_pages_in_numeric_order():
    page = "https://www.zettruyen5.com/truyen-tranh/canh-sat-thien-tai-chuyen-sinh/chuong-1"
    found = extract_page(_read("zettruyen5-canh-sat-chuong-1.html"), page)
    assert len(found["urls"]) == 109
    assert found["urls"][0].endswith("/1/0.jpg")
    assert found["urls"][-1].endswith("/1/108.jpg")
    assert [url.rsplit("/", 1)[-1] for url in found["urls"]] == [f"{n}.jpg" for n in range(109)]
    blob = " ".join(found["urls"])
    assert "cdn1.zetimage.com" not in blob
    assert "/thumb/" not in blob
    assert "favicon" not in blob
    assert "icon.svg" not in blob


def test_zettruyen_fixture_keeps_reading_order_and_skips_ads():
    found = extract_page(_read("zettruyen_chapter.html"), PAGE)
    assert found["urls"] == [
        "https://img.example/chap1/p1.webp",
        "https://img.example/chap1/p2.jpg",
        "https://img.example/chap1/p3-1200.jpg",
    ]
    assert "Cảnh Sát Thiên Tài" in found["title"]
    assert found["chapter"] == "Chương 1"
    assert "logo" not in " ".join(found["urls"])
    assert "banner" not in " ".join(found["urls"])


def test_other_sites_and_generic_fallback():
    net = extract_page(_read("nettruyen_chapter.html"), "https://nettruyen.example/truyen/chap-2")
    assert net["urls"] == ["https://img.example/net/1.jpg", "https://img.example/net/2.jpg"]
    assert net["chapter"] == "Chương 2"
    qq = extract_page(_read("truyenqq_chapter.html"), "https://truyenqq.example/truyen/chuong-4")
    assert qq["urls"] == ["https://cdn.example/qq/a.jpg", "https://cdn.example/qq/b.webp"]
    blog = extract_page(_read("blogtruyen_chapter.html"), "https://blogtruyen.example/truyen/chuong-3")
    assert blog["urls"] == [
        "https://blogtruyen.example/comics/bt/01.png",
        "https://img.example/bt/02.jpg",
    ]
    generic = extract_page(_read("generic_chapter.html"), "https://reader.example/chuong-8")
    assert generic["urls"] == ["https://img.example/page-1.jpg", "https://img.example/page-2.jpg"]


def test_chapter_range_rewrites_only_the_chapter_number():
    urls = chapter_urls(PAGE, 3)
    assert urls == [
        PAGE.replace("chuong-1", "chuong-1"),
        PAGE.replace("chuong-1", "chuong-2"),
        PAGE.replace("chuong-1", "chuong-3"),
    ]
    assert chapter_urls(PAGE, 0) == [PAGE]
    with pytest.raises(RuntimeError, match="Đến chương"):
        chapter_urls(PAGE.replace("chuong-1", "chuong-5"), 2)
    with pytest.raises(RuntimeError, match="tối đa"):
        chapter_urls(PAGE, 40)
    with pytest.raises(RuntimeError, match="http"):
        chapter_urls("ftp://example/chuong-1", 0)


def test_image_request_sends_chrome_user_agent_and_referer(monkeypatch):
    captured = {}

    class _Response:
        status = 200

        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def urlopen(request, timeout=30):
        captured["ua"] = request.get_header("User-agent")
        captured["referer"] = request.get_header("Referer")
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    from src.comicfetch import _request

    referer = "https://www.zettruyen5.com/truyen-tranh/canh-sat-thien-tai-chuyen-sinh/chuong-1"
    status, payload = _request("https://cdn3.zetimage.com/canh-sat-thien-tai-chuyen-sinh/1/0.jpg", referer, 10)
    assert status == 200 and payload == b"ok"
    assert captured["ua"].startswith("Mozilla/5.0")
    assert "Chrome/" in captured["ua"]
    assert captured["referer"] == referer


def test_cloudflare_message_names_the_block():
    html = _read("cloudflare_block.html")
    text = blocked_message(403, html)
    assert "Cloudflare" in text
    assert "1005" in text
    assert "Tải file" in text
    assert blocked_message(200, "<html>ok</html>") == ""


def test_fetch_html_raises_vietnamese_error_without_printing_body(monkeypatch, capsys):
    body = _read("cloudflare_block.html").encode()

    def fail(url, referer, timeout):
        return 403, body

    monkeypatch.setattr("src.comicfetch._request", fail)
    monkeypatch.setattr("src.comicfetch._cloudscraper", lambda url, timeout: None)
    with pytest.raises(RuntimeError, match="Cloudflare") as caught:
        fetch_html(PAGE)
    assert "1005" in str(caught.value)
    assert capsys.readouterr().out == ""


def test_download_converts_webp_and_drops_tiny_images(tmp_path, monkeypatch):
    pages = {
        "https://img.example/a.webp": _image(800, 1200, "WEBP"),
        "https://img.example/ad.png": _image(120, 80, "PNG"),
        "https://img.example/b.avif": _image(720, 1600, "AVIF"),
    }

    def grab(url, referer, timeout):
        assert referer == PAGE
        return pages[url]

    monkeypatch.setattr("src.comicfetch._download_bytes", grab)
    saved = download_pages(list(pages), str(tmp_path), PAGE, log=lambda _message: None, progress=None)
    assert [os.path.basename(path) for path in saved] == ["page_0001.png", "page_0002.png"]
    for path in saved:
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size[0] >= 720


def test_fetch_chapters_saves_under_the_job_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    html = _read("zettruyen_chapter.html")
    monkeypatch.setattr("src.comicfetch.fetch_html", lambda url: html)
    blobs = {
        "https://img.example/chap1/p1.webp": _image(800, 1000, "WEBP"),
        "https://img.example/chap1/p2.jpg": _image(800, 1100, "JPEG"),
        "https://img.example/chap1/p3-1200.jpg": _image(900, 1300, "JPEG"),
    }
    monkeypatch.setattr("src.comicfetch._download_bytes", lambda url, referer, timeout: blobs[url])
    notes = []
    result = fetch_chapters(PAGE, 0, notes.append, progress=None)
    assert result["count"] == 3
    assert result["chapter"] == "Chương 1"
    assert os.path.isdir(result["dir"])
    assert result["dir"].endswith(os.path.join(result["job_id"], "source"))
    assert all(os.path.isfile(path) for path in result["pages"])
    assert "Đã lưu 3 trang" in notes[-1]


def test_source_step_has_url_fetch_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("RM_DRIVE_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("RM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setenv("RM_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    from src.ui import build_demo

    demo = build_demo()
    labels = []
    values = []

    def walk(block):
        labels.append(getattr(block, "label", None))
        values.append(getattr(block, "value", None))
        for child in getattr(block, "children", []) or []:
            walk(child)

    walk(demo)
    assert "Link chương truyện" in labels
    assert "Lấy truyện" in values
    assert "Đến chương (0 = chỉ link này)" in labels
