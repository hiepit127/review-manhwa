"""Link công khai: thử Gradio vài lần, rồi Cloudflare, rồi proxy Colab."""

from __future__ import annotations

import os
import stat

from app import launch_options


def test_colab_launch_keeps_debug_and_does_not_hand_share_to_gradio():
    assert launch_options(in_colab=True, share=True) == {"share": False, "debug": True}
    assert launch_options(in_colab=False, share=False) == {"share": False, "debug": False}
    assert launch_options(in_colab=False, share=True) == {"share": True, "debug": False}


def test_gradio_share_is_retried_then_cloudflared_is_used():
    from src.share import choose_public_url, link_line

    calls = {"n": 0}

    def gradio(_port):
        calls["n"] += 1
        raise RuntimeError("Could not get share link from Gradio API Server.")

    def cloud(_port):
        return "https://example-tunnel.trycloudflare.com"

    def colab(_port):
        raise AssertionError("không cần proxy Colab khi đã có Cloudflare")

    result = choose_public_url(
        7860,
        attempts=3,
        pause=0,
        sleeper=lambda _seconds: None,
        gradio_share=gradio,
        cloudflared=cloud,
        colab_proxy=colab,
    )
    assert calls["n"] == 3
    assert result == {"url": "https://example-tunnel.trycloudflare.com", "via": "cloudflared"}
    line = link_line(result)
    assert line.count("https://") == 1
    assert "Mở giao diện: https://example-tunnel.trycloudflare.com" in line


def test_first_gradio_success_skips_fallbacks():
    from src.share import choose_public_url, link_line

    def cloud(_port):
        raise AssertionError("không mở cloudflared")

    result = choose_public_url(
        7860,
        attempts=3,
        sleeper=lambda _seconds: None,
        gradio_share=lambda _port: "https://abc123.gradio.live",
        cloudflared=cloud,
        colab_proxy=cloud,
    )
    assert result["via"] == "gradio"
    assert link_line(result) == "Mở giao diện: https://abc123.gradio.live"


def test_colab_proxy_is_last_and_missing_link_has_no_url():
    from src.share import choose_public_url, link_line

    slept = {"n": 0}

    def sleeper(_seconds):
        slept["n"] += 1

    result = choose_public_url(
        7860,
        attempts=3,
        pause=0.2,
        sleeper=sleeper,
        gradio_share=lambda _port: "",
        cloudflared=lambda _port: "",
        colab_proxy=lambda _port: "https://7860-example.colab.googleusercontent.com/",
    )
    assert slept["n"] == 2
    assert result["via"] == "colab"
    assert "colab.googleusercontent.com" in link_line(result)

    empty = choose_public_url(
        7860,
        attempts=1,
        sleeper=lambda _seconds: None,
        gradio_share=lambda _port: "",
        cloudflared=lambda _port: "",
        colab_proxy=lambda _port: "",
    )
    assert empty == {"url": "", "via": "none"}
    assert "http" not in link_line(empty)


def test_cloudflared_log_parser_and_process(tmp_path):
    from src.share import cloudflared_url, cloudflared_url_from_log

    assert cloudflared_url_from_log("noise\nhttps://ab-cd.trycloudflare.com\n") == "https://ab-cd.trycloudflare.com"
    assert cloudflared_url_from_log("no url here") == ""
    binary = tmp_path / "cloudflared"
    binary.write_text(
        "#!/bin/sh\necho '2026-01-01 INF https://demo-tunnel.trycloudflare.com registered'\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    url = cloudflared_url(7860, binary=str(binary), timeout=5)
    assert url == "https://demo-tunnel.trycloudflare.com"


def test_ensure_cloudflared_does_not_download_off_colab(monkeypatch):
    from src import share

    monkeypatch.setattr(share.shutil, "which", lambda _name: None)
    monkeypatch.delenv("COLAB_RELEASE_TAG", raising=False)
    monkeypatch.delenv("COLAB_GPU", raising=False)
    monkeypatch.setattr(share, "_BINARY", share.Path("/tmp/review-manhwa-cloudflared-missing"))
    assert share.ensure_cloudflared() == ""


def test_launch_cell_does_not_repeat_setup_status():
    import json

    path = os.path.join(os.path.dirname(__file__), "..", "notebooks", "Review_Manhwa.ipynb")
    notebook = json.loads(open(path, encoding="utf-8").read())
    launch = next(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and "app.launch()" in "".join(cell["source"])
    )
    assert "announce=False" in launch
    assert "summary_lines" not in launch
    assert "close_ports" not in launch
