"""Remote mode against a real local server process (S7-T04): laptop submits, GPU box renders."""

import functools
import http.server
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from typer.testing import CliRunner

from audio_smith import api
from audio_smith.cli import app as cli_app
from audio_smith.config import load_settings
from audio_smith.errors import UsageError
from audio_smith.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-token-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(autouse=True)
def _no_speaker_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from audio_smith import pipeline

    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


@pytest.fixture
def page_url() -> Iterator[str]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "tests/fixtures/pages")
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/letter-calm.html"
    httpd.shutdown()


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("AUDIO_SMITH_SERVER_TOKEN", TOKEN)
    settings = load_settings(
        overrides={
            "default_backend": "mock",
            "allow_private": True,
            "out_dir": tmp_path / "server-out",
            "llm": f"fake:{ROOT / 'tests/fixtures/llm'}",
        }
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=10)


def test_remote_run_downloads_artifacts_from_local_server(server: str, page_url: str, tmp_path: Path) -> None:
    res = api.narrate_remote(
        page_url,
        server=server,
        token=TOKEN,
        out=tmp_path / "laptop",
        backend="mock",
        sleep=lambda _s: time.sleep(0.2),
    )
    assert res.manifest is not None and res.manifest_path is not None and res.manifest_path.is_file()
    names = {p.name for p in res.out_dir.iterdir()}
    assert {
        "letter-calm.mp3",
        "letter-calm.vtt",
        "letter-calm.embed.html",
        "letter-calm.manifest.json",
    } <= names


def test_remote_run_inject_locally(server: str, page_url: str, tmp_path: Path) -> None:
    page = tmp_path / "letter-calm.html"
    page.write_text(
        (ROOT / "tests/fixtures/pages/letter-calm.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    res = api.narrate_remote(
        page_url,
        server=server,
        token=TOKEN,
        out=tmp_path / "laptop",
        backend="mock",
        inject=page,
        sleep=lambda _s: time.sleep(0.2),
    )
    assert res.inject_changed and "<!-- audio-smith:start -->" in page.read_text(encoding="utf-8")


def test_remote_wrong_token_is_usage_error(server: str, page_url: str, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        api.narrate_remote(page_url, server=server, token="nope", out=tmp_path / "x", backend="mock")


def test_remote_local_file_source_rejected(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        api.narrate_remote("letter.html", server="http://127.0.0.1:1", token=None, out=tmp_path)


def test_cli_run_server_flag(server: str, page_url: str, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "run",
            page_url,
            "--server",
            server,
            "--token",
            TOKEN,
            "--backend",
            "mock",
            "--out",
            str(tmp_path / "cli"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "manifest:" in result.output
