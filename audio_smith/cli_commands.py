"""CLI commands for the pipeline stages. Thin: parse flags, call audio_smith.api, print results."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audio_smith import api
from audio_smith.cache.store import CacheStore, parse_age
from audio_smith.config import Settings, load_settings
from audio_smith.errors import UsageError
from audio_smith.profiles import load_all, load_file
from audio_smith.profiles.loader import json_schema

ProfileOpt = Annotated[
    str | None, typer.Option("--profile", "-p", help="Profile id (kid-5, adult-brief, ...).")
]
OutOpt = Annotated[Path | None, typer.Option("--out", "-o", help="Output root directory.")]
LlmOpt = Annotated[
    str | None, typer.Option("--llm", help="LLM provider string, e.g. ollama:qwen3:14b or fake.")
]
BackendOpt = Annotated[str | None, typer.Option("--backend", "-b", help="TTS backend id.")]
VoiceOpt = Annotated[str | None, typer.Option("--voice", "-v", help="Registered voice id or built-in voice.")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Bypass the cache and re-run every stage.")]
PrivateOpt = Annotated[
    bool, typer.Option("--allow-private", help="Allow fetching private or loopback addresses.")
]


def settings_from(**overrides: object) -> Settings:
    return load_settings(overrides={k: v for k, v in overrides.items() if v not in (None, False)})


def register(app: typer.Typer, console: Console) -> None:
    """Attach stage commands to the root app."""
    profile_app = typer.Typer(help="List, show, and validate audience profiles.", no_args_is_help=True)
    cache_app = typer.Typer(help="Inspect and prune the cache.", no_args_is_help=True)
    app.add_typer(profile_app, name="profile")
    app.add_typer(cache_app, name="cache")

    @app.command("script")
    def script_cmd(
        source: Annotated[str, typer.Argument(help="Page URL or local .html/.md file.")],
        profile: ProfileOpt = None,
        out: OutOpt = None,
        llm: LlmOpt = None,
        backend: BackendOpt = None,
        voice: VoiceOpt = None,
        lang: Annotated[str, typer.Option("--lang", help="Script language.")] = "en",
        force: ForceOpt = False,
        allow_private: PrivateOpt = False,
    ) -> None:
        """Stages 1 and 2 only: extract the page and write Script Markdown for review."""
        settings = settings_from(allow_private=allow_private)
        res = api.write_script(
            source,
            profile=profile,
            llm=llm,
            backend=backend,
            voice=voice,
            lang=lang,
            out=out,
            force=force,
            settings=settings,
        )
        hit = "cache hit" if all(res.cache_hits.values()) else "generated"
        typer.echo(f"blocks: {res.blocks_path}")
        for code, path in res.scripts.items():
            typer.echo(f"script ({code}, {hit}): {path}")
        if res.parent_script:
            typer.echo(f"parent script: {res.parent_script}")
        for w in res.warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")

    @profile_app.command("list")
    def profile_list() -> None:
        """List built-in and project profiles."""
        table = Table("id", "version", "description")
        for p in load_all(load_settings().profiles_dir).values():
            table.add_row(p.id, p.version, p.description)
        console.print(table)

    @profile_app.command("show")
    def profile_show(profile_id: Annotated[str, typer.Argument(help="Profile id.")]) -> None:
        """Print one profile as JSON."""
        profiles = load_all(load_settings().profiles_dir)
        if profile_id not in profiles:
            raise UsageError(f"Unknown profile '{profile_id}'", hint=f"Known: {', '.join(sorted(profiles))}")
        typer.echo(profiles[profile_id].model_dump_json(indent=2, by_alias=True))

    @profile_app.command("validate")
    def profile_validate(path: Annotated[Path, typer.Argument(help="Profile YAML file.")]) -> None:
        """Validate a profile file; errors name the failing field path."""
        p = load_file(path)
        console.print(f"ok: {p.ref}")

    @profile_app.command("schema")
    def profile_schema() -> None:
        """Print the profile JSON Schema."""
        typer.echo(json_schema(), nl=False)

    @cache_app.command("info")
    def cache_info() -> None:
        """Show cache location, entry counts, and size."""
        info = CacheStore(load_settings().cache_dir).info()
        console.print(f"cache: {info.root}  ({info.bytes / 1024**2:.1f} MiB)")
        for kind, count in info.entries.items():
            console.print(f"  {kind}: {count}")

    @cache_app.command("prune")
    def cache_prune(
        older_than: Annotated[str, typer.Option("--older-than", help="Age such as 30d, 12h.")] = "30d",
    ) -> None:
        """Delete cache entries older than the given age."""
        try:
            age = parse_age(older_than)
        except ValueError as e:
            raise UsageError(str(e)) from e
        removed = CacheStore(load_settings().cache_dir).prune(age)
        console.print(f"removed {removed} entries")
