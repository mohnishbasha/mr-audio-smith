"""CLI for publishing commands: `inject`. Thin wrapper over embed and inject."""

from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.markup import escape

from audio_smith.errors import UsageError
from audio_smith.publish.embed import EmbedOptions, ScriptMode, Size, render_embed
from audio_smith.publish.inject import inject_file, unified_diff
from audio_smith.publish.manifest import load_manifest


def register_publish_commands(app: typer.Typer, console: Console) -> None:
    """Attach `inject` to the root app."""

    @app.command("inject")
    def inject_cmd(
        page: Annotated[Path, typer.Argument(help="HTML page to update.")],
        manifest: Annotated[Path, typer.Option("--manifest", help="Manifest JSON from a render.")],
        selector: Annotated[str, typer.Option("--selector", help="Insert after this element.")] = "h1",
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the diff, write nothing.")] = False,
        label: Annotated[str, typer.Option("--label", help="Player label.")] = "Listen",
        size: Annotated[str, typer.Option("--size", help="default | kid.")] = "default",
        script_mode: Annotated[str, typer.Option("--script-mode", help="self | jsdelivr.")] = "self",
    ) -> None:
        """Embed the player into a page between audio-smith markers (idempotent)."""
        if size not in ("default", "kid") or script_mode not in ("self", "jsdelivr"):
            raise UsageError(
                "Invalid --size or --script-mode.", hint="size: default|kid; script-mode: self|jsdelivr."
            )
        opts = EmbedOptions(label=label, size=cast(Size, size), script_mode=cast(ScriptMode, script_mode))
        snippet = render_embed(load_manifest(manifest), opts)
        old = page.read_bytes().decode("utf-8")
        res = inject_file(page, snippet, selector=selector, dry_run=dry_run)
        if not res.changed:
            console.print("unchanged")
        elif dry_run:
            console.print(unified_diff(old, res.html, str(page)), markup=False, highlight=False)
        else:
            console.print(f"updated {escape(str(page))}")
