"""REST server (TEST_PLAN 5.23): jobs, auth, limits, health, files, restart safety."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from typer.testing import CliRunner

from audio_smith import api, pipeline
from audio_smith.cli import app as cli_app
from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.fetch import FetchResult
from audio_smith.llm.fake import FakeProvider
from audio_smith.server.app import create_app
from audio_smith.server.auth import SlidingWindowLimiter, is_loopback
from audio_smith.tts.mock import MockBackend
from audio_smith.tts.runner import ProgressEvent

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "tests" / "fixtures" / "pages" / "letter-calm.html"
LLM = ROOT / "tests" / "fixtures" / "llm"
URL = "https://example.test/letter.html"
TOKEN = "s3cret-token-value"
WAIT_S = 90.0


def _settings(base: Path, **extra: Any) -> Settings:
    return Settings(
        cache_dir=base / "cache",
        voices_dir=base / "voices",
        out_dir=base / "out",
        default_backend="mock",
        **extra,
    )


def _fetch_page(source: str, settings: Settings) -> FetchResult:
    content = PAGE.read_text(encoding="utf-8")
    return FetchResult(
        url=source,
        content=content,
        content_type="text/html",
        encoding="utf-8",
        is_local=False,
        fetched_bytes=len(content),
    )


def _overrides() -> dict[str, Any]:
    return {"provider": FakeProvider(LLM), "fetcher": _fetch_page}


@pytest.fixture(autouse=True)
def _no_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    opened: list[TestClient] = []

    def build(token: str | None = None, overrides: bool = True, **extra: Any) -> TestClient:
        s = _settings(tmp_path, server_token=SecretStr(token) if token else None, **extra)
        client = TestClient(create_app(s, overrides=_overrides if overrides else None))
        client.__enter__()
        opened.append(client)
        return client

    yield build
    for c in opened:
        c.__exit__(None, None, None)


def _auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wait(client: TestClient, job_id: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        if body["status"] in {"done", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _submit(client: TestClient, **body: Any) -> str:
    resp = client.post("/v1/jobs", json={"source": URL, "options": {"llm": "fake"}, **body})
    assert resp.status_code == 202, resp.text
    return str(resp.json()["job_id"])


def test_server_post_job_returns_job_id_async(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    resp = client.post("/v1/jobs", json={"source": URL, "options": {"llm": "fake"}})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert resp.headers["location"] == f"/v1/jobs/{job_id}"
    assert client.get(f"/v1/jobs/{job_id}").status_code == 200


def test_server_job_status_endpoint_states(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    job_id = _submit(client)
    first = client.get(f"/v1/jobs/{job_id}").json()
    assert first["status"] in {"queued", "running", "done"}
    done = _wait(client, job_id)
    assert done["status"] == "done"
    assert done["error"] is None
    assert done["progress"]["stage_pct"] == 1.0
    failing = _submit(client, backend="nope")
    failed = _wait(client, failing)
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "usage"
    assert client.get(f"/v1/jobs/{failing}").status_code == 200


def test_server_artifacts_downloadable_after_done(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    job_id = _submit(client)
    assert _wait(client, job_id)["status"] == "done"
    manifest = client.get(f"/v1/jobs/{job_id}/manifest")
    assert manifest.status_code == 200
    track = manifest.json()["tracks"][0]
    mp3 = client.get(f"/v1/jobs/{job_id}/files/{track['file']}")
    assert mp3.status_code == 200
    assert mp3.headers["content-type"] == "audio/mpeg"
    assert mp3.headers["x-content-type-options"] == "nosniff"
    assert len(mp3.content) > 1000
    vtt = client.get(f"/v1/jobs/{job_id}/files/{track['captions']}")
    assert vtt.status_code == 200
    assert vtt.headers["content-type"].startswith("text/vtt")
    assert vtt.text.startswith("WEBVTT")


def test_server_progress_reported_per_stage(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_narrate = api.narrate
    seen: list[tuple[str | None, float, int | None, int | None]] = []
    client = make_client()
    store = client.app.state.runner.store  # type: ignore[attr-defined]

    def fake_narrate(source: str, **kw: Any) -> Any:
        running = store.list_running()[0]
        assert running.stage == "script"
        for i in range(1, 4):
            kw["progress"](ProgressEvent(stage="synth", done=i, total=3, chunk_id=f"{i:03d}"))
            now = store.get(running.id)
            seen.append((now.stage, now.progress, now.chunk, now.chunks_total))
        return real_narrate(source, **kw)

    monkeypatch.setattr(api, "narrate", fake_narrate)
    job_id = _submit(client)
    assert _wait(client, job_id)["status"] == "done"
    assert [s[0] for s in seen] == ["synth"] * 3
    assert [s[2:] for s in seen] == [(1, 3), (2, 3), (3, 3)]
    assert seen[0][1] == pytest.approx(1 / 3, abs=0.001)


def test_server_concurrent_jobs_run_in_submission_order(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_narrate = api.narrate
    order: list[str] = []

    def fake_narrate(source: str, **kw: Any) -> Any:
        order.append(source)
        time.sleep(0.05)
        return real_narrate(source, **kw)

    monkeypatch.setattr(api, "narrate", fake_narrate)
    client = make_client()
    ids = []
    for n in range(4):
        resp = client.post(
            "/v1/jobs", json={"source": f"https://example.test/{n}.html", "options": {"llm": "fake"}}
        )
        ids.append(resp.json()["job_id"])
    for job_id in ids:
        assert _wait(client, job_id)["status"] == "done"
    assert order == [f"https://example.test/{n}.html" for n in range(4)]


def test_server_job_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "jobs.db"
    store = api.JobStore(db)
    first = store.create("narrate", {"source": URL})
    second = store.create("narrate", {"source": URL + "2"})
    third = store.create("narrate", {"source": URL + "3"})
    store.update(first.id, status="running", stage="synth")
    store.close()
    reopened = api.JobStore(db)
    queued = reopened.recover()
    assert [j.id for j in queued] == [second.id, third.id]
    crashed = reopened.get(first.id)
    assert crashed is not None
    assert crashed.status == "failed"
    assert crashed.error is not None
    assert crashed.error["detail"] == "server restarted"
    assert reopened.get("nope") is None
    with pytest.raises(ValueError):
        reopened.update(second.id, bogus=1)


def test_server_requeued_jobs_run_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_client: Callable[..., TestClient]
) -> None:
    store = api.JobStore(tmp_path / "out" / "jobs.db")
    waiting = store.create("narrate", {"source": URL, "options": {"llm": "fake"}})
    store.close()
    client = make_client()
    assert _wait(client, waiting.id)["status"] == "done"


def test_server_bearer_token_required_when_configured(make_client: Callable[..., TestClient]) -> None:
    client = make_client(token=TOKEN)
    missing = client.get("/v1/profiles")
    assert missing.status_code == 401
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert missing.headers["www-authenticate"] == "Bearer"
    body = missing.json()
    assert body["code"] == "unauthorized" and body["status"] == 401
    wrong = client.get("/v1/profiles", headers=_auth("wrong"))
    assert wrong.status_code == 401
    assert TOKEN not in wrong.text and "wrong" not in wrong.text
    assert client.post("/v1/jobs", json={"source": URL}).status_code == 401
    assert client.get("/v1/profiles", headers=_auth()).status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}


def test_server_missing_bearer_returns_401_problem_json(make_client: Callable[..., TestClient]) -> None:
    client = make_client(token=TOKEN)
    resp = client.get("/v1/jobs/" + "0" * 32)
    assert resp.status_code == 401
    assert {"type", "title", "status", "detail", "code", "instance"} <= set(resp.json())


def test_server_no_auth_when_token_unset_binds_loopback(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    assert client.get("/v1/profiles").status_code == 200
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.5") and not is_loopback("example.com")  # noqa: S104


def test_server_non_localhost_bind_requires_token(tmp_path: Path) -> None:
    with pytest.raises(UsageError) as err:
        create_app(_settings(tmp_path, server_host="0.0.0.0"))  # noqa: S104
    assert "AUDIO_SMITH_SERVER_TOKEN" in (err.value.hint or "")
    create_app(_settings(tmp_path, server_host="0.0.0.0", server_token=SecretStr(TOKEN)))  # noqa: S104
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0", "--out", str(tmp_path / "o")])  # noqa: S104
    assert isinstance(result.exception, UsageError) and result.exception.exit_code == 2


def test_server_rate_limit_returns_429(make_client: Callable[..., TestClient]) -> None:
    client = make_client(token=TOKEN, server_rate_limit_per_hour=2)
    for _ in range(2):
        assert (
            client.post(
                "/v1/jobs", json={"source": URL, "options": {"llm": "fake"}}, headers=_auth()
            ).status_code
            == 202
        )
    limited = client.post("/v1/jobs", json={"source": URL}, headers=_auth())
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["content-type"].startswith("application/problem+json")


def test_server_rate_limit_window_slides() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=100.0, clock=lambda: now[0])
    limiter.hit("a")
    now[0] = 50.0
    limiter.hit("a")
    limiter.hit("b")
    with pytest.raises(Exception, match="Rate limit") as err:
        limiter.hit("a")
    assert err.value.retry_after == 50  # type: ignore[attr-defined]
    now[0] = 101.0
    limiter.hit("a")


def test_server_readyz_flips_when_backend_down(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_client()
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    from audio_smith.preflight import PreflightIssue

    down = [PreflightIssue(severity="error", code="down", message="Maya 2 unreachable", hint="Start it.")]
    monkeypatch.setattr(MockBackend, "preflight", lambda self: down)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert "Maya 2 unreachable" in resp.json()["detail"]


def test_server_readyz_reports_missing_ffmpeg(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    from audio_smith import catalog
    from audio_smith.doctor import CheckResult

    monkeypatch.setattr(
        catalog,
        "check_ffmpeg",
        lambda s: CheckResult(name="ffmpeg", ok=False, detail="not found", hint="install"),
    )
    resp = make_client().get("/readyz")
    assert resp.status_code == 503
    assert "ffmpeg" in resp.json()["detail"]


def test_server_file_path_traversal_rejected(make_client: Callable[..., TestClient], tmp_path: Path) -> None:
    client = make_client()
    job_id = _submit(client)
    assert _wait(client, job_id)["status"] == "done"
    (tmp_path / "out" / "secret.json").write_text('{"k": "SECRET"}', encoding="utf-8")
    job_dir = next((tmp_path / "out" / "jobs" / job_id).iterdir())
    link = job_dir / "link.json"
    link.symlink_to(tmp_path / "out" / "secret.json")
    attempts = [
        "..%2f..%2fsecret.json",
        "%2e%2e",
        "%2e%2e%2fsecret.json",
        "link.json",
        "a%00.mp3",
        "x.exe",
        ".hidden.json",
    ]
    for name in attempts:
        resp = client.get(f"/v1/jobs/{job_id}/files/{name}")
        assert resp.status_code in {400, 404, 422}, name
        assert "SECRET" not in resp.text
        assert resp.headers["content-type"].startswith("application/problem+json")


def test_server_problem_json_shapes(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    missing = client.get("/v1/jobs/" + "a" * 32)
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert missing.json()["code"] == "not_found"
    assert client.get("/v1/jobs/not-an-id").status_code == 404
    assert client.get("/nope").json()["code"] == "not_found"
    bad = client.post("/v1/jobs", json={"profile": "kid-5"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"
    approve = client.post("/v1/jobs", json={"source": URL, "options": {"approve": True}})
    assert approve.status_code == 422 and "Studio" in approve.text
    local = client.post("/v1/jobs", json={"source": "/etc/passwd"})
    assert local.status_code == 422 and local.json()["code"] == "invalid_request"
    extra = client.post("/v1/jobs", json={"source": URL, "evil": 1})
    assert extra.status_code == 422
    assert client.get(f"/v1/jobs/{'b' * 32}/manifest").status_code == 404


def test_server_clone_request_unregistered_voice_403(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    resp = client.post("/v1/jobs", json={"source": URL, "voice": "someone-else", "options": {"llm": "fake"}})
    assert resp.status_code == 403
    assert resp.json()["code"] == "consent_missing"
    render = client.post("/v1/render", json={"script_markdown": "x", "voice": "someone-else"})
    assert render.status_code in {403, 422}


def test_server_ssrf_guard_applies_to_submitted_urls(make_client: Callable[..., TestClient]) -> None:
    client = make_client(overrides=False)
    resp = client.post(
        "/v1/jobs", json={"source": "http://169.254.169.254/latest/", "options": {"llm": "fake"}}
    )
    job_id = resp.json()["job_id"]
    done = _wait(client, job_id)
    assert done["status"] == "failed"
    assert done["error"]["code"] == "fetch_failed"


def test_server_fetch_error_becomes_failed_job(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(source: str, **kw: Any) -> Any:
        raise RuntimeError("secret internals " + TOKEN)

    monkeypatch.setattr(api, "narrate", boom)
    client = make_client()
    body = _wait(client, _submit(client))
    assert body["status"] == "failed"
    assert body["error"]["code"] == "internal_error"
    assert TOKEN not in str(body)


def test_server_catalog_endpoints(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    voices = client.get("/v1/voices").json()
    assert {"id", "display_name", "backends", "cloned"} <= set(voices[0])
    assert any(v["id"] == "mock-a" and not v["cloned"] for v in voices)
    profiles = client.get("/v1/profiles").json()
    assert any(p["id"] == "kid-5" for p in profiles)
    backends = {b["id"]: b for b in client.get("/v1/backends").json()}
    assert backends["mock"]["available"] is True
    assert {"id", "available", "languages", "cloning", "license"} == set(backends["mock"])


def test_server_scripts_and_render_roundtrip(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    script = client.post("/v1/scripts", json={"source": URL, "llm": "fake"})
    assert script.status_code == 200, script.text
    data = script.json()
    assert data["chunks"] > 0 and data["est_minutes"] > 0 and data["content_hash"]
    assert data["script_markdown"].startswith("---")
    json_job = client.post("/v1/render", json={"script_markdown": data["script_markdown"], "chunks": [1]})
    assert json_job.status_code == 202, json_job.text
    done = _wait(client, json_job.json()["job_id"])
    assert done["status"] == "done"
    multi = client.post(
        "/v1/render",
        files={"script": ("s.md", data["script_markdown"].encode(), "text/markdown")},
        data={"voice": "mock-a"},
    )
    assert multi.status_code == 202, multi.text
    assert _wait(client, multi.json()["job_id"])["status"] == "done"
    invalid = client.post("/v1/render", json={"script_markdown": "not a script"})
    assert invalid.status_code == 422 and invalid.json()["code"] == "script_invalid"
    assert client.post("/v1/render", json={"script_markdown": ""}).status_code == 422
    assert client.post("/v1/render", files={"other": ("s.md", b"x")}).status_code == 422


def test_server_cors_disabled_by_default_and_allowlist(make_client: Callable[..., TestClient]) -> None:
    origin = {"Origin": "https://site.example"}
    assert "access-control-allow-origin" not in make_client().get("/healthz", headers=origin).headers
    allowed = make_client(server_cors_origins=["https://site.example"]).get("/healthz", headers=origin)
    assert allowed.headers["access-control-allow-origin"] == "https://site.example"
    other = make_client(server_cors_origins=["https://site.example"]).get(
        "/healthz", headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in other.headers


def test_server_serve_command_needs_server_extra_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "uvicorn", None)
    result = CliRunner().invoke(cli_app, ["serve", "--out", str(tmp_path / "o")])
    assert isinstance(result.exception, UsageError) and "server extra" in str(result.exception)


def test_server_serve_command_starts_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    result = CliRunner().invoke(cli_app, ["serve", "--port", "7399", "--out", str(tmp_path / "o")])
    assert result.exit_code == 0, result.output
    assert calls == [{"host": "127.0.0.1", "port": 7399, "log_level": "warning"}]
