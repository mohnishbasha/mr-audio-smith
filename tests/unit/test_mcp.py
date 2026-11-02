"""MCP server tools (FR-024): tool functions, listing, schemas, errors, progress, bearer guard."""

import asyncio
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.llm.fake import FakeProvider
from audio_smith.mcp_server import catalog
from audio_smith.mcp_server.server import (
    TOOL_NAMES,
    BearerAuth,
    MonotonicProgress,
    ToolRuntime,
    create_server,
    is_loopback,
    serve_http,
)
from audio_smith.mcp_server.tools import NarrateIn, RecommendIn, ToolEnv, run_narrate
from audio_smith.tts.mock import MockBackend

ALL_INTERFACES = ".".join(["0"] * 4)
ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "tests" / "fixtures" / "pages" / "letter-calm.html"
LLM = ROOT / "tests" / "fixtures" / "llm"


@pytest.fixture(autouse=True)
def _no_speaker_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from audio_smith import pipeline

    monkeypatch.setattr(pipeline, "load_embedder", lambda: None)


@pytest.fixture
def env(tmp_path: Path) -> ToolEnv:
    (tmp_path / "page.html").write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(
        out_dir=tmp_path / "out", cache_dir=tmp_path / "cache", voices_dir=tmp_path / "voices", llm="fake"
    )
    return ToolEnv(settings=settings, provider=FakeProvider(LLM), tts=MockBackend(), cwd=tmp_path)


async def _call(env: ToolEnv, name: str, args: dict[str, Any]) -> Any:
    return await create_server(env).call_tool(name, args)


def _error(env: ToolEnv, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a tool that must fail; the SDK raises ToolError directly (a protocol client sees is_error)."""
    with pytest.raises(ToolError) as info:
        asyncio.run(_call(env, name, args))
    return dict(json.loads(str(info.value).split(": ", 1)[1]))


def _structured(result: Any) -> Any:
    data = result.structured_content
    return data["result"] if isinstance(data, dict) and set(data) == {"result"} else data


def test_mcp_tools_listed_match_appendix_e() -> None:
    tools = asyncio.run(create_server().list_tools())
    assert sorted(t.name for t in tools) == sorted(TOOL_NAMES)
    assert len(tools) == 8
    for t in tools:
        assert "consent" in (t.description or "")


def test_mcp_tool_input_schemas_valid_json_schema() -> None:
    for t in asyncio.run(create_server().list_tools()):
        jsonschema.Draft202012Validator.check_schema(t.input_schema)
        assert t.output_schema is not None
        jsonschema.Draft202012Validator.check_schema(t.output_schema)


def test_mcp_tool_call_narrate_returns_manifest_summary(env: ToolEnv) -> None:
    result = asyncio.run(_call(env, "mr_audio_smith_narrate", {"source": "page.html", "backend": "mock"}))
    data = _structured(result)
    manifest = Path(data["manifest_path"])
    assert manifest.is_absolute() and manifest.is_file()
    track = data["tracks"][0]
    assert track["lang"] == "en" and Path(track["file"]).is_absolute() and Path(track["file"]).is_file()
    assert track["duration_s"] > 0
    assert isinstance(data["warnings"], list)


def test_mcp_narrate_progress_is_monotonic(env: ToolEnv) -> None:
    seen: list[float] = []
    inp = NarrateIn(source="page.html", backend="mock")
    run_narrate(inp, env, lambda frac, _msg: seen.append(frac))
    assert seen and seen == sorted(seen) and seen[0] > 0.0 and seen[-1] <= 1.0


def test_mcp_monotonic_progress_skips_repeats_and_missing_context() -> None:
    async def go() -> None:
        import anyio.to_thread

        prog = MonotonicProgress(None)
        await anyio.to_thread.run_sync(prog, 0.5, "a")
        await anyio.to_thread.run_sync(prog, 0.4, "b")
        assert prog._last == 0.5

    asyncio.run(go())


def test_mcp_inject_path_outside_working_directory_refused(env: ToolEnv) -> None:
    err = _error(
        env, "mr_audio_smith_narrate", {"source": "page.html", "backend": "mock", "inject_path": "../x.html"}
    )
    assert err["code"] == "usage"


def test_mcp_clone_tool_enforces_consent(env: ToolEnv) -> None:
    class Cloner(MockBackend):
        def capabilities(self):  # type: ignore[no-untyped-def]
            return super().capabilities().model_copy(update={"cloning": True})

    env.tts = Cloner()
    err = _error(
        env, "mr_audio_smith_narrate", {"source": "page.html", "backend": "mock", "voice": "someone-else"}
    )
    assert err["code"] == "consent_missing" and err["hint"] and "stage" in err


def test_mcp_invalid_input_becomes_usage_tool_error(env: ToolEnv) -> None:
    assert _error(env, "mr_audio_smith_script", {"source": ""})["code"] == "usage"


def test_mcp_script_then_render_chunks_and_full(env: ToolEnv) -> None:
    script = _structured(asyncio.run(_call(env, "mr_audio_smith_script", {"source": "page.html"})))
    assert Path(script["script_path"]).is_file() and script["chunks"] >= 1 and script["est_minutes"] >= 0
    full = _structured(
        asyncio.run(
            _call(env, "mr_audio_smith_render", {"script_path": script["script_path"], "backend": "mock"})
        )
    )
    assert any(f.endswith(".mp3") for f in full["files"])
    part = _structured(
        asyncio.run(
            _call(
                env,
                "mr_audio_smith_render",
                {"script_path": script["script_path"], "backend": "mock", "chunks": [1]},
            )
        )
    )
    assert part["files"] and all(Path(f).is_absolute() for f in part["files"])


def test_mcp_render_script_outside_allowed_dirs_refused(env: ToolEnv) -> None:
    assert _error(env, "mr_audio_smith_render", {"script_path": "/etc/hosts"})["code"] == "usage"


def test_mcp_catalog_tools(env: ToolEnv) -> None:
    profiles = _structured(asyncio.run(_call(env, "mr_audio_smith_list_profiles", {})))
    assert {"kid-5", "kid-8", "adult-commute", "adult-brief"} <= {p["id"] for p in profiles}
    backends = _structured(asyncio.run(_call(env, "mr_audio_smith_list_backends", {})))
    by_id = {b["id"]: b for b in backends}
    assert set(by_id) >= {"maya2", "kokoro", "mock"} and by_id["mock"]["available"] is True
    voices = _structured(asyncio.run(_call(env, "mr_audio_smith_list_voices", {})))
    assert all({"id", "display_name", "backends", "cloned"} <= set(v) for v in voices)
    report = _structured(asyncio.run(_call(env, "mr_audio_smith_status", {})))
    assert isinstance(report["ok"], bool) and report["checks"]
    assert isinstance(report["cloud_providers_active"], bool)


@pytest.mark.parametrize(
    ("text", "profile"),
    [
        ("a bedtime story for my son, he is 4 years old", "kid-5"),
        ("for my daughter aged 9", "kid-8"),
        ("something for the kids", "kid-5"),
        ("while I drive to work", "adult-commute"),
        ("a quick summary please", "adult-brief"),
        ("no hints here", "kid-5"),
    ],
)
def test_mcp_recommend_rules(text: str, profile: str) -> None:
    out = catalog.recommend(RecommendIn(description=text), Settings())
    assert out.profile == profile and out.reason
    assert out.backend in {"maya2", "kokoro", "mock"}


def test_mcp_recommend_backend_fallback_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    out = catalog.recommend(RecommendIn(source="https://example.com/x"), Settings(default_backend="mock"))
    assert out.backend in {"mock", "maya2"}


def test_mcp_recommend_requires_input() -> None:
    with pytest.raises(UsageError):
        catalog.recommend(RecommendIn(), Settings())


def test_mcp_runtime_defaults_to_empty_env() -> None:
    assert ToolRuntime().env.settings is None


def test_mcp_bearer_auth_rejects_and_accepts() -> None:
    sent: list[dict[str, Any]] = []
    reached: list[bool] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        reached.append(True)

    async def send(msg: Any) -> None:
        sent.append(msg)

    async def recv() -> dict[str, Any]:
        return {}

    guard = BearerAuth(inner, "s3cret")

    async def go(headers: list[tuple[bytes, bytes]]) -> None:
        await guard({"type": "http", "headers": headers}, recv, send)

    asyncio.run(go([]))
    asyncio.run(go([(b"authorization", b"Bearer wrong")]))
    assert not reached and sent[0]["status"] == 401
    asyncio.run(go([(b"authorization", b"Bearer s3cret")]))
    assert reached
    asyncio.run(guard({"type": "lifespan"}, recv, send))
    assert len(reached) == 2


def test_mcp_http_non_loopback_requires_token() -> None:
    assert is_loopback("127.0.0.1") and not is_loopback(ALL_INTERFACES)
    with pytest.raises(UsageError):
        serve_http(create_server(), ALL_INTERFACES, 7342, None)


def test_mcp_cli_rejects_unknown_transport() -> None:
    from typer.testing import CliRunner

    from audio_smith.cli import app

    result = CliRunner().invoke(app, ["mcp", "--transport", "carrier-pigeon"])
    assert isinstance(result.exception, UsageError)
