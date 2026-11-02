"""Studio backend (TEST_PLAN 5.22): token, CSP, script editing, takes, master, approve, inject, consent."""

import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from audio_smith import api, pipeline
from audio_smith.cli import app as cli_app
from audio_smith.config import Settings
from audio_smith.errors import SynthesisError, UsageError
from audio_smith.llm.fake import FakeProvider
from audio_smith.studio.routes import TOKEN_HEADER, create_app
from audio_smith.tts.base import SynthParams, VoiceRef
from audio_smith.tts.mock import MockBackend

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "tests" / "fixtures" / "pages"
LLM = ROOT / "tests" / "fixtures" / "llm"
SLUG = "letter-calm"
TOKEN = "test-token-123"
EDITED = "The rain is soft today. We can read by the window."
HEADERS = {TOKEN_HEADER: TOKEN}
PAGE_HTML = "<html><body><h1>Title</h1><p>Body</p></body></html>\n"


def _settings(base: Path) -> Settings:
    return Settings(
        cache_dir=base / "cache", voices_dir=base / "voices", out_dir=base / "out", default_backend="mock"
    )


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """One narrated project (fake LLM, mock TTS, real ffmpeg) copied into every test."""
    base = tmp_path_factory.mktemp("studio-template")
    patch = pytest.MonkeyPatch()
    patch.setattr(pipeline, "load_embedder", lambda: None)
    page = base / f"{SLUG}.html"
    shutil.copyfile(PAGES / f"{SLUG}.html", page)
    settings = _settings(base)
    api.narrate(
        str(page), llm="fake", backend="mock", out=base / "out", provider=FakeProvider(LLM), settings=settings
    )
    yield base
    patch.undo()


@pytest.fixture
def work(template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)
    dest = tmp_path / "work"
    shutil.copytree(template, dest, ignore=shutil.ignore_patterns("*.html"))
    return dest


@pytest.fixture
def client(work: Path) -> TestClient:
    site = work / "site"
    site.mkdir()
    (site / "page.html").write_text(PAGE_HTML, encoding="utf-8")
    app = create_app(work / "out", _settings(work), TOKEN, static_dir=work / "nostatic", project_root=site)
    return TestClient(app, headers=HEADERS)


def _chunks(client: TestClient) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = client.get(f"/api/projects/{SLUG}").json()["chunks"]
    return data


def _put(client: TestClient, chunks: list[dict[str, Any]]) -> Any:
    return client.put(f"/api/projects/{SLUG}/script", json={"chunks": chunks})


def _edit_first(client: TestClient, text: str) -> list[dict[str, Any]]:
    chunks = _chunks(client)
    chunks[0]["text"] = text
    return [{k: c[k] for k in ("id", "text", "verbatim")} for c in chunks]


def test_studio_routes_require_session_token(work: Path) -> None:
    bare = TestClient(create_app(work / "out", _settings(work), TOKEN, static_dir=work / "none"))
    assert bare.get("/api/projects").status_code == 403
    assert bare.get("/api/projects", headers={TOKEN_HEADER: "wrong"}).status_code == 403
    denied = bare.get(f"/media/{SLUG}/{SLUG}.mp3")
    assert denied.status_code == 403 and denied.headers["content-type"].startswith("application/problem+json")
    assert bare.get("/api/projects", headers=HEADERS).status_code == 200
    assert bare.get(f"/media/{SLUG}/{SLUG}.mp3", headers=HEADERS).status_code == 200


def test_studio_security_headers_and_placeholder_index(work: Path) -> None:
    bare = TestClient(create_app(work / "out", _settings(work), TOKEN, static_dir=work / "none"))
    res = bare.get("/")
    assert res.status_code == 200 and "make studio-build" in res.text
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert "access-control-allow-origin" not in res.headers
    denied = bare.get("/api/projects")
    assert "content-security-policy" in denied.headers


def test_studio_serves_built_static_files(work: Path) -> None:
    static = work / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>built</html>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    built = TestClient(create_app(work / "out", _settings(work), TOKEN, static_dir=static))
    assert built.get("/").text == "<html>built</html>"
    assert built.get("/assets/app.js").status_code == 200


def test_studio_player_bundle_route(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare = TestClient(create_app(work / "out", _settings(work), TOKEN, static_dir=work / "none"))
    bundle = work / "audio-smith-player.js"
    bundle.write_text("export {}", encoding="utf-8")
    monkeypatch.setattr(api, "review_player_bundle", lambda: bundle)
    assert bare.get("/player/audio-smith-player.js").text == "export {}"
    monkeypatch.setattr(api, "review_player_bundle", lambda: None)
    assert bare.get("/player/audio-smith-player.js").status_code == 404


def test_studio_lists_and_loads_projects(client: TestClient, work: Path) -> None:
    listed = client.get("/api/projects").json()
    assert [p["slug"] for p in listed] == [SLUG] and listed[0]["has_manifest"] and not listed[0]["approved"]
    data = client.get(f"/api/projects/{SLUG}").json()
    assert data["lang"] == "en" and data["source"].endswith(f"{SLUG}.html")
    assert data["chunks"] and {c["status"] for c in data["chunks"]} == {"cached"}
    assert len(data["track"]["peaks"]) == 28 and data["track"]["captions_url"].startswith("/media/")
    empty = TestClient(create_app(work / "missing", _settings(work), TOKEN), headers=HEADERS)
    assert empty.get("/api/projects").json() == []


def test_studio_unknown_project_is_404_problem(client: TestClient) -> None:
    res = client.get("/api/projects/nope")
    assert res.status_code == 404 and res.json()["code"] == "not_found"
    assert client.get("/api/projects/..%2F..").status_code in (404, 400)


def test_studio_save_script_runs_validation(client: TestClient, work: Path) -> None:
    path = work / "out" / SLUG / f"{SLUG}.en.script.md"
    before = path.read_bytes()
    res = _put(client, _edit_first(client, "This has a bad marker. [pause 5] Done now."))
    body = res.json()
    assert res.status_code == 200 and body["ok"] is False and body["errors"]
    assert "001" in body["errors"][0] and path.read_bytes() == before
    bad_id = _put(client, [{"id": "x", "text": "Hello there.", "verbatim": False}]).json()
    assert bad_id["ok"] is False and "not a number" in bad_id["errors"][0]


def test_studio_save_valid_edit_marks_chunk_stale(client: TestClient, work: Path) -> None:
    body = _put(client, _edit_first(client, EDITED)).json()
    assert body["ok"] is True and body["stale"] == ["001"]
    assert EDITED in (work / "out" / SLUG / f"{SLUG}.en.script.md").read_text(encoding="utf-8")
    statuses = {c["id"]: c["status"] for c in _chunks(client)}
    assert statuses["001"] == "stale" and set(statuses.values()) == {"stale", "cached"}


def test_studio_render_chunk_returns_take_id(client: TestClient) -> None:
    url = f"/api/projects/{SLUG}/chunks/001/render"
    first, second = client.post(url, json={}).json(), client.post(url).json()
    assert (first["take"], second["take"]) == (1, 2) and first["seed"] != second["seed"]
    assert first["duration_ms"] > 0 and client.get(first["url"]).status_code == 200
    explicit = client.post(url, json={"seed": 7}).json()
    assert explicit["seed"] == 7 and client.post(url, json={"seed": -1}).status_code == 422


def test_studio_list_takes_includes_similarity_scores(client: TestClient) -> None:
    client.post(f"/api/projects/{SLUG}/chunks/001/render")
    takes = _chunks(client)[0]["takes"]
    assert len(takes) == 1 and "similarity" in takes[0] and takes[0]["url"].startswith("/media/")


def test_studio_render_unknown_chunk_404(client: TestClient) -> None:
    assert client.post(f"/api/projects/{SLUG}/chunks/999/render").status_code == 404
    assert client.post(f"/api/projects/{SLUG}/chunks/001/select", json={"take": 9}).status_code == 404


def test_studio_select_take_and_remaster(client: TestClient, work: Path) -> None:
    _put(client, _edit_first(client, EDITED))
    client.post(f"/api/projects/{SLUG}/chunks/001/render")
    take = client.post(f"/api/projects/{SLUG}/chunks/001/render").json()["take"]
    assert client.post(f"/api/projects/{SLUG}/chunks/001/select", json={"take": take}).json() == {"ok": True}
    first = _chunks(client)[0]
    assert first["selected_take"] == take and first["status"] == "cached"
    track = client.post(f"/api/projects/{SLUG}/master").json()
    assert len(track["peaks"]) == 28 and track["duration_s"] > 1
    audio = client.get(track["url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    assert client.get(track["captions_url"]).status_code == 200
    manifest = json.loads((work / "out" / SLUG / f"{SLUG}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["tracks"][0]["duration_s"] == track["duration_s"]


def test_studio_approve_persists_in_manifest(client: TestClient, work: Path) -> None:
    assert client.post(f"/api/projects/{SLUG}/approve").json() == {"approved": True}
    manifest = json.loads((work / "out" / SLUG / f"{SLUG}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["approved"] is True
    assert client.get("/api/projects").json()[0]["approved"] is True
    client.post(f"/api/projects/{SLUG}/master")
    assert client.get(f"/api/projects/{SLUG}").json()["approved"] is False


def test_studio_approve_without_manifest_is_400(client: TestClient, work: Path) -> None:
    (work / "out" / SLUG / f"{SLUG}.manifest.json").unlink()
    assert client.post(f"/api/projects/{SLUG}/approve").status_code == 400
    assert client.get(f"/api/projects/{SLUG}").json()["track"] is None


def test_studio_inject_diff_preview_before_write(client: TestClient, work: Path) -> None:
    page = work / "site" / "page.html"
    dry = client.post(f"/api/projects/{SLUG}/inject", json={"path": "page.html", "dry_run": True}).json()
    assert dry["changed"] is True and "audio-smith:start" in dry["diff"] and "+++ b/page.html" in dry["diff"]
    assert page.read_text(encoding="utf-8") == PAGE_HTML
    done = client.post(f"/api/projects/{SLUG}/inject", json={"path": "page.html", "dry_run": False}).json()
    assert done["changed"] is True and "audio-smith-player" in page.read_text(encoding="utf-8")
    again = client.post(f"/api/projects/{SLUG}/inject", json={"path": "page.html", "dry_run": False}).json()
    assert again["changed"] is False


def test_studio_inject_rejects_paths_outside_project_root(client: TestClient, work: Path) -> None:
    (work / "outside.html").write_text(PAGE_HTML, encoding="utf-8")
    for bad in ("../outside.html", str(work / "outside.html"), "/etc/hosts"):
        res = client.post(f"/api/projects/{SLUG}/inject", json={"path": bad, "dry_run": False})
        assert res.status_code == 400, bad
    assert (work / "outside.html").read_text(encoding="utf-8") == PAGE_HTML
    missing = client.post(f"/api/projects/{SLUG}/inject", json={"path": "nope.html", "dry_run": True})
    assert missing.status_code == 404


def test_studio_media_rejects_traversal_and_unknown_types(client: TestClient) -> None:
    assert client.get(f"/media/{SLUG}/..%2F..%2Fetc%2Fhosts").status_code == 400
    assert client.get(f"/media/{SLUG}/%2Fetc%2Fhosts").status_code == 400
    assert client.get(f"/media/{SLUG}/{SLUG}.manifest.json").status_code == 404
    assert client.get(f"/media/{SLUG}/missing.mp3").status_code == 404
    assert client.get("/media/..%2F../x.mp3").status_code in (400, 404)


def test_studio_render_unregistered_cloned_voice_is_403_consent(client: TestClient, work: Path) -> None:
    path = work / "out" / SLUG / f"{SLUG}.manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["voice_id"] = "ghost-voice"
    path.write_text(json.dumps(data), encoding="utf-8")
    res = client.post(f"/api/projects/{SLUG}/chunks/001/render")
    assert res.status_code == 403 and res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["code"] == "consent_missing" and body["status"] == 403 and "hint" in body


class _Failing(MockBackend):
    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> Any:
        raise SynthesisError("backend down", retryable=False)


def test_studio_failed_render_marks_chunk_failed(work: Path) -> None:
    settings = _settings(work)
    with pytest.raises(SynthesisError):
        api.review_render_take(work / "out", SLUG, "002", settings, seed=3, tts=_Failing())
    view = api.review_load_project(work / "out", SLUG, settings)
    assert {c.id: c.status for c in view.chunks}["002"] == "failed"
    ok = api.review_render_take(work / "out", SLUG, "002", settings, seed=3)
    assert ok.take == 1
    assert {c.id: c.status for c in api.review_load_project(work / "out", SLUG, settings).chunks}["002"] == (
        "cached"
    )


def test_studio_remaster_falls_back_to_fresh_render_for_stale_selection(client: TestClient) -> None:
    client.post(f"/api/projects/{SLUG}/chunks/001/render")
    client.post(f"/api/projects/{SLUG}/chunks/001/select", json={"take": 1})
    _put(client, _edit_first(client, EDITED))
    res = client.post(f"/api/projects/{SLUG}/master")
    assert res.status_code == 200 and res.json()["duration_s"] > 0


def test_studio_binds_127_0_0_1_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr("webbrowser.open", lambda url: seen.update(opened=url))
    runner = CliRunner()
    res = runner.invoke(cli_app, ["studio", "--no-open", "--out", "audio"])
    assert res.exit_code == 0, res.output
    assert seen["host"] == "127.0.0.1" and seen["port"] == 7341 and "opened" not in seen
    assert "http://127.0.0.1:7341/?token=" in res.output
    assert runner.invoke(cli_app, ["studio", "--host", "0.0.0.0"]).exit_code == 2  # noqa: S104


def test_studio_cli_opens_browser_unless_no_open(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    opened: list[str] = []

    class _Now:
        def __init__(self, _delay: float, fn: Any, args: tuple[str, ...]) -> None:
            self.fn, self.args = fn, args

        def start(self) -> None:
            self.fn(*self.args)

    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr("threading.Timer", _Now)
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert CliRunner().invoke(cli_app, ["studio", "--port", "7399"]).exit_code == 0
    assert opened and opened[0].startswith("http://127.0.0.1:7399/?token=")


def test_studio_cli_explains_missing_server_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    res = CliRunner().invoke(cli_app, ["studio", "--no-open"])
    assert isinstance(res.exception, UsageError) and "mr-audio-smith[server]" in (res.exception.hint or "")
