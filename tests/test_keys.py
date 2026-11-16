"""API key: Colab Secrets, rồi biến môi trường / .env, rồi thiếu. Không in giá trị."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types

import pytest

NAMES = (
    "XAI_API_KEY",
    "RM_API_KEY_FROM_XAI_API_KEY",
)


@pytest.fixture
def clean_api_env(monkeypatch, tmp_path):
    saved = {name: os.environ.get(name) for name in NAMES}
    for name in NAMES:
        os.environ.pop(name, None)
    monkeypatch.setattr("src.keys._dotenv_file", lambda: str(tmp_path / "missing.env"))
    hide_colab(monkeypatch)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def hide_colab(monkeypatch):
    monkeypatch.delitem(sys.modules, "google.colab", raising=False)
    google = sys.modules.get("google")
    if google is not None and hasattr(google, "colab"):
        monkeypatch.delattr(google, "colab", raising=False)


def install_colab(monkeypatch, getter):
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=getter)
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    google = sys.modules.get("google")
    if google is None:
        google = types.ModuleType("google")
        google.__path__ = []
        monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setattr(google, "colab", colab, raising=False)


def _load_setup():
    path = os.path.join(os.path.dirname(__file__), "..", "colab", "setup_colab.py")
    spec = importlib.util.spec_from_file_location("setup_colab_keys_under_test", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_colab_secret_overrides_env_and_is_not_printed(clean_api_env, monkeypatch, capsys):
    monkeypatch.setenv("XAI_API_KEY", "env-value-should-lose-123")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-value-123456")

    def getter(name):
        if name == "XAI_API_KEY":
            return "  colab-value-do-not-print  "
        raise RuntimeError("colab-value-do-not-print was refused")

    install_colab(monkeypatch, getter)
    from src.keys import api_key_for, load_api_keys, summary_line

    sources = load_api_keys()
    assert sources == {"XAI_API_KEY": "colab"}
    assert "OPENAI_API_KEY" not in sources
    assert api_key_for() == "colab-value-do-not-print"
    assert os.environ["RM_API_KEY_FROM_XAI_API_KEY"] == "colab"
    assert os.environ["OPENAI_API_KEY"] == "openai-env-value-123456"
    printed = summary_line()
    captured = capsys.readouterr()
    blob = printed + captured.out + captured.err
    assert "colab-value-do-not-print" not in blob
    assert "env-value-should-lose-123" not in blob
    assert "openai-env-value-123456" not in blob
    assert printed == "XAI_API_KEY: đã có."
    assert "OPENAI_API_KEY" not in printed


def test_env_used_when_colab_missing(clean_api_env, monkeypatch, capsys):
    monkeypatch.setenv("XAI_API_KEY", "env-only-value-abcdef")

    def getter(name):
        raise RuntimeError("Notebook access denied")

    install_colab(monkeypatch, getter)
    from src.keys import found_message, load_api_keys, status_message

    assert load_api_keys()["XAI_API_KEY"] == "env"
    text, kind = status_message("xAI")
    assert text == found_message("env")
    assert text == "Đã có API key từ biến môi trường."
    assert kind == "ok"
    assert "env-only-value-abcdef" not in capsys.readouterr().out


def test_dotenv_used_when_colab_and_env_missing(clean_api_env, monkeypatch, tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local only",
                "export XAI_API_KEY='from-dotenv-xai-value'",
                'OPENAI_API_KEY="from-dotenv-openai-value"',
                "RM_DRIVE_ROOT=/ignored",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.keys._dotenv_file", lambda: str(env_file))
    from src.keys import api_key_for, load_api_keys, status_message

    sources = load_api_keys()
    assert sources == {"XAI_API_KEY": "dotenv"}
    assert api_key_for() == "from-dotenv-xai-value"
    assert os.environ.get("OPENAI_API_KEY") != "from-dotenv-openai-value"
    assert os.environ["XAI_API_KEY"] == "from-dotenv-xai-value"
    text, kind = status_message("xAI")
    assert text == "Đã có API key từ file .env."
    assert kind == "ok"
    captured = capsys.readouterr()
    assert "from-dotenv-xai-value" not in captured.out
    assert "from-dotenv-openai-value" not in captured.err


def test_dotenv_does_not_override_env(clean_api_env, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("XAI_API_KEY=from-dotenv-should-lose\n", encoding="utf-8")
    monkeypatch.setattr("src.keys._dotenv_file", lambda: str(env_file))
    monkeypatch.setenv("XAI_API_KEY", "from-env-should-win-123")
    from src.keys import api_key_for, load_api_keys

    assert load_api_keys()["XAI_API_KEY"] == "env"
    assert api_key_for("xAI") == "from-env-should-win-123"


def test_missing_names_the_secret_and_prints_nothing(clean_api_env, capsys):
    from src.keys import api_key_for, has_api_key, load_api_keys, status_html, status_message

    assert load_api_keys() == {"XAI_API_KEY": "missing"}
    assert os.environ.get("XAI_API_KEY", "") == ""
    assert api_key_for() == ""
    assert has_api_key() is False
    text, kind = status_message("xAI")
    assert kind == "miss"
    assert "XAI_API_KEY" in text
    assert "OPENAI_API_KEY" not in text
    assert "biểu tượng khóa" in text
    assert "Notebook access" in text
    assert "khởi động lại runtime" in text
    html = status_html("xAI")
    assert "XAI_API_KEY" in html
    assert "key-status miss" in html
    assert capsys.readouterr().out == ""


def test_colab_status_line_when_secret_exists(clean_api_env, monkeypatch):
    install_colab(monkeypatch, lambda name: "colab-status-value-999" if name == "XAI_API_KEY" else "")
    from src.keys import status_html, status_message, summary_line

    text, kind = status_message("xAI")
    assert kind == "ok"
    assert text == "Đã có API key từ Colab Secrets."
    html = status_html("xAI")
    assert "Đã có API key từ Colab Secrets." in html
    assert "colab-status-value-999" not in html
    assert summary_line() == "XAI_API_KEY: đã có."


def test_step_log_and_public_error_redact_key(clean_api_env, monkeypatch, capsys):
    monkeypatch.setenv("XAI_API_KEY", "abcdefghijklmnop")
    from src.keys import load_api_keys
    from src.textutil import StepLog, public_error

    load_api_keys()
    log = StepLog()
    log("Gọi API với abcdefghijklmnop")
    assert "abcdefghijklmnop" not in log.text()
    assert "***" in log.text()
    message = public_error(RuntimeError("bad key abcdefghijklmnop"), "abcdefghijklmnop")
    assert "abcdefghijklmnop" not in message
    captured = capsys.readouterr()
    assert "abcdefghijklmnop" not in captured.out
    assert "abcdefghijklmnop" not in captured.err


def test_generate_narrations_rejects_blank_key():
    from src.script import generate_narrations

    with pytest.raises(RuntimeError) as caught:
        generate_narrations(
            [],
            title="",
            chapter="",
            lore="",
            provider="xAI",
            api_key="   ",
            model="grok-4.7",
            base_url="",
            use_vision=False,
            temperature=0.6,
            style_key="review",
            notes="",
            log=lambda _message: None,
            progress=lambda *_args, **_kwargs: None,
        )
    assert "XAI_API_KEY" in str(caught.value)
    assert "OPENAI" not in str(caught.value)
    assert "Notebook access" in str(caught.value)


def test_prepare_exports_colab_key_without_printing_it(clean_api_env, monkeypatch, tmp_path, capsys):
    setup = _load_setup()
    monkeypatch.setattr(setup, "REPO", tmp_path / "repo")
    install_colab(
        monkeypatch,
        lambda name: "prepare-secret-value-xyz" if name == "XAI_API_KEY" else "",
    )
    setup.prepare(str(tmp_path / "ReviewManhwa"))
    assert os.environ["XAI_API_KEY"] == "prepare-secret-value-xyz"
    assert os.environ["RM_API_KEY_FROM_XAI_API_KEY"] == "colab"
    captured = capsys.readouterr()
    assert "prepare-secret-value-xyz" not in captured.out
    assert "prepare-secret-value-xyz" not in captured.err
    assert "OPENAI_API_KEY" not in captured.out
    assert "XAI_API_KEY:" not in captured.out
    assert "secret" not in captured.out.lower()


def test_notebook_tells_user_to_use_colab_secrets():
    path = os.path.join(os.path.dirname(__file__), "..", "notebooks", "Review_Manhwa.ipynb")
    notebook = json.loads(open(path, encoding="utf-8").read())
    text = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    assert "XAI_API_KEY" in text
    assert "OPENAI_API_KEY" not in text
    assert "OpenAI-compatible" not in text
    assert "announce=False" in text
    assert "print(src.storage.summary_lines())" not in text
    assert "Notebook access" in text
    assert "dán API key" not in text
    assert "import src.keys" in text
    readme = open(os.path.join(os.path.dirname(__file__), "..", "README.md"), encoding="utf-8").read()
    assert "XAI_API_KEY" in readme
    assert "OPENAI_API_KEY" not in readme
    assert "dán API key" not in readme


def _walk(block):
    yield block
    for child in getattr(block, "children", []) or []:
        yield from _walk(child)


def _isolate_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("RM_DRIVE_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("RM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("RM_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RM_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setenv("RM_OUTPUT_DIR", str(tmp_path / "output"))


def test_script_step_shows_status_and_disables_write_without_key(clean_api_env, monkeypatch, tmp_path):
    _isolate_storage(monkeypatch, tmp_path)
    from src.ui import build_demo

    demo = build_demo()
    blocks = list(_walk(demo))
    labels = [getattr(block, "label", None) for block in blocks]
    assert "API key" not in labels
    assert "Nguồn viết lời" not in labels
    assert "Base URL" not in labels
    assert "Model" in labels
    assert "OpenAI-compatible" not in json.dumps(demo.get_config_file(), default=str)
    assert not any(getattr(block, "type", None) == "password" for block in blocks)
    write = next(block for block in blocks if getattr(block, "elem_id", None) == "write-script")
    assert write.value == "Đọc chữ và viết lời"
    key_line = next(block for block in blocks if getattr(block, "elem_id", None) == "key-line")
    assert "Chưa có API key" in key_line.value
    assert "XAI_API_KEY" in key_line.value
    config = json.dumps(demo.get_config_file(), default=str)
    assert '"label": "API key"' not in config
    assert "Chỉ nằm trong phiên này" not in config
    assert '"type": "password"' not in config


def test_script_step_enables_write_when_env_key_exists(clean_api_env, monkeypatch, tmp_path):
    _isolate_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "ui-env-value-do-not-show")
    from src.ui import build_demo, on_script

    demo = build_demo()
    blocks = list(_walk(demo))
    write = next(block for block in blocks if getattr(block, "elem_id", None) == "write-script")
    key_line = next(block for block in blocks if getattr(block, "elem_id", None) == "key-line")
    assert write.interactive is True
    assert "Đã có API key từ biến môi trường." in key_line.value
    assert "ui-env-value-do-not-show" not in key_line.value
    config = json.dumps(demo.get_config_file(), default=str)
    assert "ui-env-value-do-not-show" not in config
    assert "OpenAI-compatible" not in config

    rows = list(on_script("missing-job", 2, "", "", "", "grok-4.7", 0.6, False, "review", "", None, ["ko"], False))
    blob = json.dumps(rows, default=str)
    assert "ui-env-value-do-not-show" not in blob


def test_on_script_reports_missing_key_without_printing_it(clean_api_env, capsys):
    from src.ui import on_script

    rows = list(on_script("", 2, "", "", "", "grok-4.7", 0.6, False, "review", "", None, ["ko"], False))
    status = rows[0][2]
    assert "tách panel" in status
    captured = capsys.readouterr()
    assert "sk-" not in captured.out
