"""`voice` sub-commands: add, list, check, remove. Thin wrappers over the registry."""

import datetime as dt
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audio_smith.config import load_settings
from audio_smith.errors import UsageError
from audio_smith.voices import registry
from audio_smith.voices.consent import DEFAULT_SELF_STATEMENT, ConsentRecord

EXIT_CLIP_PROBLEMS = 3
EXIT_CONSENT = 8


def _statement(statement: str | None, relationship: str, yes: bool) -> str:
    if statement:
        return statement
    if relationship == "written_permission":
        if yes:
            raise UsageError(
                "written_permission needs --statement quoting the permission", hint="Pass --statement TEXT."
            )
        return str(typer.prompt("Consent statement (quote the written permission)"))
    if yes:
        return DEFAULT_SELF_STATEMENT
    return str(typer.prompt("Consent statement", default=DEFAULT_SELF_STATEMENT))


def register_voice_commands(app: typer.Typer, console: Console) -> None:
    """Attach the `voice` sub-app to the root app."""
    voice_app = typer.Typer(help="Register, list, check, and remove cloned voices.", no_args_is_help=True)
    app.add_typer(voice_app, name="voice")

    @voice_app.command("add")
    def voice_add(
        voice_id: Annotated[str, typer.Argument(help="Voice id, e.g. dad.")],
        clip: Annotated[Path, typer.Option("--clip", help="Reference WAV, 3 to 30 s of clean speech.")],
        name: Annotated[str, typer.Option("--name", help="Speaker's full name.")],
        relationship: Annotated[str, typer.Option("--relationship", help="self | written_permission.")],
        statement: Annotated[str | None, typer.Option("--statement", help="Consent statement.")] = None,
        text: Annotated[
            str | None, typer.Option("--text", "--reference-text", help="Transcript of the clip.")
        ] = None,
        display_name: Annotated[str | None, typer.Option("--display-name", help="Label.")] = None,
        date: Annotated[str | None, typer.Option("--date", help="Consent date (YYYY-MM-DD).")] = None,
        replace: Annotated[bool, typer.Option("--replace", help="Overwrite an existing voice.")] = False,
        yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not prompt.")] = False,
    ) -> None:
        """Register a voice with its consent record after checking the clip."""
        if relationship not in ("self", "written_permission"):
            raise UsageError("--relationship must be self or written_permission")
        try:
            when = dt.date.fromisoformat(date) if date else dt.date.today()
        except ValueError as e:
            raise UsageError("--date must be YYYY-MM-DD") from e
        consent = ConsentRecord.model_validate(
            {
                "speaker_name": name,
                "relationship": relationship,
                "statement": _statement(statement, relationship, yes),
                "date": when,
            }
        )
        voices_dir = load_settings().resolved(load_settings().voices_dir)
        rec = registry.add_voice(
            voices_dir, voice_id, clip, consent, display_name=display_name or name,
            reference_text=text, replace=replace,
        )  # fmt: skip
        console.print(
            f"registered voice '{rec.id}' ({rec.clipcheck.duration_s:.1f} s, SNR {rec.clipcheck.snr_db} dB)"
        )

    @voice_app.command("list")
    def voice_list() -> None:
        """List registered voices."""
        voices_dir = load_settings().resolved(load_settings().voices_dir)
        valid, invalid = registry.scan_voices(voices_dir)
        table = Table("id", "display name", "relationship", "duration", "snr")
        for v in valid:
            table.add_row(
                v.id,
                v.display_name,
                v.consent.relationship,
                f"{v.clipcheck.duration_s:.1f} s",
                f"{v.clipcheck.snr_db} dB",
            )
        console.print(table)
        for vid, reason in invalid.items():
            console.print(f"[yellow]invalid voice {vid}:[/yellow] {reason}")

    @voice_app.command("check")
    def voice_check(
        voice_id: Annotated[str, typer.Argument(help="Voice id.")],
        fix: Annotated[bool, typer.Option("--fix", help="Tighten broad permissions.")] = False,
    ) -> None:
        """Re-run clip checks, consent, hash, and permissions audit."""
        res = registry.check_voice(
            load_settings().resolved(load_settings().voices_dir), voice_id, fix_permissions=fix
        )
        for w in res.warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
        if res.consent_error:
            console.print(f"consent: {res.consent_error}")
            raise typer.Exit(code=EXIT_CONSENT)
        if res.clip_problems:
            for p in res.clip_problems:
                console.print(f"clip: {p}")
            raise typer.Exit(code=EXIT_CLIP_PROBLEMS)
        console.print(f"ok: {voice_id}")

    @voice_app.command("remove")
    def voice_remove(
        voice_id: Annotated[str, typer.Argument(help="Voice id.")],
        yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not prompt.")] = False,
    ) -> None:
        """Delete a voice and its clips."""
        if not yes:
            typer.confirm(f"Delete voice '{voice_id}' and its clips?", abort=True)
        registry.remove_voice(load_settings().resolved(load_settings().voices_dir), voice_id)
        console.print(f"removed voice '{voice_id}'")
