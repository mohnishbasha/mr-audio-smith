"""`mr-audio-smith serve`: run the REST server (FR-023)."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from audio_smith.config import load_settings
from audio_smith.errors import UsageError
from audio_smith.server.auth import require_safe_bind

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7340
INSTALL_HINT = 'uv tool install "mr-audio-smith[server]"'


def register_server_commands(app: typer.Typer, console: Console) -> None:
    """Attach `serve` to the root app."""

    @app.command("serve")
    def serve_cmd(
        host: Annotated[
            str, typer.Option("--host", help="Bind address; non-loopback needs a token.")
        ] = DEFAULT_HOST,
        port: Annotated[int, typer.Option("--port", help="Port.")] = DEFAULT_PORT,
        out: Annotated[
            Path | None, typer.Option("--out", help="Output directory (jobs.db and jobs/).")
        ] = None,
    ) -> None:
        """Serve the REST API: POST /v1/jobs, poll, download. Set AUDIO_SMITH_SERVER_TOKEN to require auth."""
        settings = load_settings({"server_host": host, "server_port": port, "out_dir": out})
        require_safe_bind(settings)
        try:
            import uvicorn  # noqa: PLC0415 - optional `server` extra

            from audio_smith.server.app import create_app  # noqa: PLC0415 - imports fastapi
        except ImportError as e:
            raise UsageError(
                "The server needs the server extra", hint=f"Install it with: {INSTALL_HINT}"
            ) from e
        console.print(f"Serving on http://{host}:{port}", markup=False, highlight=False)
        uvicorn.run(create_app(settings), host=host, port=port, log_level="warning")
