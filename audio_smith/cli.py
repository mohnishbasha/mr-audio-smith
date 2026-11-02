"""Command line front door. A thin layer: parse flags, call the API, map errors to exit codes."""

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audio_smith import __version__, doctor
from audio_smith.cli_commands import register
from audio_smith.config import load_settings
from audio_smith.errors import AudioSmithError

app = typer.Typer(
    name="mr-audio-smith",
    help="Turn any web page into an audience-tuned narration. Every page deserves a voice.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"mr-audio-smith {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True, help="Print the version.")
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show stack traces on errors.")] = False,
) -> None:
    """mr-audio-smith command line."""


@app.command("doctor")
def doctor_cmd(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Check the environment (Python, ffmpeg, GPU, backends, LLM, voices, disk)."""
    settings = load_settings()
    report = doctor.run_checks(settings, doctor.default_checks())
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        table = Table(title="mr-audio-smith doctor")
        for col in ("check", "status", "detail", "hint"):
            table.add_column(col)
        for r in report.results:
            status = "ok" if r.ok else ("FAIL" if r.required else "warn")
            table.add_row(r.name, status, r.detail, r.hint or "")
        console.print(table)
        for w in settings.config_warnings:
            err_console.print(f"warning: {w}")
    if not report.ok:
        raise typer.Exit(code=3)


register(app, console)


def _print_error(err: AudioSmithError, debug: bool) -> None:
    if debug:
        err_console.print_exception()
    err_console.print(f"error [{err.code}]: {err.message}")
    if err.hint:
        err_console.print(f"hint: {err.hint}")


def main() -> None:
    """Console script entry point: typer handles usage errors (exit 2); AudioSmithError maps to its code."""
    debug = "--debug" in sys.argv
    try:
        app(prog_name="mr-audio-smith")
    except AudioSmithError as err:
        _print_error(err, debug)
        sys.exit(err.exit_code)
    except KeyboardInterrupt:
        err_console.print("aborted")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
