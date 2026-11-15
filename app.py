"""Chạy giao diện web, hoặc kiểm tra môi trường Colab bằng --doctor."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys

from src.paths import ROOT


def _in_colab() -> bool:
    return "COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ


def _in_notebook() -> bool:
    try:
        from IPython import get_ipython

        return get_ipython() is not None
    except Exception:
        return False


def doctor() -> str:
    lines = []
    exe = shutil.which("ffmpeg")
    lines.append("ffmpeg: " + (exe or "chưa có trong PATH, sẽ dùng imageio-ffmpeg khi xuất video"))
    try:
        import torch

        cuda = torch.cuda.is_available()
        name = torch.cuda.get_device_name(0) if cuda else ""
        lines.append(f"torch {torch.__version__} | CUDA {cuda} {name}".rstrip())
    except Exception as error:
        lines.append(f"torch: chưa dùng được ({error.__class__.__name__})")
    for module in ("gradio", "cv2", "pymupdf", "easyocr", "vieneu", "openai", "soundfile"):
        try:
            importlib.import_module(module)
            lines.append(f"{module}: ok")
        except Exception as error:
            lines.append(f"{module}: thiếu ({error.__class__.__name__})")
    try:
        from src.storage import summary_lines

        lines.extend(summary_lines().splitlines())
    except Exception as error:
        lines.append(f"storage: lỗi ({error.__class__.__name__})")
    return "\n".join(lines)


def _port_free(port: int) -> bool:
    import socket

    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(port: int | None) -> int | None:
    """Giữ cổng yêu cầu khi còn trống. Cổng bận thì để Gradio tìm cổng kế tiếp."""
    if port is None or _port_free(port):
        return port
    print(f"Cổng {port} đang bận. Mở cổng trống kế tiếp.")
    return None


def launch(share=None, port: int | None = 7860):
    from src.storage import allowed_paths, prepare_runtime, summary_lines

    prepare_runtime()
    print(summary_lines())
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.chdir(ROOT)
    if share is None:
        share = _in_colab()
    from src.ports import close_ports
    from src.ui import CSS, HEAD, I18N, THEME, build_demo

    close_ports(port or 7860)
    demo = build_demo()
    kwargs = {
        "server_name": "0.0.0.0",
        "server_port": choose_port(port),
        "share": share,
        "allowed_paths": allowed_paths(),
        "show_error": True,
        "max_file_size": "1024mb",
        "css": CSS,
        "theme": THEME,
        "i18n": I18N,
        "head": HEAD,
        "footer_links": [],
    }
    if _in_notebook():
        kwargs["inline"] = True
    demo.queue(default_concurrency_limit=1).launch(**kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Review Manhwa")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--share", action="store_true")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args(argv)
    if args.doctor:
        print(doctor())
        return
    launch(share=True if args.share or _in_colab() else False, port=args.port)


if __name__ == "__main__":
    main(sys.argv[1:])
