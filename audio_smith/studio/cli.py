"""`mr-audio-smith studio`: serve the local review UI on loopback only (FR-022)."""

import secrets
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from audio_smith.config import Settings, load_settings
from audio_smith.errors import UsageError

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 7341
TOKEN_BYTES = 24
OPEN_DELAY_S = 0.6
INSTALL_HINT = 'uv tool install "mr-audio-smith[server]"'


def session_url(port: int, token: str) -> str:
    """The URL the user opens; the page reads the token from the query once, keeps it in memory."""
    return f"http://{LOOPBACK_HOST}:{port}/?token={token}"


def serve(port: int, out: Path | None, open_browser: bool, console: Console, settings: Settings) -> None:
    """Start uvicorn on loopback. FastAPI is imported here so the base install stays light."""
    try:
        import uvicorn  # noqa: PLC0415 - optional `server` extra

        from audio_smith.studio.routes import create_app  # noqa: PLC0415 - imports fastapi
    except ImportError as e:
        raise UsageError("Studio needs the server extra", hint=f"Install it with: {INSTALL_HINT}") from e
    token = secrets.token_urlsafe(TOKEN_BYTES)
    out_dir = (out or settings.out_dir).expanduser()
    app = create_app(out_dir, settings, token, project_root=Path.cwd())
    url = session_url(port, token)
    console.print(f"Studio: {url}", markup=False, highlight=False)
    if open_browser:
        threading.Timer(OPEN_DELAY_S, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=LOOPBACK_HOST, port=port, log_level="warning")


def register_studio_commands(app: typer.Typer, console: Console) -> None:
    """Attach `studio` to the root app. There is deliberately no --host: loopback only."""

    @app.command("studio")
    def studio_cmd(
        port: Annotated[int, typer.Option("--port", help="Port on 127.0.0.1.")] = DEFAULT_PORT,
        out: Annotated[Path | None, typer.Option("--out", help="Output directory to review.")] = None,
        no_open: Annotated[bool, typer.Option("--no-open", help="Do not open a browser.")] = False,
    ) -> None:
        """Review and fix narration in the browser: edit chunks, compare takes, approve."""
        serve(port, out, not no_open, console, load_settings())
