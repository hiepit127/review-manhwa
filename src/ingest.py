"""Nhận PDF, ảnh, hoặc ZIP và xếp thành danh sách trang PNG theo đúng thứ tự."""

from __future__ import annotations

import os
import zipfile

from src.images import save_png_from_file
from src.textutil import apply_range, natural_key

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _within(parent: str, target: str) -> bool:
    parent = os.path.abspath(parent)
    target = os.path.abspath(target)
    try:
        return os.path.commonpath([parent, target]) == parent
    except ValueError:
        return False


def _unzip(zip_path: str, dest: str, log) -> list[str]:
    os.makedirs(dest, exist_ok=True)
    found = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or "__MACOSX" in name.split("/") or os.path.basename(name).startswith("."):
                continue
            target = os.path.abspath(os.path.join(dest, name))
            if not _within(dest, target):
                log(f"Bỏ qua file nén không an toàn: {name}")
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXT and ext != ".pdf":
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as handle:
                handle.write(source.read())
            found.append(target)
    log(f"Giải nén {os.path.basename(zip_path)}: {len(found)} file")
    return found


def _expand(paths: list[str], unpack_dir: str, log) -> list[str]:
    found = []
    for path in paths:
        if not path or not os.path.isfile(path):
            continue
        if path.lower().endswith(".zip"):
            found.extend(_unzip(path, unpack_dir, log))
        else:
            found.append(path)
    return found


def _pymupdf():
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    return pymupdf


def _render_pdf(pdf_path: str, pages_dir: str, start_page, end_page, counter: int, log) -> tuple[list[str], int]:
    fitz = _pymupdf()
    document = fitz.open(pdf_path)
    total = document.page_count
    start = 1 if not start_page or int(start_page) < 1 else int(start_page)
    end = total if not end_page or int(end_page) < 1 else min(int(end_page), total)
    saved = []
    if start <= end:
        for number in range(start, end + 1):
            page = document.load_page(number - 1)
            zoom = min(2.2, max(1.0, 1400 / float(page.rect.width)))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            out = os.path.join(pages_dir, f"page_{counter:04d}.png")
            pixmap.save(out)
            saved.append(out)
            counter += 1
    document.close()
    log(f"PDF {os.path.basename(pdf_path)}: lấy trang {start}-{end} / {total}")
    return saved, counter


def collect_pages(inputs: list[str], job_dir: str, start_page, end_page, log) -> list[str]:
    unpack_dir = os.path.join(job_dir, "unpack")
    pages_dir = os.path.join(job_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    raw = _expand(inputs, unpack_dir, log)
    pdfs = []
    images = []
    for path in raw:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            pdfs.append(path)
        elif ext in IMAGE_EXT:
            images.append(path)
        else:
            log(f"Bỏ qua {os.path.basename(path)}")

    pages: list[str] = []
    counter = 1
    single_pdf = len(pdfs) == 1 and not images
    if single_pdf:
        rendered, _ = _render_pdf(pdfs[0], pages_dir, start_page, end_page, counter, log)
        return rendered

    for pdf_path in pdfs:
        rendered, counter = _render_pdf(pdf_path, pages_dir, None, None, counter, log)
        pages.extend(rendered)
    for image_path in sorted(images, key=natural_key):
        out = os.path.join(pages_dir, f"page_{counter:04d}.png")
        save_png_from_file(image_path, out)
        pages.append(out)
        counter += 1

    before = len(pages)
    pages = apply_range(pages, start_page, end_page)
    if before != len(pages):
        end_label = end_page or "hết"
        log(f"Chọn trang {int(start_page or 1)}-{end_label}: còn {len(pages)}/{before}")
    return pages
