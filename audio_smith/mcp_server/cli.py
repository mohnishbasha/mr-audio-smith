"""`mr-audio-smith mcp`: run the MCP server over stdio (default) or streamable HTTP (FR-024)."""

from typing import Annotated

import typer
from rich.console import Console

from audio_smith.config import load_settings
from audio_smith.errors import UsageError

TRANSPORTS = ("stdio", "http")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7342
INSTALL_HINT = 'uv tool install "mr-audio-smith[mcp]"'


def register_mcp_commands(app: typer.Typer, console: Console) -> None:
    """Attach `mcp` to the root app."""

    @app.command("mcp")
    def mcp_cmd(
        transport: Annotated[str, typer.Option("--transport", help="stdio or http.")] = "stdio",
        host: Annotated[str, typer.Option("--host", help="HTTP bind address.")] = DEFAULT_HOST,
        port: Annotated[int, typer.Option("--port", help="HTTP port.")] = DEFAULT_PORT,
    ) -> None:
        """Serve the MCP tools. stdio keeps stdout for the protocol; logs go to stderr."""
        if transport not in TRANSPORTS:
            raise UsageError(f"Unknown transport {transport!r}", hint="Use stdio or http.")
        try:
            from audio_smith.mcp_server import server  # noqa: PLC0415 - optional `mcp` extra
        except ImportError as e:
            raise UsageError("The MCP server needs the mcp extra", hint=f"Install it: {INSTALL_HINT}") from e
        mcp = server.create_server()
        if transport == "stdio":
            mcp.run(transport="stdio")
            return
        secret = load_settings().server_token
        token = secret.get_secret_value() if secret else None
        Console(stderr=True).print(
            f"MCP streamable HTTP on http://{host}:{port}{server.MCP_PATH}", highlight=False
        )
        server.serve_http(mcp, host, port, token)
