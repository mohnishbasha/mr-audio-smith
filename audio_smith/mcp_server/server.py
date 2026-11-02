"""MCP server (FR-024, ADR-013): eight tools over stdio or streamable HTTP.

The sync pipeline runs in a worker thread; progress notifications are sent from there
back to the event loop. Nothing here may write to stdout (it carries the stdio protocol).
"""

import hmac
import json
import sys
import threading
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from contextlib import contextmanager
from functools import partial
from typing import Annotated, Any

import anyio
import anyio.from_thread
import anyio.lowlevel
import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, ValidationError

from audio_smith.errors import AudioSmithError, UsageError
from audio_smith.mcp_server import catalog
from audio_smith.mcp_server.tools import (
    CONSENT_NOTE,
    BackendInfo,
    NarrateIn,
    NarrateOut,
    ProfileInfo,
    RecommendIn,
    RecommendOut,
    RenderIn,
    RenderOut,
    ScriptIn,
    ScriptOut,
    StatusOut,
    ToolEnv,
    VoiceInfo,
    run_narrate,
    run_render,
    run_script,
)

SERVER_NAME = "mr-audio-smith"
TOOL_NAMES = (
    "mr_audio_smith_narrate",
    "mr_audio_smith_script",
    "mr_audio_smith_render",
    "mr_audio_smith_list_voices",
    "mr_audio_smith_list_profiles",
    "mr_audio_smith_list_backends",
    "mr_audio_smith_status",
    "mr_audio_smith_recommend",
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
BEARER_PREFIX = "bearer "
HTTP_UNAUTHORIZED = 401
MCP_PATH = "/mcp"
INSTALL_HINT = 'uv tool install "mr-audio-smith[mcp]"'

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
Ctx = Context[Any, Any]


@contextmanager
def tool_errors() -> Iterator[None]:
    """Turn typed errors into MCP tool errors carrying code, stage, message, and hint (no traces)."""
    try:
        yield
    except ValidationError as e:
        fields = ", ".join(sorted({".".join(str(p) for p in err["loc"]) for err in e.errors()}))
        raise ToolError(
            _payload(UsageError(f"Invalid input: {fields}", hint="Check the tool schema."))
        ) from None
    except AudioSmithError as e:
        raise ToolError(_payload(e)) from None


def _payload(e: AudioSmithError) -> str:
    return json.dumps({"code": e.code, "stage": e.stage, "message": e.message, "hint": e.hint})


async def _notify(ctx: Ctx | None, progress: float, message: str) -> None:
    """Best-effort progress notification; a client without a progress token is fine."""
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress, 1.0, message)
    except Exception as e:  # progress must never fail a narration
        print(f"mcp progress skipped: {e}", file=sys.stderr)


class MonotonicProgress:
    """Thread-safe bridge: worker thread calls it, the event loop gets increasing notifications."""

    def __init__(self, ctx: Ctx | None) -> None:
        self._ctx = ctx
        self._last = -1.0
        self._lock = threading.Lock()
        self._token = anyio.lowlevel.current_token()

    def __call__(self, fraction: float, message: str) -> None:
        """Called from any worker thread (the synth runner has its own pool)."""
        with self._lock:
            if fraction <= self._last:
                return
            self._last = fraction
        anyio.from_thread.run(_notify, self._ctx, fraction, message, token=self._token)


class ToolRuntime:
    """Tool implementations; tests inject settings, an LLM provider, and a TTS backend via ToolEnv."""

    def __init__(self, env: ToolEnv | None = None) -> None:
        self.env = env or ToolEnv()

    async def narrate(
        self,
        source: Annotated[str, Field(description="Page URL or local .html/.md path.")],
        ctx: Ctx,
        profile: str | None = None,
        voice: str | None = None,
        backend: str | None = None,
        langs: list[str] | None = None,
        inject_path: str | None = None,
    ) -> NarrateOut:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            inp = NarrateIn(
                source=source,
                profile=profile,
                voice=voice,
                backend=backend,
                langs=langs,
                inject_path=inject_path,
            )
            await _notify(ctx, 0.0, "fetch and script")
            progress = MonotonicProgress(ctx)
            out = await anyio.to_thread.run_sync(partial(run_narrate, inp, self.env, progress))
            await _notify(ctx, 1.0, "publish")
            return out

    async def script(self, source: str, profile: str | None = None) -> ScriptOut:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            inp = ScriptIn(source=source, profile=profile)
            return await anyio.to_thread.run_sync(partial(run_script, inp, self.env))

    async def render(
        self,
        script_path: str,
        chunks: list[int] | None = None,
        voice: str | None = None,
        backend: str | None = None,
    ) -> RenderOut:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            inp = RenderIn(script_path=script_path, chunks=chunks, voice=voice, backend=backend)
            return await anyio.to_thread.run_sync(partial(run_render, inp, self.env))

    async def list_voices(self) -> list[VoiceInfo]:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            return await anyio.to_thread.run_sync(partial(catalog.list_voices, self.env.resolved_settings()))

    async def list_profiles(self) -> list[ProfileInfo]:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            return catalog.list_profiles(self.env.resolved_settings())

    async def list_backends(self) -> list[BackendInfo]:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            return await anyio.to_thread.run_sync(
                partial(catalog.list_backends, self.env.resolved_settings())
            )

    async def status(self) -> StatusOut:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            return await anyio.to_thread.run_sync(partial(catalog.status, self.env.resolved_settings()))

    async def recommend(self, source: str | None = None, description: str | None = None) -> RecommendOut:
        """Placeholder replaced by the registered description."""
        with tool_errors():
            inp = RecommendIn(source=source, description=description)
            settings = self.env.resolved_settings()
            return await anyio.to_thread.run_sync(partial(catalog.recommend, inp, settings))


def _descriptions() -> dict[str, str]:
    return {
        "mr_audio_smith_narrate": (
            "Turn a web page or local file into narrated audio (MP3, captions, player manifest). "
            "Long-running; "
            "emits progress. Returns absolute file paths. inject_path must be inside the server working "
            f"directory. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_script": (
            "Write only the reviewable narration script for a page (no audio). Returns the script path, "
            f"chunk count, and estimated minutes. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_render": (
            "Render audio from a reviewed script, or preview only the listed chunk numbers. Returns absolute "
            f"file paths. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_list_voices": (
            "List built-in voices and registered cloned voices. A cloned voice can only be used because a "
            f"consent record exists for it. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_list_profiles": f"List audience profiles (id, version, description). {CONSENT_NOTE}",
        "mr_audio_smith_list_backends": (
            f"List TTS backends with availability, languages, cloning support, and license. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_status": (
            f"Environment check: the same report as `mr-audio-smith doctor`, as JSON. {CONSENT_NOTE}"
        ),
        "mr_audio_smith_recommend": (
            "Recommend a profile and backend from a description of the listener or a source. Deterministic "
            f"keyword rules; does not fetch the page. {CONSENT_NOTE}"
        ),
    }


def create_server(env: ToolEnv | None = None) -> MCPServer:
    """Build the MCP server with all eight tools registered."""
    runtime = ToolRuntime(env)
    mcp = MCPServer(SERVER_NAME)
    impls: dict[str, Callable[..., Any]] = {
        "mr_audio_smith_narrate": runtime.narrate,
        "mr_audio_smith_script": runtime.script,
        "mr_audio_smith_render": runtime.render,
        "mr_audio_smith_list_voices": runtime.list_voices,
        "mr_audio_smith_list_profiles": runtime.list_profiles,
        "mr_audio_smith_list_backends": runtime.list_backends,
        "mr_audio_smith_status": runtime.status,
        "mr_audio_smith_recommend": runtime.recommend,
    }
    docs = _descriptions()
    for name in TOOL_NAMES:
        mcp.add_tool(impls[name], name=name, description=docs[name], structured_output=True)
    return mcp


def is_loopback(host: str) -> bool:
    return host in LOOPBACK_HOSTS


class BearerAuth:
    """ASGI middleware: reject HTTP requests without the right bearer token (constant-time compare)."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]], token: str) -> None:
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._allowed(scope):
            await self._app(scope, receive, send)
            return
        body = b'{"title":"unauthorized","status":401}'
        headers = [(b"content-type", b"application/problem+json"), (b"www-authenticate", b"Bearer")]
        await send({"type": "http.response.start", "status": HTTP_UNAUTHORIZED, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _allowed(self, scope: Scope) -> bool:
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                text = value.decode("latin-1")
                given = text[len(BEARER_PREFIX) :] if text.lower().startswith(BEARER_PREFIX) else ""
                return hmac.compare_digest(given.encode(), self._token)
        return False


def serve_http(mcp: MCPServer, host: str, port: int, token: str | None) -> None:
    """Serve streamable HTTP. Non-loopback binds need a token and are bearer-protected."""
    if not is_loopback(host) and not token:
        raise UsageError(
            f"Refusing to listen on {host} without a token",
            hint="Set AUDIO_SMITH_SERVER_TOKEN, or bind 127.0.0.1.",
        )
    import uvicorn  # noqa: PLC0415 - only the HTTP transport needs it

    app: Callable[[Scope, Receive, Send], Awaitable[None]] = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH, host=host
    )
    if token:
        app = BearerAuth(app, token)
    uvicorn.run(app, host=host, port=port, log_level="warning")
