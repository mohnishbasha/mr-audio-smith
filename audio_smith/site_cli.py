"""CLI for site batch mode (FR-019): `mr-audio-smith site <index-url> --match GLOB`.

Kept out of cli_commands so the front-door import contract holds: this module reaches the
pipeline only through audio_smith.site.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from audio_smith import site
from audio_smith.config import load_settings

FAILED_EXIT_CODE = 6
STATUS_STYLE = {"cached": "cyan", "rendered": "green", "failed": "red"}


def summary_table(rows: list[site.SiteRow]) -> Table:
    """Page, status, duration, plus the failure reason so CI logs say why."""
    table = Table("page", "status", "duration", "note")
    for row in rows:
        style = STATUS_STYLE[row.status]
        note = escape(row.error) if row.error else (str(row.injected) if row.injected else "")
        table.add_row(escape(row.page), f"[{style}]{row.status}[/{style}]", f"{row.duration_s:.1f}s", note)
    return table


def register_site_commands(app: typer.Typer, console: Console) -> None:
    """Attach `site` to the root app."""

    @app.command("site")
    def site_cmd(
        index_url: Annotated[str, typer.Argument(help="Index page URL (or local file) listing the pages.")],
        match: Annotated[str, typer.Option("--match", help='Glob on the file name, e.g. "letter-*.html".')],
        max_pages: Annotated[int, typer.Option("--max-pages", help="Stop after this many pages.")] = 50,
        inject_root: Annotated[Path | None, typer.Option("--inject-root", help="Static site dir.")] = None,
        selector: Annotated[str, typer.Option("--selector", help="Insert the player after this.")] = "h1",
        profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile id.")] = None,
        voice: Annotated[str | None, typer.Option("--voice", "-v", help="Registered voice id.")] = None,
        backend: Annotated[str | None, typer.Option("--backend", "-b", help="TTS backend id.")] = None,
        llm: Annotated[str | None, typer.Option("--llm", help="LLM provider string.")] = None,
        out: Annotated[Path | None, typer.Option("--out", "-o", help="Output root directory.")] = None,
        force: Annotated[bool, typer.Option("--force", help="Bypass the cache.")] = False,
        server: Annotated[str | None, typer.Option("--server", help="Remote serve URL.")] = None,
        token: Annotated[
            str | None, typer.Option("--token", envvar="AUDIO_SMITH_SERVER_TOKEN", help="Token for --server.")
        ] = None,
        allow_private: Annotated[bool, typer.Option("--allow-private", help="Allow private hosts.")] = False,
        accept_noncommercial: Annotated[
            bool, typer.Option("--accept-noncommercial", help="Allow non-commercial weights.")
        ] = False,
    ) -> None:
        """Narrate every page linked from an index; exits 6 if any page failed."""
        overrides = {"allow_private": allow_private, "accept_noncommercial": accept_noncommercial}
        settings = load_settings(overrides={k: v for k, v in overrides.items() if v})
        rows = site.narrate_site(
            index_url,
            match_glob=match,
            max_pages=max_pages,
            inject_root=inject_root,
            selector=selector,
            server=server,
            token=token,
            narrate_kwargs={
                "profile": profile,
                "voice": voice,
                "backend": backend,
                "llm": llm,
                "out": out,
                "force": force,
                "settings": settings,
            },
        )
        console.print(summary_table(rows))
        if any(r.status == "failed" for r in rows):
            raise typer.Exit(FAILED_EXIT_CODE)
